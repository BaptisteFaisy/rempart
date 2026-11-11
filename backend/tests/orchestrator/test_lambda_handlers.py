"""Tests des adaptateurs Lambda de l'orchestrateur (CONTRACT-PHASE0 § 2).

Aucun test ne touche AWS ni le réseau : les handlers reçoivent une fabrique de
``Deps`` construite sur les fakes de ``tests.fakes``.
"""

from __future__ import annotations

import inspect
from typing import Any

import pytest

from rempart.common.config import Settings
from rempart.common.models import Application, Tenant, TestConfig
from rempart.common.store import Store
from rempart.common.timeutil import iso, utcnow
from rempart.orchestrator import lambda_handlers as lh
from rempart.orchestrator import tasks
from rempart.orchestrator.github_client import GitHubClient
from rempart.orchestrator.sa_client import SecurityAgentClient
from rempart.orchestrator.task_types import Deps
from tests.fakes import FakeGitHub, FakeSecurityAgentClient, FakeStore

HANDLER_NAMES = (
    "budget_gate",
    "start_run",
    "poll_run",
    "collect_findings",
    "dispatch_triage",
    "create_tickets",
    "request_remediation",
    "close_or_reopen",
    "discover_runs",
)

START_EVENT = {"app_id": "app-1", "tenant_id": "t-1", "pentest_id": "pt-1"}


def _tenant() -> Tenant:
    """Client de démonstration : mandat valide, free tier confirmé, 10 h/mois."""
    return Tenant(
        tenant_id="t-1",
        name="Acme",
        aws_account_id="123456789012",
        region="eu-west-3",
        role_arn="arn:aws:iam::123456789012:role/rempart",
        external_id="ext",
        plan="continu",
        contacts=[],
        monthly_budget_hours=10.0,
        mandate_status="valid",
        free_tier_confirmed=True,
        created_at="2026-11-01T00:00:00Z",
    )


