"""Agent de revue de code : un vrai modèle Strands, ou rien d'annoncé.

Les deux propriétés qui comptent :

1. **sans modèle réel, la revue est déclarée non faite** — une liste vide avec
   un statut `model_unavailable`, jamais un « aucun problème trouvé » ;
2. **avec un modèle, chaque commentaire passe les garde-fous** : un commentaire
   ancré survit, un commentaire inventé est écarté avec sa raison.

Le modèle est scripté (`tests/fakes_model.py`) : mêmes événements de flux qu'un
vrai, aucun appel réseau, aucun coût.
"""

from __future__ import annotations

from rempart.review.agent import (
    STATUS_MODEL_UNAVAILABLE,
    STATUS_REVIEWED,
    ReviewResult,
    run_review,
)
from rempart.review.diff import from_text
from tests.fakes_model import BrokenModel, ScriptedToolModel
from tests.review.conftest import SAMPLE_DIFF, SECRET_EVIDENCE, SQL_EVIDENCE, comment_payload

TOOL = "tool_submit_review_comment"
ARG = "comment"


def _source() -> object:
    return from_text(SAMPLE_DIFF, origin="banc")


def test_sans_model_la_revues_est_declaree_non_faite():
    result = run_review(_source(), model_client=None)
    assert result.status == STATUS_MODEL_UNAVAILABLE
    assert result.comments == []
    assert result.source == "none"
    # La raison est lisible : un appelant ne peut pas confondre avec « rien trouvé ».
    assert "aucun modèle" in result.note.lower()


def test_un_faux_client_n_est_pas_un_modele():
    """`is_real_model` refuse tout objet qui n'est pas un Model Strands."""
    result = run_review(_source(), model_client=object())
    assert result.status == STATUS_MODEL_UNAVAILABLE


def test_un_modele_qui_echoue_ne_produit_aucune_fausse_revues():
    result = run_review(_source(), model_client=BrokenModel())
    assert result.status == STATUS_MODEL_UNAVAILABLE
    assert "indisponible" in result.note
    assert result.comments == []


def test_un_commentaire_ancre_passe():
    model = ScriptedToolModel(TOOL, ARG, [comment_payload()])
    result = run_review(_source(), model_client=model)
    assert result.status == STATUS_REVIEWED
    assert result.source == "model"
    assert len(result.comments) == 1
    assert result.comments[0].evidence == SECRET_EVIDENCE
    assert result.comments[0].blocking is True
    assert result.needs_human == ["api/orders.py:10"]
    assert result.model_id == "scripted/test"


def test_un_commentaire_invente_est_ecarte_avec_sa_raison():
    model = ScriptedToolModel(TOOL, ARG, [comment_payload(evidence='api_key = "sk-live-INVENTEE"')])
    result = run_review(_source(), model_client=model)
    assert result.comments == []
    assert result.dropped and "citation inventée" in result.dropped[0]["reason"]


def test_plusieurs_commentaires_angres_survivent():
    model = ScriptedToolModel(
        TOOL,
        ARG,
        [
            comment_payload(),
            comment_payload(
                line=11,
                evidence=SQL_EVIDENCE,
                category="injection",
                severity="High",
                title="SQL concaténé",
                references=["CWE-89"],
            ),
        ],
    )
    result = run_review(_source(), model_client=model)
    assert len(result.comments) == 2
    assert {c.category for c in result.comments} == {"secrets", "injection"}
    assert sorted(result.needs_human) == ["api/orders.py:10", "api/orders.py:11"]


def test_un_diff_vide_ne_jamais_appelle_le_modele():
    model = ScriptedToolModel(TOOL, ARG, [comment_payload()])
    result = run_review(from_text("   "), model_client=model)
    assert result.status == STATUS_MODEL_UNAVAILABLE
    assert model.calls == 0


def test_le_meme_diff_est_revu_une_seule_fois():
    """Cache par empreinte : un rejeu (double dispatch) ne rappelle pas le modèle."""
    model = ScriptedToolModel(TOOL, ARG, [comment_payload()])
    premier = run_review(_source(), model_client=model)
    tours_apres_premiere = model.calls
    second = run_review(_source(), model_client=model)
    assert premier.source == "model"
    assert second.source == "cache"
    assert len(second.comments) == len(premier.comments)
    # Un tour d'outil + un tour de clôture : le second appel n'ajoute rien.
    assert tours_apres_premiere == 2
    assert model.calls == tours_apres_premiere


def test_un_diff_tronque_est_signale_comme_partiel():
    source = from_text("x" * 300_000)
    model = ScriptedToolModel(TOOL, ARG, [])
    result = run_review(source, model_client=model)
    assert result.truncated is True
    assert result.status not in (STATUS_MODEL_UNAVAILABLE,)
    assert "tronqué" in result.note or result.status != STATUS_REVIEWED


def test_le_payload_contient_les_compteurs():
    model = ScriptedToolModel(TOOL, ARG, [comment_payload()])
    result = run_review(_source(), model_client=model)
    payload = result.to_dict()
    assert payload["counts"]["comments"] == 1
    assert payload["counts"]["blocking"] == 1
    assert payload["diff_fingerprint"] and len(payload["diff_fingerprint"]) == 64
    assert isinstance(result, ReviewResult)


def test_les_jetons_sont_mesures_et_non_estimes():
    """Le relevé vient de Strands : deux tours scriptés à 10+10 jetons chacun."""
    model = ScriptedToolModel(TOOL, ARG, [comment_payload()])
    result = run_review(_source(), model_client=model)
    assert result.usage["inputTokens"] == 20
    assert result.usage["outputTokens"] == 20
    assert result.usage["totalTokens"] == 40
    # Sans prix configuré, le coût en dollars est abstenu — pas zéro.
    assert result.cost.usd is None
    assert result.cost.input_tokens == 20


def test_le_cache_conserve_le_cout_mesure(monkeypatch):
    """Un rejeu depuis le cache doit rendre les jetons de la revue d'origine."""
    monkeypatch.setenv("REMPART_LLM_USD_PER_M_INPUT", "2.0")
    monkeypatch.setenv("REMPART_LLM_USD_PER_M_OUTPUT", "8.0")
    from rempart.review.cost import estimate_cost

    model = ScriptedToolModel(TOOL, ARG, [comment_payload()])
    premier = run_review(_source(), model_client=model)
    second = run_review(_source(), model_client=model)
    assert second.source == "cache"
    assert second.usage == premier.usage
    attendu = estimate_cost(premier.usage)
    assert second.cost.usd == attendu.usd
