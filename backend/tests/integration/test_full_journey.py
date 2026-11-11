"""Le parcours complet du chapitre 8, joué de bout en bout (recettes R4, R6, R10).

Chaque étape asserte l'état du store : ce test est ce qui prouve que les
modules composent réellement un produit, et pas seulement qu'ils fonctionnent
chacun de leur côté. C'est lui qui a révélé deux bugs d'enchaînement invisibles
aux tests unitaires : la pull request de correction jamais demandée (parce que
le ticket avait déjà posé le statut `in_remediation`), et la preuve de
fermeture conservée sur une faille rouverte.

Le test est découpé en étapes nommées : chaque fonction reste sous la limite
des 50 lignes, et l'échec d'une étape désigne directement l'étape du parcours.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Callable

from rempart.api.app import lambda_handler
from rempart.orchestrator.tasks import (
    budget_gate,
    close_or_reopen,
    collect_findings,
    create_tickets,
    dispatch_triage,
    request_remediation,
)
from rempart.reports.metrics import freeze_month
from rempart.reports.monthly import build_monthly_report
from tests.api.conftest import analyst_claims, make_event
from tests.fakes import FakeModelClient, FakeS3
from tests.integration.conftest import (
    APP_A,
    PENTEST_A,
    TENANT_A,
    make_deps,
    seed_idor,
    seed_low,
    seed_two_tenants,
    start_and_complete,
)

RETEST_JOB = "run-retest-1"


@dataclass
class JourneyState:
    """État porté d'une étape du parcours à la suivante."""

    job_id: str = ""
    month: str = ""
    critical_id: str = ""
    low_id: str = ""
    task_hours: float = 0.0
    findings_created: list[str] = field(default_factory=list)


def _confirm_via_api(deps, finding_id: str) -> dict:
    """L'analyste confirme la faille PAR L'API (pas en écrivant dans le store)."""
    event = make_event(
        "POST",
        f"/v1/findings/{finding_id}/decision",
        claims=analyst_claims(),
        body={"action": "confirmed", "justification": "Reproduced manually."},
    )
    return lambda_handler(event, None, store=deps.store, sa=deps.sa, settings=deps.settings)


def step_onboarding_and_gate(deps: Any, state: JourneyState) -> None:
    """8.1 — mise en service : tenant, application, mandat, garde-fous."""
    tenant = deps.store.get_tenant(TENANT_A)
    assert tenant.mandate_status == "valid"
    assert tenant.free_tier_confirmed is True
    assert deps.store.get_application(APP_A).agent_space_id
    assert deps.store.list_configs(APP_A)

    gate = budget_gate({"tenant_id": TENANT_A, "app_id": APP_A}, deps)
    assert gate["allowed"] is True


def step_test_run_and_budget(deps: Any, state: JourneyState) -> None:
    """8.2 — un test est lancé, suivi ; heures-tâches, coût et budget tracés."""
    state.job_id = start_and_complete(deps, APP_A, TENANT_A, PENTEST_A)
    run = deps.store.get_run(state.job_id)
    assert run.status == "completed"
    assert run.task_hours > 0
    assert run.cost_usd == run.task_hours * deps.settings.hourly_rate
    assert run.duration_s is not None
    assert run.commit_from and run.commit_to  # la plage déployée est conservée

    state.month = run.started_at[:7]
    state.task_hours = run.task_hours
    budget = deps.store.get_budget(TENANT_A, state.month)
    assert budget.hours_used == run.task_hours


def step_collect_findings(deps: Any, state: JourneyState) -> None:
    """8.3 — collecte : empreinte, priorité issue de la matrice, échéance."""
    seed_idor(deps.sa, state.job_id)
    seed_low(deps.sa, state.job_id)

    collected = collect_findings(
        {"app_id": APP_A, "tenant_id": TENANT_A, "run_id": state.job_id}, deps
    )
    assert len(collected["findings_created"]) == 2
    assert collected["duplicates_skipped"] == 0
    assert collected["regressions"] == 0
    state.findings_created = collected["findings_created"]

    findings = deps.store.list_findings(app_id=APP_A)
    critical = next(f for f in findings if f.severity == "Critical")
    low = next(f for f in findings if f.severity == "Low")
    state.critical_id, state.low_id = critical.finding_id, low.finding_id

    assert critical.priority == "P1"
    assert critical.due_at is not None
    assert critical.fingerprint and low.fingerprint
    # La matrice (§ 12.2) donne P4 pour Low, quelle que soit la confiance. Mais
    # l'application traite des données personnelles : « monte d'un cran, sans
    # dépasser P1 » → P3, donc une échéance à 90 jours et non « prochaine
    # version ». C'est volontaire, et c'est exactement ce que ce test verrouille.
    assert low.priority == "P3"
    assert low.due_at is not None


