"""Routes de gouvernance : dossier de preuves, industrialisation, prévision.

Ces trois capacités existaient côté backend sans aucune route HTTP — donc
invisibles dans le portail. Ces tests vérifient l'exposition, l'autorisation
(un client ne lit jamais un autre tenant) et l'immuabilité (rien n'est écrit
sauf la génération du dossier).
"""

from __future__ import annotations

import json

from rempart.api.app import lambda_handler
from rempart.reports.evidence import integrity_digest
from tests.api.conftest import (
    analyst_claims,
    client_claims,
    make_event,
    platform_admin_claims,
    seed_two_tenants,
)
from tests.fakes import FakeS3

TENANT_A = "t-a"
TENANT_B = "t-b"


def _call(store, method, path, claims, body=None, query=None):
    event = make_event(method, path, claims=claims, body=body, query=query)
    resp = lambda_handler(event, None, store=store, sa=None)
    payload = json.loads(resp["body"]) if resp.get("body") else {}
    return resp["statusCode"], payload


def test_get_evidence_returns_a_self_contained_pack():
    store = seed_two_tenants()
    status, pack = _call(store, "GET", f"/v1/tenants/{TENANT_A}/evidence", analyst_claims())
    assert status == 200
    for section in ("identity", "scope", "tests", "decision_chains", "kpis"):
        assert section in pack, f"section manquante : {section}"
    assert pack["identity"]["tenant_id"] == TENANT_A


def test_get_evidence_accepts_an_explicit_period():
    store = seed_two_tenants()
    status, pack = _call(
        store, "GET", f"/v1/tenants/{TENANT_A}/evidence", analyst_claims(),
        query={"period": "2026-10"},
    )
    assert status == 200
    assert pack["identity"]["period"] == "2026-10"


def test_post_evidence_seals_the_pack_with_a_recomputable_digest():
    store = seed_two_tenants()
    status, sealed = _call(
        store, "POST", f"/v1/tenants/{TENANT_A}/evidence", analyst_claims()
    )
    assert status == 201
    digest = sealed["integrity"]["digest"]
    assert len(digest) == 64
    # L'empreinte est recalculable par un auditeur : même contenu, même hash.
    payload = {k: v for k, v in sealed.items() if k != "integrity"}
    assert integrity_digest(payload) == digest


def test_post_evidence_writes_an_audit_entry():
    store = seed_two_tenants()
    _call(store, "POST", f"/v1/tenants/{TENANT_A}/evidence", analyst_claims())
    actions = [e.action for e in store.list_audit()]
    assert "evidence.generated" in actions


def test_get_industrialization_returns_all_four_families():
    store = seed_two_tenants()
    status, payload = _call(
        store, "GET", f"/v1/tenants/{TENANT_A}/industrialization", analyst_claims()
    )
    assert status == 200
    for key in ("intervention", "alert_fatigue", "minutes_saved", "corpus"):
        assert key in payload, f"famille manquante : {key}"
    assert payload["tenant_id"] == TENANT_A


def test_get_forecast_projects_the_month_end():
    store = seed_two_tenants()
    status, payload = _call(
        store, "GET", f"/v1/tenants/{TENANT_A}/forecast", analyst_claims(),
        query={"month": "2026-10"},
    )
    assert status == 200
    for key in (
        "period",
        "days_in_month",
        "days_elapsed",
        "hours_per_day",
        "projected_hours",
        "projected_pct",
        "exceeds_budget",
        "reference_cost_per_config",
    ):
        assert key in payload, f"champ manquant : {key}"
    assert payload["days_in_month"] == 31  # octobre
    assert payload["days_elapsed"] >= 1  # jamais 0 : pas de division par zéro


def test_a_client_cannot_read_another_tenant_governance():
    """R9 appliqué aux nouvelles routes : 403 sur chacune."""
    store = seed_two_tenants()
    claims = client_claims(TENANT_B)
    for path in (
        f"/v1/tenants/{TENANT_A}/evidence",
        f"/v1/tenants/{TENANT_A}/industrialization",
        f"/v1/tenants/{TENANT_A}/forecast",
    ):
        status, _ = _call(store, "GET", path, claims)
        assert status == 403, f"{path} a renvoyé {status} au lieu de 403"


def test_post_evidence_is_refused_to_the_read_only_demo_role():
    """Le compte des juges est en lecture seule : générer un dossier lui est refusé."""
    store = seed_two_tenants()
    demo = {"sub": "judge", "cognito:groups": ["demo"], "custom:tenant_id": TENANT_A}
    status, _ = _call(store, "POST", f"/v1/tenants/{TENANT_A}/evidence", demo)
    assert status == 403


def test_unauthenticated_request_is_refused():
    store = seed_two_tenants()
    status, _ = _call(store, "GET", f"/v1/tenants/{TENANT_A}/evidence", None)
    assert status == 401


def test_unknown_tenant_returns_404():
    store = seed_two_tenants()
    status, _ = _call(store, "GET", "/v1/tenants/nope/evidence", platform_admin_claims())
    assert status == 404


def test_platform_admin_reaches_every_tenant():
    store = seed_two_tenants()
    for tenant_id in (TENANT_A, TENANT_B):
        status, _ = _call(
            store, "GET", f"/v1/tenants/{tenant_id}/evidence", platform_admin_claims()
        )
        assert status == 200


def test_forecast_does_not_invent_consumption_for_an_empty_tenant():
    """Un tenant sans run ne doit pas projeter de consommation."""
    store = seed_two_tenants()
    status, payload = _call(
        store, "GET", f"/v1/tenants/{TENANT_B}/forecast", analyst_claims(),
        query={"month": "2026-10"},
    )
    assert status == 200
    assert payload["hours_used"] == 0.0
    assert payload["hours_per_day"] == 0.0
    assert payload["exhaustion_date"] is None


def test_evidence_of_one_tenant_contains_nothing_from_the_other():
    store = seed_two_tenants()
    _, pack = _call(store, "GET", f"/v1/tenants/{TENANT_A}/evidence", analyst_claims())
    serialized = json.dumps(pack)
    assert TENANT_B not in serialized


def test_digest_survives_the_s3_key_added_after_sealing():
    """`build_and_upload` ajoute `s3_key` APRÈS scellement : l'empreinte doit
    rester recalculable, sinon un auditeur qui récupère le dossier stocké ne
    peut plus le vérifier."""
    from rempart.reports.evidence import build_and_upload

    store = seed_two_tenants()
    s3 = FakeS3()
    sealed = build_and_upload(
        store=store, tenant_id=TENANT_A, period="2026-10", s3=s3,
        generated_at="2026-11-03T06:00:00Z",
    )
    assert sealed["s3_key"]
    assert len(s3.objects) >= 1
    assert integrity_digest(sealed) == sealed["integrity"]["digest"]
