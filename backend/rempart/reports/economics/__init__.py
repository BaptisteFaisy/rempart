"""Modèle économique de Rempart : coûts directs, prix de rupture, marge, capacité.

Découpé en trois modules pour rester sous la limite de 500 lignes :
``numbers`` (constantes sourcées, helpers Decimal, formules, profils),
``costs`` (coût direct d'une application), ``pricing`` (prix de rupture,
marge, capacité analyste, sensibilité).

Chaque chiffre porte son origine : AWS (documenté), mesuré, ou ASSUMED.
Aucun modèle n'intervient : tout est calculé par du code (ENF-IA-01).
"""

from rempart.reports.economics.costs import (
    FormulaCost,
    UnitCost,
    formula_cost,
    formula_unit_cost,
    unit_cost,
)
from rempart.reports.economics.numbers import (
    AWS_FREE_TRIAL_HOURS_PER_MONTH,
    AWS_HOURLY_RATE,
    AWS_TASK_HOURS_COMPLEX_SAAS,
    AWS_TASK_HOURS_MERCHANT_SITE,
    AWS_TASK_HOURS_NEW_API,
    PLAN_SPECS,
    PROFILES,
    AppProfile,
    PlanSpec,
    dec,
    hours,
    money,
    plan_spec,
    quantity,
    rate,
    resolve_profile,
    safe_ratio,
)
from rempart.reports.economics.pricing import (
    BreakEven,
    Capacity,
    ClientMargin,
    SensitivityCase,
    analyst_capacity,
    break_even_from_cost,
    break_even_price,
    cost_rate,
    margin_from_costs,
    margin_per_client,
    sensitivity,
)

__all__ = [
    "AWS_FREE_TRIAL_HOURS_PER_MONTH",
    "AWS_HOURLY_RATE",
    "AWS_TASK_HOURS_COMPLEX_SAAS",
    "AWS_TASK_HOURS_MERCHANT_SITE",
    "AWS_TASK_HOURS_NEW_API",
    "AppProfile",
    "BreakEven",
    "Capacity",
    "ClientMargin",
    "FormulaCost",
    "PLAN_SPECS",
    "PROFILES",
    "PlanSpec",
    "SensitivityCase",
    "UnitCost",
    "analyst_capacity",
    "break_even_from_cost",
    "break_even_price",
    "cost_rate",
    "dec",
    "formula_cost",
    "formula_unit_cost",
    "hours",
    "margin_from_costs",
    "margin_per_client",
    "money",
    "plan_spec",
    "quantity",
    "rate",
    "resolve_profile",
    "safe_ratio",
    "sensitivity",
    "unit_cost",
]
