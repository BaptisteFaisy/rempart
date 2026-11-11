"""Tests for the deterministic KPI computation (ENF-IA-01) and the month freezing."""

from datetime import datetime, timezone

from rempart.reports.metrics import (
    compute_kpis,
    first_business_day,
    freeze_date,
    freeze_month,
    period_bounds,
)
from tests.reports.conftest import PERIOD, make_app, make_finding, make_run

CONTRACT_KEYS = (
    "delivery_to_result_hours",
    "critical_blocked_before_prod",
    "mean_time_to_fix_days_by_priority",
    "sla_compliance",
    "coverage",
    "reopen_rate",
    "findings_open_by_priority",
    "findings_closed",
    "tests_total",
    "tests_blocked",
    "task_hours_used",
    "cost_usd",
)


def test_period_bounds_are_half_open_month():
    start, end = period_bounds("2026-10")
    assert start == datetime(2026, 10, 1, tzinfo=timezone.utc)
    assert end == datetime(2026, 11, 1, tzinfo=timezone.utc)
    start, end = period_bounds("2026-12")
    assert end == datetime(2027, 1, 1, tzinfo=timezone.utc)


def test_first_business_day_skips_weekend():
    # 1st of November 2026 is a Sunday -> first business day is Monday 2.
    assert first_business_day(2026, 11) == datetime(2026, 11, 2, tzinfo=timezone.utc)
    # 1st of June 2026 is a Monday.
    assert first_business_day(2026, 6) == datetime(2026, 6, 1, tzinfo=timezone.utc)


def test_freeze_date_is_first_business_day_of_next_month():
    assert freeze_date("2026-10") == datetime(2026, 11, 2, tzinfo=timezone.utc)
    assert freeze_date("2026-12") == datetime(2027, 1, 1, tzinfo=timezone.utc)


def test_compute_kpis_exposes_every_contract_key(kpis):
    for key in CONTRACT_KEYS:
        assert key in kpis
    assert kpis["period"] == PERIOD
    assert kpis["tenant_id"] == "t-1"


def test_delivery_to_result_hours_is_the_median_of_cicd_runs(kpis):
    # cicd runs of the period: 1.5 h (blocked) and 2.0 h (completed) -> median 1.75
    assert kpis["delivery_to_result_hours"] == 1.75


def test_critical_blocked_before_prod_ratio(kpis):
    # f-1 (P1) and f-2 (P2) were both detected on the staging application.
    assert kpis["critical_blocked_before_prod"] == 1.0


def test_mean_time_to_fix_days_by_priority(kpis):
    mttf = kpis["mean_time_to_fix_days_by_priority"]
    assert mttf["P1"] == 0.0
    assert mttf["P2"] == 8.0  # (4 days + 12 days) / 2
    assert mttf["P3"] == 12.0
    assert mttf["P4"] == 0.0
    assert set(mttf) == {"P1", "P2", "P3", "P4"}


def test_sla_compliance_counts_closures_before_due_date(kpis):
    # f-2 on time, f-3 and f-5 late -> 1/3
    assert kpis["sla_compliance"] == round(1 / 3, 4)


def test_coverage_ratio(kpis):
    # both applications of the contract were tested during the period
    assert kpis["coverage"] == 1.0


def test_reopen_rate(kpis):
    # 1 reopened finding (f-5) over 3 findings closed in the period
    assert kpis["reopen_rate"] == round(1 / 3, 4)


def test_open_findings_and_closed_count(kpis):
    assert kpis["findings_open_by_priority"] == {"P1": 1, "P2": 1, "P3": 0, "P4": 1}
    assert kpis["findings_closed"] == 3


def test_tests_and_budget_totals_ignore_other_periods(kpis):
    assert kpis["tests_total"] == 4  # run-5 belongs to November
    assert kpis["tests_blocked"] == 1
    assert kpis["task_hours_used"] == 7.5
    assert kpis["cost_usd"] == 375.0


def test_risk_level_is_critical_when_a_p1_is_open(kpis):
    assert kpis["risk_level"] == "critical"


def test_compute_kpis_is_tenant_scoped(store):
    other = compute_kpis(store, tenant_id="t-2", period=PERIOD)
    assert other["findings_open_by_priority"]["P1"] == 1
    assert other["tests_total"] == 1
    assert other["task_hours_used"] == 5.0
    # the P1 of the other tenant never leaks into t-1
    assert compute_kpis(store, tenant_id="t-1", period=PERIOD)["findings_open_by_priority"][
        "P1"
    ] == 1


def test_compute_kpis_is_deterministic(store):
    first = compute_kpis(store, tenant_id="t-1", period=PERIOD)
    second = compute_kpis(store, tenant_id="t-1", period=PERIOD)
    assert first == second


