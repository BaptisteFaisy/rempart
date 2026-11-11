"""Amorçage partagé des tests d'intégration du parcours complet (chapitre 8).

Un seul jeu d'amorçage pour tous les tests de parcours : deux tenants, chacun
avec son application et sa configuration de test. Les failles sont semées sur
le client de Sécurité factice, jamais sur AWS.
"""

from __future__ import annotations

from typing import Any

import pytest

from rempart.common.config import Settings
from rempart.common.models import Application, Tenant, TestConfig
from rempart.orchestrator.task_types import Deps
from tests.fakes import (
    FakeGitHub,
    FakeModelClient,
    FakeSecurityAgentClient,
    FakeStore,
)

PERIOD = "2026-10"
TENANT_A = "tenant-a"
TENANT_B = "tenant-b"
APP_A = "app-shop"
APP_B = "app-book"
SPACE_A = "space-shop"
SPACE_B = "space-book"
PENTEST_A = "pt-shop-delivery"
PENTEST_B = "pt-book-delivery"
BUDGET_HOURS = 40.0


def make_tenant(tenant_id: str, name: str, *, mandate: str = "valid") -> Tenant:
    return Tenant(
        tenant_id=tenant_id,
        name=name,
        aws_account_id="123456789012",
        region="eu-west-3",
        role_arn=f"arn:aws:iam::123456789012:role/rempart-ops-{tenant_id}",
        external_id=f"ext-{tenant_id}",
        plan="continu",
        contacts=[{"name": "Ops", "email": f"ops@{tenant_id}.example", "role": "security"}],
        monthly_budget_hours=BUDGET_HOURS,
        mandate_status=mandate,
        created_at="2026-10-01T08:00:00Z",
        free_tier_confirmed=True,
    )


def make_application(tenant_id: str, app_id: str, name: str, space_id: str) -> Application:
    """Application critique, exposée, traitant des données personnelles.

    Ces trois attributs font monter la matrice de priorité : Critical+High
    donne P1, et une faille High+High donne P1 aussi (au lieu de P2).
    """
    return Application(
        app_id=app_id,
        tenant_id=tenant_id,
        name=name,
        criticality="high",
        internet_exposed=True,
        data_types=["personal"],
        environment="staging",
        agent_space_id=space_id,
        domains=[f"{app_id}.demo.example"],
        repositories=[f"demo/{app_id}"],
        team="Core",
        ticket_channel="github",
        context={"business": "integration test"},
        created_at="2026-10-01T08:00:00Z",
    )


def make_config(app_id: str, pentest_id: str) -> TestConfig:
    return TestConfig(
        config_id=f"cfg-{app_id}-delivery",
        app_id=app_id,
        sa_pentest_id=pentest_id,
        kind="delivery",
        scope={"paths": ["/orders", "/search"]},
        risk_types=["IDOR", "SQLI"],
        blocking_threshold="High",
        schedule=None,
    )


def seed_tenant(
    store: FakeStore, tenant_id: str, name: str, app_id: str, space_id: str,
    pentest_id: str, *, mandate: str = "valid",
) -> None:
    """Enregistre un tenant, son application et sa configuration de test."""
    store.save_tenant(make_tenant(tenant_id, name, mandate=mandate))
    store.save_application(make_application(tenant_id, app_id, name, space_id))
    store.save_config(make_config(app_id, pentest_id))


def seed_two_tenants(store: FakeStore | None = None) -> FakeStore:
    store = store or FakeStore()
    seed_tenant(store, TENANT_A, "Northwind Retail", APP_A, SPACE_A, PENTEST_A)
    seed_tenant(store, TENANT_B, "Contoso Books", APP_B, SPACE_B, PENTEST_B)
    return store


def make_deps(
    store: FakeStore | None = None,
    *,
    github: Any = None,
    model_client: Any = None,
    settings: Settings | None = None,
) -> Deps:
    """Deps prêtes à l'emploi : store à deux tenants, GitHub et SA factices."""
    if settings is None:
        settings = Settings(github_owner="demo")
    return Deps(
        store=store if store is not None else seed_two_tenants(),
        sa=FakeSecurityAgentClient(),
        settings=settings,
        github=github if github is not None else FakeGitHub(),
        model_client=model_client or FakeModelClient(),
    )


@pytest.fixture
def deps() -> Deps:
    return make_deps()


@pytest.fixture
def store() -> FakeStore:
    return seed_two_tenants()


def seed_idor(sa: FakeSecurityAgentClient, job_id: str, *, title: str = "IDOR on orders") -> str:
    """Sème une faille Critical/High : la matrice doit la classer P1."""
    raw = sa.seed_finding(
        job_id,
        severity="Critical",
        confidence="High",
        risk_type="IDOR",
        entry_point="/orders/{id}",
        parameter="id",
        title=title,
        description="Un client connecté peut lire les commandes d'un autre client.",
    )
    return str(raw["findingId"])


def seed_low(sa: FakeSecurityAgentClient, job_id: str) -> str:
    """Sème une faille Low/Low : la matrice doit la classer P4."""
    raw = sa.seed_finding(
        job_id,
        severity="Low",
        confidence="Low",
        risk_type="InfoLeak",
        entry_point="/errors",
        title="Verbose error page",
        description="La page d'erreur expose la version du serveur.",
    )
    return str(raw["findingId"])


def start_and_complete(deps: Deps, app_id: str, tenant_id: str, pentest_id: str) -> str:
    """Démarre un test et le fait aboutir ; rend son identifiant de job."""
    from rempart.orchestrator.tasks import poll_run, start_run

    payload = {
        "app_id": app_id,
        "tenant_id": tenant_id,
        "pentest_id": pentest_id,
        "trigger": "manual",
        "commit_from": "aaa111",
        "commit_to": "bbb222",
    }
    started = start_run(payload, deps)
    job_id = started["run_id"]
    deps.sa.set_job_outcome(job_id, "COMPLETED")
    poll_run({**payload, "run_id": job_id}, deps)
    return job_id
