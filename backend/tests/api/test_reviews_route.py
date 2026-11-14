"""Route `POST /v1/applications/:id/reviews` : autorisation, garde-fous, honnêteté.

Trois comportements verrouillés ici, dans l'ordre où ils comptent :

1. **personne ne paie pour un autre** : un client d'un tenant ne déclenche jamais
   une revue sur un autre tenant, et sans jeton d'identité la route refuse ;
2. **les garde-fous existants s'appliquent** : le coupe-circuit global arrête
   toute inférence, et un plafond d'appels borne le coût par application ;
3. **sans modèle, la route ne ment pas** : elle répond 503 avec le statut
   ``model_unavailable``. Un 200 accompagné d'une liste vide se lirait
   « revue sans problème », ce qui serait une fausse preuve.
"""

from __future__ import annotations

import json

import pytest

from rempart.api.app import lambda_handler
from rempart.common.config import Settings
from rempart.common.ratelimit import reset as reset_ratelimit
from tests.api.conftest import (
    analyst_claims,
    client_claims,
    make_event,
    platform_admin_claims,
    seed_two_tenants,
)
from tests.fakes_model import ScriptedToolModel
from tests.review.conftest import SAMPLE_DIFF, comment_payload

TENANT_A = "t-a"
APP_A = "app-t-a"
TOOL = "tool_submit_review_comment"


@pytest.fixture(autouse=True)
def _propres_compteurs():
    reset_ratelimit()
    yield
    reset_ratelimit()


def _call(store, claims, body=None, *, model_client=None, settings=None, app_id=APP_A):
    event = make_event("POST", f"/v1/applications/{app_id}/reviews", claims=claims, body=body)
    resp = lambda_handler(
        event, None, store=store, sa=None, settings=settings, model_client=model_client
    )
    payload = json.loads(resp["body"]) if resp.get("body") else {}
    return resp["statusCode"], payload


def _model():
    return ScriptedToolModel(TOOL, "comment", [comment_payload()])


def test_sans_identite_la_revue_est_refusee():
    status, _payload = _call(seed_two_tenants(), None, {"diff": SAMPLE_DIFF})
    assert status == 401


def test_un_client_d_autre_tenant_ne_peut_pas_declencher_une_revue():
    """Une revue coûte une inférence : personne ne la déclenche sur un tenant tiers."""
    store = seed_two_tenants()
    status, _payload = _call(
        store, client_claims("t-b"), {"diff": SAMPLE_DIFF}, model_client=_model()
    )
    assert status == 403


def test_une_revue_ancoree_repond_200_avec_les_commentaires():
    store = seed_two_tenants()
    status, payload = _call(store, analyst_claims(), {"diff": SAMPLE_DIFF}, model_client=_model())
    assert status == 200, payload
    assert payload["status"] == "reviewed"
    assert payload["source"] == "model"
    assert payload["application_id"] == APP_A
    assert payload["counts"]["comments"] == 1
    assert payload["comments"][0]["file"] == "api/orders.py"
    assert payload["needs_human"] == ["api/orders.py:10"]
    # Le dépôt de l'application est rendu : c'est lui qui aurait été lu sans `diff`.
    assert payload["repository"] == "t-a/shop"


def test_sans_modele_disponible_la_reponse_est_503_jamais_une_revue_propre():
    store = seed_two_tenants()
    status, payload = _call(store, analyst_claims(), {"diff": SAMPLE_DIFF}, model_client=None)
    assert status == 503
    assert payload["status"] == "model_unavailable"
    assert payload["comments"] == []
    assert payload["note"]


def test_coupe_circuit_global_arrete_toute_inférence():
    store = seed_two_tenants()
    status, payload = _call(
        store,
        platform_admin_claims(),
        {"diff": SAMPLE_DIFF},
        model_client=_model(),
        settings=Settings(kill_switch=True),
    )
    assert status == 503
    assert "coupe-circuit" in payload["error"]


def test_le_plafond_d_appels_par_fenetre_protege_le_portefeuille(monkeypatch):
    """Un pipeline qui rappelle la revue en boucle ne doit pas brûler d'inférences."""
    from rempart.api.routes import reviews

    monkeypatch.setattr(reviews, "REVIEW_LIMIT", 1)
    store = seed_two_tenants()
    premier, _ = _call(store, analyst_claims(), {"diff": SAMPLE_DIFF}, model_client=_model())
    second, payload = _call(store, analyst_claims(), {"diff": SAMPLE_DIFF}, model_client=_model())
    assert premier == 200
    assert second == 429
    assert "trop de revue" in payload["error"]


def test_sans_diff_ni_pr_ni_commit_la_requete_est_invalide():
    store = seed_two_tenants()
    status, payload = _call(store, analyst_claims(), {}, model_client=_model())
    assert status == 400
    assert "diff" in payload["error"] or "pull_request" in payload["error"]


def test_un_depot_invalide_est_refuse_avant_tout_appel(monkeypatch):
    """`repository` doit être 'owner/repo' : sinon GitHub serait appelé à l'aveugle."""
    monkeypatch.setenv("REMPART_GITHUB_TOKEN", "fake-token")
    store = seed_two_tenants()
    status, payload = _call(
        store,
        analyst_claims(),
        {"repository": "un-seul-element", "pull_request": 7},
        model_client=_model(),
    )
    assert status == 400
    assert "owner/repo" in payload["error"]


def test_sans_jeton_github_une_pr_repond_501_pas_une_revue_vide():
    """Lire une PR sans jeton est impossible : la route le dit, elle ne revient pas vide."""
    import os

    store = seed_two_tenants()
    saved = os.environ.pop("REMPART_GITHUB_TOKEN", None)
    saved2 = os.environ.pop("GITHUB_TOKEN", None)
    try:
        status, payload = _call(store, analyst_claims(), {"pull_request": 7}, model_client=_model())
    finally:
        if saved:
            os.environ["REMPART_GITHUB_TOKEN"] = saved
        if saved2:
            os.environ["GITHUB_TOKEN"] = saved2
    assert status == 501
    assert "jeton GitHub" in payload["error"]


def test_un_app_inconnue_repond_404():
    store = seed_two_tenants()
    status, _payload = _call(
        store, analyst_claims(), {"diff": SAMPLE_DIFF}, model_client=_model(), app_id="app-fantome"
    )
    assert status == 404
