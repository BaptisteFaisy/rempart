"""Formes réelles des claims Cognito, preflight CORS et origines autorisées.

Ces tests verrouillent l'incident du 2026-11-12 : sur l'environnement déployé
(eu-north-1), un **vrai jeton Cognito** faisait répondre l'API
`401 {"error": "Authentication required"}` alors que l'autorisateur JWT avait
laissé passer la requête. Deux causes possibles, toutes deux reproduites :
claims dans un autre emplacement, ou `cognito:groups` sérialisé en chaîne JSON.
Aucune des deux ne doit pouvoir redescendre en production.

Le preflight `OPTIONS` est testé ici aussi : sur l'API réelle il répondait 401
(l'autorisateur s'appliquait à OPTIONS), donc aucun navigateur ne pouvait
appeler l'API depuis le portail CloudFront.
"""

from __future__ import annotations

import json

import pytest

from rempart.api.app import lambda_handler
from rempart.common.config import Settings
from tests.api.conftest import make_event, seed_two_tenants

TENANT_A = "t-a"
PORTAL_ORIGIN = "https://d1o2xnfrq8xomh.cloudfront.net"


def _call(event, store=None, settings=None):
    resp = lambda_handler(
        event, None, store=store or seed_two_tenants(), sa=None, settings=settings
    )
    payload = json.loads(resp["body"]) if resp.get("body") else {}
    return resp["statusCode"], payload, resp.get("headers", {})


def _event_with_claims(claims):
    return make_event("GET", f"/v1/tenants/{TENANT_A}", claims=claims)


def _event_flat_authorizer(claims):
    """Claims posées directement sous `authorizer.claims` (autre forme réelle)."""
    event = make_event("GET", f"/v1/tenants/{TENANT_A}")
    event["requestContext"]["authorizer"] = {"claims": claims}
    return event


@pytest.mark.parametrize(
    "groups",
    [
        ["analyst"],
        "analyst",
        '["analyst"]',
        "analyst,client_dev",
        '["analyst", "client_dev"]',
    ],
)
def test_groups_claim_is_accepted_in_every_real_shape(groups):
    """Liste, chaîne simple, chaîne JSON, liste séparée par des virgules."""
    status, payload, _ = _call(_event_with_claims({"sub": "u-1", "cognito:groups": groups}))
    assert status == 200
    assert payload["tenant_id"] == TENANT_A


def test_claims_under_flat_authorizer_are_accepted():
    """`authorizer.claims` (et pas seulement `authorizer.jwt.claims`)."""
    status, payload, _ = _call(
        _event_flat_authorizer({"sub": "u-2", "cognito:groups": ["analyst"]})
    )
    assert status == 200
    assert payload["tenant_id"] == TENANT_A


def test_username_is_used_when_sub_is_absent():
    status, _, _ = _call(
        _event_with_claims({"username": "u-3", "cognito:groups": ["analyst"]})
    )
    assert status == 200


@pytest.mark.parametrize(
    "groups",
    [None, "", "[]", '["pas-un-role"]', '["platform_admin"', {"role": "analyst"}, 42],
)
def test_unusable_groups_claim_fails_closed(groups):
    """Aucune élévation de privilège : toute forme non reconnue → 401."""
    claims = {"sub": "u-4"}
    if groups is not None:
        claims["cognito:groups"] = groups
    status, _, _ = _call(_event_with_claims(claims))
    assert status == 401


def test_missing_authorizer_is_refused():
    status, _, _ = _call(make_event("GET", f"/v1/tenants/{TENANT_A}"))
    assert status == 401


def test_authorizer_shape_is_logged_without_any_claim_value(caplog):
    """Le diagnostic journalise des NOMS de clés, jamais de valeurs.

    La trace n'est émise qu'une fois par processus (garde module-level) : le
    test remet la garde à zéro pour observer le comportement de démarrage à
    froid, qui est exactement ce qu'on lira dans CloudWatch.
    """
    from rempart.api import app as api_app

    api_app._AUTHORIZER_SHAPE_LOGGED = False
    with caplog.at_level("INFO", logger="rempart.api"):
        _call(_event_with_claims({"sub": "sub-secret", "cognito:groups": ["analyst"]}))
    logged = "\n".join(record.getMessage() for record in caplog.records)
    assert "sub-secret" not in logged
    assert "authorizer=" in logged
    assert "claims=['cognito:groups', 'sub']" in logged


def test_preflight_options_is_answered_without_authentication():
    """204 sur OPTIONS, même sans claims : sinon le navigateur bloque tout."""
    event = make_event("OPTIONS", f"/v1/tenants/{TENANT_A}")
    status, _, headers = _call(event)
    assert status == 204
    assert headers["Access-Control-Allow-Methods"].split(", ")[0] == "GET"
    assert "Authorization" in headers["Access-Control-Allow-Headers"]


def test_cors_echoes_only_allowed_origins():
    settings = Settings(cors_allow_origins=(PORTAL_ORIGIN,))
    allowed = make_event(
        "GET", f"/v1/tenants/{TENANT_A}",
        claims={"sub": "u-5", "cognito:groups": ["analyst"]},
        headers={"Origin": PORTAL_ORIGIN},
    )
    status, _, headers = _call(allowed, settings=settings)
    assert status == 200
    assert headers["Access-Control-Allow-Origin"] == PORTAL_ORIGIN

    stranger = make_event(
        "GET", f"/v1/tenants/{TENANT_A}",
        claims={"sub": "u-5", "cognito:groups": ["analyst"]},
        headers={"Origin": "https://evil.example"},
    )
    _, _, headers = _call(stranger, settings=settings)
    assert "Access-Control-Allow-Origin" not in headers


def test_cors_falls_back_to_wildcard_when_unconfigured():
    """Comportement historique conservé pour le serveur de démonstration locale."""
    _, _, headers = _call(
        make_event("GET", f"/v1/tenants/{TENANT_A}",
                   claims={"sub": "u-6", "cognito:groups": ["analyst"]})
    )
    assert headers["Access-Control-Allow-Origin"] == "*"
