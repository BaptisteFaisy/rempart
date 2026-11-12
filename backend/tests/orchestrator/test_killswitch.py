"""Tests du coupe-circuit global (kill-switch) de l'orchestrateur.

Le kill-switch est indépendant de tous les autres garde-fous : quand il est
levé, ``budget_gate`` refuse le test avant même de résoudre le tenant ou
d'évaluer le mandat, le free tier, le quota, la fenêtre ou le budget.
"""

from rempart.common.config import Settings
from rempart.common.models import Application, Tenant
from rempart.orchestrator.tasks import Deps, budget_gate
from tests.fakes import FakeSecurityAgentClient, FakeStore


def _seed() -> FakeStore:
    store = FakeStore()
    store.save_tenant(
        Tenant(
            tenant_id="t-1",
            name="Acme",
            aws_account_id="123456789012",
            region="eu-west-3",
            role_arn="arn:aws:iam::123456789012:role/rempart",
            external_id="ext",
            plan="continu",
            contacts=[],
            monthly_budget_hours=100.0,
            mandate_status="valid",
            free_tier_confirmed=True,
            created_at="2026-11-01T00:00:00Z",
        )
    )
    store.save_application(
        Application(
            app_id="app-1",
            tenant_id="t-1",
            name="ShopLite",
            criticality="high",
            internet_exposed=True,
            data_types=["personal"],
            environment="staging",
            agent_space_id="space-1",
            domains=["shop.acme.com"],
            repositories=["acme/shop"],
            team="Core",
            ticket_channel="github",
            context={},
            created_at="2026-11-01T00:00:00Z",
        )
    )
    return store


def _deps(kill_switch: bool) -> Deps:
    return Deps(
        store=_seed(),
        sa=FakeSecurityAgentClient(),
        settings=Settings(kill_switch=kill_switch),
    )


def test_budget_gate_refuses_when_kill_switch_active():
    deps = _deps(kill_switch=True)
    out = budget_gate({"tenant_id": "t-1", "app_id": "app-1"}, deps)
    assert out["allowed"] is False
    assert out["reason"] == "kill_switch"


def test_kill_switch_refusal_is_audited():
    deps = _deps(kill_switch=True)
    budget_gate({"tenant_id": "t-1", "app_id": "app-1"}, deps)
    events = deps.store.list_audit(action="run.refused_kill_switch")
    assert len(events) == 1
    assert events[0].object_type == "tenant"
    assert events[0].object_id == "t-1"
    assert events[0].result == "denied"


def test_budget_gate_allows_when_kill_switch_inactive():
    deps = _deps(kill_switch=False)
    out = budget_gate({"tenant_id": "t-1", "app_id": "app-1"}, deps)
    assert out["allowed"] is True
