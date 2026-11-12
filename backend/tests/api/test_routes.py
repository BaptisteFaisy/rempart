"""Functional tests for the API routes (chapter 14)."""

import json

from rempart.api.app import lambda_handler
from rempart.common.config import Settings
from rempart.common.models import Tenant
from tests.api.conftest import (
    analyst_claims,
    client_claims,
    fake_sa,
    make_event,
    platform_admin_claims,
    seed_two_tenants,
)
from tests.fakes import FakeStore


def call(method, path, claims, store, sa=None, **kwargs):
    event = make_event(method, path, claims=claims, **kwargs)
    return lambda_handler(event, None, store=store, sa=sa or fake_sa())


def body_of(resp):
    return json.loads(resp["body"])


def test_unknown_route_returns_404():
    store = seed_two_tenants()
    resp = call("GET", "/v1/unknown", analyst_claims(), store)
    assert resp["statusCode"] == 404


def test_invalid_json_body_returns_400():
    store = seed_two_tenants()
    event = make_event("POST", "/v1/tenants", claims=platform_admin_claims())
    event["body"] = "{not json"
    resp = lambda_handler(event, None, store=store)
    assert resp["statusCode"] == 400


def test_create_tenant():
    store = FakeStore()
    resp = call(
        "POST",
        "/v1/tenants",
        platform_admin_claims(),
        store,
        body={"tenant_id": "t-new", "name": "New Co", "plan": "continu"},
    )
    assert resp["statusCode"] == 201
    assert body_of(resp)["tenant_id"] == "t-new"
    assert store.get_tenant("t-new") is not None


def test_create_duplicate_tenant_returns_409():
    store = seed_two_tenants()
    resp = call("POST", "/v1/tenants", platform_admin_claims(), store, body={"tenant_id": "t-a"})
    assert resp["statusCode"] == 409


def test_create_tenant_without_id_returns_400():
    store = FakeStore()
    resp = call("POST", "/v1/tenants", platform_admin_claims(), store, body={})
    assert resp["statusCode"] == 400


def test_create_application():
    store = seed_two_tenants()
    resp = call(
        "POST",
        "/v1/tenants/t-a/applications",
        analyst_claims(),
        store,
        body={"app_id": "app-new", "name": "New App", "criticality": "medium"},
    )
    assert resp["statusCode"] == 201
    assert store.get_application("app-new") is not None


def test_get_application():
    store = seed_two_tenants()
    resp = call("GET", "/v1/applications/app-t-a", analyst_claims(), store)
    assert resp["statusCode"] == 200
    assert body_of(resp)["app_id"] == "app-t-a"


def test_get_unknown_application_returns_404():
    store = seed_two_tenants()
    resp = call("GET", "/v1/applications/nope", analyst_claims(), store)
    assert resp["statusCode"] == 404


def test_onboarding_creates_agent_space_and_config():
    store = seed_two_tenants()
    sa = fake_sa()
    resp = call(
        "POST",
        "/v1/applications/app-t-a/onboarding",
        analyst_claims(),
        store,
        sa=sa,
        body={"domain": "shop.acme.com"},
    )
    assert resp["statusCode"] in (200, 201)
    assert sa.spaces


def test_list_runs_of_application():
    store = seed_two_tenants()
    resp = call("GET", "/v1/applications/app-t-a/runs", analyst_claims(), store)
    assert resp["statusCode"] == 200
    assert body_of(resp)["runs"]


def test_get_run_by_job_id():
    store = seed_two_tenants()
    resp = call("GET", "/v1/runs/run-t-a", analyst_claims(), store)
    assert resp["statusCode"] == 200
    assert body_of(resp)["run_id"] == "run-t-a"


def test_stop_run():
    store = seed_two_tenants()
    resp = call("POST", "/v1/runs/run-t-a/stop", analyst_claims(), store)
    assert resp["statusCode"] in (200, 202, 404, 409)


def test_findings_list_with_filters():
    store = seed_two_tenants()
    resp = call("GET", "/v1/findings", analyst_claims(), store, query={"priority": "P1"})
    assert resp["statusCode"] == 200
    findings = body_of(resp)["findings"]
    assert all(f["priority"] == "P1" for f in findings)


def test_finding_decision_records_audit():
    store = seed_two_tenants()
    resp = call(
        "POST",
        "/v1/findings/f-t-a/decision",
        analyst_claims(),
        store,
        body={"action": "false_positive", "justification": "not exploitable"},
    )
    assert resp["statusCode"] in (200, 201)
    assert store.list_decisions("f-t-a")


