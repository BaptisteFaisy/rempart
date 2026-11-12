"""Prévision de consommation budgétaire (#44, EF-BUD-04).

Face à un coût de 50 $/heure-tâche, un compteur ne suffit pas : il faut une
projection. « À ce rythme vous atteindrez 100 % de votre budget le 18 du mois »
transforme un chiffre en décision.

ENF-IA-01 : tout est calculé par du code déterministe, aucun modèle.
Méthode de projection, vérifiable à la main :
    jours_écoulés   = jour du mois de `as_of` (jamais 30, jamais 0)
    taux_journalier = heures consommées depuis le 1er / jours_écoulés
    projection      = taux journalier × jours dans le mois
    rupture         = budget restant / taux journalier, ajouté à `as_of`
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from rempart.common.models import Run
from rempart.common.store import Store
from rempart.common.timeutil import utcnow

SECONDS_PER_DAY = 86_400


def days_in_month(year: int, month: int) -> int:
    return calendar.monthrange(year, month)[1]


def _month_start(period: str) -> datetime:
    year, month = (int(part) for part in period.split("-")[:2])
    return datetime(year, month, 1, tzinfo=utcnow().tzinfo)


def _runs_of_month(store: Store, tenant_id: str, period: str) -> list[Run]:
    """Runs dont le début tombe dans `period` (AAAA-MM)."""
    return [
        run
        for run in store.list_runs(tenant_id=tenant_id, limit=1000)
        if (run.started_at or "").startswith(period)
    ]


@dataclass
class BurnRate:
    """Vitesse de consommation depuis le début du mois."""

    hours_used: float
    days_elapsed: int
    hours_per_day: float


def period_end(period: str) -> datetime:
    """Dernier instant de la période (fin du mois, 23:59:59)."""
    year, month = (int(part) for part in period.split("-")[:2])
    start = _month_start(period)
    last = days_in_month(year, month)
    return start + timedelta(days=last - 1, hours=23, minutes=59, seconds=59)


def evaluation_instant(period: str, as_of: datetime | None = None) -> datetime:
    """Instant d'évaluation d'une période : la fin de la période, pas « maintenant ».

    BUG CORRIGÉ (12 nov. 2026, trouvé en rendant la démo réaliste) : la
    prévision d'une période **passée** était évaluée à l'heure courante. Pour
    octobre, cela donnait 43 « jours écoulés » (le 12 novembre) au lieu de 31 :
    le taux journalier, la projection de fin de mois et le coût projeté étaient
    tous faux. On n'évalue jamais au-delà de la fin de la période.
    """
    if as_of is not None:
        return as_of
    return min(utcnow(), period_end(period))


def daily_burn_rate(
    store: Store, *, tenant_id: str, period: str, as_of: datetime | None = None
) -> BurnRate:
    """Heures-tâches consommées par jour ÉCOULÉ (pas par jour du mois)."""
    moment = evaluation_instant(period, as_of)
    hours = sum(run.task_hours or 0.0 for run in _runs_of_month(store, tenant_id, period))
    start = _month_start(period)
    elapsed = max(1, (moment - start).days + 1)
    return BurnRate(
        hours_used=round(hours, 4),
        days_elapsed=elapsed,
        hours_per_day=round(hours / elapsed, 6),
    )


@dataclass
class Forecast:
    period: str
    days_in_month: int
    days_elapsed: int
    hours_used: float
    hours_per_day: float
    projected_hours: float
    projected_cost_usd: float
    monthly_budget_hours: float
    projected_pct: float
    exceeds_budget: bool
    exhaustion_date: str | None
    reference_cost_per_config: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "period": self.period,
            "days_in_month": self.days_in_month,
            "days_elapsed": self.days_elapsed,
            "hours_used": self.hours_used,
            "hours_per_day": self.hours_per_day,
            "projected_hours": self.projected_hours,
            "projected_cost_usd": self.projected_cost_usd,
            "monthly_budget_hours": self.monthly_budget_hours,
            "projected_pct": self.projected_pct,
            "exceeds_budget": self.exceeds_budget,
            "exhaustion_date": self.exhaustion_date,
            "reference_cost_per_config": self.reference_cost_per_config,
        }


def _exhaustion_date(
    as_of: datetime, hours_per_day: float, remaining: float
) -> str | None:
    """Date à laquelle le budget sera épuisé, ou None s'il tient jusqu'à la fin."""
    if hours_per_day <= 0 or remaining <= 0:
        return None
    days_left = remaining / hours_per_day
    return (as_of + timedelta(days=days_left)).date().isoformat()


def reference_cost_per_config(
    store: Store, *, tenant_id: str | None = None
) -> dict[str, Any]:
    """Coût de référence par configuration de test (EF-BUD-04).

    Moyenne des heures-tâches des runs terminés, groupés par configuration.
    C'est la seule estimation disponible avant de lancer un test : AWS n'en
    fournit aucune, seul l'historique de la même configuration fait foi.
    """
    buckets: dict[str, list[float]] = {}
    for run in store.list_runs(tenant_id=tenant_id, limit=1000):
        if run.status != "completed" or not run.task_hours:
            continue
        buckets.setdefault(run.config_id or "unknown", []).append(run.task_hours)

    out: dict[str, Any] = {}
    for config_id, hours in sorted(buckets.items()):
        samples = len(hours)
        average = sum(hours) / samples
        out[config_id] = {
            "samples": samples,
            "avg_task_hours": round(average, 4),
            "avg_cost_usd": round(average * 50.0, 2),
            "low_confidence": samples < 3,
        }
    return out


def forecast_month(
    store: Store,
    *,
    tenant_id: str,
    period: str,
    as_of: datetime | None = None,
    hourly_rate: float = 50.0,
) -> Forecast:
    """Projection de fin de mois et date de rupture du budget."""
    moment = evaluation_instant(period, as_of)
    burn = daily_burn_rate(store, tenant_id=tenant_id, period=period, as_of=moment)
    year, month = (int(part) for part in period.split("-")[:2])
    total_days = days_in_month(year, month)

    tenant = store.get_tenant(tenant_id)
    budget = float(tenant.monthly_budget_hours) if tenant else 0.0

    projected_hours = round(burn.hours_per_day * total_days, 4)
    projected_cost = round(projected_hours * hourly_rate, 2)
    projected_pct = round((projected_hours / budget) * 100, 2) if budget > 0 else 0.0
    exceeds = budget > 0 and projected_hours > budget

    remaining = max(0.0, budget - burn.hours_used)
    exhaustion = _exhaustion_date(moment, burn.hours_per_day, remaining)
    if exhaustion and not exceeds:
        # Le budget tient : aucune rupture projetée dans le mois.
        exhaustion = None

    return Forecast(
        period=period,
        days_in_month=total_days,
        days_elapsed=burn.days_elapsed,
        hours_used=burn.hours_used,
        hours_per_day=burn.hours_per_day,
        projected_hours=projected_hours,
        projected_cost_usd=projected_cost,
        monthly_budget_hours=budget,
        projected_pct=projected_pct,
        exceeds_budget=exceeds,
        exhaustion_date=exhaustion,
        reference_cost_per_config=reference_cost_per_config(store, tenant_id=tenant_id),
    )
