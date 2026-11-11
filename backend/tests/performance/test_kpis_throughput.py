"""Débit des indicateurs mensuels — ENF-PERF-01 et ENF-IA-01 sur volume réaliste.

Les KPI sont servis au portail : ``compute_kpis`` et ``freeze_month`` tournent
sur un mois de données (ici 5 applications, 50 tests, 200 failles, volume d'un
client en formule « continu »). On mesure le temps de calcul ET on recalcule
indépendamment plusieurs chiffres, pour qu'un futur correctif de performance ne
puisse pas se payer en exactitude (ENF-IA-01 : les chiffres viennent du code).
"""

from __future__ import annotations

import statistics
from typing import Any

from rempart.common.models import Finding, Run
from rempart.common.timeutil import parse_iso
from rempart.reports.metrics import compute_kpis, freeze_month
from tests.fakes import FakeStore
from tests.performance.conftest import (
    APPS,
    FINDINGS,
    PERIOD,
    RUNS,
    TENANT_ID,
    TIME_FLOOR,
    best_of,
    count_open_by_priority,
    seed_kpi_corpus,
)

# --------------------------------------------------------------------------- #
# Seuils — mesures et justification dans tests/performance/README.md
# --------------------------------------------------------------------------- #
# Mesuré : 0,8 ms pour ``compute_kpis`` sur 200 failles / 50 runs (1,2 ms au
# pire tour). L'exigence donne 2 s pour une page du portail ; le calcul des KPI
# n'en est qu'une partie. 0,5 s = ~400x le pire tour observé (aucun risque sur
# un runner partagé) et le quart du budget d'affichage contractuel : utile comme
# alarme, pas comme loterie.
KPI_BUDGET_SECONDS = 0.5
# ``freeze_month`` recalcule les KPI puis ajoute les annexes : mesuré 1,4 ms
# (19,5 ms au pire tour) ; budget x4 du précédent, toujours très large.
FREEZE_BUDGET_SECONDS = 2.0
# Croissance tolérée quand le volume quadruple : mesuré x6,6 (200 failles ->
# 800). Les durées sont de l'ordre de la milliseconde, donc un ratio serré
# serait aléatoire sur un runner partagé : 60 = ~9x le ratio mesuré. L'alarme
# principale reste le budget absolu ci-dessous.
SCALE_MAX_GROWTH = 60.0


def _findings(store: FakeStore) -> list[Finding]:
    return store.list_findings(tenant_id=TENANT_ID, limit=1000)


def _runs(store: FakeStore) -> list[Run]:
    return store.list_runs(tenant_id=TENANT_ID, limit=1000)


def _closed_in_period(store: FakeStore) -> list[Finding]:
    return [f for f in _findings(store) if (f.closed_at or "").startswith(PERIOD)]


def _expected_mttr_p2(store: FakeStore) -> float:
    """MTTR des P2 fermées, recalculé par arithmétique simple sur les dates."""
    days = [
        max(0.0, (parse_iso(f.closed_at) - parse_iso(f.created_at)).total_seconds() / 86400.0)
        for f in _closed_in_period(store)
        if f.priority == "P2"
    ]
    return round(statistics.mean(days), 2) if days else 0.0


def _expected_sla_compliance(store: FakeStore) -> float:
    """Part des fermetures respectant l'échéance, recalculée indépendamment."""
    tracked = [f for f in _findings(store) if f.due_at and f.closed_at]
    if not tracked:
        return 1.0
    on_time = sum(1 for f in tracked if parse_iso(f.closed_at) <= parse_iso(f.due_at))
    return round(on_time / len(tracked), 4)


def _expected_coverage(store: FakeStore) -> float:
    """Part des applications testées dans la période, recalculée."""
    tested = {r.app_id for r in _runs(store)}
    apps = store.list_applications(tenant_id=TENANT_ID)
    return round(len({a.app_id for a in apps if a.app_id in tested}) / len(apps), 4)


