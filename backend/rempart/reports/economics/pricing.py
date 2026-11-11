"""Prix de rupture, marge, capacité analyste et sensibilité.

Découpé depuis ``economics.py`` (647 lignes > la limite de 500). Chaque chiffre
porte son origine : AWS (documenté), mesuré, ou ASSUMED (supposition à valider).
Aucun modèle n'intervient : tout est calculé par du code (ENF-IA-01).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from numbers import Number

from .costs import (
    UnitCost,
    _analyst_hours,
    unit_cost,
)
from .numbers import (
    AWS_HOURLY_RATE,
    DEFAULT_ANALYST_HOURS_PER_MONTH,
    ONE,
    PRICE_MULTIPLIERS,
    VOLUME_MULTIPLIERS,
    dec,
    hours,
    money,
    plan_spec,
    quantity,
    rate,
    safe_ratio,
)


class BreakEven:
    """Break-even price of a subscription and its margin at a given price."""

    plan: str
    direct_cost: Decimal
    break_even_price: Decimal
    target_price: Decimal
    subscription_price: Decimal
    margin: Decimal
    margin_rate: Decimal
    meets_target: bool


def break_even_from_cost(
    cost: UnitCost,
    *,
    subscription_price: Number,
    target_margin_rate: Number = Decimal("0"),
) -> BreakEven:
    """Minimum price covering the direct cost, and margin at ``subscription_price``.

    ``target_price`` is the price that reaches ``target_margin_rate`` on the
    selling price (``cost / (1 - rate)``); at ``target_margin_rate = 0`` it is
    exactly the break-even price, where the margin is exactly zero.
    """
    target = rate(target_margin_rate)
    direct = money(cost.total)
    price = money(subscription_price)
    target_price = money(direct / (ONE - target)) if target < ONE else direct
    margin = money(price - direct)
    margin_rate = safe_ratio(margin, price)
    return BreakEven(
        plan=cost.plan,
        direct_cost=direct,
        break_even_price=direct,
        target_price=target_price,
        subscription_price=price,
        margin=margin,
        margin_rate=margin_rate,
        meets_target=margin_rate >= target,
    )


def break_even_price(
    plan: str,
    *,
    subscription_price: Number,
    tests_per_month: Number,
    task_hours_per_test: Number,
    hourly_rate: Number = AWS_HOURLY_RATE,
    analyst_minutes_per_finding: Number,
    findings_per_test: Number,
    analyst_hourly_cost: Number,
    target_margin_rate: Number = Decimal("0"),
) -> BreakEven:
    """Break-even point of one application under ``plan`` (see above)."""
    cost = unit_cost(
        plan,
        tests_per_month=tests_per_month,
        task_hours_per_test=task_hours_per_test,
        hourly_rate=hourly_rate,
        analyst_minutes_per_finding=analyst_minutes_per_finding,
        findings_per_test=findings_per_test,
        analyst_hourly_cost=analyst_hourly_cost,
    )
    return break_even_from_cost(
        cost, subscription_price=subscription_price, target_margin_rate=target_margin_rate
    )


@dataclass(frozen=True)
class ClientMargin:
    """Monthly margin of a client: revenue minus direct cost."""

    plan: str
    applications: int
    subscription_price_per_app: Decimal
    revenue: Decimal
    direct_cost: Decimal
    margin: Decimal
    margin_rate: Decimal
    cost_per_app: Decimal


def margin_from_costs(
    costs: Sequence[UnitCost],
    *,
    subscription_price: Number,
    plan: str = "",
) -> ClientMargin:
    """Margin of a client whose applications have heterogeneous unit costs."""
    applications = len(costs)
    price = money(subscription_price)
    revenue = money(price * applications)
    direct = money(sum((c.total for c in costs), Decimal("0")))
    margin = money(revenue - direct)
    cost_per_app = money(direct / applications) if applications else Decimal("0.00")
    return ClientMargin(
        plan=plan,
        applications=applications,
        subscription_price_per_app=price,
        revenue=revenue,
        direct_cost=direct,
        margin=margin,
        margin_rate=safe_ratio(margin, revenue),
        cost_per_app=cost_per_app,
    )


def margin_per_client(
    plan: str,
    *,
    applications: int,
    subscription_price: Number,
    tests_per_month: Number,
    task_hours_per_test: Number,
    hourly_rate: Number = AWS_HOURLY_RATE,
    analyst_minutes_per_finding: Number,
    findings_per_test: Number,
    analyst_hourly_cost: Number,
) -> ClientMargin:
    """Monthly margin of a client with ``applications`` identical applications."""
    cost = unit_cost(
        plan,
        tests_per_month=tests_per_month,
        task_hours_per_test=task_hours_per_test,
        hourly_rate=hourly_rate,
        analyst_minutes_per_finding=analyst_minutes_per_finding,
        findings_per_test=findings_per_test,
        analyst_hourly_cost=analyst_hourly_cost,
    )
    return margin_from_costs(
        [cost] * max(0, int(applications)),
        subscription_price=subscription_price,
        plan=cost.plan,
    )


# --------------------------------------------------------------------------- #
# Analyst capacity (the "> 40 applications per analyst" claim of chapter 4)
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Capacity:
    """Applications one analyst can follow, given the triage load."""

    plan: str
    tests_per_application: Decimal
    findings_per_application: Decimal
    analyst_hours_per_application: Decimal
    available_hours_per_month: Decimal
    applications_per_analyst: Decimal
    max_applications: int


def analyst_capacity(
    plan: str,
    *,
    tests_per_month: Number,
    findings_per_test: Number,
    analyst_minutes_per_finding: Number,
    available_hours_per_month: Number = DEFAULT_ANALYST_HOURS_PER_MONTH,
    include_plan_overhead: bool = True,
) -> Capacity:
    """Applications per analyst, from the triage time and the finding volume.

    Bounded by construction: a zero load per application returns ``0`` instead
    of an infinite capacity, and ``max_applications`` is the integer floor of
    the raw ratio (an analyst cannot follow a fraction of an application).
    """
    spec = plan_spec(plan)
    tests = quantity(tests_per_month)
    findings = quantity(tests * dec(findings_per_test))
    overhead = spec.overhead_minutes_per_app_month if include_plan_overhead else Decimal("0")
    per_app = _analyst_hours(findings, dec(analyst_minutes_per_finding), overhead)
    available = hours(available_hours_per_month)
    apps = safe_ratio(available, per_app) if per_app > 0 else Decimal("0")
    return Capacity(
        plan=spec.plan,
        tests_per_application=tests,
        findings_per_application=findings,
        analyst_hours_per_application=per_app,
        available_hours_per_month=available,
        applications_per_analyst=apps,
        max_applications=int(apps),
    )


# --------------------------------------------------------------------------- #
# Sensitivity (chapter 20: "a test costs more than expected")
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class SensitivityCase:
    """One scenario: what a price or volume change does to the unit cost."""

    name: str
    hourly_rate: Decimal
    tests_per_month: Decimal
    direct_cost: Decimal
    break_even_price: Decimal
    delta_cost: Decimal
    delta_cost_pct: Decimal


def sensitivity(
    plan: str,
    *,
    tests_per_month: Number,
    task_hours_per_test: Number,
    hourly_rate: Number = AWS_HOURLY_RATE,
    analyst_minutes_per_finding: Number,
    findings_per_test: Number,
    analyst_hourly_cost: Number,
    price_multipliers: Sequence[Number] = PRICE_MULTIPLIERS,
    volume_multipliers: Sequence[Number] = VOLUME_MULTIPLIERS,
) -> tuple[SensitivityCase, ...]:
    """Cost of one application under AWS price rises and a doubled test volume.

    The first case is always the reference (multiplier ``1``); the AWS price
    cases come first, then the volume cases.  A higher hourly rate always gives
    a higher cost, and a higher volume always gives a higher cost.
    """
    kwargs = {
        "analyst_minutes_per_finding": analyst_minutes_per_finding,
        "findings_per_test": findings_per_test,
        "analyst_hourly_cost": analyst_hourly_cost,
    }
    base = unit_cost(
        plan, tests_per_month=tests_per_month, task_hours_per_test=task_hours_per_test, **kwargs
    )
    cases: list[SensitivityCase] = []
    for label, new_rate in (("base", dec(hourly_rate)),) + tuple(
        (f"aws_x{dec(m):g}", dec(hourly_rate) * dec(m)) for m in price_multipliers
    ):
        cost = unit_cost(
            plan,
            tests_per_month=tests_per_month,
            task_hours_per_test=task_hours_per_test,
            hourly_rate=new_rate,
            **kwargs,
        )
        cases.append(_case(label, cost, base.total, new_rate, cost.tests_per_month))
    for multiplier in volume_multipliers:
        volume = quantity(dec(tests_per_month) * dec(multiplier))
        cost = unit_cost(
            plan,
            tests_per_month=volume,
            task_hours_per_test=task_hours_per_test,
            hourly_rate=hourly_rate,
            **kwargs,
        )
        cases.append(
            _case(f"volume_x{dec(multiplier):g}", cost, base.total,
                  cost_rate(hourly_rate), volume)
        )
    return tuple(cases)


def cost_rate(hourly_rate: Number) -> Decimal:
    """Hourly rate of a sensitivity case, rounded like a rate."""
    return rate(hourly_rate)


def _case(
    name: str, cost: UnitCost, base_total: Decimal, hourly_rate: Decimal, tests: Decimal
) -> SensitivityCase:
    delta = money(cost.total - base_total)
    return SensitivityCase(
        name=name,
        hourly_rate=rate(hourly_rate),
        tests_per_month=tests,
        direct_cost=cost.total,
        break_even_price=cost.total,
        delta_cost=delta,
        delta_cost_pct=safe_ratio(delta, base_total),
    )
