"""Tests du journal d'audit consultable (EF-ADM-02, ENF-SEC-06).

Deux garanties : le journal se lit (avec cloisonnement par tenant) et il ne
se modifie pas — aucune méthode d'écriture n'existe sur ``/v1/audit``.
"""

import inspect
import json
import uuid
from typing import Any

from rempart.api.app import lambda_handler
from rempart.common.models import AuditEvent
from rempart.common.store import Store
from tests.api.conftest import (
    analyst_claims,
    client_claims,
    demo_claims,
    make_event,
    platform_admin_claims,
    seed_two_tenants,
)
from tests.fakes import FakeStore


def call(method: str, path: str, claims: dict[str, Any] | None, store: FakeStore, **kwargs):
    event = make_event(method, path, claims=claims, **kwargs)
    return lambda_handler(event, None, store=store, sa=None)


def body_of(resp: dict[str, Any]) -> dict[str, Any]:
    return json.loads(resp["body"])


def event(
    actor: str,
    action: str,
    object_type: str,
    object_id: str,
    created_at: str,
    result: str = "ok",
) -> AuditEvent:
    """Build an audit event with a controlled timestamp (deterministic filters)."""
    return AuditEvent(
        audit_id=f"audit-{uuid.uuid4().hex[:12]}",
        actor=actor,
        action=action,
        object_type=object_type,
        object_id=object_id,
        result=result,
        created_at=created_at,
    )


def seed_audit(store: FakeStore) -> FakeStore:
    """Seed a journal spread over two tenants and three dates."""
    store.audits.extend(
        [
            event("user-admin", "tenant.create", "tenant", "t-a", "2026-11-01T08:00:00Z"),
            event("user-admin", "tenant.create", "tenant", "t-b", "2026-11-01T09:00:00Z"),
            event("user-client", "run.start", "run", "run-t-a", "2026-11-05T12:00:00Z"),
            event("user-client", "finding.decision", "finding", "f-t-a", "2026-11-10T18:00:00Z"),
            event("user-client", "finding.decision", "finding", "f-t-b", "2026-11-10T19:00:00Z"),
        ]
    )
    return store


def account_manager_claims(tenant_id: str | None) -> dict[str, Any]:
    claims: dict[str, Any] = {"sub": "user-am", "cognito:groups": ["account_manager"]}
    if tenant_id:
        claims["custom:tenant_id"] = tenant_id
    return claims


def executive_claims(tenant_id: str = "t-a") -> dict[str, Any]:
    return {
        "sub": "user-exec",
        "cognito:groups": ["executive"],
        "custom:tenant_id": tenant_id,
    }


# --- lecture autorisée ----------------------------------------------------


def test_platform_admin_reads_the_whole_journal():
    store = seed_audit(seed_two_tenants())
    resp = call("GET", "/v1/audit", platform_admin_claims(), store)

    assert resp["statusCode"] == 200
    payload = body_of(resp)
    assert payload["total"] == 5
    assert payload["count"] == 5
    assert {e["object_id"] for e in payload["events"]} == {
        "t-a",
        "t-b",
        "run-t-a",
        "f-t-a",
        "f-t-b",
    }


def test_analyst_can_filter_by_tenant():
    store = seed_audit(seed_two_tenants())
    resp = call("GET", "/v1/audit", analyst_claims(), store, query={"tenant_id": "t-a"})

    assert resp["statusCode"] == 200
    object_ids = {e["object_id"] for e in body_of(resp)["events"]}
    assert object_ids == {"t-a", "run-t-a", "f-t-a"}


def test_tenant_route_returns_one_client_journal():
    store = seed_audit(seed_two_tenants())
    resp = call("GET", "/v1/tenants/t-b/audit", platform_admin_claims(), store)

    assert resp["statusCode"] == 200
    payload = body_of(resp)
    assert {e["object_id"] for e in payload["events"]} == {"t-b", "f-t-b"}


def test_client_sees_only_its_own_tenant_events():
    store = seed_audit(seed_two_tenants())
    resp = call("GET", "/v1/audit", client_claims("t-a"), store)

    assert resp["statusCode"] == 200
    events = body_of(resp)["events"]
    assert events
    assert {e["object_id"] for e in events} == {"t-a", "run-t-a", "f-t-a"}


