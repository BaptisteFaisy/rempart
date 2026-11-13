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
        "source",
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
        "source": "model",
    }
    p = TriageProposal.from_dict(raw)
    assert p.finding_id == "f-999"
    assert p.duplicate_of == "f-100"
    assert p.is_regression is True
    assert p.proposed_status == "TO_VERIFY"
    assert p.priority == "P2"
    # La provenance du verdict fait partie du contrat sérialisé.
    assert p.source == "model"
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


def test_les_booleens_ecrits_en_chaine_sont_lus_correctement() -> None:
    """Un modèle écrit « false » en chaîne : `bool("false")` vaut True en Python.

    Mesuré le 13/11/2026 en production : la décision du modèle portait
    `isRegression: true` alors qu'il affirmait `false`, et `duplicateOf` valait
    la chaîne « false ». La régression était donc **inventée**, et un doublon
    était pointé vers une chaîne au lieu de rien.
    """
    p = TriageProposal.from_dict(
        {
            "findingId": "f-1",
            "duplicateOf": "false",
            "isRegression": "false",
            "proposedStatus": "TO_VERIFY",
            "needsHumanValidation": "true",
        }
    )
    assert p.is_regression is False
    assert p.duplicate_of is None
    assert p.needs_human_validation is True


def test_les_references_imbriquees_sont_aplaties() -> None:
    """Le modèle a imbriqué sa liste : on garde les références, pas la liste."""
    p = TriageProposal.from_dict(
        {
            "findingId": "f-1",
            "references": [["CWE-639", "OWASP API1:2023"], "CWE-639", "  "],
        }
    )
    assert p.references == ["CWE-639", "OWASP API1:2023"]


def test_les_valeurs_absentes_restent_absentes() -> None:
    p = TriageProposal.from_dict({"findingId": "f-1", "references": None})
    assert p.references == []
    assert p.duplicate_of is None
    assert p.is_regression is False
