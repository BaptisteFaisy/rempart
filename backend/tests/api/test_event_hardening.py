"""Endurcissement du webhook CI/CD : signature HMAC, validation stricte, débit.

Le webhook est le seul point d'entrée sans jeton : c'est celui qu'on protège
le plus. Ces tests vérifient les trois protections, en recalculant la signature
localement (implémentation standard, indépendante de celle de la route).
"""

from __future__ import annotations

import hashlib
import hmac
import json

import pytest

import rempart.api.routes.events as events
from rempart.api.app import lambda_handler
from rempart.common import ratelimit
from rempart.common.config import Settings
from tests.api.conftest import make_event, seed_two_tenants

KEY = "secret-cle-partagee"


def _sign(body: dict) -> str:
    """Signature standard : HMAC-SHA256 du JSON canonique (indépendant de la route)."""
    canonical = json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hmac.new(KEY.encode("utf-8"), canonical, hashlib.sha256).hexdigest()


def _post(store, body: dict, *, signature: str | None = None, extra_headers: dict | None = None):
    headers = {"X-Rempart-Key": KEY}
    if signature is not None:
        headers["X-Rempart-Signature"] = signature
    headers.update(extra_headers or {})
    event = make_event("POST", "/v1/events/deployment", body=body, headers=headers)
    response = lambda_handler(
        event, None, store=store, sa=None, settings=Settings(pipeline_key=KEY)
    )
    return response["statusCode"], response


def _body(response):
    return json.loads(response["body"])


def test_un_evenement_signe_correctement_est_accepte():
    body = {"repository": "acme/shop", "commit_sha": "abc", "environment": "staging"}
    status, response = _post(seed_two_tenants(), body, signature=_sign(body))
    assert status == 202
    assert _body(response)["received"] is True


def test_une_signature_fausse_est_refusee_comme_une_cle_fausse():
    """Même message neutre : on ne distingue pas « signature fausse » de « clé fausse »."""
    body = {"repository": "acme/shop"}
    status_bad_key = _post(
        seed_two_tenants(), body, extra_headers={"X-Rempart-Key": "fausse"}
    )[0]
    status_bad_sig = _post(seed_two_tenants(), body, signature="0" * 64)[0]
    assert status_bad_key == status_bad_sig == 403
    _status, refused = _post(seed_two_tenants(), body, signature="0" * 64)
    assert "configur" not in _body(refused)["error"].lower()


def test_une_signature_absente_est_refusee():
    status, _ = _post(seed_two_tenants(), {"repository": "acme/shop"})
    assert status == 403


@pytest.mark.parametrize(
    "body",
    [
        ["pas", "un", "objet"],
        "juste une chaîne",
        42,
        {},
        {"repository": 5},
        {"repository": "acme/shop", "commit_sha": 123},
        {"commit_sha": "abc"},  # repository manquant
    ],
)
def test_un_corps_invalide_est_refuse_sans_500(body):
    """Toute entrée invalide est rejetée explicitement, jamais par une 500."""
    store = seed_two_tenants()
    headers = {"X-Rempart-Key": KEY, "X-Rempart-Signature": "0" * 64}
    event = make_event("POST", "/v1/events/deployment", body=body, headers=headers)
    response = lambda_handler(
        event, None, store=store, sa=None, settings=Settings(pipeline_key=KEY)
    )
    assert response["statusCode"] in (400, 401, 403)


def test_un_repository_trop_long_est_refuse():
    body = {"repository": "a" * 300}
    status, _ = _post(seed_two_tenants(), body, signature=_sign(body))
    assert status == 400


def test_le_debit_est_limite_par_depot(monkeypatch):
    ratelimit.reset()
    monkeypatch.setattr(events.ratelimit, "MAX_PER_WINDOW", 3)
    body = {"repository": "acme/shop"}
    statuses = [
        _post(seed_two_tenants(), body, signature=_sign(body))[0] for _ in range(5)
    ]
    assert statuses[:3] == [202, 202, 202]
    assert statuses[3] == 429
    assert statuses[4] == 429
    ratelimit.reset()
