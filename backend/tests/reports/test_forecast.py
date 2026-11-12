"""Prévision de fin de mois (EF-BUD-04) — la projection, testée.

BUG TROUVÉ EN RENDANT LA DÉMO RÉALISTE (12 nov. 2026) : la prévision d'une
période **passée** était évaluée à l'heure courante. Pour octobre, cela
donnait 43 « jours écoulés » (le 12 novembre) au lieu de 31 : le taux
journalier, la projection de fin de mois et le coût projeté étaient tous faux.
Le module n'avait **aucun test** — le correctif vient avec les siens.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from rempart.common.models import BudgetState, Run
from rempart.common.timeutil import utcnow
from rempart.reports.forecast import (
    daily_burn_rate,
    days_in_month,
    evaluation_instant,
    forecast_month,
    period_end,
)
from tests.fakes import FakeStore
from tests.reports.conftest import make_app, make_run, make_tenant

PAST_PERIOD = "2026-10"


def _store(hours: float = 5.4, budget: float = 40.0) -> FakeStore:
    """Un client, une application, un test de 5,4 h sur la période."""
    store = FakeStore()
    store.save_tenant(make_tenant("t-1", budget_hours=budget))
    store.save_application(make_app("app-1", tenant_id="t-1"))
    store.save_run(
        make_run("run-1", "app-1", task_hours=hours, started_at="2026-10-05T08:00:00Z")
    )
    store.save_budget(
        BudgetState(
            tenant_id="t-1", month=PAST_PERIOD, hours_used=hours,
            thresholds_hit=[], auto_stop=False,
        )
    )
    return store


def test_une_periode_passee_est_evaluee_a_sa_fin_et_non_a_aujourd_hui():
    """Le bug : 43 jours écoulés pour octobre au lieu de 31."""
    store = _store()
    forecast = forecast_month(store, tenant_id="t-1", period=PAST_PERIOD)
    assert forecast.days_elapsed == days_in_month(2026, 10)
    assert forecast.days_elapsed == 31


def test_la_projection_dune_periode_passee_reproduit_les_heures_consommees():
    """Sur une période close, projeter ne doit rien inventer : 5,4 h → 5,4 h."""
    store = _store(hours=5.4)
    forecast = forecast_month(store, tenant_id="t-1", period=PAST_PERIOD)
    assert forecast.hours_used == 5.4
    assert forecast.projected_hours == 5.4
    assert forecast.projected_cost_usd == 270.0
    assert forecast.projected_pct == 13.5


def test_le_mois_en_cours_compte_les_jours_ecoules_reels():
    """Mois courant : on compte jusqu'à aujourd'hui, pas jusqu'à la fin du mois."""
    store = _store()
    today = datetime.now(timezone.utc).strftime("%Y-%m")
    forecast = forecast_month(store, tenant_id="t-1", period=today)
    assert forecast.days_elapsed == datetime.now(timezone.utc).day
    assert 1 <= forecast.days_elapsed < days_in_month(*_year_month(today))


def _year_month(period: str) -> tuple[int, int]:
    year, month = (int(part) for part in period.split("-")[:2])
    return year, month


def test_l_instant_d_evaluation_ne_depasse_jamais_la_fin_de_periode():
    assert evaluation_instant(PAST_PERIOD) <= period_end(PAST_PERIOD)
    assert evaluation_instant(PAST_PERIOD) == period_end(PAST_PERIOD)
    current = utcnow().strftime("%Y-%m")
    assert evaluation_instant(current) <= utcnow()


def test_un_as_of_explicite_prime_toujours():
    moment = datetime(2026, 10, 10, tzinfo=timezone.utc)
    assert evaluation_instant(PAST_PERIOD, moment) == moment


def test_le_taux_journalier_ne_s_appuie_sur_zero_ou_trente_jours():
    store = _store(hours=5.4)
    burn = daily_burn_rate(store, tenant_id="t-1", period=PAST_PERIOD)
    assert burn.days_elapsed not in (0, 30)
    assert burn.hours_per_day == pytest.approx(5.4 / 31, abs=1e-6)


def test_aucun_test_rodu_ne_donne_de_heures_nulles_qui_cachent_une_erreur():
    store = FakeStore()
    store.save_tenant(make_tenant("t-1", budget_hours=40.0))
    forecast = forecast_month(store, tenant_id="t-1", period=PAST_PERIOD)
    assert forecast.hours_used == 0.0
    assert forecast.projected_hours == 0.0
    assert forecast.exhaustion_date is None


def test_un_budget_zero_ne_provoque_pas_de_division_par_zero():
    store = _store(hours=5.4, budget=0.0)
    forecast = forecast_month(store, tenant_id="t-1", period=PAST_PERIOD)
    assert forecast.projected_pct == 0.0
    assert forecast.monthly_budget_hours == 0.0


def test_une_rupture_de_budget_est_datee_quand_la_projection_depasse():
    store = _store(hours=30.0, budget=10.0)
    forecast = forecast_month(store, tenant_id="t-1", period=PAST_PERIOD)
    assert forecast.exceeds_budget is True
    assert forecast.projected_hours > forecast.monthly_budget_hours


def test_le_cout_projete_utilise_le_tarif_horaire_fourni():
    store = _store(hours=5.4)
    forecast = forecast_month(
        store, tenant_id="t-1", period=PAST_PERIOD, hourly_rate=100.0
    )
    assert forecast.projected_cost_usd == 540.0


def test_le_run_hors_periode_n_entame_pas_la_prevision():
    store = _store(hours=5.4)
    store.save_run(
        Run(
            run_id="run-old", config_id="cfg-app-1", app_id="app-1", tenant_id="t-1",
            trigger="cicd", commit_from="a", commit_to="b", scope_decision="full",
            status="completed", started_at="2026-09-05T08:00:00Z",
            ended_at="2026-09-05T09:00:00Z", duration_s=3600.0, task_hours=99.0,
            cost_usd=4950.0,
        )
    )
    forecast = forecast_month(store, tenant_id="t-1", period=PAST_PERIOD)
    assert forecast.hours_used == 5.4
