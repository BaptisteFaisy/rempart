"""Shared fixtures for the Rempart reports tests."""

from typing import Any

import pytest

from rempart.common.models import Application, Finding, Run, Tenant
from tests.fakes import FakeStore

PERIOD = "2026-10"
FROZEN_AT = "2026-11-02T00:00:00Z"  # first business day of November 2026


def make_tenant(tenant_id: str = "t-1", *, budget_hours: float = 40.0) -> Tenant:
    """Build a tenant with a monthly budget of task hours."""
    return Tenant(
        tenant_id=tenant_id,
        name=f"Client {tenant_id}",
        aws_account_id="123456789012",
        region="eu-west-3",
        role_arn="arn:aws:iam::123456789012:role/rempart",
        external_id="ext-1",
        plan="continu",
        contacts=[{"email": "cto@example.com"}],
        monthly_budget_hours=budget_hours,
        mandate_status="valid",
            free_tier_confirmed=True,
        created_at="2026-01-01T00:00:00Z",
    )


def make_app(
    app_id: str,
    tenant_id: str = "t-1",
    *,
    name: str | None = None,
    environment: str = "staging",
    criticality: str = "high",
    team: str = "Equipe Shop",
) -> Application:
    """Build an application of the contract."""
    return Application(
        app_id=app_id,
        tenant_id=tenant_id,
        name=name or app_id,
        criticality=criticality,
        internet_exposed=True,
        data_types=["personal"],
        environment=environment,
        agent_space_id=f"space-{app_id}",
        domains=[f"{app_id}.example.com"],
        repositories=[f"acme/{app_id}"],
        team=team,
        ticket_channel="github",
        context={},
        created_at="2026-01-01T00:00:00Z",
    )


def make_run(
    run_id: str,
    app_id: str,
    *,
    tenant_id: str = "t-1",
    trigger: str = "cicd",
    status: str = "completed",
    started_at: str = "2026-10-05T08:00:00Z",
    ended_at: str | None = "2026-10-05T09:30:00Z",
    duration_s: float | None = 5400.0,
    task_hours: float | None = 1.5,
    cost_usd: float | None = 75.0,
) -> Run:
    """Build a test run."""
    return Run(
        run_id=run_id,
        config_id=f"cfg-{app_id}",
        app_id=app_id,
        tenant_id=tenant_id,
        trigger=trigger,
        commit_from="abc123",
        commit_to="def456",
        scope_decision="full",
        status=status,
        started_at=started_at,
        ended_at=ended_at,
        duration_s=duration_s,
        task_hours=task_hours,
        cost_usd=cost_usd,
    )


def make_finding(
    finding_id: str,
    app_id: str,
    *,
    tenant_id: str = "t-1",
    run_id: str = "run-1",
    priority: str = "P2",
    status: str = "confirmed",
    created_at: str = "2026-10-05T09:00:00Z",
    updated_at: str | None = None,
    due_at: str | None = None,
    closed_at: str | None = None,
    title: str = "SQL injection",
    remediation_pr_url: str | None = None,
    ticket_url: str | None = None,
    closed_by_run_id: str | None = None,
) -> Finding:
    """Build a finding with all timestamps needed by the KPI computation."""
    return Finding(
        finding_id=finding_id,
        app_id=app_id,
        tenant_id=tenant_id,
        run_id=run_id,
        fingerprint=f"fp-{finding_id}",
        title=title,
        risk_type="injection",
        severity="High",
        confidence="High",
        priority=priority,
        status=status,
        due_at=due_at,
        ticket_url=ticket_url,
        remediation_pr_url=remediation_pr_url,
        evidence={"steps": ["..."]},
        cvss={"score": 8.1},
        created_at=created_at,
        updated_at=updated_at or closed_at or created_at,
        closed_at=closed_at,
        closed_by_run_id=closed_by_run_id,
    )


def _seed_primary(store: FakeStore) -> None:
    """Seed the reference dataset used by the report tests."""
    _seed_primary_entities(store)
    _seed_primary_runs_a(store)
    _seed_primary_runs_b(store)
    _seed_primary_runs_outside(store)
    _seed_primary_findings_a(store)
    _seed_primary_findings_b(store)


def _seed_primary_entities(store: FakeStore) -> None:
    """Seed the tenant and its two applications."""
    store.save_tenant(make_tenant("t-1", budget_hours=40.0))
    store.save_application(make_app("app-a", "t-1", name="ShopLite", environment="staging"))
    store.save_application(
        make_app(
            "app-b",
            "t-1",
            name="BookWorm",
            environment="production",
            criticality="medium",
            team="Equipe Book",
        )
    )


