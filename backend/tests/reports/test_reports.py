"""Tests for deterministic metrics and monthly report generation.

The reference dataset lives in ``tests/reports/conftest.py`` (builders and
``_seed_primary``); this module only exercises the public report API.
"""

from rempart.reports.metrics import compute_kpis, freeze_month
from rempart.reports.monthly import build_monthly_report
from tests.fakes import FakeModelClient, FakeS3, FakeStore
from tests.reports.conftest import _seed_primary


def _store_with_reference_data() -> FakeStore:
    """Return a store seeded with the reference dataset of the report tests."""
    store = FakeStore()
    _seed_primary(store)
    return store


def test_compute_kpis():
    store = _store_with_reference_data()
    kpis = compute_kpis(store, tenant_id="t-1", period="2026-10")
    assert "delivery_to_result_hours" in kpis
    assert "critical_blocked_before_prod" in kpis
    assert "sla_compliance" in kpis
    assert kpis["tests_total"] >= 1
    assert kpis["task_hours_used"] > 0
    assert kpis["cost_usd"] > 0


def test_freeze_month():
    store = _store_with_reference_data()
    frozen = freeze_month(store, tenant_id="t-1", period="2026-10")
    assert frozen["period"] == "2026-10"
    assert frozen["frozen"] is True
    assert frozen["task_hours_used"] > 0


def test_build_monthly_report():
    store = _store_with_reference_data()
    model = FakeModelClient(canned_response="Executive summary: all clear, low risk.")
    s3 = FakeS3()
    report = build_monthly_report(
        store=store, tenant_id="t-1", period="2026-10", model_client=model, s3=s3
    )
    assert report.report_id.startswith("rep-")
    assert report.period == "2026-10"
    assert report.s3_key is not None
    assert len(s3.objects) >= 1
