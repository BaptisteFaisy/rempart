"""Cloisonnement multi-tenant sur le parcours COMPLET (recette R9, ENF-SEC-01).

`tests/api/test_isolation.py` vérifie le cloisonnement route par route. Ici on
le vérifie après avoir joué un vrai parcours sur le tenant A : aucune donnée ne
doit fuir vers le tenant B, ni par les listes, ni par les KPI, ni par l'audit,
ni par le rapport mensuel.
"""

from __future__ import annotations

import json

from rempart.api.app import lambda_handler
from rempart.orchestrator.tasks import (
    collect_findings,
    create_tickets,
    dispatch_triage,
    request_remediation,
)
from rempart.reports.metrics import compute_kpis
from rempart.reports.monthly import build_monthly_report
from tests.api.conftest import analyst_claims, client_claims, make_event
from tests.fakes import FakeModelClient, FakeS3
from tests.integration.conftest import (
    APP_A,
    APP_B,
    PENTEST_A,
    TENANT_A,
    TENANT_B,
    make_deps,
    seed_idor,
    seed_two_tenants,
    start_and_complete,
)


def _run_full_journey_on_a(deps) -> str:
    """Joue le parcours complet sur le tenant A et rend l'identifiant du test.

    La confirmation passe PAR L'API (et non par une écriture directe dans le
    store) pour que le journal d'audit soit alimenté, comme en production.
    """
    job_id = start_and_complete(deps, APP_A, TENANT_A, PENTEST_A)
    seed_idor(deps.sa, job_id)
    collected = collect_findings(
        {"app_id": APP_A, "tenant_id": TENANT_A, "run_id": job_id}, deps
    )
    dispatch_triage(
        {
            "app_id": APP_A,
            "tenant_id": TENANT_A,
            "run_id": job_id,
            "findings_created": collected["findings_created"],
        },
        deps,
    )
    finding_id = collected["findings_created"][0]
    event = make_event(
        "POST",
        f"/v1/findings/{finding_id}/decision",
        claims=analyst_claims(),
        body={"action": "confirmed", "justification": "Reproduced manually."},
    )
    response = lambda_handler(
        event, None, store=deps.store, sa=deps.sa, settings=deps.settings
    )
    assert response["statusCode"] == 201
    create_tickets({"app_id": APP_A, "tenant_id": TENANT_A}, deps)
    request_remediation(
        {"app_id": APP_A, "tenant_id": TENANT_A, "confirmed": [finding_id]},
        deps,
    )
    return job_id


def _get(deps, path: str, claims: dict, query: dict | None = None) -> tuple[int, dict]:
    event = make_event("GET", path, claims=claims, query=query)
    resp = lambda_handler(event, None, store=deps.store, sa=deps.sa, settings=deps.settings)
    return resp["statusCode"], json.loads(resp["body"])


def test_tenant_b_stays_empty_after_a_full_journey_on_a():
    deps = make_deps(seed_two_tenants())
    _run_full_journey_on_a(deps)

    assert len(deps.store.list_findings(tenant_id=TENANT_A)) >= 1
    assert deps.store.list_findings(tenant_id=TENANT_B) == []
    assert deps.store.list_runs(app_id=APP_B) == []
    assert len(deps.store.list_applications(TENANT_B)) == 1  # l'app existe, sans test


def test_client_of_b_gets_403_on_every_a_resource():
    """R9 : refus sur CHAQUE point d'API, pas seulement sur certains."""
    deps = make_deps(seed_two_tenants())
    job_id = _run_full_journey_on_a(deps)
    finding_id = deps.store.list_findings(tenant_id=TENANT_A)[0].finding_id
    claims_b = client_claims(TENANT_B)

    reads = [
        f"/v1/tenants/{TENANT_A}",
        f"/v1/applications/{APP_A}",
        f"/v1/applications/{APP_A}/runs",
        f"/v1/runs/{job_id}",
        f"/v1/findings/{finding_id}",
        f"/v1/tenants/{TENANT_A}/kpis",
        f"/v1/tenants/{TENANT_A}/budget",
        f"/v1/tenants/{TENANT_A}/audit",
    ]
    for path in reads:
        status, _ = _get(deps, path, claims_b)
        assert status == 403, f"{path} a renvoyé {status} au lieu de 403"