def test_client_can_read_its_own_tenant_route():
    store = seed_audit(seed_two_tenants())
    resp = call("GET", "/v1/tenants/t-a/audit", client_claims("t-a", "client_dev"), store)

    assert resp["statusCode"] == 200
    assert all(e["object_id"] in {"t-a", "run-t-a", "f-t-a"} for e in body_of(resp)["events"])


def test_account_manager_is_restricted_to_its_own_tenant():
    store = seed_audit(seed_two_tenants())
    resp = call("GET", "/v1/audit", account_manager_claims("t-a"), store)

    assert resp["statusCode"] == 200
    assert {e["object_id"] for e in body_of(resp)["events"]} == {"t-a", "run-t-a", "f-t-a"}


# --- refus ----------------------------------------------------------------


def test_cross_tenant_query_on_journal_is_forbidden():
    store = seed_audit(seed_two_tenants())
    resp = call("GET", "/v1/audit", client_claims("t-a"), store, query={"tenant_id": "t-b"})

    assert resp["statusCode"] == 403


def test_cross_tenant_on_tenant_route_is_forbidden():
    store = seed_audit(seed_two_tenants())
    resp = call("GET", "/v1/tenants/t-b/audit", client_claims("t-a"), store)

    assert resp["statusCode"] == 403


def test_account_manager_cannot_read_another_tenant_route():
    store = seed_audit(seed_two_tenants())
    resp = call("GET", "/v1/tenants/t-b/audit", account_manager_claims("t-a"), store)

    assert resp["statusCode"] == 403


def test_account_manager_without_tenant_is_denied():
    store = seed_audit(seed_two_tenants())
    resp = call("GET", "/v1/audit", account_manager_claims(None), store)

    assert resp["statusCode"] == 403


def test_demo_and_executive_have_no_journal_access():
    store = seed_audit(seed_two_tenants())
    cases = [
        ("/v1/audit", demo_claims()),
        ("/v1/audit", executive_claims()),
        ("/v1/tenants/t-a/audit", demo_claims()),
        ("/v1/tenants/t-a/audit", executive_claims()),
    ]
    for path, claims in cases:
        resp = call("GET", path, claims, store)
        assert resp["statusCode"] == 403, f"{path} {claims['cognito:groups']}"


def test_unauthenticated_journal_read_is_rejected():
    store = seed_audit(seed_two_tenants())
    resp = call("GET", "/v1/audit", None, store)

    assert resp["statusCode"] == 401


def test_unknown_tenant_route_returns_404_for_admin():
    store = seed_audit(seed_two_tenants())
    resp = call("GET", "/v1/tenants/t-ghost/audit", platform_admin_claims(), store)

    assert resp["statusCode"] == 404


# --- filtres --------------------------------------------------------------


def test_filters_by_action_actor_and_object():
    store = seed_audit(seed_two_tenants())

    by_action = call("GET", "/v1/audit", platform_admin_claims(), store,
                     query={"action": "finding.decision"})
    assert {e["object_id"] for e in body_of(by_action)["events"]} == {"f-t-a", "f-t-b"}

    by_actor = call("GET", "/v1/audit", platform_admin_claims(), store,
                    query={"actor": "user-admin"})
    assert {e["object_id"] for e in body_of(by_actor)["events"]} == {"t-a", "t-b"}

    by_object = call("GET", "/v1/audit", platform_admin_claims(), store,
                     query={"object_type": "run", "object_id": "run-t-a"})
    assert body_of(by_object)["total"] == 1


def test_filters_by_date_range():
    store = seed_audit(seed_two_tenants())
    resp = call(
        "GET",
        "/v1/audit",
        platform_admin_claims(),
        store,
        query={"from": "2026-11-04T00:00:00Z", "to": "2026-11-08T00:00:00Z"},
    )

    assert resp["statusCode"] == 200
    payload = body_of(resp)
    assert payload["total"] == 1
    assert payload["events"][0]["object_id"] == "run-t-a"


def test_filtered_events_stay_tenant_scoped():
    store = seed_audit(seed_two_tenants())
    resp = call("GET", "/v1/audit", client_claims("t-a"), store,
                query={"action": "finding.decision"})

    assert resp["statusCode"] == 200
    assert {e["object_id"] for e in body_of(resp)["events"]} == {"f-t-a"}