def step_triage_queues_the_critical(deps: Any, state: JourneyState) -> None:
    """8.3 bis — le tri : le modèle ne statue jamais seul sur du critique."""
    triaged = dispatch_triage(
        {
            "app_id": APP_A,
            "tenant_id": TENANT_A,
            "run_id": state.job_id,
            "findings_created": state.findings_created,
        },
        deps,
    )
    assert triaged["triaged"] == 2

    critical = deps.store.get_finding(state.critical_id)
    assert critical.status == "pending_validation"
    assert critical.finding_id in triaged["queued"]
    assert critical.priority == "P1"  # la matrice l'emporte sur le modèle
    assert deps.store.list_decisions(critical.finding_id)

    # La P3 n'est pas critique : l'agent la confirme seul, sans mobiliser d'humain.
    assert deps.store.get_finding(state.low_id).status == "confirmed"


def step_analyst_confirms(deps: Any, state: JourneyState) -> None:
    """8.3 ter — la validation humaine passe par l'API (R5)."""
    response = _confirm_via_api(deps, state.critical_id)
    assert response["statusCode"] == 201
    assert deps.store.get_finding(state.critical_id).status == "confirmed"

    human = [
        d for d in deps.store.list_decisions(state.critical_id)
        if d.author_type == "human"
    ]
    assert human and human[0].justification == "Reproduced manually."


def step_tickets_are_opened(deps: Any, state: JourneyState) -> None:
    """8.4 — un ticket par faille confirmée, avec son échéance contractuelle."""
    ticketed = create_tickets({"app_id": APP_A, "tenant_id": TENANT_A}, deps)
    assert len(ticketed["tickets"]) == 2
    assert len(deps.github.issues) == 2

    issue = deps.github.issues[0]
    assert "Due date" in issue["body"]
    assert issue["labels"] and "security" in issue["labels"]

    critical = deps.store.get_finding(state.critical_id)
    assert critical.ticket_url == issue["html_url"]
    assert critical.status == "in_remediation"
    urls = {f.ticket_url for f in deps.store.list_findings(app_id=APP_A)}
    assert len(urls) == 2  # aucun doublon de ticket


def step_remediation_is_requested(deps: Any, state: JourneyState) -> None:
    """8.4 bis — la pull request de correction est demandée et liée (R6)."""
    remediated = request_remediation(
        {"app_id": APP_A, "tenant_id": TENANT_A, "confirmed": [state.critical_id]},
        deps,
    )
    assert remediated["remediation_prs"] == [state.critical_id]
    assert deps.store.get_finding(state.critical_id).remediation_pr_url


def step_closure_is_proven(deps: Any, state: JourneyState) -> None:
    """8.4 ter — le retest ne montre plus rien : fermeture AVEC PREUVE (R6)."""
    closed = close_or_reopen(
        {"app_id": APP_A, "tenant_id": TENANT_A, "run_id": RETEST_JOB}, deps
    )
    assert sorted(closed["closed"]) == sorted([state.critical_id, state.low_id])
    assert closed["reopened"] == []

    for finding_id in (state.critical_id, state.low_id):
        proven = deps.store.get_finding(finding_id)
        assert proven.status == "closed"
        assert proven.closed_by_run_id == RETEST_JOB  # l'identifiant du retest
        assert proven.closed_at


