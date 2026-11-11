"""Coûts directs : heures-tâches AWS et temps analyste.

Découpé depuis ``economics.py`` (647 lignes > la limite de 500). Chaque chiffre
porte son origine : AWS (documenté), mesuré, ou ASSUMED (supposition à valider).
Aucun modèle n'intervient : tout est calculé par du code (ENF-IA-01).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from numbers import Number

from .numbers import (
    AWS_HOURLY_RATE,
    DEFAULT_ANALYST_HOURLY_COST,
    DEFAULT_ANALYST_MINUTES_PER_FINDING,
    DEFAULT_DELIVERIES_PER_MONTH,
    MINUTES_PER_HOUR,
    AppProfile,
    PlanSpec,
    dec,
    hours,
    money,
    plan_spec,
    quantity,
    resolve_profile,
)


def _task_cost(task_hours: Decimal, hourly_rate: Decimal) -> Decimal:
    return money(task_hours * hourly_rate)


def _analyst_hours(
    findings: Decimal, minutes_per_finding: Decimal, overhead_minutes: Decimal
) -> Decimal:
    return hours((findings * minutes_per_finding + overhead_minutes) / MINUTES_PER_HOUR)


def _analyst_cost(analyst_hours: Decimal, analyst_hourly_cost: Decimal) -> Decimal:
    return money(analyst_hours * analyst_hourly_cost)


# --------------------------------------------------------------------------- #
# Unit cost
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class UnitCost:
    """Direct monthly cost of one application: task hours + analyst time."""

    plan: str
    tests_per_month: Decimal
    task_hours_per_month: Decimal
    task_cost: Decimal
    findings_per_month: Decimal
    analyst_hours_per_month: Decimal
    analyst_cost: Decimal
    total: Decimal


def unit_cost(
    plan: str,
    *,
    tests_per_month: Number,
    task_hours_per_test: Number,
    hourly_rate: Number = AWS_HOURLY_RATE,
    analyst_minutes_per_finding: Number,
    findings_per_test: Number,
    analyst_hourly_cost: Number,
    include_plan_overhead: bool = True,
) -> UnitCost:
    """Direct monthly cost of one application under ``plan``.

    The plan only contributes its recurring analyst overhead (report, review
    meeting, threat-model upkeep): the variable part is entirely driven by the
    explicit parameters.  ``include_plan_overhead=False`` isolates the variable
    cost, which is what :func:`formula_cost` needs to price each test kind.
    """
    spec = plan_spec(plan)
    tests = quantity(tests_per_month)
    findings = quantity(tests * dec(findings_per_test))
    overhead = spec.overhead_minutes_per_app_month if include_plan_overhead else Decimal("0")
    task_hours = hours(tests * dec(task_hours_per_test))
    analyst_hours = _analyst_hours(findings, dec(analyst_minutes_per_finding), overhead)
    task_cost = _task_cost(task_hours, dec(hourly_rate))
    analyst_cost = _analyst_cost(analyst_hours, dec(analyst_hourly_cost))
    return UnitCost(
        plan=spec.plan,
        tests_per_month=tests,
        task_hours_per_month=task_hours,
        task_cost=task_cost,
        findings_per_month=findings,
        analyst_hours_per_month=analyst_hours,
        analyst_cost=analyst_cost,
        total=money(task_cost + analyst_cost),
    )


# --------------------------------------------------------------------------- #
# Per-formula cost (chapter 7.1 differences)
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class FormulaCost:
    """Direct monthly cost of one application for a formula and a profile."""

    plan: str
    profile: str
    tests_by_kind: dict[str, Decimal]
    task_hours_by_kind: dict[str, Decimal]
    findings_by_kind: dict[str, Decimal]
    task_hours: Decimal
    task_cost: Decimal
    findings: Decimal
    analyst_hours: Decimal
    analyst_cost: Decimal
    total: Decimal


def _kind_mix(spec: PlanSpec, profile: AppProfile, deliveries: Decimal) -> dict[str, tuple]:
    """Tests per month, task hours per test and findings per test, by kind."""
    gate = deliveries if spec.cicd_enabled else Decimal("0")
    return {
        "scheduled": (
            spec.scheduled_full_tests_per_month,
            profile.full_task_hours,
            profile.full_findings,
        ),
        "cicd": (gate, profile.cicd_task_hours, profile.cicd_findings),
        "on_demand": (
            spec.on_demand_tests_per_month,
            profile.full_task_hours,
            profile.full_findings,
        ),
    }


def formula_cost(
    plan: str,
    profile: AppProfile | str = "new_api",
    *,
    deliveries_per_month: Number = DEFAULT_DELIVERIES_PER_MONTH,
    hourly_rate: Number = AWS_HOURLY_RATE,
    analyst_minutes_per_finding: Number = DEFAULT_ANALYST_MINUTES_PER_FINDING,
    analyst_hourly_cost: Number = DEFAULT_ANALYST_HOURLY_COST,
) -> FormulaCost:
    """Price one application of one formula, test kind by test kind.

    The formula differences of chapter 7.1 are the mix itself: Essentiel has no
    gate test and a full test every three months, Continu adds one gate test
    per delivery plus one on-demand test, Critique doubles the on-demand quota.
    """
    spec = plan_spec(plan)
    prof = resolve_profile(profile)
    deliveries = quantity(deliveries_per_month)
    tests: dict[str, Decimal] = {}
    task_hours: dict[str, Decimal] = {}
    findings: dict[str, Decimal] = {}
    mix = _kind_mix(spec, prof, deliveries)
    for kind, (count, hours_per_test, findings_per_test) in mix.items():
        tests[kind] = quantity(count)
        task_hours[kind] = hours(count * dec(hours_per_test))
        findings[kind] = quantity(count * dec(findings_per_test))
    total_hours = hours(sum(task_hours.values(), Decimal("0")))
    total_findings = quantity(sum(findings.values(), Decimal("0")))
    analyst_hours = _analyst_hours(
        total_findings, dec(analyst_minutes_per_finding), spec.overhead_minutes_per_app_month
    )
    task_cost = _task_cost(total_hours, dec(hourly_rate))
    analyst_cost = _analyst_cost(analyst_hours, dec(analyst_hourly_cost))
    return FormulaCost(
        plan=spec.plan,
        profile=prof.name,
        tests_by_kind=tests,
        task_hours_by_kind=task_hours,
        findings_by_kind=findings,
        task_hours=total_hours,
        task_cost=task_cost,
        findings=total_findings,
        analyst_hours=analyst_hours,
        analyst_cost=analyst_cost,
        total=money(task_cost + analyst_cost),
    )


def formula_unit_cost(cost: FormulaCost) -> UnitCost:
    """Flatten a :class:`FormulaCost` into the :class:`UnitCost` shape."""
    return UnitCost(
        plan=cost.plan,
        tests_per_month=quantity(sum(cost.tests_by_kind.values(), Decimal("0"))),
        task_hours_per_month=cost.task_hours,
        task_cost=cost.task_cost,
        findings_per_month=cost.findings,
        analyst_hours_per_month=cost.analyst_hours,
        analyst_cost=cost.analyst_cost,
        total=cost.total,
    )
