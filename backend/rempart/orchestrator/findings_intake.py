"""Intake des failles : construction, doublons, régressions (tâche n°4).

Isolé de :mod:`rempart.orchestrator.tasks` pour que chaque module reste sous la
limite de 500 lignes. ``collect_findings`` est ré-exportée par ``tasks`` : le
contrat public ne change pas.

Ce que la vraie API change (constat du 2026-11-12) :
- `ListFindings` renvoie des `FindingSummary` : ni `entryPoint`, ni `parameter`,
  ni `description`. L'empreinte calculée dessus dégénérait (21 failles → 3
  créées, 18 jetées comme doublons) ;
- les détails (`description`, `codeLocations`, `riskScore`) viennent de
  `BatchGetFindings`, qui est appelé ici pour chaque job.

L'empreinte est donc calculée sur `codeLocations` puis sur le nom de la faille —
voir :mod:`rempart.common.fingerprint`.
"""

from __future__ import annotations

import uuid
from typing import Any

from rempart.common.api_enums import normalize_confidence, normalize_severity
from rempart.common.fingerprint import finding_fingerprint
from rempart.common.models import Application, Finding
from rempart.common.priority import compute_priority, due_date
from rempart.common.timeutil import iso, utcnow

from .task_types import Deps, app_of, exposed_critical, sensitive_data


def fetch_findings(sa: Any, space_id: str, job_id: str) -> list[tuple[dict, dict]]:
    """Les failles d'un job : résumé (ListFindings) + détail (BatchGetFindings).

    Renvoie des paires ``(résumé, détail)``. Le détail peut être vide si
    l'API ne le fournit pas : l'empreinte se rabat alors sur le nom.
    """
    raws = list(sa.list_findings(space_id, pentest_job_id=job_id))
    details: dict[str, dict] = {}
    ids = [str(raw.get("findingId")) for raw in raws if raw.get("findingId")]
    if ids:
        for detail in sa.batch_get_findings(space_id, ids):
            details[str(detail.get("findingId"))] = detail
    return [(raw, details.get(str(raw.get("findingId")), {})) for raw in raws]


def _evidence_of(raw: dict[str, Any], detail: dict[str, Any]) -> dict[str, Any]:
    """Preuves conservées avec la faille (jamais dans le dossier d'audit).

    ENF-SEC-05 : `Finding.evidence` est exclu du dossier de preuves, donc la
    description et l'emplacement ne fuient pas vers l'extérieur. On ne recopie
    jamais `attackScript` ni `verificationScript` : ce sont des détails
    d'exploitation.
    """
    locations = [
        {
            "file_path": str(location.get("filePath") or ""),
            "line_start": location.get("lineStart"),
            "line_end": location.get("lineEnd"),
        }
        for location in (detail.get("codeLocations") or [])
        if isinstance(location, dict)
    ]
    return {
        "description": str(detail.get("description") or raw.get("description") or ""),
        "code_locations": locations,
        "risk_score": detail.get("riskScore"),
        "api_risk_level": raw.get("riskLevel"),
        "api_confidence": raw.get("confidence"),
    }


def _finding_from_sa(
    raw: dict[str, Any],
    app: Application,
    run_id: str,
    detail: dict[str, Any] | None = None,
) -> Finding:
    """Construit une `Finding` depuis un résumé officiel et son détail."""
    detail = detail or {}
    # La vraie API envoie `riskLevel`/`confidence` en MAJUSCULES (énumérations
    # officielles) ; le modèle interne attend la casse de `models.SEVERITIES`.
    # Sans cette normalisation, toute faille réelle tombait en P4 sans échéance
    # et le garde-fou EF-TRI-05 ne se déclenchait jamais (voir api_enums).
    severity = normalize_severity(raw.get("severity") or raw.get("riskLevel"))
    confidence = normalize_confidence(raw.get("confidence"))
    risk_type = str(raw.get("riskType") or raw.get("risk_type") or "Unknown")

    result = compute_priority(
        severity,
        confidence,
        exposed_critical=exposed_critical(app),
        sensitive_data=sensitive_data(app),
    )
    created = utcnow()
    deadline = due_date(result.priority, created)
    return Finding(
        finding_id=str(raw.get("findingId") or raw.get("id") or f"f-{uuid.uuid4().hex[:8]}"),
        app_id=app.app_id,
        tenant_id=app.tenant_id,
        run_id=run_id,
        fingerprint=finding_fingerprint(app.app_id, raw, detail),
        title=str(raw.get("title") or raw.get("name") or "Untitled finding"),
        risk_type=risk_type,
        severity=severity,
        confidence=confidence,
        priority=result.priority,
        status="new",
        due_at=iso(deadline) if deadline else None,
        ticket_url=None,
        remediation_pr_url=None,
        evidence=_evidence_of(raw, detail),
        cvss=raw.get("cvss") or {},
        created_at=iso(created),
        updated_at=iso(created),
        closed_at=None,
        closed_by_run_id=None,
    )


def collect_findings(payload: dict[str, Any], deps: Deps) -> dict[str, Any]:
    """Fetch findings, skip duplicates, flag regressions, compute priority."""
    app = app_of(deps, payload["app_id"])
    if app is None:
        return {**payload, "error": "unknown_application"}

    space_id = app.agent_space_id or ""
    rows = fetch_findings(deps.sa, space_id, payload["run_id"])
    created: list[Finding] = []
    duplicates = 0
    regressions = 0

    for raw, detail in rows:
        finding = _finding_from_sa(raw, app, payload["run_id"], detail)
        existing = deps.store.find_by_fingerprint(app.app_id, finding.fingerprint)
        if existing is not None:
            if existing.status == "closed":
                existing.status = "reopened"
                existing.updated_at = iso(utcnow())
                existing.closed_at = None
                # La preuve de fermeture doit disparaître avec elle : garder
                # `closed_by_run_id` sur une faille rouverte laisserait croire
                # qu'un retest l'a validée alors qu'elle est réapparue.
                existing.closed_by_run_id = None
                deps.store.save_finding(existing)
                regressions += 1
            else:
                duplicates += 1
            continue
        deps.store.save_finding(finding)
        created.append(finding)

    return {
        **payload,
        "findings_created": [f.finding_id for f in created],
        "duplicates_skipped": duplicates,
        "regressions": regressions,
    }
