"""Tenant isolation tests (ENF-SEC-01, acceptance R9).

A user of tenant A must get 403 on every endpoint that targets tenant B.
"""

import json

from rempart.api.app import lambda_handler
from tests.api.conftest import (
    client_claims,
    demo_claims,
    make_event,
    platform_admin_claims,
    seed_two_tenants,
)


def call(method, path, claims, store, **kwargs):
    event = make_event(method, path, claims=claims, **kwargs)
    return lambda_handler(event, None, store=store, sa=None)


def test_cross_tenant_reads_are_forbidden():
    store = seed_two_tenants()
    claims = client_claims("t-a")
    cases = [
        ("GET", "/v1/tenants/t-b"),
        ("GET", "/v1/applications/app-t-b"),
        ("GET", "/v1/applications/app-t-b/onboarding"),
        ("GET", "/v1/applications/app-t-b/runs"),
        ("GET", "/v1/findings/f-t-b"),
        ("GET", "/v1/tenants/t-b/kpis"),
        ("GET", "/v1/tenants/t-b/budget"),
    ]
    for method, path in cases:
        resp = call(method, path, claims, store)
        assert resp["statusCode"] == 403, f"{method} {path} -> {resp['statusCode']}"


def test_cross_tenant_writes_are_forbidden():
    store = seed_two_tenants()
    claims = client_claims("t-a")
    cases = [
        ("POST", "/v1/tenants/t-b/applications", {"name": "x"}),
        ("POST", "/v1/applications/app-t-b/onboarding", {}),
        ("POST", "/v1/applications/app-t-b/runs", {}),
        ("POST", "/v1/findings/f-t-b/decision", {"action": "confirmed"}),
        ("POST", "/v1/findings/f-t-b/remediation", {}),
        ("POST", "/v1/tenants/t-b/reports", {"period": "2026-11"}),
        ("PUT", "/v1/tenants/t-b/budget", {"monthly_budget_hours": 1}),
    ]
    for method, path, body in cases:
        resp = call(method, path, claims, store, body=body)
        assert resp["statusCode"] == 403, f"{method} {path} -> {resp['statusCode']}"


def test_fleet_kpis_are_forbidden_for_clients():
    store = seed_two_tenants()
    resp = call("GET", "/v1/fleet/kpis", client_claims("t-a"), store)
    assert resp["statusCode"] == 403


def test_findings_list_never_leaks_other_tenants():
    store = seed_two_tenants()
    resp = call("GET", "/v1/findings", client_claims("t-a"), store)
    assert resp["statusCode"] == 200
    payload = json.loads(resp["body"])
    for finding in payload["findings"]:
        assert finding["tenant_id"] == "t-a"


def test_findings_filtered_by_other_tenant_is_forbidden():
    store = seed_two_tenants()
    resp = call(
        "GET", "/v1/findings", client_claims("t-a"), store, query={"tenant_id": "t-b"}
    )
    assert resp["statusCode"] == 403


def test_analyst_sees_all_tenants():
    store = seed_two_tenants()
    resp = call("GET", "/v1/tenants", {"sub": "a", "cognito:groups": ["analyst"]}, store)
    assert resp["statusCode"] == 200
    payload = json.loads(resp["body"])
    assert len(payload["tenants"]) == 2


def test_client_sees_only_own_tenant():
    store = seed_two_tenants()
    resp = call("GET", "/v1/tenants", client_claims("t-a"), store)
    assert resp["statusCode"] == 200
    payload = json.loads(resp["body"])
    assert len(payload["tenants"]) == 1
    assert payload["tenants"][0]["tenant_id"] == "t-a"


def test_demo_account_is_read_only():
    store = seed_two_tenants()
    resp = call("GET", "/v1/tenants", demo_claims(), store)
    assert resp["statusCode"] in (200, 403)
    resp2 = call("POST", "/v1/tenants", demo_claims(), store, body={"tenant_id": "t-x"})
    assert resp2["statusCode"] == 403


def test_unauthenticated_request_is_rejected():
    store = seed_two_tenants()
    resp = call("GET", "/v1/tenants", None, store)
    assert resp["statusCode"] == 401


def test_platform_admin_reaches_every_tenant():
    store = seed_two_tenants()
    for tenant_id in ("t-a", "t-b"):
        resp = call("GET", f"/v1/tenants/{tenant_id}", platform_admin_claims(), store)
        assert resp["statusCode"] == 200
