"""Tests API du coupe-circuit global exposé dans le payload du budget.

Le portail lit ``kill_switch`` dans la réponse de ``GET/PUT
/v1/tenants/{id}/budget`` pour afficher le bandeau d'arrêt ; ces tests
garantissent que le flag est bien présent et fidèle au réglage.
"""

import json

from rempart.api.app import lambda_handler
from rempart.common.config import Settings
from tests.api.conftest import analyst_claims, fake_sa, make_event, seed_two_tenants
from tests.fakes import FakeStore


def _budget_payload(settings: Settings) -> dict:
    store: FakeStore = seed_two_tenants()
    event = make_event("GET", "/v1/tenants/t-a/budget", claims=analyst_claims())
    resp = lambda_handler(event, None, store=store, sa=fake_sa(), settings=settings)
    assert resp["statusCode"] == 200
    return json.loads(resp["body"])


def test_budget_payload_exposes_kill_switch_when_active():
    payload = _budget_payload(Settings(kill_switch=True))
    assert payload["kill_switch"] is True


def test_budget_payload_exposes_kill_switch_when_inactive():
    payload = _budget_payload(Settings(kill_switch=False))
    assert payload["kill_switch"] is False
