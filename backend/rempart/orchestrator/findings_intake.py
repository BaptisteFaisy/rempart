"""Intake des failles : construction, doublons, régressions (tâche n°4).

Isolé de :mod:`rempart.orchestrator.tasks` pour que chaque module reste sous la
limite de 500 lignes. ``collect_findings`` est ré-exportée par ``tasks`` : le
contrat public ne change pas.
"""

from __future__ import annotations

import uuid
from typing import Any

from rempart.common.api_enums import normalize_confidence, normalize_severity
from rempart.common.fingerprint import fingerprint as make_fingerprint
from rempart.common.models import Application, Finding
from rempart.common.priority import compute_priority, due_date
from rempart.common.timeutil import iso, utcnow

from .task_types import Deps, app_of, exposed_critical, sensitive_data


def _finding_from_sa(raw: dict[str, Any], app: Application, run_id: str) -> Finding:
    # FindingSummary documenté : name/riskLevel ; Rempart accepte aussi les
    # champs détaillés (title/severity) renvoyés par BatchGetFindings/fakes.
    # La vraie API envoie `riskLevel`/`confidence` en MAJUSCULES (énumérations
    # officielles) ; le modèle interne attend la casse de `models.SEVERITIES`.
    # Sans cette normalisation, toute faille réelle tombait en P4 sans échéance
    # et le garde-fou EF-TRI-05 ne se déclenchait jamais (voir api_enums).
    severity = normalize_severity(raw.get("severity") or raw.get("riskLevel"))
    confidence = normalize_confidence(raw.get("confidence"))
    risk_type = str(raw.get("riskType") or raw.get("risk_type") or "Unknown")
    entry_point = str(raw.get("entryPoint") or raw.get("entry_point") or "")
    parameter = raw.get("parameter")

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
        fingerprint=make_fingerprint(app.app_id, risk_type, entry_point, parameter),
        title=str(raw.get("title") or raw.get("name") or "Untitled finding"),
        risk_type=risk_type,
        severity=severity,
        confidence=confidence,
        priority=result.priority,
        status="new",
        due_at=iso(deadline) if deadline else None,
        ticket_url=None,
        remediation_pr_url=None,
        evidence={
            "description": raw.get("description", ""),
            # Valeurs brutes de l'API : la normalisation ne doit rien faire perdre.
            "api_risk_level": raw.get("riskLevel"),
            "api_confidence": raw.get("confidence"),
        },
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

    # ListFindings : agentSpaceId requis ; pentestJobId optionnel ;
    # champs documentés : name/riskLevel (FindingSummary).
    raws = deps.sa.list_findings(
        app.agent_space_id or "", pentest_job_id=payload["run_id"]
    )
    created: list[Finding] = []
    duplicates = 0
    regressions = 0

    for raw in raws:
        finding = _finding_from_sa(raw, app, payload["run_id"])
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
