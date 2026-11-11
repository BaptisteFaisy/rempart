"""Tests for models dataclass serialization and constants."""

from rempart.common.models import (
    CONFIDENCES,
    FINDING_STATUSES,
    PLANS,
    PRIORITIES,
    RUN_STATUSES,
    SEVERITIES,
    TRIGGERS,
    Application,
    AuditEvent,
    BudgetState,
    Decision,
    Finding,
    Report,
    Run,
    Tenant,
    TestConfig,
)


def test_model_constants():
    assert "essentiel" in PLANS
    assert "Critical" in SEVERITIES
    assert "High" in CONFIDENCES
    assert "P1" in PRIORITIES
    assert "confirmed" in FINDING_STATUSES
    assert "running" in RUN_STATUSES
    assert "cicd" in TRIGGERS


def test_tenant_serialization():
    t = Tenant(
        tenant_id="t-1",
        name="Acme",
        aws_account_id="123456789012",
        region="eu-west-3",
        role_arn="arn:aws:iam::123456789012:role/Rempart",
        external_id="ext-123",
        plan="continu",
        contacts=[{"name": "Alice", "email": "a@acme.com"}],
        monthly_budget_hours=40.0,
        mandate_status="valid",
        created_at="2026-11-10T10:00:00Z",
    )
    item = t.to_item()
    assert item["tenant_id"] == "t-1"
    assert item["contacts"][0]["name"] == "Alice"
    loaded = Tenant.from_item(item)
    assert loaded == t


def test_application_serialization():
    app = Application(
        app_id="app-1",
        tenant_id="t-1",
        name="ShopLite",
        criticality="high",
        internet_exposed=True,
        data_types=["personal", "payment"],
        environment="staging",
        agent_space_id="space-1",
        domains=["shop.example.com"],
        repositories=["owner/repo"],
        team="Security",
        ticket_channel="#sec",
        context={"framework": "Flask"},
        created_at="2026-11-10T10:00:00Z",
    )
    item = app.to_item()
    assert item["app_id"] == "app-1"
    assert Application.from_item(item) == app


def test_test_config_serialization():
    c = TestConfig(
        config_id="cfg-1",
        app_id="app-1",
        sa_pentest_id="sa-pt-1",
        kind="delivery",
        scope={"paths": ["/api/*"]},
        risk_types=["IDOR", "SQLi"],
        blocking_threshold="High",
        schedule=None,
    )
    assert TestConfig.from_item(c.to_item()) == c


def test_run_serialization():
    r = Run(
        run_id="run-1",
        config_id="cfg-1",
        app_id="app-1",
        tenant_id="t-1",
        trigger="cicd",
        commit_from="abc",
        commit_to="def",
        scope_decision="diff",
        status="completed",
        started_at="2026-11-10T10:00:00Z",
        ended_at="2026-11-10T11:00:00Z",
        duration_s=3600.0,
        task_hours=1.0,
        cost_usd=50.0,
    )
    assert Run.from_item(r.to_item()) == r


def test_finding_serialization():
    f = Finding(
        finding_id="f-1",
        app_id="app-1",
        tenant_id="t-1",
        run_id="run-1",
        fingerprint="fp12345678901234",
        title="IDOR in order lookup",
        risk_type="IDOR",
        severity="High",
        confidence="High",
        priority="P1",
        status="new",
        due_at="2026-11-17T10:00:00Z",
        ticket_url=None,
        remediation_pr_url=None,
        evidence={"request": "GET /orders/2"},
        cvss={"score": 8.0},
        created_at="2026-11-10T10:00:00Z",
        updated_at="2026-11-10T10:00:00Z",
        closed_at=None,
        closed_by_run_id=None,
    )
    assert Finding.from_item(f.to_item()) == f


def test_decision_report_budget_audit_serialization():
    d = Decision(
        "d-1", "f-1", "agent", "rempart-triage", "confirmed", "rule", "2026-11-10T10:00:00Z"
    )
    assert Decision.from_item(d.to_item()) == d

    rep = Report("r-1", "t-1", "2026-11", "reports/r-1.pdf", {"kpi": 1}, "2026-11-10T10:00:00Z")
    assert Report.from_item(rep.to_item()) == rep

    b = BudgetState("t-1", "2026-11", 12.5, [50], False)
    assert BudgetState.from_item(b.to_item()) == b

    a = AuditEvent("a-1", "user-1", "login", "session", "s-1", "ok", "2026-11-10T10:00:00Z")
    assert AuditEvent.from_item(a.to_item()) == a
