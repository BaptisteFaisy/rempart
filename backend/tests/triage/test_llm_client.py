"""Client LLM du triage : configuration, chaîne de repli, traçabilité.

Ces tests n'appellent JAMAIS un modèle (aucun réseau, aucun coût) : ils
vérifient la construction du client, la chaîne de repli et la provenance des
verdicts.
"""

from __future__ import annotations

import pytest

from rempart.common.models import Application, Finding
from rempart.triage import llm as llm_module
from rempart.triage.guardrails import enforce
from rempart.triage.llm import (
    DEFAULT_MODELS,
    SSM_PARAM_ENV,
    api_key,
    build_model_client,
    llm_configured,
    model_ids,
)
from rempart.triage.proposal import TriageProposal


@pytest.fixture(autouse=True)
def _ssm_cache_vide():
    """La clé SSM est mémoïsée par conteneur : chaque test part d'un cache vide."""
    llm_module._SSM_CACHE.clear()
    yield
    llm_module._SSM_CACHE.clear()


class _FakeSSM:
    """Double de `boto3.client("ssm")` : aucune requête, aucun AWS, aucun coût."""

    def __init__(self, value: str | None = "cle-ssm", raises: bool = False) -> None:
        self.value = value
        self.raises = raises
        self.calls: list[dict] = []

    def get_parameter(self, **kwargs):
        self.calls.append(kwargs)
        if self.raises:
            raise RuntimeError("AccessDeniedException")
        return {"Parameter": {"Value": self.value}}


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
    monkeypatch.delenv(SSM_PARAM_ENV, raising=False)
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


def test_la_cle_peut_venir_d_un_parametre_ssm_et_n_est_lue_qu_une_fois(monkeypatch):
    """En production la clé vit dans un SecureString : une lecture, puis cache."""
    monkeypatch.setenv("REMPART_LLM_BASE_URL", "https://example.invalid/v1")
    monkeypatch.delenv("REMPART_LLM_API_KEY", raising=False)
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.setenv(SSM_PARAM_ENV, "/rempart/prod/llm-key")
    fake = _FakeSSM(value="cle-lue-dans-ssm")
    monkeypatch.setattr(llm_module, "_ssm_client", lambda: fake)

    assert llm_configured() is True
    assert api_key() == "cle-lue-dans-ssm"
    assert api_key() == "cle-lue-dans-ssm"

    assert len(fake.calls) == 1, "chaque triage referait une requête SSM"
    assert fake.calls[0]["WithDecryption"] is True
    assert fake.calls[0]["Name"] == "/rempart/prod/llm-key"


def test_un_parametre_ssm_illisible_ne_casse_pas_le_triage(monkeypatch):
    """Droit manquant ou paramètre supprimé : repli déterministe, pas d'exception."""
    monkeypatch.setenv("REMPART_LLM_BASE_URL", "https://example.invalid/v1")
    monkeypatch.delenv("REMPART_LLM_API_KEY", raising=False)
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.setenv(SSM_PARAM_ENV, "/rempart/prod/llm-key")
    monkeypatch.setattr(llm_module, "_ssm_client", lambda: _FakeSSM(raises=True))

    assert api_key() is None
    assert llm_configured() is False
    assert build_model_client() is None


def test_la_valeur_d_environnement_prime_sur_le_parametre_ssm(monkeypatch):
    """En local on ne touche pas à SSM : la clé du fichier de secrets suffit."""
    monkeypatch.setenv("REMPART_LLM_API_KEY", "cle-locale")
    monkeypatch.setenv(SSM_PARAM_ENV, "/rempart/prod/llm-key")
    monkeypatch.setattr(llm_module, "_ssm_client", lambda: _FakeSSM(value="cle-ssm"))

    assert api_key() == "cle-locale"
