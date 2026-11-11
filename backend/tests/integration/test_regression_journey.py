"""La faille réintroduite : régression détectée et rouverte (recette R7).

Le cycle de vie (§ 11.5) prévoit `Fermée → Rouverte` quand une faille
réapparaît. Sans ce test, une régression pourrait être silencieusement
ignorée : la faille est fermée, le retest la retrouve, et rien ne se passe.
"""

from __future__ import annotations

from rempart.orchestrator.tasks import (
    close_or_reopen,
    collect_findings,
    create_tickets,
    dispatch_triage,
    request_remediation,
)
from tests.integration.conftest import (
    APP_A,
    PENTEST_A,
    TENANT_A,
    make_deps,
    seed_idor,
    seed_two_tenants,
    start_and_complete,
)


def _walk_until_closed(deps, first_job: str) -> str:
    """Joue collecte → tri → ticket → PR, puis ferme par un retest propre."""
    collected = collect_findings(
        {"app_id": APP_A, "tenant_id": TENANT_A, "run_id": first_job}, deps
    )
    finding_id = collected["findings_created"][0]
    dispatch_triage(
        {
            "app_id": APP_A,
            "tenant_id": TENANT_A,
            "run_id": first_job,
            "findings_created": collected["findings_created"],
        },
        deps,
    )
    # L'analyste confirme : une Critical ne peut pas être validée par le modèle.
    finding = deps.store.get_finding(finding_id)
    finding.status = "confirmed"
    deps.store.save_finding(finding)
    create_tickets({"app_id": APP_A, "tenant_id": TENANT_A}, deps)
    request_remediation(
        {"app_id": APP_A, "tenant_id": TENANT_A, "confirmed": [finding_id]}, deps
    )
    clean_retest = "run-retest-clean"
    close_or_reopen(
        {"app_id": APP_A, "tenant_id": TENANT_A, "run_id": clean_retest}, deps
    )
    return finding_id


def test_reappearing_finding_is_reopened_not_closed():
    deps = make_deps(seed_two_tenants())
    first_job = start_and_complete(deps, APP_A, TENANT_A, PENTEST_A)
    seed_idor(deps.sa, first_job)
    finding_id = _walk_until_closed(deps, first_job)

    closed = deps.store.get_finding(finding_id)
    assert closed.status == "closed"
    assert closed.closed_by_run_id == "run-retest-clean"
    assert closed.closed_at

    # La même faille réapparaît sur une livraison suivante : même empreinte.
    regression_job = start_and_complete(deps, APP_A, TENANT_A, PENTEST_A)
    seed_idor(deps.sa, regression_job)
    recollected = collect_findings(
        {"app_id": APP_A, "tenant_id": TENANT_A, "run_id": regression_job}, deps
    )

    # Elle ne crée PAS une nouvelle faille : c'est une régression, pas un doublon.
    assert recollected["findings_created"] == []
    assert recollected["regressions"] == 1
    assert len(deps.store.list_findings(app_id=APP_A)) == 1

    reopened = deps.store.get_finding(finding_id)
    assert reopened.status == "reopened"
    assert reopened.closed_at is None
    assert reopened.closed_by_run_id is None


def test_reopened_finding_keeps_its_ticket_and_pr_history():
    """La réouverture ne doit pas effacer la trace de la première correction."""
    deps = make_deps(seed_two_tenants())
    first_job = start_and_complete(deps, APP_A, TENANT_A, PENTEST_A)
    seed_idor(deps.sa, first_job)
    finding_id = _walk_until_closed(deps, first_job)
    before = deps.store.get_finding(finding_id)
    ticket_url = before.ticket_url
    pr_url = before.remediation_pr_url
    assert ticket_url and pr_url

    regression_job = start_and_complete(deps, APP_A, TENANT_A, PENTEST_A)
    seed_idor(deps.sa, regression_job)
    collect_findings(
        {"app_id": APP_A, "tenant_id": TENANT_A, "run_id": regression_job}, deps
    )

    after = deps.store.get_finding(finding_id)
    assert after.status == "reopened"
    assert after.ticket_url == ticket_url
    assert after.remediation_pr_url == pr_url
    # L'historique des décisions est préservé : un auditeur voit les deux tours.
    assert len(deps.store.list_decisions(finding_id)) >= 1


def test_reopened_finding_can_be_closed_again_with_a_new_proof():
    """Après réouverture, un second retest propre referme avec une nouvelle preuve."""
    deps = make_deps(seed_two_tenants())
    first_job = start_and_complete(deps, APP_A, TENANT_A, PENTEST_A)
    seed_idor(deps.sa, first_job)
    finding_id = _walk_until_closed(deps, first_job)

    regression_job = start_and_complete(deps, APP_A, TENANT_A, PENTEST_A)
    seed_idor(deps.sa, regression_job)
    collect_findings(
        {"app_id": APP_A, "tenant_id": TENANT_A, "run_id": regression_job}, deps
    )
    assert deps.store.get_finding(finding_id).status == "reopened"

    second_retest = "run-retest-second"
    closed = close_or_reopen(
        {"app_id": APP_A, "tenant_id": TENANT_A, "run_id": second_retest}, deps
    )
    assert closed["closed"] == [finding_id]
    final = deps.store.get_finding(finding_id)
    assert final.status == "closed"
    assert final.closed_by_run_id == second_retest  # nouvelle preuve, pas l'ancienne


def test_a_clean_retest_does_not_reopen_anything():
    """Un retest propre sur une faille jamais ouverte ne crée pas de bruit."""
    deps = make_deps(seed_two_tenants())
    job_id = start_and_complete(deps, APP_A, TENANT_A, PENTEST_A)
    result = close_or_reopen(
        {"app_id": APP_A, "tenant_id": TENANT_A, "run_id": job_id}, deps
    )
    assert result["closed"] == []
    assert result["reopened"] == []
