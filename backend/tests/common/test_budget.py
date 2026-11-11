"""Tests for budget computation, threshold tracking, and auto-stop."""

from rempart.common.budget import (
    DEFAULT_HOURLY_RATE,
    check_budget,
    consume,
    estimate_cost,
)
from rempart.common.models import BudgetState


def test_estimate_cost():
    assert estimate_cost(2.0, 50.0) == 100.0
    assert estimate_cost(1.5, 60.0) == 90.0
    assert estimate_cost(2.5, DEFAULT_HOURLY_RATE) == 125.0
    assert round(estimate_cost(4 / 3, 50.0), 2) == 66.67


def test_check_budget_clean_state():
    state = BudgetState("t-1", "2026-11", 10.0, [], False)
    verdict = check_budget(state, monthly_budget_hours=40.0)
    assert verdict.allowed is True
    assert verdict.pct == 25.0
    assert verdict.newly_crossed == []
    assert verdict.auto_stop is False


def test_check_budget_thresholds():
    # 50% hit
    s1 = BudgetState("t-1", "2026-11", 20.0, [], False)
    v1 = check_budget(s1, 40.0)
    assert v1.allowed is True
    assert v1.pct == 50.0
    assert v1.newly_crossed == [50]
    assert v1.auto_stop is False

    # 85% with 50 already hit
    s2 = BudgetState("t-1", "2026-11", 34.0, [50], False)
    v2 = check_budget(s2, 40.0)
    assert v2.allowed is True
    assert v2.pct == 85.0
    assert v2.newly_crossed == [80]
    assert v2.auto_stop is False

    # 100% reached -> auto_stop True, allowed False
    s3 = BudgetState("t-1", "2026-11", 40.0, [50, 80], False)
    v3 = check_budget(s3, 40.0)
    assert v3.allowed is False
    assert v3.pct == 100.0
    assert v3.newly_crossed == [100]
    assert v3.auto_stop is True


def test_consume_updates_state_and_verdict():
    initial = BudgetState("t-1", "2026-11", 18.0, [], False)
    # add 3h -> 21h (52.5%) -> crosses 50
    st1, v1 = consume(initial, task_hours=3.0, monthly_budget_hours=40.0)
    assert st1.hours_used == 21.0
    assert st1.thresholds_hit == [50]
    assert v1.newly_crossed == [50]
    assert v1.allowed is True
    assert v1.auto_stop is False

    # jump straight to 42h (105%) -> crosses 80 and 100
    st2, v2 = consume(st1, task_hours=21.0, monthly_budget_hours=40.0)
    assert st2.hours_used == 42.0
    assert st2.thresholds_hit == [50, 80, 100]
    assert v2.newly_crossed == [80, 100]
    assert v2.allowed is False
    assert v2.auto_stop is True


def test_check_budget_existing_auto_stop_enforced():
    s = BudgetState("t-1", "2026-11", 10.0, [], auto_stop=True)
    v = check_budget(s, 40.0)
    assert v.allowed is False
    assert v.auto_stop is True
