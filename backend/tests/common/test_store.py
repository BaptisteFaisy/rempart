"""Tests verifying Store, FakeStore, and FakeDdbResource."""

import inspect

import pytest

from rempart.common.models import (
    Application,
    BudgetState,
    Decision,
    Finding,
    Report,
    Run,
    Tenant,
    TestConfig,
)
from rempart.common.store import Store
from tests.fakes import FakeDdbResource, FakeStore


def test_interface_conformity():
    """Verify that FakeStore exposes the exact same public methods as Store."""
    store_methods = {
        name: inspect.signature(getattr(Store, name))
        for name in dir(Store)
        if not name.startswith("_") and callable(getattr(Store, name))
    }
    fake_methods = {
        name: inspect.signature(getattr(FakeStore, name))
        for name in dir(FakeStore)
        if not name.startswith("_") and callable(getattr(FakeStore, name))
    }

    assert store_methods.keys() == fake_methods.keys()
    for name, sig in store_methods.items():
        assert list(sig.parameters.keys()) == list(fake_methods[name].parameters.keys())


@pytest.fixture(params=["fake_store", "store_with_fake_ddb"])
def store_instance(request):
    if request.param == "fake_store":
        return FakeStore()
    ddb = FakeDdbResource()
    return Store(ddb_resource=ddb, table_prefix="test-")


# --------------------------------------------------------------------------- #
# Object builders: one per model, reused by every CRUD test below.
# --------------------------------------------------------------------------- #
def _tenant() -> Tenant:
    return Tenant(
        tenant_id="t-1",
        name="Acme",
        aws_account_id="123456789012",
        region="eu-west-3",
        role_arn="arn:aws:iam::123:role/x",
        external_id="ext-1",
        plan="continu",
        contacts=[{"email": "ops@acme.com"}],
        monthly_budget_hours=30.0,
        mandate_status="valid",
        created_at="2026-11-10T09:00:00Z",
    )


def _application() -> Application:
    return Application(
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
        ticket_channel="#shop",
        context={},
        created_at="2026-11-10T09:00:00Z",
    )


def _test_config() -> TestConfig:
    return TestConfig("cfg-1", "app-1", "sa-1", "delivery", {}, ["IDOR"], "High", None)


def _run() -> Run:
    return Run(
        "run-1",
        "cfg-1",
        "app-1",
        "t-1",
        "cicd",
        "c1",
        "c2",
        "diff",
        "running",
        "2026-11-10T09:00:00Z",
        None,
        None,
        1.5,
        75.0,
    )


def _finding() -> Finding:
    return Finding(
        finding_id="f-1",
        app_id="app-1",
        tenant_id="t-1",
        run_id="run-1",
        fingerprint="fp12345678901234",
        title="IDOR",
        risk_type="IDOR",
        severity="High",
        confidence="High",
        priority="P1",
        status="new",
        due_at="2026-11-17T09:00:00Z",
        ticket_url=None,
        remediation_pr_url=None,
        evidence={"param": "id"},
        cvss={"score": 8.5},
        created_at="2026-11-10T09:00:00Z",
        updated_at="2026-11-10T09:00:00Z",
        closed_at=None,
        closed_by_run_id=None,
    )


def _decision() -> Decision:
    return Decision(
        "d-1", "f-1", "human", "analyst", "confirmed", "valid finding", "2026-11-10T10:00:00Z"
    )


def _report() -> Report:
    return Report(
        "rep-1", "t-1", "2026-11", "s3://reports/rep-1.pdf", {"kpi": 10}, "2026-11-10T10:00:00Z"
    )


def _budget() -> BudgetState:
    return BudgetState("t-1", "2026-11", 15.0, [50], False)


# --------------------------------------------------------------------------- #
# CRUD lifecycle, split per family of objects (same coverage as before).
# --------------------------------------------------------------------------- #
def test_store_tenant_crud(store_instance):
    s = store_instance

    s.save_tenant(_tenant())

    assert s.get_tenant("t-1").name == "Acme"
    assert len(s.list_tenants()) == 1


def test_store_application_config_run_crud(store_instance):
    s = store_instance
    s.save_tenant(_tenant())

    s.save_application(_application())

    assert s.get_application("app-1").criticality == "high"
    assert len(s.list_applications("t-1")) == 1
    assert len(s.list_applications("other")) == 0

    s.save_config(_test_config())

    assert len(s.list_configs("app-1")) == 1

    s.save_run(_run())

    assert s.get_run("run-1").status == "running"
    assert len(s.list_runs(app_id="app-1")) == 1


def test_store_finding_decision_report_crud(store_instance):
    s = store_instance

    s.save_finding(_finding())

    assert s.get_finding("f-1").title == "IDOR"
    assert s.find_by_fingerprint("app-1", "fp12345678901234").finding_id == "f-1"
    assert len(s.list_findings(tenant_id="t-1", priority="P1")) == 1

    s.save_decision(_decision())

    assert len(s.list_decisions("f-1")) == 1

    s.save_report(_report())

    assert s.get_report("rep-1").period == "2026-11"
    assert len(s.list_reports("t-1")) == 1


def test_store_budget_and_audit_crud(store_instance):
    s = store_instance

    s.save_budget(_budget())
    loaded_b = s.get_budget("t-1", "2026-11")

    assert loaded_b.hours_used == 15.0

    evt = s.append_audit("analyst-1", "confirm_finding", "finding", "f-1")

    assert evt.object_id == "f-1"
    assert len(s.list_audit(object_type="finding")) == 1
