"""Unit economics of the Rempart subscription formulas (ENF-IA-01).

Every figure is computed by plain Python from explicit parameters: no language
model ever takes part in a number.  Money is :class:`~decimal.Decimal` from end
to end — the convention of the sibling project ``marge-msp``: a binary float
never enters an amount.

Each reference figure carries a source tag:

``AWS``
    published by AWS, reproduced in cahier des charges 7.3 ("vérifié").
``CONTRACT``
    a service commitment of cahier des charges 7.1 or 12.2.
``ASSUMED``
    a modelling assumption of this module — **not** a measurement.

The full hypothesis table, with what still has to be measured, lives in
``docs/unit-economics.md``.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal

Source = Literal["AWS", "CONTRACT", "ASSUMED"]
Number = Decimal | float | int | str

CENTS = Decimal("0.01")
HUNDREDTH = Decimal("0.01")
TEN_THOUSANDTH = Decimal("0.0001")
ONE = Decimal("1")
MINUTES_PER_HOUR = Decimal("60")
ONE_PER_QUARTER = Decimal(1) / Decimal(3)

# --- Documented reference figures (cahier des charges 7.3) ------------------
AWS_HOURLY_RATE = Decimal("50")  # USD per task hour — AWS
AWS_TASK_HOURS_NEW_API = Decimal("3.5")  # 173 USD — AWS
AWS_TASK_HOURS_MERCHANT_SITE = Decimal("24")  # 1 200 USD — AWS
AWS_TASK_HOURS_COMPLEX_SAAS = Decimal("31")  # 1 563 USD — AWS
AWS_FREE_TRIAL_HOURS_PER_MONTH = Decimal("400")  # first 2 months — AWS

# --- Assumptions (docs/unit-economics.md, table 2) --------------------------
CICD_SCOPE_RATIO = Decimal("0.15")  # ASSUMED: a delivery touches 15 % of the surface
CICD_FINDING_RATIO = Decimal("0.25")  # ASSUMED: a delivery test yields 25 % of the findings
DEFAULT_DELIVERIES_PER_MONTH = Decimal("8")  # ASSUMED: 2 deliveries per week
DEFAULT_ANALYST_MINUTES_PER_FINDING = Decimal("6")  # ASSUMED: triage of one agent proposal
DEFAULT_ANALYST_HOURLY_COST = Decimal("60")  # ASSUMED: loaded cost of one analyst hour (USD)
DEFAULT_ANALYST_HOURS_PER_MONTH = Decimal("140")  # ASSUMED: 35 h/week x 4 productive weeks
PRICE_MULTIPLIERS: tuple[Decimal, ...] = (Decimal("1.25"), Decimal("1.5"), Decimal("2"))
VOLUME_MULTIPLIERS: tuple[Decimal, ...] = (Decimal("2"),)


# --------------------------------------------------------------------------- #
# Decimal helpers — the only place where numbers are rounded
# --------------------------------------------------------------------------- #
def dec(value: Number) -> Decimal:
    """Coerce into a Decimal via its text form (never through a binary float)."""
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _q(value: Number, exponent: Decimal) -> Decimal:
    return dec(value).quantize(exponent, rounding=ROUND_HALF_UP)


def money(value: Number) -> Decimal:
    """Round an amount to cents (HALF_UP)."""
    return _q(value, CENTS)


def hours(value: Number) -> Decimal:
    """Round a duration to hundredths of an hour."""
    return _q(value, HUNDREDTH)


def quantity(value: Number) -> Decimal:
    """Round a count expectation (findings, tests) to hundredths."""
    return _q(value, HUNDREDTH)


def rate(value: Number) -> Decimal:
    """Round a rate or a ratio to four decimals (kept for auditability)."""
    return _q(value, TEN_THOUSANDTH)


def safe_ratio(numerator: Decimal, denominator: Decimal) -> Decimal:
    """Division that returns ``Decimal(0)`` instead of crashing on zero."""
    if denominator == 0:
        return Decimal("0")
    return rate(numerator / denominator)


# --------------------------------------------------------------------------- #
# The three formulas of chapter 7.1
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class PlanSpec:
    """Service commitments of a formula and their cost consequences (7.1).

    ``overhead_minutes_per_app_month`` is the recurring analyst time that is
    *not* proportional to the findings: report preparation, review meeting,
    threat-model upkeep, ticket follow-up.  ASSUMED, derived from the 7.1 row
    of the formula (report frequency, triage SLA, meeting).
    """

    plan: str
    label: str
    scheduled_full_tests_per_month: Decimal  # CONTRACT: monthly or quarterly
    cicd_enabled: bool  # CONTRACT: gate test on every delivery
    on_demand_tests_per_month: Decimal  # CONTRACT: 0, 1, or "within budget"
    triage_sla_hours: Decimal  # CONTRACT: business hours for a P1
    report_per_month: Decimal  # CONTRACT: quarterly or monthly
    overhead_minutes_per_app_month: Decimal  # ASSUMED


PLAN_SPECS: dict[str, PlanSpec] = {
    "essentiel": PlanSpec(
        plan="essentiel",
        label="Essentiel",
        scheduled_full_tests_per_month=ONE_PER_QUARTER,  # trimestriel
        cicd_enabled=False,
        on_demand_tests_per_month=Decimal("0"),
        triage_sla_hours=Decimal("16"),  # 2 jours ouvrés
        report_per_month=ONE_PER_QUARTER,
        overhead_minutes_per_app_month=Decimal("15"),
    ),
    "continu": PlanSpec(
        plan="continu",
        label="Continu",
        scheduled_full_tests_per_month=Decimal("1"),  # mensuel
        cicd_enabled=True,
        on_demand_tests_per_month=Decimal("1"),  # 1 par mois
        triage_sla_hours=Decimal("8"),  # 1 jour ouvré
        report_per_month=Decimal("1"),
        overhead_minutes_per_app_month=Decimal("30"),
    ),
    "critique": PlanSpec(
        plan="critique",
        label="Critique",
        scheduled_full_tests_per_month=Decimal("1"),  # mensuel
        cicd_enabled=True,
        on_demand_tests_per_month=Decimal("2"),  # ASSUMED: "dans la limite du budget"
        triage_sla_hours=Decimal("4"),  # 4 heures ouvrées pour une P1
        report_per_month=Decimal("1"),
        overhead_minutes_per_app_month=Decimal("45"),
    ),
}


def plan_spec(plan: str) -> PlanSpec:
    """Return the specification of a formula, or raise on an unknown name."""
    key = plan.strip().lower()
    if key not in PLAN_SPECS:
        raise ValueError(f"unknown plan '{plan}' (expected: {', '.join(PLAN_SPECS)})")
    return PLAN_SPECS[key]


# --------------------------------------------------------------------------- #
# Application cost profiles
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class AppProfile:
    """Cost profile of one application: task hours and findings per test.

    ``full_task_hours`` comes from the examples published by AWS (7.3);
    ``full_findings`` is ASSUMED.  The delivery (CI/CD) figures are derived by
    ratio so that only one assumption governs the whole model.
    """

    name: str
    label: str
    full_task_hours: Decimal  # AWS
    full_findings: Decimal  # ASSUMED

    @property
    def cicd_task_hours(self) -> Decimal:
        return hours(self.full_task_hours * CICD_SCOPE_RATIO)

    @property
    def cicd_findings(self) -> Decimal:
        return quantity(self.full_findings * CICD_FINDING_RATIO)


PROFILES: dict[str, AppProfile] = {
    "new_api": AppProfile("new_api", "Nouvelle API", AWS_TASK_HOURS_NEW_API, Decimal("2")),
    "merchant_site": AppProfile(
        "merchant_site", "Site marchand", AWS_TASK_HOURS_MERCHANT_SITE, Decimal("6")
    ),
    "complex_saas": AppProfile(
        "complex_saas", "SaaS complexe", AWS_TASK_HOURS_COMPLEX_SAAS, Decimal("12")
    ),
}


def resolve_profile(profile: AppProfile | str) -> AppProfile:
    """Accept a profile object or its name."""
    if isinstance(profile, AppProfile):
        return profile
    key = profile.strip().lower()
    if key not in PROFILES:
        raise ValueError(f"unknown profile '{profile}' (expected: {', '.join(PROFILES)})")
    return PROFILES[key]


# --------------------------------------------------------------------------- #
# Shared pricing primitives (no duplicated arithmetic)
# --------------------------------------------------------------------------- #
