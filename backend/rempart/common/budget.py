"""Budget calculation and auto-stop policies (chapters 12 & 16)."""

from dataclasses import dataclass

from .models import BudgetState

DEFAULT_HOURLY_RATE: float = 50.0
THRESHOLDS = (50, 80, 100)


def estimate_cost(task_hours: float, hourly_rate: float = DEFAULT_HOURLY_RATE) -> float:
    """Return task cost in USD rounded to two decimals."""
    return round(float(task_hours) * float(hourly_rate), 2)


@dataclass
class BudgetVerdict:
    allowed: bool
    pct: float
    newly_crossed: list[int]
    auto_stop: bool


def check_budget(
    state: BudgetState,
    monthly_budget_hours: float,
    hourly_rate: float = DEFAULT_HOURLY_RATE,
) -> BudgetVerdict:
    """Check budget consumption against 50/80/100 thresholds and auto-stop."""
    if monthly_budget_hours <= 0:
        pct = 100.0 if state.hours_used > 0 else 0.0
    else:
        pct = (state.hours_used / monthly_budget_hours) * 100.0

    already_hit = set(state.thresholds_hit)
    newly_crossed = [t for t in THRESHOLDS if pct >= t and t not in already_hit]
    auto_stop = bool(state.auto_stop or pct >= 100.0)
    allowed = not auto_stop

    return BudgetVerdict(
        allowed=allowed,
        pct=round(pct, 2),
        newly_crossed=newly_crossed,
        auto_stop=auto_stop,
    )


def consume(
    state: BudgetState,
    task_hours: float,
    monthly_budget_hours: float,
) -> tuple[BudgetState, BudgetVerdict]:
    """Consume task hours, record crossed thresholds, and return updated state."""
    new_hours = round(state.hours_used + float(task_hours), 4)
    tmp_state = BudgetState(
        tenant_id=state.tenant_id,
        month=state.month,
        hours_used=new_hours,
        thresholds_hit=list(state.thresholds_hit),
        auto_stop=state.auto_stop,
    )
    verdict = check_budget(tmp_state, monthly_budget_hours)
    updated_hit = sorted(set(state.thresholds_hit) | set(verdict.newly_crossed))

    final_state = BudgetState(
        tenant_id=state.tenant_id,
        month=state.month,
        hours_used=new_hours,
        thresholds_hit=updated_hit,
        auto_stop=verdict.auto_stop,
    )
    return final_state, verdict
