"""Tests for the policy / settings routes (EF-ADM-01).

Couvre GET/PUT ``/v1/tenants/{id}/policy``, GET ``/v1/settings/defaults``,
l'acceptation de ``policy`` sur POST/PUT ``/v1/tenants`` et les règles
d'autorisation : écriture réservée à ``platform_admin``, lecture pour les
analystes et les rôles du tenant, 403 pour un client visant un autre tenant.
"""

import json

import pytest

from rempart.api.app import lambda_handler
from tests.api.conftest import (
    analyst_claims,
    client_claims,
    demo_claims,
    fake_sa,
    make_event,
    platform_admin_claims,
    seed_two_tenants,
)

VALID_POLICY = {
    "due_days": {"P1": 3, "P2": 14, "P3": 60, "P4": None},
    "matrix_overrides": {"Critical": "P1", "Medium": "P2"},
    "blocking_threshold": "Medium",
    "hourly_rate": 75.0,
}

DEFAULT_DUE_DAYS_PAYLOAD = {"P1": 7, "P2": 30, "P3": 90, "P4": None}


def call(method, path, claims, store, **kwargs):
    event = make_event(method, path, claims=claims, **kwargs)
    return lambda_handler(event, None, store=store, sa=fake_sa())


def body_of(resp):
    return json.loads(resp["body"])


# ---------------------------------------------------------------- GET policy


def test_get_policy_defaults_for_platform_admin():
    store = seed_two_tenants()
    resp = call("GET", "/v1/tenants/t-a/policy", platform_admin_claims(), store)
    assert resp["statusCode"] == 200
    body = body_of(resp)
    assert body["tenant_id"] == "t-a"
    assert body["policy"] == {}
    assert body["effective"]["due_days"] == DEFAULT_DUE_DAYS_PAYLOAD
    assert body["effective"]["matrix_overrides"] == {}
    assert body["effective"]["blocking_threshold"] == "High"
    assert body["effective"]["hourly_rate"] == 50.0


def test_get_policy_allowed_for_analyst_and_own_client():
    store = seed_two_tenants()
    for claims in (analyst_claims(), client_claims("t-a"), client_claims("t-a", "client_dev")):
        resp = call("GET", "/v1/tenants/t-a/policy", claims, store)
        assert resp["statusCode"] == 200


def test_get_policy_cross_tenant_client_is_forbidden():
    store = seed_two_tenants()
    resp = call("GET", "/v1/tenants/t-b/policy", client_claims("t-a"), store)
    assert resp["statusCode"] == 403


def test_get_policy_demo_other_tenant_is_forbidden():
    store = seed_two_tenants()
    resp = call("GET", "/v1/tenants/t-a/policy", demo_claims(), store)
    assert resp["statusCode"] == 403


def test_get_policy_unauthenticated_is_401():
    store = seed_two_tenants()
    resp = call("GET", "/v1/tenants/t-a/policy", None, store)
    assert resp["statusCode"] == 401


def test_get_policy_unknown_tenant_is_404():
    store = seed_two_tenants()
    resp = call("GET", "/v1/tenants/t-zzz/policy", platform_admin_claims(), store)
    assert resp["statusCode"] == 404


# ---------------------------------------------------------------- PUT policy


def test_put_policy_platform_admin_persists_and_audits():
    store = seed_two_tenants()
    resp = call(
        "PUT", "/v1/tenants/t-a/policy", platform_admin_claims(), store, body=VALID_POLICY
    )
    assert resp["statusCode"] == 200
    body = body_of(resp)
    assert body["policy"] == VALID_POLICY
    assert body["effective"]["due_days"]["P1"] == 3
    assert body["effective"]["blocking_threshold"] == "Medium"
    assert store.get_tenant("t-a").policy == VALID_POLICY
    assert any(a.action == "tenant.policy_update" and a.object_id == "t-a"
               for a in store.audits)


