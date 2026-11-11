"""Tests for deterministic metrics and monthly report generation."""

from rempart.common.models import Application, Finding, Run, Tenant
from rempart.reports.metrics import compute_kpis, freeze_month
from rempart.reports.monthly import build_monthly_report
from tests.fakes import FakeModelClient, FakeS3, FakeStore


def _seed_store():
    store = FakeStore()
    t = Tenant(
        tenant_id="t-1",
        name="Acme Corp",
        aws_account_id="123456789012",
        region="eu-west-3",
        role_arn="arn:aws:iam::123456789012:role/rempart",
        external_id="ext-123",
        plan="continu",
        contacts=[{"name": "Alice", "email": "alice@acme.com"}],
        monthly_budget_hours=40.0,
        mandate_status="valid",
        created_at="2026-10-01T00:00:00Z",
    )
    store.save_tenant(t)

    app = Application(
        app_id="app-1",
        tenant_id="t-1",
        name="ShopLite",
        criticality="high",
        internet_exposed=True,
        data_types=["personal"],
        environment="staging",
        agent_space_id="space-1",
        domains=["shop.acme.com"],
        repositories=["acme/shop"],
        team="Core",
        ticket_channel="github",
        context={},
        created_at="2026-10-01T00:00:00Z",
    )
    store.save_application(app)

    r1 = Run(
        run_id="run-1",
        config_id="cfg-1",
        app_id="app-1",
        tenant_id="t-1",
        trigger="cicd",
        commit_from="c1",
        commit_to="c2",
        scope_decision="full",
        status="completed",
        started_at="2026-11-01T10:00:00Z",
        ended_at="2026-11-01T11:00:00Z",
        duration_s=3600.0,
        task_hours=1.5,
        cost_usd=75.0,
    )
    store.save_run(r1)

    f1 = Finding(
        finding_id="f-1",
        app_id="app-1",
        tenant_id="t-1",
        run_id="run-1",
        fingerprint="fp1",
        title="IDOR on orders",
        risk_type="IDOR",
        severity="Critical",
        confidence="High",
        priority="P1",
        status="closed",
        due_at="2026-11-08T10:00:00Z",
        ticket_url="https://github.com/acme/shop/issues/1",
        remediation_pr_url=None,
        evidence={},
        cvss={},
        created_at="2026-11-01T11:00:00Z",
        updated_at="2026-11-03T11:00:00Z",
        closed_at="2026-11-03T11:00:00Z",
        closed_by_run_id="run-2",
    )
    store.save_finding(f1)
    return store


def test_compute_kpis():
    store = _seed_store()
    kpis = compute_kpis(store, tenant_id="t-1", period="2026-11")
    assert "delivery_to_result_hours" in kpis
    assert "critical_blocked_before_prod" in kpis
    assert "sla_compliance" in kpis
    assert kpis["tests_total"] >= 1
    assert kpis["task_hours_used"] == 1.5
    assert kpis["cost_usd"] == 75.0


def test_freeze_month():
    store = _seed_store()
    frozen = freeze_month(store, tenant_id="t-1", period="2026-11")
    assert frozen["period"] == "2026-11"
    assert frozen["task_hours_used"] == 1.5
    assert frozen["frozen"] is True


def test_build_monthly_report():
    store = _seed_store()
    model = FakeModelClient(canned_response="Executive summary: all clear, low risk.")
    s3 = FakeS3()
    report = build_monthly_report(
        store=store, tenant_id="t-1", period="2026-11", model_client=model, s3=s3
    )
    assert report.report_id.startswith("rep-")
    assert report.period == "2026-11"
    assert report.s3_key is not None
    assert len(s3.objects) >= 1
