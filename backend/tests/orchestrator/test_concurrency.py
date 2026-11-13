"""Quota de tests simultanés par compte client (EF-ORC-05, chapitre 11.1).

AWS n'autorise que 5 tests simultanés par compte et par région, quota non
ajustable. Sans cette garde, un sixième test échoue côté AWS et personne ne le
rejoue : le client perd sa fenêtre de livraison en silence.
"""

from __future__ import annotations

import pytest

from rempart.common.config import Settings
from rempart.common.models import Run
from rempart.orchestrator.concurrency import (
    BLOCKING_STATUSES,
    DEFAULT_CONCURRENT_TEST_QUOTA,
    can_start,
    count_running,
    quota_of,
)
from rempart.orchestrator.tasks import budget_gate
from tests.fakes_store import FakeStore
from tests.integration.conftest import make_deps, seed_two_tenants

TENANT_A = "tenant-a"
TENANT_B = "tenant-b"
APP_A = "app-shop"


def _run(run_id: str, status: str, tenant_id: str = TENANT_A) -> Run:
    return Run(
        run_id=run_id,
        config_id="cfg-1",
        app_id=APP_A,
        tenant_id=tenant_id,
        trigger="manual",
        commit_from="a",
        commit_to="b",
        scope_decision="full",
        status=status,
        started_at="2026-11-01T10:00:00Z",
        ended_at=None if status in BLOCKING_STATUSES else "2026-11-01T11:00:00Z",
        duration_s=None,
        task_hours=None,
        cost_usd=None,
    )


def _seed_runs(store: FakeStore, count: int, tenant_id: str = TENANT_A) -> None:
    for index in range(count):
        store.save_run(_run(f"run-{tenant_id}-{index}", "running", tenant_id))


def test_quota_matches_the_documented_aws_limit():
    """Le chiffre doit rester celui de la documentation AWS (chapitre 11.1)."""
    assert DEFAULT_CONCURRENT_TEST_QUOTA == 5
    assert Settings().concurrent_test_quota == 5


def test_only_queued_and_running_runs_occupy_a_slot():
    store = FakeStore()
    seed_two_tenants(store)
    store.save_run(_run("r-queued", "queued"))
    store.save_run(_run("r-running", "running"))
    for status in ("completed", "failed", "stopped", "blocked"):
        store.save_run(_run(f"r-{status}", status))
    assert count_running(store, TENANT_A) == 2


def test_can_start_refuses_the_sixth_test():
    store = FakeStore()
    seed_two_tenants(store)
    _seed_runs(store, 5)
    allowed, running = can_start(store, TENANT_A)
    assert running == 5
    assert allowed is False


def test_can_start_allows_while_under_the_quota():
    store = FakeStore()
    seed_two_tenants(store)
    _seed_runs(store, 4)
    allowed, running = can_start(store, TENANT_A)
    assert running == 4
    assert allowed is True


def test_a_finished_run_frees_its_slot():
    store = FakeStore()
    seed_two_tenants(store)
    _seed_runs(store, 5)
    assert can_start(store, TENANT_A)[0] is False

    done = store.get_run("run-tenant-a-0")
    done.status = "completed"
    store.save_run(done)
    assert can_start(store, TENANT_A)[0] is True


def test_quota_is_counted_per_tenant():
    """Le quota AWS est par compte : chaque client a ses 5 places."""
    store = FakeStore()
    seed_two_tenants(store)
    _seed_runs(store, 5, TENANT_A)
    _seed_runs(store, 1, TENANT_B)
    assert can_start(store, TENANT_A)[0] is False
    assert can_start(store, TENANT_B)[0] is True
    assert count_running(store, TENANT_B) == 1


def test_budget_gate_refuses_with_the_quota_reason():
    deps = make_deps(seed_two_tenants())
    _seed_runs(deps.store, 5)

    out = budget_gate({"tenant_id": TENANT_A, "app_id": APP_A}, deps)
    assert out["allowed"] is False
    assert out["reason"] == "concurrency_quota_reached"
    assert out["running"] == 5


def test_budget_gate_writes_an_audit_entry_on_refusal():
    deps = make_deps(seed_two_tenants())
    _seed_runs(deps.store, 5)
    budget_gate({"tenant_id": TENANT_A, "app_id": APP_A}, deps)

    actions = [e.action for e in deps.store.list_audit()]
    assert "run.refused_quota" in actions


def test_quota_is_configurable_without_touching_the_code():
    store = FakeStore()
    seed_two_tenants(store)
    _seed_runs(store, 2)
    # Quota relevé à 3 : le troisième test passe encore.
    assert can_start(store, TENANT_A, limit=3)[0] is True
    # Quota abaissé à 2 : il est déjà atteint.
    assert can_start(store, TENANT_A, limit=2)[0] is False


def test_quota_of_reads_the_settings_override():
    assert quota_of(Settings(concurrent_test_quota=8)) == 8
    assert quota_of(Settings()) == DEFAULT_CONCURRENT_TEST_QUOTA
    # Une valeur invalide ne doit pas désactiver la garde.
    assert quota_of(Settings(concurrent_test_quota=0)) == DEFAULT_CONCURRENT_TEST_QUOTA


def test_settings_read_the_quota_from_the_environment(monkeypatch):
    monkeypatch.setenv("REMPART_CONCURRENT_TEST_QUOTA", "3")
    assert Settings.from_env().concurrent_test_quota == 3
    monkeypatch.delenv("REMPART_CONCURRENT_TEST_QUOTA")
    assert Settings.from_env().concurrent_test_quota == 5


@pytest.mark.parametrize("status", BLOCKING_STATUSES)
def test_every_blocking_status_is_counted(status):
    store = FakeStore()
    seed_two_tenants(store)
    store.save_run(_run("r-1", status))
    assert count_running(store, TENANT_A) == 1


def test_budget_gate_resout_le_tenant_depuis_l_application():
    """INCIDENT RÉEL (13 nov 2026) : la machine d'états ne porte pas `tenant_id`.

    Le payload réel de `RempartPentestLifecycle` est `{app_id, pentest_id, …}` ;
    `payload["tenant_id"]` levait `KeyError`, la machine échouait sur
    « Invalid path '$.allowed' » et **aucun test n'a jamais pu partir** — pas
    même le cron mensuel, dont le payload ne porte que `{"trigger": "schedule"}`.
    """
    deps = make_deps(seed_two_tenants())
    out = budget_gate({"app_id": APP_A}, deps)
    assert out["allowed"] is True
    assert out["tenant_id"] == TENANT_A


def test_budget_gate_refuse_proprement_sans_application_ni_tenant():
    """Sans application ni tenant : refus motivé, pas une exception."""
    deps = make_deps(seed_two_tenants())
    out = budget_gate({"trigger": "schedule"}, deps)
    assert out["allowed"] is False
    assert out["reason"] == "unknown_tenant"
