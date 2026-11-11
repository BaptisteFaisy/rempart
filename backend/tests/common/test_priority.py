"""Tests for priority matrix (chapter 12.2) and due dates."""

from datetime import datetime, timezone

import pytest

from rempart.common.priority import compute_priority, due_date


@pytest.mark.parametrize(
    ("sev", "conf", "exposed", "expected_p", "expected_val"),
    [
        # Critical
        ("Critical", "High", True, "P1", False),
        ("Critical", "High", False, "P1", False),
        ("Critical", "Medium", True, "P1", True),
        ("Critical", "Medium", False, "P2", True),
        ("Critical", "Low", True, "P1", True),
        ("Critical", "Low", False, "P2", True),
        # High
        ("High", "High", True, "P1", False),
        ("High", "High", False, "P2", False),
        ("High", "Medium", True, "P2", True),
        ("High", "Medium", False, "P3", True),
        ("High", "Low", True, "P2", True),
        ("High", "Low", False, "P3", True),
        # Medium
        ("Medium", "High", True, "P2", False),
        ("Medium", "High", False, "P3", False),
        ("Medium", "Medium", True, "P3", False),
        ("Medium", "Medium", False, "P4", False),
        ("Medium", "Low", True, "P3", False),
        ("Medium", "Low", False, "P4", False),
        # Low | Informational
        ("Low", "High", True, "P4", False),
        ("Low", "Low", False, "P4", False),
        ("Informational", "High", True, "P4", False),
        ("Informational", "Low", False, "P4", False),
    ],
)
def test_priority_matrix_base(sev, conf, exposed, expected_p, expected_val):
    res = compute_priority(
        sev,
        conf,
        exposed_critical=exposed,
        sensitive_data=False,
    )
    assert res.priority == expected_p
    assert res.needs_validation is expected_val


def test_priority_sensitive_data_bump():
    # Medium+Med non-exposed -> base P4 -> bump to P3, needs_validation False
    res = compute_priority(
        "Medium",
        "Medium",
        exposed_critical=False,
        sensitive_data=True,
    )
    assert res.priority == "P3"
    assert res.needs_validation is False

    # High+Med non-exposed -> base P3 -> bump to P2, needs_validation remains True
    res2 = compute_priority(
        "High",
        "Medium",
        exposed_critical=False,
        sensitive_data=True,
    )
    assert res2.priority == "P2"
    assert res2.needs_validation is True

    # Critical+High -> base P1 -> bump stays capped at P1
    res3 = compute_priority(
        "Critical",
        "High",
        exposed_critical=True,
        sensitive_data=True,
    )
    assert res3.priority == "P1"
    assert res3.needs_validation is False


def test_due_date_calculation():
    dt = datetime(2026, 11, 10, 12, 0, 0, tzinfo=timezone.utc)
    d1 = due_date("P1", dt)
    assert d1 == datetime(2026, 11, 17, 12, 0, 0, tzinfo=timezone.utc)

    d2 = due_date("P2", dt)
    assert d2 == datetime(2026, 12, 10, 12, 0, 0, tzinfo=timezone.utc)

    d3 = due_date("P3", dt)
    assert d3 == datetime(2027, 2, 8, 12, 0, 0, tzinfo=timezone.utc)

    d4 = due_date("P4", dt)
    assert d4 is None


def test_due_date_custom_mapping():
    dt = datetime(2026, 11, 10, 12, 0, 0, tzinfo=timezone.utc)
    custom = {"P1": 3, "P2": 10, "P3": 20, "P4": 50}
    assert due_date("P1", dt, custom) == datetime(2026, 11, 13, 12, 0, 0, tzinfo=timezone.utc)
    assert due_date("P4", dt, custom) == datetime(2026, 12, 30, 12, 0, 0, tzinfo=timezone.utc)