def test_compute_kpis_without_data_is_safe(store):
    empty = compute_kpis(store, tenant_id="t-1", period="2026-01")
    assert empty["tests_total"] == 0
    assert empty["findings_closed"] == 0
    assert empty["coverage"] == 0.0
    assert empty["sla_compliance"] == 1.0
    assert empty["delivery_to_result_hours"] == 0.0


def test_freeze_month_snapshot_contains_the_deterministic_sections(store):
    frozen = freeze_month(store, "t-1", PERIOD)
    assert frozen["frozen"] is True
    assert frozen["frozen_at"] == "2026-11-02T00:00:00Z"
    assert frozen["period_start"] == "2026-10-01T00:00:00Z"
    assert frozen["period_end"] == "2026-11-01T00:00:00Z"
    assert frozen["tests_detail"]["tests_total"] == 4
    assert frozen["tests_detail"]["tests_by_type"] == {"cicd": 2, "schedule": 1, "retest": 1}
    assert frozen["budget_detail"]["task_hours_used"] == 7.5
    assert frozen["budget_detail"]["monthly_budget_hours"] == 40.0
    assert frozen["budget_detail"]["remaining_task_hours"] == 32.5
    assert frozen["findings_new_by_priority"] == {"P1": 1, "P2": 1, "P3": 1, "P4": 0}


def test_freeze_month_lists_closed_and_overdue_findings(store):
    frozen = freeze_month(store, "t-1", PERIOD)
    closed = {item["finding_id"] for item in frozen["closed_findings"]}
    assert closed == {"f-2", "f-3", "f-5"}
    proof = next(i for i in frozen["closed_findings"] if i["finding_id"] == "f-2")
    assert proof["proof"] == "https://github.com/acme/app-a/pull/12"

    overdue = {item["finding_id"] for item in frozen["overdue_findings"]}
    assert overdue == {"f-1", "f-5"}
    late = next(i for i in frozen["overdue_findings"] if i["finding_id"] == "f-1")
    assert late["owner"] == "Equipe Shop"
    assert late["new_target_date"] == "2026-10-12T09:00:00Z"


def test_freeze_month_recommendations_are_deterministic(store):
    frozen = freeze_month(store, "t-1", PERIOD)
    recs = frozen["recommendations"]
    assert len(recs) == 3
    assert any("P1" in rec for rec in recs)
    assert any("SLA" in rec for rec in recs)


def test_freeze_month_applications_detail(store):
    frozen = freeze_month(store, "t-1", PERIOD)
    apps = {item["app_id"]: item for item in frozen["applications_detail"]}
    assert set(apps) == {"app-a", "app-b"}
    assert apps["app-a"]["tests"] == 3
    assert apps["app-a"]["open_by_priority"] == {"P1": 1, "P2": 1, "P3": 0, "P4": 0}
    assert apps["app-b"]["environment"] == "production"


def test_freeze_month_ignores_the_other_tenant(store):
    frozen = freeze_month(store, "t-1", PERIOD)
    assert all("Autre" not in item["title"] for item in frozen["closed_findings"])
    assert "f-z" not in {item["finding_id"] for item in frozen["overdue_findings"]}


def test_kpis_are_computed_from_timestamps_only(store):
    """A finding without any timestamp never contributes to a KPI."""
    store.save_finding(make_finding("f-x", "app-a", priority="P1", status="confirmed"))
    kpis = compute_kpis(store, tenant_id="t-1", period=PERIOD)
    assert kpis["findings_open_by_priority"]["P1"] == 2  # snapshot only, not a period metric


def test_new_finding_in_period_increases_open_count(store):
    store.save_run(
        make_run(
            "run-6",
            "app-a",
            trigger="manual",
            status="completed",
            started_at="2026-10-25T08:00:00Z",
            ended_at="2026-10-25T08:30:00Z",
            duration_s=1800.0,
            task_hours=0.5,
            cost_usd=25.0,
        )
    )
    store.save_finding(
        make_finding(
            "f-6",
            "app-a",
            run_id="run-6",
            priority="P1",
            status="confirmed",
            created_at="2026-10-25T08:10:00Z",
            due_at="2026-11-01T08:10:00Z",
        )
    )
    kpis = compute_kpis(store, tenant_id="t-1", period=PERIOD)
    assert kpis["tests_total"] == 5
    assert kpis["task_hours_used"] == 8.0
    assert kpis["findings_new_by_priority"]["P1"] == 2
    assert kpis["coverage"] == 1.0


def test_application_without_run_is_not_covered(store):
    store.save_application(make_app("app-c", "t-1", name="Non teste"))
    kpis = compute_kpis(store, tenant_id="t-1", period=PERIOD)
    assert kpis["coverage"] == round(2 / 3, 4)
