"""Shared helpers for the API tests."""

import json
from typing import Any

from rempart.common.models import Application, Finding, Run, Tenant
from tests.fakes import FakeSecurityAgentClient, FakeStore


def make_event(
    method: str,
    path: str,
    *,
    claims: dict[str, Any] | None = None,
    query: dict[str, str] | None = None,
    body: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Build an API Gateway HTTP API v2 event."""
    event: dict[str, Any] = {
        "rawPath": path,
        "requestContext": {"http": {"method": method}},
        "headers": headers or {},
    }
    if query:
        event["queryStringParameters"] = query
    if body is not None:
        event["body"] = json.dumps(body)
    if claims is not None:
        event["requestContext"]["authorizer"] = {"jwt": {"claims": claims}}
    return event


def platform_admin_claims(tenant_id: str | None = None) -> dict[str, Any]:
    claims: dict[str, Any] = {
        "sub": "user-admin",
        "cognito:groups": ["platform_admin"],
    }
    if tenant_id:
        claims["custom:tenant_id"] = tenant_id
    return claims


def analyst_claims() -> dict[str, Any]:
    return {"sub": "user-analyst", "cognito:groups": ["analyst"]}


def client_claims(tenant_id: str, group: str = "client_security") -> dict[str, Any]:
    return {
        "sub": "user-client",
        "cognito:groups": [group],
        "custom:tenant_id": tenant_id,
    }


def demo_claims() -> dict[str, Any]:
    return {"sub": "user-demo", "cognito:groups": ["demo"], "custom:tenant_id": "demo"}


def _seed_tenant(tenant_id: str, name: str) -> Tenant:
    return Tenant(
        tenant_id=tenant_id,
        name=name,
        aws_account_id="123456789012",
        region="eu-west-3",
        role_arn="arn:aws:iam::123456789012:role/rempart",
        external_id=f"ext-{tenant_id}",
        plan="continu",
        contacts=[{"name": "Ops", "email": "ops@example.com"}],
        monthly_budget_hours=40.0,
        mandate_status="valid",
            free_tier_confirmed=True,
        created_at="2026-11-01T00:00:00Z",
    )


def _seed_application(tenant_id: str, name: str) -> Application:
    return Application(
        app_id=f"app-{tenant_id}",
        tenant_id=tenant_id,
        name=f"{name} Shop",
        criticality="high",
        internet_exposed=True,
        data_types=["personal"],
        environment="staging",
        agent_space_id=f"space-{tenant_id}",
        domains=[f"{tenant_id}.example.com"],
        repositories=[f"{tenant_id}/shop"],
        team="Core",
        ticket_channel="github",
        context={},
        created_at="2026-11-01T00:00:00Z",
    )


def _seed_run(tenant_id: str) -> Run:
    return Run(
        run_id=f"run-{tenant_id}",
        config_id="cfg-1",
        app_id=f"app-{tenant_id}",
        tenant_id=tenant_id,
        trigger="cicd",
        commit_from="aaa",
        commit_to="bbb",
        scope_decision="full",
        status="completed",
        started_at="2026-11-01T10:00:00Z",
        ended_at="2026-11-01T11:00:00Z",
        duration_s=3600.0,
        task_hours=2.0,
        cost_usd=100.0,
    )


def _seed_finding(tenant_id: str) -> Finding:
    return Finding(
        finding_id=f"f-{tenant_id}",
        app_id=f"app-{tenant_id}",
        tenant_id=tenant_id,
        run_id=f"run-{tenant_id}",
        fingerprint=f"fp-{tenant_id}",
        title="IDOR on orders",
        risk_type="IDOR",
        severity="Critical",
        confidence="High",
        priority="P1",
        status="confirmed",
        due_at="2026-11-08T10:00:00Z",
        ticket_url=None,
        remediation_pr_url=None,
        evidence={"description": "detail"},
        cvss={},
        created_at="2026-11-01T11:00:00Z",
        updated_at="2026-11-01T11:00:00Z",
        closed_at=None,
        closed_by_run_id=None,
    )


def seed_two_tenants() -> FakeStore:
    """Seed two tenants with one application, run, and finding each."""
    store = FakeStore()
    for tenant_id, name in (("t-a", "Acme"), ("t-b", "Globex")):
        store.save_tenant(_seed_tenant(tenant_id, name))
        store.save_application(_seed_application(tenant_id, name))
        store.save_run(_seed_run(tenant_id))
        store.save_finding(_seed_finding(tenant_id))
    return store


def fake_sa() -> FakeSecurityAgentClient:
    return FakeSecurityAgentClient()