def test_put_policy_accepts_wrapped_form():
    store = seed_two_tenants()
    resp = call(
        "PUT", "/v1/tenants/t-a/policy", platform_admin_claims(), store,
        body={"policy": VALID_POLICY},
    )
    assert resp["statusCode"] == 200
    assert store.get_tenant("t-a").policy == VALID_POLICY


def test_put_policy_replaces_previous_policy():
    store = seed_two_tenants()
    call("PUT", "/v1/tenants/t-a/policy", platform_admin_claims(), store, body=VALID_POLICY)
    resp = call(
        "PUT", "/v1/tenants/t-a/policy", platform_admin_claims(), store,
        body={"due_days": {"P1": 1}},
    )
    assert resp["statusCode"] == 200
    assert store.get_tenant("t-a").policy == {"due_days": {"P1": 1}}


def test_put_policy_empty_body_clears_policy():
    store = seed_two_tenants()
    call("PUT", "/v1/tenants/t-a/policy", platform_admin_claims(), store, body=VALID_POLICY)
    resp = call("PUT", "/v1/tenants/t-a/policy", platform_admin_claims(), store, body={})
    assert resp["statusCode"] == 200
    assert store.get_tenant("t-a").policy == {}


@pytest.mark.parametrize(
    "claims",
    [analyst_claims(), client_claims("t-a"), client_claims("t-a", "client_dev")],
    ids=["analyst", "client_security", "client_dev"],
)
def test_put_policy_non_admin_roles_are_forbidden(claims):
    store = seed_two_tenants()
    resp = call("PUT", "/v1/tenants/t-a/policy", claims, store, body=VALID_POLICY)
    assert resp["statusCode"] == 403
    assert store.get_tenant("t-a").policy == {}


def test_put_policy_cross_tenant_client_is_forbidden():
    store = seed_two_tenants()
    resp = call("PUT", "/v1/tenants/t-b/policy", client_claims("t-a"), store, body=VALID_POLICY)
    assert resp["statusCode"] == 403
    assert store.get_tenant("t-b").policy == {}


def test_put_policy_unauthenticated_is_401():
    store = seed_two_tenants()
    resp = call("PUT", "/v1/tenants/t-a/policy", None, store, body=VALID_POLICY)
    assert resp["statusCode"] == 401


def test_put_policy_unknown_tenant_is_404():
    store = seed_two_tenants()
    resp = call("PUT", "/v1/tenants/t-zzz/policy", platform_admin_claims(), store, body={})
    assert resp["statusCode"] == 404


@pytest.mark.parametrize(
    "payload",
    [
        {"unknown_key": 1},
        {"due_days": 7},
        {"due_days": {"P5": 3}},
        {"due_days": {"P1": 0}},
        {"due_days": {"P1": -5}},
        {"due_days": {"P1": "7"}},
        {"due_days": {"P1": 7.5}},
        {"due_days": {"P1": True}},
        {"matrix_overrides": 5},
        {"matrix_overrides": {"Ultra": "P1"}},
        {"matrix_overrides": {"Critical": "P0"}},
        {"matrix_overrides": {"Critical": 1}},
        {"blocking_threshold": "SuperHigh"},
        {"blocking_threshold": 5},
        {"hourly_rate": 0},
        {"hourly_rate": -10},
        {"hourly_rate": "50"},
        {"policy": 5},
        {"policy": {}, "extra": 1},
    ],
)
def test_put_policy_validation_rejects_bad_payloads(payload):
    store = seed_two_tenants()
    resp = call("PUT", "/v1/tenants/t-a/policy", platform_admin_claims(), store, body=payload)
    assert resp["statusCode"] == 400
    assert "error" in body_of(resp)
    assert store.get_tenant("t-a").policy == {}


# ------------------------------------------------------------ GET defaults


def test_get_settings_defaults():
    store = seed_two_tenants()
    resp = call("GET", "/v1/settings/defaults", analyst_claims(), store)
    assert resp["statusCode"] == 200
    assert body_of(resp) == {
        "due_days": DEFAULT_DUE_DAYS_PAYLOAD,
        "matrix_overrides": {},
        "blocking_threshold": "High",
        "hourly_rate": 50.0,
    }


