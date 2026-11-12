"""EF-ORC-08 atteignable par l'API : fenêtres de test à la création et en PUT.

Défaut mesuré le 2026-11-12 sur le banc réel : `_build_application` ignorait
`test_windows` et aucune route ne les mettait à jour, donc toute application
créée via le portail avait une liste vide et `budget_gate` refusait chaque test
complet en production (`allowed=false, reason=outside_test_window`). Le dernier
test de ce fichier rejoue exactement ce scénario.
"""

from __future__ import annotations

import json

import pytest

from rempart.api.app import lambda_handler
from rempart.common.timeutil import utcnow
from rempart.orchestrator.gates import budget_gate
from rempart.orchestrator.task_types import Deps
from tests.api.conftest import (
    analyst_claims,
    client_claims,
    fake_sa,
    make_event,
    platform_admin_claims,
    seed_two_tenants,
)
from tests.fakes_store import FakeStore

TENANT_A = "t-a"


def _window_now() -> dict[str, str | list[str]]:
    """Fenêtre qui couvre l'instant présent, en UTC, tous les jours."""
    return {"days": [], "start": "00:00", "end": "23:59", "environment": "production"}


def _call(store: FakeStore, method, path, claims, body=None):
    event = make_event(method, path, claims=claims, body=body)
    resp = lambda_handler(event, None, store=store, sa=None)
    payload = json.loads(resp["body"]) if resp.get("body") else {}
    return resp["statusCode"], payload


def _create(store, body, claims=None):
    return _call(
        store, "POST", f"/v1/tenants/{TENANT_A}/applications", claims or analyst_claims(), body
    )


def test_creation_accepte_les_fenetres_de_test():
    store = seed_two_tenants()
    status, app = _create(store, {"name": "Shop", "test_windows": [_window_now()]})
    assert status == 201
    assert app["test_windows"] == [_window_now()]
    # réellement relues depuis le store, pas seulement renvoyées
    status, fetched = _call(store, "GET", f"/v1/applications/{app['app_id']}", analyst_claims())
    assert status == 200
    assert fetched["test_windows"] == [_window_now()]


@pytest.mark.parametrize(
    "windows,attendu_dans_le_message",
    [
        ({"days": []}, "liste"),
        ([{"days": ["lundi"], "start": "00:00", "end": "23:59"}], "days"),
        ([{"days": ["mon"], "start": "25:00", "end": "23:59"}], "start"),
        ([{"days": ["mon"], "start": "00:00", "end": "minuit"}], "end"),
        ([{"days": ["mon"], "start": "00:00", "end": "23:59", "environment": 5}], "environment"),
        (["00:00-23:59"], "objet"),
    ],
)
def test_fenetre_malformee_refusee_en_400(windows, attendu_dans_le_message):
    """Une fenêtre invalide ne doit jamais être enregistrée silencieusement."""
    store = seed_two_tenants()
    status, payload = _create(store, {"name": "Shop", "test_windows": windows})
    assert status == 400
    assert attendu_dans_le_message in json.dumps(payload, ensure_ascii=False)


def test_put_met_a_jour_les_fenetres():
    store = seed_two_tenants()
    status, app = _create(store, {"name": "Shop"})
    assert status == 201
    assert app["test_windows"] == []

    status, updated = _call(
        store, "PUT", f"/v1/applications/{app['app_id']}", analyst_claims(),
        {"test_windows": [_window_now()], "criticality": "critical"},
    )
    assert status == 200
    assert updated["test_windows"] == [_window_now()]
    assert updated["criticality"] == "critical"
    assert store.get_application(app["app_id"]).test_windows == [_window_now()]


def test_put_refuse_un_type_invalide_et_un_champs_inconnu_sans_rien_casser():
    store = seed_two_tenants()
    _status, app = _create(store, {"name": "Shop"})
    status, payload = _call(
        store, "PUT", f"/v1/applications/{app['app_id']}", analyst_claims(),
        {"criticality": 5},
    )
    assert status == 400
    assert "criticality" in json.dumps(payload)
    assert store.get_application(app["app_id"]).criticality == "medium"


def test_put_est_refuse_a_un_autre_client_et_introuvable():
    store = seed_two_tenants()
    _status, app = _create(store, {"name": "Shop"})
    status, _ = _call(
        store, "PUT", f"/v1/applications/{app['app_id']}", client_claims("t-b"),
        {"test_windows": [_window_now()]},
    )
    assert status == 403
    status, _ = _call(
        store, "PUT", "/v1/applications/app-inconnue", platform_admin_claims(),
        {"test_windows": [_window_now()]},
    )
    assert status == 404


def _gate_verdict(store: FakeStore, app_id: str) -> dict:
    """Verdict réel de `budget_gate` pour un test complet en production."""
    deps = Deps(store=store, sa=fake_sa())
    return budget_gate(
        {
            "tenant_id": TENANT_A,
            "app_id": app_id,
            "kind": "full",
            "environment": "production",
        },
        deps,
        now=utcnow(),
    )


def test_un_test_complet_en_production_nest_plus_refuse_quand_la_fenetre_vient_de_l_api():
    """Bout en bout : la fenêtre posée via HTTP débloque le garde-fou EF-ORC-08."""
    sans_fenetre = seed_two_tenants()
    _status, app = _create(sans_fenetre, {"name": "Shop", "environment": "production"})
    assert _gate_verdict(sans_fenetre, app["app_id"])["reason"] == "outside_test_window"

    avec_fenetre = seed_two_tenants()
    _status, app = _create(
        avec_fenetre,
        {"name": "Shop", "environment": "production", "test_windows": [_window_now()]},
    )
    verdict = _gate_verdict(avec_fenetre, app["app_id"])
    assert verdict["allowed"] is True, verdict