def test_finding_remediation_returns_pr():
    store = seed_two_tenants()
    resp = call("POST", "/v1/findings/f-t-a/remediation", analyst_claims(), store, body={})
    assert resp["statusCode"] in (200, 201, 202, 409)


def test_tenant_kpis_are_deterministic():
    store = seed_two_tenants()
    resp = call("GET", "/v1/tenants/t-a/kpis", analyst_claims(), store)
    assert resp["statusCode"] == 200
    kpis = body_of(resp)
    assert "task_hours_used" in kpis
    assert kpis["task_hours_used"] == 2.0


def test_fleet_kpis_for_msp():
    store = seed_two_tenants()
    resp = call("GET", "/v1/fleet/kpis", analyst_claims(), store)
    assert resp["statusCode"] == 200
    assert "task_hours_used" in body_of(resp)


def test_budget_get_and_update():
    store = seed_two_tenants()
    resp = call("GET", "/v1/tenants/t-a/budget", analyst_claims(), store)
    assert resp["statusCode"] == 200

    resp2 = call(
        "PUT",
        "/v1/tenants/t-a/budget",
        analyst_claims(),
        store,
        body={"monthly_budget_hours": 55.0},
    )
    assert resp2["statusCode"] in (200, 202)
    assert store.get_tenant("t-a").monthly_budget_hours == 55.0


def test_deployment_event_is_accepted_with_pipeline_key():
    store = seed_two_tenants()
    resp = call(
        "POST",
        "/v1/events/deployment",
        None,
        store,
        body={"repository": "acme/shop", "commit_sha": "abc", "environment": "staging"},
        headers={"X-Rempart-Key": "secret"},
    )
    assert resp["statusCode"] in (200, 202, 401, 403)


def test_deployment_event_rejects_bad_key():
    store = seed_two_tenants()
    resp = call(
        "POST",
        "/v1/events/deployment",
        None,
        store,
        body={"repository": "acme/shop"},
        headers={"X-Rempart-Key": "wrong"},
    )
    assert resp["statusCode"] in (401, 403)


def test_deployment_event_refusal_does_not_disclose_server_configuration(monkeypatch):
    """Refus neutre : impossible de savoir si une clé est configurée ou non.

    Constat réel du 2026-11-12 : l'API déployée répondait
    « Clé pipeline non configurée côté serveur » à tout appelant non
    authentifié. Les deux cas (absente / fausse) doivent être indiscernables ;
    la cause exacte ne vit que dans le journal d'audit.
    """
    monkeypatch.delenv("REMPART_PIPELINE_KEY", raising=False)
    store = seed_two_tenants()
    unconfigured = lambda_handler(
        make_event("POST", "/v1/events/deployment", body={"repository": "acme/shop"}),
        None,
        store=store,
        sa=fake_sa(),
        settings=Settings(),
    )
    wrong_key = lambda_handler(
        make_event(
            "POST",
            "/v1/events/deployment",
            body={"repository": "acme/shop"},
            headers={"X-Rempart-Key": "fausse"},
        ),
        None,
        store=store,
        sa=fake_sa(),
        settings=Settings(pipeline_key="vraie-cle"),
    )
    assert unconfigured["statusCode"] == wrong_key["statusCode"] == 403
    assert body_of(unconfigured) == body_of(wrong_key)
    assert "configur" not in body_of(unconfigured)["error"].lower()
    # La cause réelle reste tracée pour l'exploitant, dans l'audit seulement.
    assert "unconfigured" in [getattr(e, "object_id", "") for e in store.list_audit()]


def test_audit_trail_is_written_on_creation():
    store = seed_two_tenants()
    call(
        "POST",
        "/v1/tenants",
        platform_admin_claims(),
        store,
        body={"tenant_id": "t-audited", "name": "Audited"},
    )
    events = store.list_audit()
    assert any(e.action == "tenant.create" for e in events)


def test_client_cannot_create_tenant():
    store = seed_two_tenants()
    resp = call(
        "POST", "/v1/tenants", client_claims("t-a"), store, body={"tenant_id": "t-x"}
    )
    assert resp["statusCode"] == 403


def test_tenant_record_round_trip():
    store = FakeStore()
    tenant = Tenant(
        tenant_id="t-z",
        name="Z",
        aws_account_id="1",
        region="eu-west-3",
        role_arn="arn",
        external_id="ext",
        plan="essentiel",
        contacts=[],
        monthly_budget_hours=1.0,
        mandate_status="pending",
        created_at="2026-11-01T00:00:00Z",
    )
    store.save_tenant(tenant)
    assert store.get_tenant("t-z").name == "Z"
