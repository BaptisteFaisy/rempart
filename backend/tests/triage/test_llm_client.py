"""Client LLM du triage : configuration, chaîne de repli, traçabilité.

Ces tests n'appellent JAMAIS un modèle (aucun réseau, aucun coût) : ils
vérifient la construction du client, la chaîne de repli et la provenance des
verdicts.
"""

from __future__ import annotations

import pytest

from rempart.common.models import Application, Finding
from rempart.triage.guardrails import enforce
from rempart.triage.llm import (
    DEFAULT_MODELS,
    build_model_client,
    llm_configured,
    model_ids,
)
from rempart.triage.proposal import TriageProposal


def _finding(severity: str = "Critical") -> Finding:
    return Finding(
        finding_id="f-1", app_id="app-1", tenant_id="t-1", run_id="run-1",
        fingerprint="fp-1", title="Faille test", risk_type="IDOR",
        severity=severity, confidence="High", priority="P1", status="new",
        due_at=None, ticket_url=None, remediation_pr_url=None,
        evidence={"description": "d"}, cvss={},
        created_at="2026-11-12T10:00:00Z", updated_at="2026-11-12T10:00:00Z",
        closed_at=None, closed_by_run_id=None,
    )


def _app() -> Application:
    return Application(
        app_id="app-1", tenant_id="t-1", name="App", criticality="high",
        internet_exposed=True, data_types=["personal"], environment="production",
        agent_space_id="space-1", domains=[], repositories=[], team="",
        ticket_channel="github", context={}, created_at="2026-11-01T00:00:00Z",
    )


def test_sans_configuration_aucun_client_n_est_construit(monkeypatch):
    """Pas d'endpoint = pas de modèle = repli déterministe (la démo reste gratuite)."""
    monkeypatch.delenv("REMPART_LLM_BASE_URL", raising=False)
    monkeypatch.delenv("LLM_BASE_URL", raising=False)
    monkeypatch.delenv("REMPART_LLM_API_KEY", raising=False)
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    assert llm_configured() is False
    assert build_model_client() is None


def test_une_url_sans_cle_ne_compte_pas(monkeypatch):
    monkeypatch.setenv("REMPART_LLM_BASE_URL", "https://example.invalid/v1")
    monkeypatch.delenv("REMPART_LLM_API_KEY", raising=False)
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    assert llm_configured() is False


def test_la_chaine_de_modeles_se_lit_dans_l_environnement(monkeypatch):
    monkeypatch.setenv("REMPART_LLM_MODELS", "combo/cheap, ali/glm-5.2")
    assert model_ids() == ("combo/cheap", "ali/glm-5.2")
    monkeypatch.delenv("REMPART_LLM_MODELS")
    monkeypatch.setenv("REMPART_LLM_MODEL", "solo/model")
    assert model_ids() == ("solo/model",)
    monkeypatch.delenv("REMPART_LLM_MODEL")
    assert model_ids() == DEFAULT_MODELS


def test_un_client_injecté_prime_sur_l_environnement(monkeypatch):
    sentinel = object()
    assert build_model_client(sentinel) is sentinel


def test_un_client_construit_avec_les_deux_variables(monkeypatch):
    pytest.importorskip("openai")
    pytest.importorskip("strands.models.openai")
    monkeypatch.setenv("REMPART_LLM_BASE_URL", "https://example.invalid/v1")
    monkeypatch.setenv("REMPART_LLM_API_KEY", "cle-de-test")
    monkeypatch.setenv("REMPART_LLM_MODELS", "combo/cheap")
    client = build_model_client()
    assert client is not None
    from strands.models import Model

    assert isinstance(client, Model)


def test_la_provenance_du_verdict_survit_aux_garde_fous():
    """`enforce` ne doit pas effacer l'origine du verdict (modèle ou règleur)."""
    proposal = TriageProposal(
        finding_id="f-1", duplicate_of=None, is_regression=False,
        proposed_status="CONFIRMED", priority="P1",
        plain_summary="résumé", technical_summary="détail", references=[],
        justification="raison", needs_human_validation=False, source="model",
    )
    enforced = enforce(proposal, _finding(), _app())
    assert enforced.source == "model"
    assert enforced.priority == "P1"
    assert enforced.needs_human_validation is True


def test_la_provenance_par_defaut_est_le_regleur():
    proposal = TriageProposal(
        finding_id="f-1", duplicate_of=None, is_regression=False,
        proposed_status="CONFIRMED", priority="P2", plain_summary="s",
        technical_summary="t", references=[], justification="j",
        needs_human_validation=False,
    )
    assert proposal.source == "deterministic"
