"""Dossier de preuves exportable pour les audits (EF-RAP-04, ISO 27001 / SOC 2).

Un rapport mensuel dit *ce qui s'est passé* ; un dossier de preuves doit
pouvoir être vérifié par un tiers des mois plus tard. Trois propriétés le
rendent probant :

1. **Autoportant** : toutes les pièces sont dans le document (périmètre, tests,
   chaîne de décision, preuves de fermeture, journal d'audit, KPI figés).
2. **Horodaté et déterministe** : même contenu → exactement même rendu JSON,
   donc même empreinte.
3. **Scellé** : un SHA-256 du contenu sérialisé permet à un auditeur de vérifier
   que le dossier n'a pas été retouché après coup.

ENF-SEC-05 : aucun détail d'exploitation (étapes de reproduction, scripts de
vérification) ne sort du compte client. `Finding.evidence` est exclu.
ENF-IA-01 : tous les chiffres viennent de `rempart.reports.metrics`, jamais
d'un modèle.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from typing import Any

from rempart.common.models import Decision, Finding
from rempart.common.store import Store
from rempart.common.timeutil import iso, utcnow
from rempart.reports.metrics import (
    applications_detail,
    budget_detail,
    closed_findings_detail,
    freeze_month,
    gather_scope,
    tests_detail,
    within_period,
)

PRODUCT = "Rempart"
EVIDENCE_VERSION = "1.0"
# Champs de Finding qui pourraient contenir des détails d'exploitation.
EXCLUDED_FINDING_FIELDS = ("evidence",)


def pack_identity(store: Store, tenant_id: str, period: str, generated_at: str) -> dict[str, Any]:
    """Qui, quand, quoi : l'en-tête du dossier."""
    tenant = store.get_tenant(tenant_id)
    return {
        "product": PRODUCT,
        "evidence_version": EVIDENCE_VERSION,
        "tenant_id": tenant_id,
        "tenant_name": tenant.name if tenant else tenant_id,
        "period": period,
        "generated_at": generated_at,
        "mandate_status": tenant.mandate_status if tenant else "unknown",
        "plan": tenant.plan if tenant else "unknown",
    }


def pack_scope(store: Store, tenant_id: str) -> list[dict[str, Any]]:
    """Le périmètre couvert : applications, domaines, environnements."""
    return [
        {
            "app_id": app.app_id,
            "name": app.name,
            "environment": app.environment,
            "criticality": app.criticality,
            "internet_exposed": app.internet_exposed,
            "data_types": sorted(app.data_types or []),
            "domains": sorted(app.domains or []),
            "repositories": sorted(app.repositories or []),
            "agent_space_id": app.agent_space_id,
        }
        for app in sorted(store.list_applications(tenant_id), key=lambda a: a.app_id)
    ]


def pack_tests(store: Store, tenant_id: str, period: str) -> list[dict[str, Any]]:
    """Les tests réalisés sur la période : ce qui a été fait, quand, à quel coût."""
    start, end = _period_window(period)
    runs = [
        run
        for run in store.list_runs(tenant_id=tenant_id, limit=1000)
        if within_period(run.started_at, start, end)
    ]
    return [
        {
            "run_id": run.run_id,
            "tenant_id": run.tenant_id,
            "app_id": run.app_id,
            "trigger": run.trigger,
            "status": run.status,
            "commit_from": run.commit_from,
            "commit_to": run.commit_to,
            "scope_decision": run.scope_decision,
            "started_at": run.started_at,
            "ended_at": run.ended_at,
            "duration_s": run.duration_s,
            "task_hours": run.task_hours,
            "cost_usd": run.cost_usd,
        }
        for run in sorted(runs, key=lambda r: r.started_at)
    ]


def _period_window(period: str):
    from rempart.reports.metrics import period_bounds

    return period_bounds(period)


def _finding_identity(finding: Finding) -> dict[str, Any]:
    """Identité d'une faille, SANS les détails d'exploitation (ENF-SEC-05)."""
    item = finding.to_item()
    return {
        key: value
        for key, value in item.items()
        if key not in EXCLUDED_FINDING_FIELDS
    }


def _decision_chain(store: Store, finding: Finding) -> list[dict[str, Any]]:
    """Chaîne de décision d'une faille, chronologique : qui a décidé quoi."""
    decisions = sorted(store.list_decisions(finding.finding_id), key=lambda d: d.created_at)
    return [
        {
            "decision_id": d.decision_id,
            "author_type": d.author_type,
            "author": d.author,
            "action": d.action,
            "justification": d.justification,
            "created_at": d.created_at,
        }
        for d in decisions
    ]


def pack_decision_chains(store: Store, tenant_id: str, period: str) -> list[dict[str, Any]]:
    """Cœur de la valeur probante : aucune décision n'est anonyme ou datée au hasard."""
    start, end = _period_window(period)
    findings = [
        finding
        for finding in store.list_findings(tenant_id=tenant_id, limit=1000)
        if within_period(finding.created_at, start, end)
    ]
    return [
        {
            "finding": _finding_identity(finding),
            "decisions": _decision_chain(store, finding),
        }
        for finding in sorted(findings, key=lambda f: f.created_at)
    ]