def test_get_settings_defaults_for_client_role():
    store = seed_two_tenants()
    resp = call("GET", "/v1/settings/defaults", client_claims("t-a"), store)
    assert resp["statusCode"] == 200


def test_get_settings_defaults_unauthenticated_is_401():
    store = seed_two_tenants()
    resp = call("GET", "/v1/settings/defaults", None, store)
    assert resp["statusCode"] == 401


# ------------------------------------------------- policy via tenant routes


def test_create_tenant_with_policy():
    store = seed_two_tenants()
    resp = call(
        "POST", "/v1/tenants", platform_admin_claims(), store,
        body={"tenant_id": "t-new", "name": "New Co", "policy": VALID_POLICY},
    )
    assert resp["statusCode"] == 201
    assert body_of(resp)["policy"] == VALID_POLICY
    assert store.get_tenant("t-new").policy == VALID_POLICY


def test_create_tenant_without_policy_defaults_to_empty():
    store = seed_two_tenants()
    resp = call(
        "POST", "/v1/tenants", platform_admin_claims(), store, body={"tenant_id": "t-new"}
    )
    assert resp["statusCode"] == 201
    assert store.get_tenant("t-new").policy == {}


def test_create_tenant_invalid_policy_is_400():
    store = seed_two_tenants()
    resp = call(
        "POST", "/v1/tenants", platform_admin_claims(), store,
        body={"tenant_id": "t-new", "policy": {"due_days": {"P1": 0}}},
    )
    assert resp["statusCode"] == 400
    assert store.get_tenant("t-new") is None


def test_create_tenant_policy_requires_platform_admin():
    store = seed_two_tenants()
    resp = call(
        "POST", "/v1/tenants", analyst_claims(), store,
        body={"tenant_id": "t-new", "policy": VALID_POLICY},
    )
    assert resp["statusCode"] == 403
    resp = call("POST", "/v1/tenants", analyst_claims(), store, body={"tenant_id": "t-new"})
    assert resp["statusCode"] == 201


def test_put_tenant_updates_policy_and_fields():
    store = seed_two_tenants()
    resp = call(
        "PUT", "/v1/tenants/t-a", platform_admin_claims(), store,
        body={"name": "Acme Corp", "policy": VALID_POLICY},
    )
    assert resp["statusCode"] == 200
    body = body_of(resp)
    assert body["name"] == "Acme Corp"
    assert body["policy"] == VALID_POLICY
    tenant = store.get_tenant("t-a")
    assert tenant.name == "Acme Corp"
    assert tenant.policy == VALID_POLICY


def test_put_tenant_policy_requires_platform_admin():
    store = seed_two_tenants()
    resp = call(
        "PUT", "/v1/tenants/t-a", analyst_claims(), store, body={"policy": VALID_POLICY}
    )
    assert resp["statusCode"] == 403


def test_put_tenant_cross_tenant_client_is_forbidden():
    store = seed_two_tenants()
    resp = call("PUT", "/v1/tenants/t-b", client_claims("t-a"), store, body={"name": "x"})
    assert resp["statusCode"] == 403


def test_put_tenant_unauthenticated_is_401():
    store = seed_two_tenants()
    resp = call("PUT", "/v1/tenants/t-a", None, store, body={"name": "x"})
    assert resp["statusCode"] == 401


def test_put_tenant_unknown_tenant_is_404():
    store = seed_two_tenants()
    resp = call("PUT", "/v1/tenants/t-zzz", platform_admin_claims(), store, body={"name": "x"})
    assert resp["statusCode"] == 404


@pytest.mark.parametrize(
    "payload",
    [
        {"unknown_field": 1},
        {"contacts": "not-a-list"},
        {"monthly_budget_hours": -1},
        {"monthly_budget_hours": "abc"},
        {"policy": {"nope": 1}},
    ],
)
def test_put_tenant_validation_rejects_bad_payloads(payload):
    store = seed_two_tenants()
    resp = call("PUT", "/v1/tenants/t-a", platform_admin_claims(), store, body=payload)
    assert resp["statusCode"] == 400