def test_findings_list_never_mixes_tenants():
    deps = make_deps(seed_two_tenants())
    _run_full_journey_on_a(deps)

    status, body = _get(deps, "/v1/findings", client_claims(TENANT_B))
    assert status == 200
    assert body["findings"] == []

    status_a, body_a = _get(deps, "/v1/findings", client_claims(TENANT_A))
    assert status_a == 200
    assert body_a["findings"], "le tenant A doit voir ses propres failles"
    assert all(f["tenant_id"] == TENANT_A for f in body_a["findings"])


def test_asking_for_the_other_tenant_explicitly_is_refused():
    """Demander explicitement le tenant A depuis un jeton du tenant B : 403."""
    deps = make_deps(seed_two_tenants())
    _run_full_journey_on_a(deps)
    status, _ = _get(
        deps, "/v1/findings", client_claims(TENANT_B), query={"tenant_id": TENANT_A}
    )
    assert status == 403


def test_kpis_of_one_tenant_do_not_count_the_other():
    deps = make_deps(seed_two_tenants())
    job_id = _run_full_journey_on_a(deps)

    month = deps.store.get_run(job_id).started_at[:7]
    kpis_a = compute_kpis(deps.store, tenant_id=TENANT_A, period=month)
    kpis_b = compute_kpis(deps.store, tenant_id=TENANT_B, period=month)

    assert kpis_a["tests_total"] >= 1
    assert kpis_b["tests_total"] == 0
    assert kpis_b["task_hours_used"] == 0.0
    assert kpis_b["findings_closed"] == 0


def test_monthly_report_of_b_contains_nothing_from_a():
    deps = make_deps(seed_two_tenants())
    job_id = _run_full_journey_on_a(deps)
    month = deps.store.get_run(job_id).started_at[:7]

    report_b = build_monthly_report(
        store=deps.store,
        tenant_id=TENANT_B,
        period=month,
        model_client=FakeModelClient(canned_response="No activity this month."),
        s3=FakeS3(),
    )
    assert report_b.tenant_id == TENANT_B
    assert report_b.kpis["tests_total"] == 0
    serialized = json.dumps(report_b.kpis)
    assert TENANT_A not in serialized
    assert APP_A not in serialized


def test_audit_log_is_filtered_by_tenant():
    deps = make_deps(seed_two_tenants())
    _run_full_journey_on_a(deps)

    status_a, body_a = _get(deps, f"/v1/tenants/{TENANT_A}/audit", analyst_claims())
    assert status_a == 200
    assert body_a["events"], "le journal du tenant A ne doit pas être vide"

    status_b, body_b = _get(deps, f"/v1/tenants/{TENANT_B}/audit", client_claims(TENANT_B))
    assert status_b == 200
    assert body_b["events"] == []


def test_demo_role_cannot_read_audit():
    """Le rôle de démonstration des juges est en lecture seule et sans audit."""
    deps = make_deps(seed_two_tenants())
    _run_full_journey_on_a(deps)
    demo = {"sub": "judge", "cognito:groups": ["demo"], "custom:tenant_id": TENANT_A}
    status, _ = _get(deps, "/v1/audit", demo)
    assert status in (403, 404)


def test_tickets_are_scoped_to_the_owning_repository():
    """Le ticket d'une faille du tenant A part sur le dépôt du tenant A."""
    deps = make_deps(seed_two_tenants())
    _run_full_journey_on_a(deps)
    assert deps.github.issues
    for issue in deps.github.issues:
        assert issue["repo"] == APP_A
        assert issue["owner"] == "demo"
