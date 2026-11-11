"""Tests for the CI/CD discovery pass (EF-ORC-01)."""

from rempart.common.models import Application, Tenant, TestConfig
from rempart.common.timeutil import iso, utcnow
from rempart.orchestrator.discovery import discover_cicd_runs
from rempart.orchestrator.tasks import Deps
from tests.fakes import FakeSecurityAgentClient, FakeStore


def _seed(store):
    store.save_tenant(
        Tenant(
            tenant_id="t-1",
            name="Acme",
            aws_account_id="123456789012",
            region="eu-west-3",
            role_arn="arn:aws:iam::123456789012:role/rempart",
            external_id="ext",
            plan="continu",
            contacts=[],
            monthly_budget_hours=10.0,
            mandate_status="valid",
            free_tier_confirmed=True,
            created_at="2026-11-01T00:00:00Z",
        )
    )
    store.save_application(
        Application(
            app_id="app-1",
            tenant_id="t-1",
            name="ShopLite",
            criticality="high",
            internet_exposed=True,
            data_types=[],
            environment="staging",
            agent_space_id="space-1",
            domains=["shop.acme.com"],
            repositories=["acme/shop"],
            team="Core",
            ticket_channel="github",
            context={},
            created_at="2026-11-01T00:00:00Z",
        )
    )
    store.save_config(
        TestConfig(
            config_id="cfg-delivery",
            app_id="app-1",
            sa_pentest_id="pt-delivery",
            kind="delivery",
            scope={"paths": ["/orders"]},
            risk_types=["IDOR"],
            blocking_threshold="High",
            schedule=None,
        )
    )
    return store


def test_discovery_creates_run_for_recent_job():
    store = _seed(FakeStore())
    sa = FakeSecurityAgentClient()
    now = iso(utcnow())
    sa.pentests["pt-delivery"] = {
        "pentestId": "pt-delivery", "agentSpaceId": "space-1", "title": "Livraison"
    }
    sa.jobs["job-cicd"] = {
        "jobId": "job-cicd",
        "pentestId": "pt-delivery",
        "status": "COMPLETED",
        "startedAt": now,
    }
    deps = Deps(store=store, sa=sa)

    runs = discover_cicd_runs(deps, since_minutes=5)
    assert len(runs) == 1
    assert runs[0].run_id == "job-cicd"
    assert runs[0].trigger == "cicd"
    assert store.get_run("job-cicd") is not None


def test_discovery_is_idempotent():
    store = _seed(FakeStore())
    sa = FakeSecurityAgentClient()
    sa.pentests["pt-delivery"] = {
        "pentestId": "pt-delivery", "agentSpaceId": "space-1", "title": "Livraison"
    }
    sa.jobs["job-cicd"] = {
        "pentestJobId": "job-cicd",
        "pentestId": "pt-delivery",
        "agentSpaceId": "space-1",
        "status": "COMPLETED",
        "startedAt": iso(utcnow()),
    }
    deps = Deps(store=store, sa=sa)

    first = discover_cicd_runs(deps, since_minutes=5)
    second = discover_cicd_runs(deps, since_minutes=5)
    assert len(first) == 1
    assert second == []


def test_discovery_ignores_old_jobs():
    store = _seed(FakeStore())
    sa = FakeSecurityAgentClient()
    sa.pentests["pt-delivery"] = {
        "pentestId": "pt-delivery", "agentSpaceId": "space-1", "title": "Livraison"
    }
    sa.jobs["job-old"] = {
        "pentestJobId": "job-old",
        "pentestId": "pt-delivery",
        "agentSpaceId": "space-1",
        "status": "COMPLETED",
        "startedAt": "2020-01-01T00:00:00Z",
    }
    deps = Deps(store=store, sa=sa)

    assert discover_cicd_runs(deps, since_minutes=5) == []


def test_discovery_ignores_non_delivery_configs():
    store = _seed(FakeStore())
    store.save_config(
        TestConfig(
            config_id="cfg-full",
            app_id="app-1",
            sa_pentest_id="pt-full",
            kind="full",
            scope={},
            risk_types=[],
            blocking_threshold="Critical",
            schedule="cron(0 6 1 * ? *)",
        )
    )
    sa = FakeSecurityAgentClient()
    deps = Deps(store=store, sa=sa)
    assert discover_cicd_runs(deps, since_minutes=5) == []
