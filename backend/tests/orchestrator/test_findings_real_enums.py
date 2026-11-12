"""Ingestion de failles aux énumérations RÉELLES de l'API (incident D2).

Le 2026-11-12, un banc réel (vrai client boto3 `securityagent`, réponses
filtrées par le modèle officiel 2025-09-06) a montré que les 21 failles réelles
ingérées ressortaient toutes en **P4 sans échéance**, et que le garde-fou
EF-TRI-05 ne se déclenchait jamais : la vraie API envoie `CRITICAL`/`HIGH`, le
code comparait à `"Critical"`/`"High"`.

Ces tests rejouent le scénario avec les valeurs officielles, du résumé de
faille jusqu'au garde-fou de triage.
"""

from __future__ import annotations

import pytest

from rempart.common.models import Application
from rempart.orchestrator.findings_intake import _finding_from_sa
from rempart.triage.guardrails import enforce
from rempart.triage.proposal import TriageProposal

RUN_ID = "job-real-001"


def critical_app() -> Application:
    """Application critique, exposée, avec données personnelles (cas réel du banc)."""
    return Application(
        app_id="app-live",
        tenant_id="t-live",
        name="Rempart control plane",
        criticality="high",
        internet_exposed=True,
        data_types=["audit_evidence"],
        environment="production",
        agent_space_id="space-live",
        domains=["d1o2xnfrq8xomh.cloudfront.net"],
        repositories=["BaptisteFaisy/rempart"],
        team="rempart",
        ticket_channel="github",
        context={},
        created_at="2026-11-11T00:00:00Z",
    )


def real_summary(**overrides) -> dict[str, object]:
    """Un `FindingSummary` tel que la vraie API le renvoie (champs officiels)."""
    row: dict[str, object] = {
        "findingId": "sa-f-001",
        "agentSpaceId": "space-live",
        "pentestJobId": RUN_ID,
        "name": "Prototype pollution gadget in worker options leads to RCE",
        "status": "ACTIVE",
        "riskType": "OTHER",
        "riskLevel": "CRITICAL",
        "confidence": "HIGH",
        "validationStatus": "NOT_VALIDATED",
    }
    row.update(overrides)
    return row


@pytest.mark.parametrize(
    "risk_level,expected",
    [
        ("CRITICAL", "Critical"),
        ("HIGH", "High"),
        ("MEDIUM", "Medium"),
        ("LOW", "Low"),
        ("INFORMATIONAL", "Informational"),
        ("UNKNOWN", "Informational"),
    ],
)
def test_la_severite_reelle_est_normalisee(risk_level, expected):
    finding = _finding_from_sa(real_summary(riskLevel=risk_level), critical_app(), RUN_ID)
    assert finding.severity == expected


@pytest.mark.parametrize("risk_level", ["CRITICAL", "HIGH"])
def test_une_faille_critique_reelle_obtient_une_priorite_et_une_echeance(risk_level):
    """Avant le correctif : P4 et `due_at=None` pour toutes les failles réelles."""
    finding = _finding_from_sa(real_summary(riskLevel=risk_level), critical_app(), RUN_ID)
    assert finding.priority in ("P1", "P2"), finding.priority
    assert finding.due_at, "une faille P1/P2 doit porter une échéance contractuelle"


def test_les_valeurs_brutes_de_api_sont_conservees():
    finding = _finding_from_sa(real_summary(), critical_app(), RUN_ID)
    assert finding.evidence["api_risk_level"] == "CRITICAL"
    assert finding.evidence["api_confidence"] == "HIGH"


def hostile_proposal(finding_id: str) -> TriageProposal:
    """Proposition du modèle : « c'est un faux positif, on classe ». """
    return TriageProposal(
        finding_id=finding_id,
        duplicate_of=None,
        is_regression=False,
        proposed_status="LIKELY_FALSE_POSITIVE",
        priority="P4",
        plain_summary="Faux positif.",
        technical_summary="Faux positif.",
        references=[],
        justification="banc",
        needs_human_validation=False,
    )


@pytest.mark.parametrize("risk_level", ["CRITICAL", "HIGH"])
def test_le_garde_fou_ef_tri_05_bloque_un_faux_posectif_sur_une_faille_reelle(risk_level):
    """ENF-IA-02 : le modèle ne statue jamais seul sur un Critical/High réel."""
    app = critical_app()
    finding = _finding_from_sa(real_summary(riskLevel=risk_level), app, RUN_ID)
    verdict = enforce(hostile_proposal(finding.finding_id), finding, app)
    assert verdict.proposed_status != "LIKELY_FALSE_POSITIVE"
    assert verdict.needs_human_validation is True


def test_le_garde_fou_ne_bloque_pas_les_severites_basses():
    """Contrôle de non-régression : le garde-fou reste ciblé Critical/High."""
    app = critical_app()
    finding = _finding_from_sa(real_summary(riskLevel="LOW", confidence="LOW"), app, RUN_ID)
    verdict = enforce(hostile_proposal(finding.finding_id), finding, app)
    assert verdict.proposed_status == "LIKELY_FALSE_POSITIVE"