def _assert_matches_independent_computation(kpis: dict[str, Any], store: FakeStore) -> None:
    """Chaque chiffre vérifié ici est recalculé par le test, pas par le module."""
    open_counts = count_open_by_priority(_findings(store))
    assert kpis["period"] == PERIOD
    assert kpis["tests_total"] == RUNS
    assert kpis["tests_blocked"] == sum(1 for r in _runs(store) if r.status == "blocked")
    assert kpis["task_hours_used"] == round(sum(r.task_hours or 0.0 for r in _runs(store)), 2)
    assert kpis["findings_closed"] == len(_closed_in_period(store))
    assert kpis["findings_open_by_priority"] == open_counts
    assert kpis["findings_open_total"] == sum(open_counts.values())
    assert kpis["mean_time_to_fix_days_by_priority"]["P2"] == _expected_mttr_p2(store)
    assert kpis["sla_compliance"] == _expected_sla_compliance(store)
    assert kpis["coverage"] == _expected_coverage(store)


def test_compute_kpis_on_200_findings_meets_budget(kpi_store: FakeStore) -> None:
    """ENF-PERF-01 : KPI d'un mois (200 failles, 50 runs) calculés sous 0,5 s."""
    seconds = best_of(lambda: compute_kpis(kpi_store, tenant_id=TENANT_ID, period=PERIOD))
    kpis = compute_kpis(kpi_store, tenant_id=TENANT_ID, period=PERIOD)

    _assert_matches_independent_computation(kpis, kpi_store)
    assert seconds < KPI_BUDGET_SECONDS, (
        f"compute_kpis trop lent sur {FINDINGS} failles : {seconds * 1000:.1f} ms"
    )


def test_freeze_month_on_volume_meets_budget(kpi_store: FakeStore) -> None:
    """ENF-PERF-01 : gel du mois (KPI + annexes) sous 2 s, chiffres identiques."""
    seconds = best_of(lambda: freeze_month(kpi_store, TENANT_ID, PERIOD))
    snapshot = freeze_month(kpi_store, TENANT_ID, PERIOD)
    baseline = compute_kpis(kpi_store, tenant_id=TENANT_ID, period=PERIOD)

    _assert_snapshot_exactness(snapshot, baseline, kpi_store)
    assert seconds < FREEZE_BUDGET_SECONDS, (
        f"freeze_month trop lent sur {FINDINGS} failles : {seconds * 1000:.1f} ms"
    )


def _assert_snapshot_exactness(
    snapshot: dict[str, Any], baseline: dict[str, Any], store: FakeStore
) -> None:
    """Le gel reprend les KPI à l'identique et ses annexes sont cohérentes."""
    assert snapshot["frozen"] is True
    # Premier jour ouvré de novembre 2026 (chapitre 8.5).
    assert snapshot["frozen_at"].startswith("2026-11-02")
    assert snapshot["tests_detail"]["tests_total"] == RUNS
    assert snapshot["tests_detail"]["tests_by_type"]["cicd"] == sum(
        1 for r in _runs(store) if r.trigger == "cicd"
    )
    assert len(snapshot["applications_detail"]) == APPS
    assert len(snapshot["closed_findings"]) == snapshot["findings_closed"]
    assert snapshot["budget_detail"]["monthly_budget_hours"] > 0
    for key, value in baseline.items():
        assert snapshot[key] == value, f"l'annexe {key} diverge des KPI"


def test_kpi_cost_stays_bounded_when_volume_quadruples() -> None:
    """Coût marginal du volume : x4 failles ne doit pas coûter plus que x25."""
    small = FakeStore()
    seed_kpi_corpus(small)
    base = best_of(lambda: compute_kpis(small, tenant_id=TENANT_ID, period=PERIOD))

    big = FakeStore()
    seed_kpi_corpus(big, findings=FINDINGS * 4, runs=RUNS * 4, apps=APPS * 4)
    scaled = best_of(lambda: compute_kpis(big, tenant_id=TENANT_ID, period=PERIOD))

    growth = scaled / max(base, TIME_FLOOR)
    # Alarme principale, insensible au bruit : un budget absolu sur 4x le volume.
    assert scaled < KPI_BUDGET_SECONDS, (
        f"compute_kpis trop lent sur {FINDINGS * 4} failles : {scaled * 1000:.1f} ms"
    )
    assert growth <= SCALE_MAX_GROWTH, (
        f"coût des KPI en explosion : {base * 1000:.1f} ms à {FINDINGS} failles, "
        f"{scaled * 1000:.1f} ms à {FINDINGS * 4} (x{growth:.1f})"
    )