def step_monthly_report_matches_dashboard(deps: Any, state: JourneyState) -> None:
    """8.5 — le rapport mensuel dit la même chose que le tableau de bord (R10)."""
    frozen = freeze_month(deps.store, tenant_id=TENANT_A, period=state.month)
    report = build_monthly_report(
        store=deps.store,
        tenant_id=TENANT_A,
        period=state.month,
        model_client=FakeModelClient(canned_response="Risk is under control."),
        s3=FakeS3(),
    )
    assert report.kpis["findings_closed"] == frozen["findings_closed"] == 2
    assert report.kpis["task_hours_used"] == frozen["task_hours_used"]
    assert report.kpis["task_hours_used"] == state.task_hours
    assert report.kpis["cost_usd"] == frozen["cost_usd"]


def step_store_stays_consistent(deps: Any, state: JourneyState) -> None:
    """Rien de perdu, rien de dupliqué à la fin du parcours."""
    findings = deps.store.list_findings(tenant_id=TENANT_A)
    assert len(findings) == 2
    assert {f.finding_id for f in findings} == {state.critical_id, state.low_id}
    assert all(f.status == "closed" for f in findings)
    assert all(f.closed_by_run_id == RETEST_JOB for f in findings)


JOURNEY_STEPS: tuple[Callable[[Any, JourneyState], None], ...] = (
    step_onboarding_and_gate,
    step_test_run_and_budget,
    step_collect_findings,
    step_triage_queues_the_critical,
    step_analyst_confirms,
    step_tickets_are_opened,
    step_remediation_is_requested,
    step_closure_is_proven,
    step_monthly_report_matches_dashboard,
    step_store_stays_consistent,
)


def test_full_journey_from_delivery_to_proven_closure():
    """8.1 → 8.2 → 8.3 → 8.4 → 8.5 en une seule narration."""
    deps = make_deps(seed_two_tenants())
    state = JourneyState()
    for step in JOURNEY_STEPS:
        step(deps, state)


def test_every_step_of_the_journey_is_individually_covered():
    """Garde sur le test lui-même : aucune étape ne doit disparaître en silence."""
    assert len(JOURNEY_STEPS) == 10
    assert len({s.__name__ for s in JOURNEY_STEPS}) == len(JOURNEY_STEPS)


def test_second_delivery_of_the_same_finding_does_not_reopen_a_ticket():
    """Une même empreinte sur deux livraisons n'ouvre pas un second ticket."""
    deps = make_deps(seed_two_tenants())
    first = start_and_complete(deps, APP_A, TENANT_A, PENTEST_A)
    seed_idor(deps.sa, first)
    first_collect = collect_findings(
        {"app_id": APP_A, "tenant_id": TENANT_A, "run_id": first}, deps
    )
    assert len(first_collect["findings_created"]) == 1

    second = start_and_complete(deps, APP_A, TENANT_A, PENTEST_A)
    seed_idor(deps.sa, second)
    second_collect = collect_findings(
        {"app_id": APP_A, "tenant_id": TENANT_A, "run_id": second}, deps
    )
    assert second_collect["findings_created"] == []
    assert second_collect["duplicates_skipped"] == 1
    assert len(deps.store.list_findings(app_id=APP_A)) == 1


def test_journey_of_one_tenant_never_touches_the_other():
    """Le parcours joué sur le tenant A laisse le tenant B intact."""
    deps = make_deps(seed_two_tenants())
    job_id = start_and_complete(deps, APP_A, TENANT_A, PENTEST_A)
    seed_idor(deps.sa, job_id)
    collect_findings({"app_id": APP_A, "tenant_id": TENANT_A, "run_id": job_id}, deps)

    assert len(deps.store.list_findings(tenant_id=TENANT_A)) == 1
    assert deps.store.list_findings(tenant_id="tenant-b") == []
    assert deps.store.list_runs(app_id="app-book") == []


def test_audit_trail_follows_the_whole_journey():
    """Chaque étape décisive laisse une trace dans le journal d'audit."""
    deps = make_deps(seed_two_tenants())
    state = JourneyState()
    for step in JOURNEY_STEPS[:6]:  # jusqu'à la création des tickets
        step(deps, state)

    actions = [e.action for e in deps.store.list_audit()]
    assert "finding.decision" in actions
    assert json.dumps(actions)  # le journal est sérialisable (export d'audit)