def pack_closure_proofs(chains: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Preuves de fermeture : l'identifiant du retest qui a fait disparaître la faille."""
    proofs = []
    for entry in chains:
        finding = entry["finding"]
        if finding.get("status") == "closed" and finding.get("closed_by_run_id"):
            proofs.append(
                {
                    "finding_id": finding["finding_id"],
                    "title": finding.get("title"),
                    "priority": finding.get("priority"),
                    "closed_at": finding.get("closed_at"),
                    "proven_by_run_id": finding["closed_by_run_id"],
                }
            )
    return proofs


def pack_exceptions(chains: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """Faux positifs et risques acceptés : les cas où rien n'a été corrigé."""
    false_positives, risk_accepted = [], []
    for entry in chains:
        finding = entry["finding"]
        record = {
            "finding_id": finding["finding_id"],
            "title": finding.get("title"),
            "severity": finding.get("severity"),
            "priority": finding.get("priority"),
            "decided_by": [
                d["author"] for d in entry["decisions"] if d["author_type"] == "human"
            ],
            "decided_at": [
                d["created_at"] for d in entry["decisions"] if d["author_type"] == "human"
            ],
        }
        if finding.get("status") == "false_positive":
            false_positives.append(record)
        elif finding.get("status") == "risk_accepted":
            risk_accepted.append(record)
    return {"false_positives": false_positives, "risk_accepted": risk_accepted}


def pack_audit(store: Store, period: str) -> list[dict[str, Any]]:
    """Journal d'audit de la période (ENF-SEC-06 : il n'est pas modifiable)."""
    start, end = _period_window(period)
    events = [e for e in store.list_audit(limit=1000) if within_period(e.created_at, start, end)]
    return [
        {
            "audit_id": e.audit_id,
            "actor": e.actor,
            "action": e.action,
            "object_type": e.object_type,
            "object_id": e.object_id,
            "result": e.result,
            "created_at": e.created_at,
        }
        for e in sorted(events, key=lambda x: x.created_at)
    ]


def _guardrail_findings(chains: list[dict[str, Any]]) -> dict[str, Any]:
    """Preuve que les garde-fous IA ont tenu (ENF-IA-01 et ENF-IA-02)."""
    critical_auto_closed = [
        entry["finding"]["finding_id"]
        for entry in chains
        if entry["finding"].get("severity") in ("Critical", "High")
        and entry["finding"].get("status") == "false_positive"
        and not any(d["author_type"] == "human" for d in entry["decisions"])
    ]
    return {
        "priority_source": "deterministic matrix, recomputed by code after the model",
        "model_can_dismiss_critical": False,
        "critical_dismissed_without_human": critical_auto_closed,
    }


def build_evidence_pack(
    *,
    store: Store,
    tenant_id: str,
    period: str,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Constitue le dossier de preuves d'un client pour une période donnée."""
    stamp = generated_at or iso(utcnow())
    scope = gather_scope(store, tenant_id, period)
    chains = pack_decision_chains(store, tenant_id, period)
    frozen = freeze_month(store, tenant_id, period)
    return {
        "identity": pack_identity(store, tenant_id, period, stamp),
        "scope": pack_scope(store, tenant_id),
        "mandate_and_controls": {
            "mandate_status": frozen.get("mandate_status", "unknown"),
            "applications_detail": applications_detail(scope),
            "budget_detail": budget_detail(store, tenant_id, scope),
        },
        "tests": pack_tests(store, tenant_id, period),
        "tests_summary": tests_detail(scope),
        "closed_findings": closed_findings_detail(scope),
        "closure_proofs": pack_closure_proofs(chains),
        "decision_chains": chains,
        "exceptions": pack_exceptions(chains),
        "ai_guardrails": _guardrail_findings(chains),
        "audit_events": pack_audit(store, period),
        "kpis": frozen,
    }


def render_evidence_pack_json(pack: dict[str, Any]) -> str:
    """Rendu JSON **déterministe** : clés triées, aucune donnée volatile."""
    return json.dumps(pack, indent=2, sort_keys=True, ensure_ascii=False, default=str)


def integrity_digest(pack: dict[str, Any]) -> str:
    """SHA-256 du rendu déterministe.

    Recalculable par un auditeur : `sha256sum` du JSON, ou
    `hashlib.sha256(render_evidence_pack_json(pack).encode()).hexdigest()`.
    Le champ `integrity` n'est PAS inclus dans le contenu haché, sinon le
    condensé dépendrait de lui-même.
    """
    payload = {k: v for k, v in pack.items() if k != "integrity"}
    return hashlib.sha256(render_evidence_pack_json(payload).encode("utf-8")).hexdigest()


def seal_evidence_pack(pack: dict[str, Any]) -> dict[str, Any]:
    """Ajoute l'empreinte d'intégrité au dossier et le rend vérifiable."""
    sealed = dict(pack)
    sealed["integrity"] = {
        "algorithm": "sha256",
        "digest": integrity_digest(pack),
        "canonical_form": "JSON, sort_keys=True, indent=2, ensure_ascii=False",
        "recompute": "sha256(render_evidence_pack_json(pack_without_integrity))",
    }
    return sealed


def render_evidence_pack_html(pack: dict[str, Any]) -> str:
    """Rendu HTML sobre, imprimable, sans style externe ni script."""
    identity = pack["identity"]
    integrity = pack.get("integrity", {}).get("digest", "n/a")
    sections = [
        _html_section("1. Identity", _html_table([list(identity.keys())], [list(identity.values())])),
        _html_section("2. Scope", _html_rows(pack["scope"])),
        _html_section("3. Tests performed", _html_rows(pack["tests"])),
        _html_section("4. Closure proofs", _html_rows(pack["closure_proofs"])),
        _html_section("5. Exceptions", _html_rows(_flatten_exceptions(pack["exceptions"]))),
        _html_section("6. AI guardrails", _html_rows([pack["ai_guardrails"]])),
        _html_section("7. Audit events", _html_rows(pack["audit_events"])),
        _html_section("8. Frozen KPIs", _html_rows([pack["kpis"]])),
    ]
    body = "\n".join(sections)
    return (
        "<!DOCTYPE html><html lang=\"en\"><head><meta charset=\"utf-8\"/>"
        f"<title>Rempart evidence — {_esc(identity['tenant_id'])} {_esc(identity['period'])}</title>"
        "<style>body{font:13px/1.5 system-ui,sans-serif;margin:24px auto;max-width:960px;color:#0f172a}"
        "h1{font-size:20px}h2{font-size:15px;margin-top:24px;border-bottom:1px solid #cbd5e1}"
        "table{width:100%;border-collapse:collapse;font-size:12px;margin:8px 0}"
        "th,td{border:1px solid #cbd5e1;padding:6px;text-align:left;vertical-align:top}"
        "th{background:#f1f5f9}code{background:#f1f5f9;padding:1px 4px}"
        "footer{margin-top:24px;color:#94a3b8;font-size:11px}</style></head><body>"
        f"<h1>Rempart — audit evidence pack</h1>{body}"
        f"<footer>Integrity SHA-256: <code>{_esc(integrity)}</code> — "
        "all figures computed by code (ENF-IA-01); no exploitation detail leaves "
        "the customer account (ENF-SEC-05).</footer></body></html>"
    )


def _esc(value: Any) -> str:
    import html as _html

    return _html.escape(str(value), quote=True)


def _flatten_exceptions(exceptions: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    rows = []
    for kind, items in exceptions.items():
        for item in items:
            rows.append({"kind": kind, **item})
    return rows


def _html_table(headers: list[list[Any]], rows: list[list[Any]]) -> str:
    head = "".join(f"<th>{_esc(h)}</th>" for h in (headers[0] if headers else []))
    body = "".join(
        "<tr>" + "".join(f"<td>{_esc(cell)}</td>" for cell in row) + "</tr>" for row in rows
    )
    return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


def _html_rows(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "<p>None for this period.</p>"
    headers = sorted({key for row in rows for key in row})
    return _html_table([headers], [[_cell(row.get(h)) for h in headers] for row in rows])


def _cell(value: Any) -> str:
    if isinstance(value, (dict, list)):
        return json.dumps(value, sort_keys=True, default=str)
    return "" if value is None else str(value)


def _html_section(title: str, inner: str) -> str:
    return f"<h2>{_esc(title)}</h2>{inner}"


def upload_evidence_pack(
    pack: dict[str, Any], *, tenant_id: str, period: str, s3: Any = None
) -> tuple[str, dict[str, Any]]:
    """Téléverse le dossier (JSON + HTML) et rend (clé S3, dossier scellé)."""
    sealed = seal_evidence_pack(pack)
    pack_id = f"ev-{uuid.uuid4().hex[:12]}"
    key = f"evidence/{tenant_id}/{period}/{pack_id}.json"
    if s3 is not None:
        bucket = getattr(s3, "bucket_name", "rempart-reports")
        s3.put_object(
            Bucket=bucket,
            Key=key,
            Body=render_evidence_pack_json(sealed).encode("utf-8"),
            ContentType="application/json",
        )
        s3.put_object(
            Bucket=bucket,
            Key=key.replace(".json", ".html"),
            Body=render_evidence_pack_html(sealed).encode("utf-8"),
            ContentType="text/html; charset=utf-8",
        )
    return key, sealed


def build_and_upload(
    *, store: Store, tenant_id: str, period: str, s3: Any = None, generated_at: str | None = None
) -> dict[str, Any]:
    """Point d'entrée unique : constitue, scelle et téléverse le dossier."""
    pack = build_evidence_pack(
        store=store, tenant_id=tenant_id, period=period, generated_at=generated_at
    )
    key, sealed = upload_evidence_pack(pack, tenant_id=tenant_id, period=period, s3=s3)
    sealed["s3_key"] = key
    return sealed


__all__ = [
    "Decision",
    "build_and_upload",
    "build_evidence_pack",
    "integrity_digest",
    "render_evidence_pack_html",
    "render_evidence_pack_json",
    "seal_evidence_pack",
    "upload_evidence_pack",
]