def _application() -> Application:
    """Application critique exposée, espace agent ``space-1``, dépôt ``acme/shop``."""
    return Application(
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


def _delivery_config() -> TestConfig:
    """Configuration de livraison : celle que la découverte CI/CD interroge."""
    return TestConfig(
        config_id="cfg-delivery",
        app_id="app-1",
        sa_pentest_id="pt-delivery",
        kind="delivery",
        scope={"paths": ["/orders"]},
        risk_types=["IDOR"],
        blocking_threshold="High",
        schedule=None,
    )


def _seed_store() -> FakeStore:
    """FakeStore avec un client, une application et un pentest de livraison."""
    store = FakeStore()
    store.save_tenant(_tenant())
    store.save_application(_application())
    store.save_config(_delivery_config())
    return store


def _deps(
    store: FakeStore | None = None,
    sa: FakeSecurityAgentClient | None = None,
    github: Any = None,
    **settings_kw: Any,
) -> Deps:
    """Deps 100 % fakes (store, client Security Agent, client GitHub optionnel)."""
    return Deps(
        store=store if store is not None else _seed_store(),
        sa=sa if sa is not None else FakeSecurityAgentClient(),
        settings=Settings(**settings_kw),
        github=github,
    )


def _run(name: str, event: dict[str, Any], deps: Deps) -> dict[str, Any]:
    """Invoque un handler par son nom, avec les fakes injectés."""
    return getattr(lh, name)(event, None, deps_factory=lambda: deps)


def _seed_job(deps: Deps, job_id: str = "job-1") -> dict[str, Any]:
    """Scénario : un job terminé portant une faille critique."""
    deps.sa.jobs[job_id] = {"jobId": job_id, "status": "COMPLETED"}
    deps.sa.seed_finding(
        job_id=job_id,
        title="IDOR on orders",
        severity="Critical",
        confidence="High",
        risk_type="IDOR",
        entry_point="/orders/{id}",
    )
    return {"app_id": "app-1", "tenant_id": "t-1", "run_id": job_id}


def _first_finding(deps: Deps, event: dict[str, Any]) -> str:
    """Collecte les failles et rend l'identifiant de la première créée."""
    collected = _run("collect_findings", event, deps)
    return collected["findings_created"][0]


# --------------------------------------------------------------------------- #
# Surface publique et signature AWS
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("name", HANDLER_NAMES)
def test_handler_is_exposed_with_lambda_signature(name: str) -> None:
    handler = getattr(lh, name)
    assert callable(handler)
    inspect.signature(handler).bind({}, None)  # (event, context) acceptés
    assert lh.HANDLERS[name] is handler


@pytest.mark.parametrize("name", HANDLER_NAMES)
def test_handler_never_raises_even_on_empty_event(name: str) -> None:
    """§ 2.4 : un payload incomplet rend un dict, il ne lève jamais."""
    assert isinstance(_run(name, {}, _deps()), dict)


def test_handler_returns_error_dict_when_task_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(payload: dict[str, Any], deps: Deps) -> dict[str, Any]:
        raise RuntimeError("continuum down")

    monkeypatch.setattr(tasks, "budget_gate", boom)
    out = _run("budget_gate", {"tenant_id": "t-1", "app_id": "app-1"}, _deps())
    assert out == {"task": "budget_gate", "error": "RuntimeError: continuum down"}


def test_handler_returns_error_dict_when_deps_build_fails() -> None:
    def broken() -> Deps:
        raise OSError("no credentials")

    out = lh.budget_gate({"tenant_id": "t-1"}, None, deps_factory=broken)
    assert out["task"] == "budget_gate"
    assert "OSError" in out["error"]


# --------------------------------------------------------------------------- #
# Chaque handler délègue bien à sa tâche
# --------------------------------------------------------------------------- #
def test_budget_gate_allows_valid_mandate() -> None:
    out = _run("budget_gate", {"tenant_id": "t-1", "app_id": "app-1"}, _deps())
    assert out["allowed"] is True


def test_budget_gate_refuses_unknown_tenant_without_raising() -> None:
    out = _run("budget_gate", {"tenant_id": "t-404", "app_id": "app-1"}, _deps())
    assert out["allowed"] is False
    assert out["reason"] == "unknown_tenant"


def test_start_run_records_running_run() -> None:
    deps = _deps()
    out = _run("start_run", START_EVENT, deps)
    run = deps.store.get_run(out["run_id"])
    assert run is not None
    assert run.status == "running"


def test_poll_run_counts_iterations_across_polls() -> None:
    deps = _deps()
    started = _run("start_run", START_EVENT, deps)
    first = _run("poll_run", started, deps)
    assert first["run_status"] == "completed"
    assert first["done"] is True
    assert first["iterations"] == 1
    second = _run("poll_run", first, deps)
    assert second["iterations"] == 2


def test_poll_run_iterations_reach_the_four_hour_cap() -> None:
    """Le compteur monte jusqu'à 240, ce que la Choice § 3 transforme en échec."""
    deps = _deps()
    started = _run("start_run", START_EVENT, deps)
    out = _run("poll_run", {**started, "iterations": 239}, deps)
    assert out["iterations"] == 240


def test_collect_findings_creates_and_prioritises() -> None:
    deps = _deps()
    event = _seed_job(deps)
    out = _run("collect_findings", event, deps)
    assert len(out["findings_created"]) == 1
    assert deps.store.get_finding(out["findings_created"][0]).priority == "P1"


def test_dispatch_triage_records_decisions() -> None:
    deps = _deps()
    event = _seed_job(deps)
    collected = _run("collect_findings", event, deps)
    out = _run("dispatch_triage", {**event, **collected}, deps)
    assert out["triaged"] == 1


def test_create_tickets_opens_github_issue() -> None:
    github = FakeGitHub()
    deps = _deps(github=github, github_owner="acme")
    event = _seed_job(deps)
    finding_id = _first_finding(deps, event)
    finding = deps.store.get_finding(finding_id)
    finding.status = "confirmed"
    deps.store.save_finding(finding)

    out = _run("create_tickets", {**event, "confirmed": [finding_id]}, deps)
    assert out["tickets"]
    assert github.issues


def test_request_remediation_links_pull_request() -> None:
    deps = _deps()
    event = _seed_job(deps)
    finding_id = _first_finding(deps, event)

    out = _run(
        "request_remediation", {"app_id": "app-1", "confirmed": [finding_id]}, deps
    )
    assert out["remediation_prs"] == [finding_id]
    assert deps.store.get_finding(finding_id).remediation_pr_url


def test_close_or_reopen_closes_findings_gone_from_retest() -> None:
    deps = _deps()
    event = _seed_job(deps)
    finding_id = _first_finding(deps, event)
    finding = deps.store.get_finding(finding_id)
    finding.status = "in_remediation"
    deps.store.save_finding(finding)

    out = _run("close_or_reopen", {"app_id": "app-1", "run_id": "job-retest"}, deps)
    assert out["closed"] == [finding_id]
    assert out["reopened"] == []
    assert deps.store.get_finding(finding_id).status == "closed"


def test_discover_runs_wraps_discovery_counts() -> None:
    sa = FakeSecurityAgentClient()
    sa.jobs["job-cicd"] = {
        "jobId": "job-cicd",
        "pentestId": "pt-delivery",
        "status": "COMPLETED",
        "startedAt": iso(utcnow()),
    }
    out = _run("discover_runs", {}, _deps(sa=sa))
    assert out == {"discovered": 1, "run_ids": ["job-cicd"]}


# --------------------------------------------------------------------------- #
# build_deps : point d'injection unique (§ 2.5)
# --------------------------------------------------------------------------- #
def test_build_deps_without_token_builds_no_github_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("REMPART_GITHUB_TOKEN", raising=False)
    deps = lh.build_deps()
    assert deps.github is None
    assert isinstance(deps.store, Store)
    assert isinstance(deps.sa, SecurityAgentClient)


def test_build_deps_with_token_builds_github_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("REMPART_GITHUB_TOKEN", raising=False)
    monkeypatch.setenv("GITHUB_TOKEN", "tok-test")
    deps = lh.build_deps(Settings(github_api="https://ghe.example.com/"))
    assert isinstance(deps.github, GitHubClient)
    assert deps.github.token == "tok-test"
    assert deps.github.api == "https://ghe.example.com"


def test_build_deps_prefers_the_rempart_prefixed_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("REMPART_GITHUB_TOKEN", "tok-prod")
    monkeypatch.setenv("GITHUB_TOKEN", "tok-test")
    assert lh.build_deps().github.token == "tok-prod"


def test_build_deps_wires_settings_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("REMPART_TABLE_PREFIX", "test-")
    monkeypatch.setenv("REMPART_REGION", "us-east-1")
    monkeypatch.setenv("REMPART_SA_ENDPOINT_URL", "http://localhost:4566")
    deps = lh.build_deps()
    assert deps.settings.table_prefix == "test-"
    assert deps.store._table_prefix == "test-"
    assert deps.sa._region == "us-east-1"
    assert deps.sa._endpoint_url == "http://localhost:4566"
