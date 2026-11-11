"""Tests for the per-tenant correction policy (EF-ADM-01).

Vérifie ``compute_priority_with_policy`` / ``resolve_due_days`` sans toucher
au comportement historique de ``compute_priority`` ni de ``due_date``.
"""

from datetime import datetime, timedelta, timezone

import pytest

from rempart.common.priority import (
    DEFAULT_DUE_DAYS,
    PriorityResult,
    compute_priority,
    compute_priority_with_policy,
    due_date,
    resolve_due_days,
)

CREATED = datetime(2026, 11, 1, 10, 0, tzinfo=timezone.utc)

SEVERITIES = ("Critical", "High", "Medium", "Low", "Informational")
CONFIDENCES = ("High", "Medium", "Low")


def with_policy(
    severity: str,
    confidence: str,
    *,
    exposed: bool = False,
    sensitive: bool = False,
    policy: dict | None = None,
):
    return compute_priority_with_policy(
        severity,
        confidence,
        exposed_critical=exposed,
        sensitive_data=sensitive,
        policy=policy,
    )


@pytest.mark.parametrize("severity", SEVERITIES)
@pytest.mark.parametrize("confidence", CONFIDENCES)
@pytest.mark.parametrize("exposed", [False, True])
@pytest.mark.parametrize("sensitive", [False, True])
def test_without_policy_matches_compute_priority(severity, confidence, exposed, sensitive):
    base = compute_priority(
        severity, confidence, exposed_critical=exposed, sensitive_data=sensitive
    )
    result = with_policy(severity, confidence, exposed=exposed, sensitive=sensitive)
    assert result.priority == base.priority
    assert result.needs_validation == base.needs_validation
    assert result.due_days == DEFAULT_DUE_DAYS[result.priority]


def test_legacy_compute_priority_and_due_date_unchanged():
    result = compute_priority(
        "Critical", "High", exposed_critical=True, sensitive_data=False
    )
    assert result == PriorityResult(priority="P1", needs_validation=False)
    assert due_date("P1", CREATED) == CREATED + timedelta(days=7)
    assert due_date("P2", CREATED) == CREATED + timedelta(days=30)
    assert due_date("P3", CREATED) == CREATED + timedelta(days=90)
    assert due_date("P4", CREATED) is None


def test_due_days_override_is_applied():
    policy = {"due_days": {"P1": 3, "P2": 14}}
    p1 = with_policy("Critical", "High", policy=policy)
    assert (p1.priority, p1.due_days) == ("P1", 3)
    p2 = with_policy("High", "High", policy=policy)
    assert (p2.priority, p2.due_days) == ("P2", 14)
    # Priorités non surchargées : délai global par défaut.
    p3 = with_policy("High", "Medium", policy=policy)
    assert (p3.priority, p3.due_days) == ("P3", 90)


def test_due_days_override_feeds_due_date():
    policy = {"due_days": {"P1": 3}}
    result = with_policy("Critical", "High", policy=policy)
    when = due_date(result.priority, CREATED, resolve_due_days(policy))
    assert when == CREATED + timedelta(days=3)


def test_due_days_null_means_no_deadline():
    result = with_policy("Low", "Low", policy={"due_days": {"P4": None}})
    assert result.priority == "P4"
    assert result.due_days is None
    assert due_date("P4", CREATED, resolve_due_days({"due_days": {"P4": None}})) is None


def test_matrix_override_replaces_base_priority():
    result = with_policy("Critical", "High", exposed=True,
                         policy={"matrix_overrides": {"Critical": "P4"}})
    assert result.priority == "P4"
    assert result.needs_validation is False


def test_matrix_override_still_gets_sensitive_data_bump():
    result = with_policy("Medium", "High", sensitive=True,
                         policy={"matrix_overrides": {"Medium": "P3"}})
    assert result.priority == "P2"


def test_matrix_override_bump_is_capped_at_p1():
    result = with_policy("Low", "Low", sensitive=True,
                         policy={"matrix_overrides": {"Low": "P1"}})
    assert result.priority == "P1"


def test_unknown_matrix_override_value_is_ignored():
    result = with_policy("Critical", "High",
                         policy={"matrix_overrides": {"Critical": "P9"}})
    assert result.priority == "P1"


def test_resolve_due_days_merges_over_defaults():
    assert resolve_due_days(None) == DEFAULT_DUE_DAYS
    assert resolve_due_days({}) == DEFAULT_DUE_DAYS
    merged = resolve_due_days({"due_days": {"P1": 1}})
    assert merged == {"P1": 1, "P2": 30, "P3": 90, "P4": None}


def test_resolve_due_days_drops_malformed_entries():
    merged = resolve_due_days({"due_days": {"P1": "7", "P2": 14, "P9": 5}})
    assert merged["P1"] == 7
    assert merged["P2"] == 14
    assert "P9" not in merged
