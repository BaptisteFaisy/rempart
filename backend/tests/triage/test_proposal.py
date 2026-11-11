"""Tests for TriageProposal dataclass and Annexe B serialization."""

from rempart.triage.proposal import TriageProposal


def test_triage_proposal_to_dict_camelcase() -> None:
    p = TriageProposal(
        finding_id="f-0123",
        duplicate_of=None,
        is_regression=False,
        proposed_status="CONFIRMED",
        priority="P1",
        plain_summary="Un client connecté peut lire les commandes d'un autre client.",
        technical_summary="Contrôle d'accès manquant sur GET /orders/{id}.",
        references=["CWE-639", "OWASP A01"],
        justification="Sévérité High, confiance High, application exposée à Internet.",
        needs_human_validation=True,
    )
    d = p.to_dict()
    assert set(d.keys()) == {
        "findingId",
        "duplicateOf",
        "isRegression",
        "proposedStatus",
        "priority",
        "plainSummary",
        "technicalSummary",
        "references",
        "justification",
        "needsHumanValidation",
    }
    assert d["findingId"] == "f-0123"
    assert d["duplicateOf"] is None
    assert d["isRegression"] is False
    assert d["proposedStatus"] == "CONFIRMED"
    assert d["priority"] == "P1"
    assert d["references"] == ["CWE-639", "OWASP A01"]
    assert d["needsHumanValidation"] is True


def test_triage_proposal_from_dict_roundtrip() -> None:
    raw = {
        "findingId": "f-999",
        "duplicateOf": "f-100",
        "isRegression": True,
        "proposedStatus": "TO_VERIFY",
        "priority": "P2",
        "plainSummary": "Résumé simple.",
        "technicalSummary": "Résumé technique.",
        "references": ["CWE-89"],
        "justification": "Détails.",
        "needsHumanValidation": False,
    }
    p = TriageProposal.from_dict(raw)
    assert p.finding_id == "f-999"
    assert p.duplicate_of == "f-100"
    assert p.is_regression is True
    assert p.proposed_status == "TO_VERIFY"
    assert p.priority == "P2"
    assert p.to_dict() == raw


def test_triage_proposal_from_snake_case() -> None:
    raw = {
        "finding_id": "f-2",
        "duplicate_of": None,
        "is_regression": False,
        "proposed_status": "LIKELY_FALSE_POSITIVE",
        "priority": "P4",
        "plain_summary": "Info",
        "technical_summary": "Tech",
        "references": [],
        "justification": "Low",
        "needs_human_validation": False,
    }
    p = TriageProposal.from_dict(raw)
    assert p.finding_id == "f-2"
    assert p.proposed_status == "LIKELY_FALSE_POSITIVE"
    assert p.priority == "P4"