def _seed_primary_runs_a(store: FakeStore) -> None:
    """Seed the first two runs of the period."""
    store.save_run(
        make_run(
            "run-1",
            "app-a",
            trigger="cicd",
            status="blocked",
            started_at="2026-10-05T08:00:00Z",
            ended_at="2026-10-05T09:30:00Z",
            duration_s=5400.0,
            task_hours=1.5,
            cost_usd=75.0,
        )
    )
    store.save_run(
        make_run(
            "run-2",
            "app-a",
            trigger="cicd",
            status="completed",
            started_at="2026-10-07T08:00:00Z",
            ended_at="2026-10-07T10:00:00Z",
            duration_s=7200.0,
            task_hours=2.0,
            cost_usd=100.0,
        )
    )


def _seed_primary_runs_b(store: FakeStore) -> None:
    """Seed the last two runs of the period."""
    store.save_run(
        make_run(
            "run-3",
            "app-b",
            trigger="schedule",
            status="completed",
            started_at="2026-10-12T08:00:00Z",
            ended_at="2026-10-12T11:00:00Z",
            duration_s=10800.0,
            task_hours=3.0,
            cost_usd=150.0,
        )
    )
    store.save_run(
        make_run(
            "run-4",
            "app-a",
            trigger="retest",
            status="completed",
            started_at="2026-10-20T08:00:00Z",
            ended_at="2026-10-20T09:00:00Z",
            duration_s=3600.0,
            task_hours=1.0,
            cost_usd=50.0,
        )
    )


def _seed_primary_runs_outside(store: FakeStore) -> None:
    """Seed a run outside the period (never counted)."""
    store.save_run(
        make_run(
            "run-5",
            "app-b",
            trigger="manual",
            status="completed",
            started_at="2026-11-03T08:00:00Z",
            ended_at="2026-11-03T09:00:00Z",
            duration_s=3600.0,
            task_hours=9.0,
            cost_usd=450.0,
        )
    )


def _seed_primary_findings_a(store: FakeStore) -> None:
    """Seed the first pair of findings."""
    store.save_finding(
        make_finding(
            "f-1",
            "app-a",
            run_id="run-1",
            priority="P1",
            status="confirmed",
            created_at="2026-10-05T09:00:00Z",
            due_at="2026-10-12T09:00:00Z",
            title="IDOR on orders",
        )
    )
    store.save_finding(
        make_finding(
            "f-2",
            "app-a",
            run_id="run-2",
            priority="P2",
            status="closed",
            created_at="2026-10-07T10:00:00Z",
            due_at="2026-11-06T10:00:00Z",
            closed_at="2026-10-11T10:00:00Z",
            closed_by_run_id="run-4",
            remediation_pr_url="https://github.com/acme/app-a/pull/12",
            title="SQL injection on search",
        )
    )


def _seed_primary_findings_b(store: FakeStore) -> None:
    """Seed the remaining findings."""
    store.save_finding(
        make_finding(
            "f-3",
            "app-b",
            run_id="run-3",
            priority="P3",
            status="closed",
            created_at="2026-10-12T10:00:00Z",
            due_at="2026-10-13T10:00:00Z",
            closed_at="2026-10-24T10:00:00Z",
            closed_by_run_id="run-4",
            title="Missing security header",
        )
    )
    store.save_finding(
        make_finding(
            "f-5",
            "app-a",
            run_id="run-4",
            priority="P2",
            status="reopened",
            created_at="2026-09-20T10:00:00Z",
            updated_at="2026-10-25T10:00:00Z",
            due_at="2026-10-01T10:00:00Z",
            closed_at="2026-10-02T10:00:00Z",
            title="XSS in profile",
        )
    )
    store.save_finding(
        make_finding(
            "f-4",
            "app-b",
            run_id="run-5",
            priority="P4",
            status="new",
            created_at="2026-11-03T10:00:00Z",
            title="Verbose error page",
        )
    )


def _seed_other_tenant(store: FakeStore) -> None:
    """Seed a second tenant to check the tenant isolation of the KPIs."""
    store.save_tenant(make_tenant("t-2", budget_hours=10.0))
    store.save_application(make_app("app-z", "t-2", name="Autre"))
    store.save_run(
        make_run(
            "run-z",
            "app-z",
            tenant_id="t-2",
            trigger="cicd",
            status="completed",
            started_at="2026-10-05T08:00:00Z",
            ended_at="2026-10-05T10:00:00Z",
            duration_s=7200.0,
            task_hours=5.0,
            cost_usd=250.0,
        )
    )
    store.save_finding(
        make_finding(
            "f-z",
            "app-z",
            tenant_id="t-2",
            run_id="run-z",
            priority="P1",
            status="confirmed",
            created_at="2026-10-05T09:00:00Z",
            title="Faille autre client",
        )
    )


@pytest.fixture
def store() -> FakeStore:
    """Return a seeded fake store with two tenants."""
    fake = FakeStore()
    _seed_primary(fake)
    _seed_other_tenant(fake)
    return fake


@pytest.fixture
def kpis(store: FakeStore) -> dict[str, Any]:
    """Return the deterministic KPIs of the reference dataset."""
    from rempart.reports.metrics import compute_kpis

    return compute_kpis(store, tenant_id="t-1", period=PERIOD)