def test_invalid_date_window_is_rejected():
    store = seed_audit(seed_two_tenants())
    bad_format = call("GET", "/v1/audit", platform_admin_claims(), store,
                      query={"from": "not-a-date"})
    reversed_range = call("GET", "/v1/audit", platform_admin_claims(), store,
                          query={"from": "2026-11-10T00:00:00Z", "to": "2026-11-01T00:00:00Z"})

    assert bad_format["statusCode"] == 400
    assert reversed_range["statusCode"] == 400


# --- pagination -----------------------------------------------------------


def test_pagination_uses_limit_offset_and_next_offset():
    store = seed_audit(seed_two_tenants())

    first = body_of(call("GET", "/v1/audit", platform_admin_claims(), store,
                         query={"limit": "2"}))
    assert first["count"] == 2
    assert first["total"] == 5
    assert first["next_offset"] == 2
    assert first["events"][0]["created_at"] == "2026-11-10T19:00:00Z"

    last = body_of(call("GET", "/v1/audit", platform_admin_claims(), store,
                        query={"limit": "2", "offset": "4"}))
    assert last["count"] == 1
    assert last["next_offset"] is None


def test_page_size_is_capped():
    store = seed_audit(seed_two_tenants())
    resp = call("GET", "/v1/audit", platform_admin_claims(), store, query={"limit": "10000"})

    assert resp["statusCode"] == 200
    assert body_of(resp)["limit"] == 200


def test_invalid_pagination_is_rejected():
    store = seed_audit(seed_two_tenants())
    for query in ({"limit": "0"}, {"limit": "abc"}, {"offset": "-1"}):
        resp = call("GET", "/v1/audit", platform_admin_claims(), store, query=query)
        assert resp["statusCode"] == 400, query


# --- immuabilité (ENF-SEC-06) ---------------------------------------------


def test_journal_write_methods_are_not_exposed():
    store = seed_audit(seed_two_tenants())
    paths = ["/v1/audit", "/v1/audit/audit-123", "/v1/tenants/t-a/audit"]
    for method in ("POST", "PUT", "DELETE", "PATCH"):
        for path in paths:
            resp = call(method, path, platform_admin_claims(), store, body={"action": "x"})
            assert resp["statusCode"] in (404, 405), f"{method} {path} -> {resp['statusCode']}"


def test_writing_through_the_journal_leaves_it_unchanged():
    store = seed_audit(seed_two_tenants())
    before = len(store.audits)
    call("POST", "/v1/audit", platform_admin_claims(), store, body={"action": "forged"})

    assert len(store.audits) == before


# --- cohérence écriture / lecture -----------------------------------------


def test_what_api_writes_is_what_the_journal_reads():
    store = seed_two_tenants()
    call("POST", "/v1/tenants", platform_admin_claims(), store,
         body={"tenant_id": "t-new", "name": "New"})

    resp = call("GET", "/v1/audit", platform_admin_claims(), store,
                query={"action": "tenant.create"})
    events = body_of(resp)["events"]

    assert len(events) == 1
    assert events[0]["actor"] == "user-admin"
    assert events[0]["object_type"] == "tenant"
    assert events[0]["object_id"] == "t-new"
    assert events[0]["result"] == "ok"


def test_platform_level_events_never_reach_a_tenant_journal():
    store = seed_audit(seed_two_tenants())
    store.audits.extend(
        [
            event("pipeline", "deployment_event.received", "repository", "acme/shop",
                  "2026-11-06T00:00:00Z"),
            event("orchestrator", "budget.update", "budget", "t-a#2026-11",
                  "2026-11-07T00:00:00Z"),
        ]
    )

    admin = body_of(call("GET", "/v1/audit", platform_admin_claims(), store))
    client_a = body_of(call("GET", "/v1/audit", client_claims("t-a"), store))
    client_b = body_of(call("GET", "/v1/tenants/t-b/audit", platform_admin_claims(), store))

    assert admin["total"] == 7
    assert "acme/shop" not in {e["object_id"] for e in client_a["events"]}
    assert "t-a#2026-11" in {e["object_id"] for e in client_a["events"]}
    assert "t-a#2026-11" not in {e["object_id"] for e in client_b["events"]}


def test_list_audit_signature_is_identical_in_both_implementations():
    assert list(inspect.signature(Store.list_audit).parameters) == list(
        inspect.signature(FakeStore.list_audit).parameters
    )
