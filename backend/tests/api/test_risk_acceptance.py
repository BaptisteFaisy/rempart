"""Acceptation de risque (EF-COR-07, chapitre 6 et 9.4).

Seul le responsable sécurité du client propriétaire de la faille
(``client_security``) peut accepter un risque, avec une justification et une
date de revue enregistrées. Aucun rôle MSP ne peut le faire à sa place.
"""

import json

from rempart.api.app import lambda_handler
from rempart.common.models import Finding
from rempart.common.timeutil import parse_iso
from tests.api.conftest import (
    analyst_claims,
    client_claims,
    make_event,
    platform_admin_claims,
    seed_two_tenants,
)

# Alias local : chaque test part d'un store fraîchement semé.
seed_store = seed_two_tenants

BODY_OK = {
    "action": "risk_accepted",
    "justification": "Interne seulement, correctif planifié à la refonte Q1 (revue RSSI).",
}


def _finding(store, finding_id: str = "f-t-a") -> Finding:
    return store.get_finding(finding_id)


def test_client_security_accepte_un_risque_avec_date_et_auteur():
    store = seed_store()
    event = make_event(
        "POST",
        "/v1/findings/f-t-a/decision",
        claims=client_claims("t-a"),
        body=dict(BODY_OK),
    )
    resp = lambda_handler(event, None, store=store, sa=None)
    assert resp["statusCode"] == 201
    payload = json.loads(resp["body"])
    assert payload["finding"]["status"] == "risk_accepted"
    assert payload["decision"]["action"] == "risk_accepted"
    assert payload["decision"]["justification"] == BODY_OK["justification"]

    finding = _finding(store)
    assert finding.status == "risk_accepted"
    assert finding.risk_review_by == "user-client"
    # Date de revue enregistrée et lisible (horodatage ISO réel du serveur).
    assert finding.risk_review_at
    parse_iso(finding.risk_review_at)
    # La décision est tracée dans le store.
    decisions = store.list_decisions("f-t-a")
    assert any(d.action == "risk_accepted" for d in decisions)


def test_analyste_msp_ne_peut_pas_accepter_un_risque():
    store = seed_store()
    event = make_event(
        "POST",
        "/v1/findings/f-t-a/decision",
        claims=analyst_claims(),
        body=dict(BODY_OK),
    )
    resp = lambda_handler(event, None, store=store, sa=None)
    assert resp["statusCode"] == 403
    assert "client" in json.loads(resp["body"])["error"].lower()
    # Rien n'a été enregistré : le statut d'origine survit.
    assert _finding(store).status == "confirmed"
    assert _finding(store).risk_review_at is None


def test_platform_admin_ne_peut_pas_accepter_un_risque():
    store = seed_store()
    event = make_event(
        "POST",
        "/v1/findings/f-t-a/decision",
        claims=platform_admin_claims(),
        body=dict(BODY_OK),
    )
    resp = lambda_handler(event, None, store=store, sa=None)
    assert resp["statusCode"] == 403
    assert _finding(store).status == "confirmed"


def test_client_security_d_un_autre_tenant_est_refuse():
    store = seed_store()
    event = make_event(
        "POST",
        "/v1/findings/f-t-a/decision",
        claims=client_claims("t-b"),
        body=dict(BODY_OK),
    )
    resp = lambda_handler(event, None, store=store, sa=None)
    assert resp["statusCode"] == 403
    assert _finding(store).status == "confirmed"
    assert _finding(store).risk_review_at is None


def test_acceptation_sans_justification_est_refusee():
    store = seed_store()
    for body in (
        {"action": "risk_accepted"},
        {"action": "risk_accepted", "justification": ""},
        {"action": "risk_accepted", "justification": "   "},
    ):
        event = make_event(
            "POST",
            "/v1/findings/f-t-a/decision",
            claims=client_claims("t-a"),
            body=body,
        )
        resp = lambda_handler(event, None, store=store, sa=None)
        assert resp["statusCode"] == 400, body
        assert _finding(store).status == "confirmed"
        assert _finding(store).risk_review_at is None


def test_les_autres_decisions_ne_changent_pas_de_regime():
    """Une confirmation par l'analyste reste possible sans justification."""
    store = seed_store()
    event = make_event(
        "POST",
        "/v1/findings/f-t-a/decision",
        claims=analyst_claims(),
        body={"action": "false_positive"},
    )
    resp = lambda_handler(event, None, store=store, sa=None)
    assert resp["statusCode"] == 201
    assert _finding(store).status == "false_positive"
    assert _finding(store).risk_review_at is None


def test_la_date_de_revue_survit_a_l_aller_retour_item():
    finding = _finding(seed_store())
    finding.status = "risk_accepted"
    finding.risk_review_at = "2026-11-11T09:30:00Z"
    finding.risk_review_by = "user-client"
    loaded = Finding.from_item(finding.to_item())
    assert loaded.risk_review_at == "2026-11-11T09:30:00Z"
    assert loaded.risk_review_by == "user-client"
    assert loaded == finding


def test_une_faille_sans_revue_garde_les_champs_vides():
    """Rétrocompatibilité : les anciens items sans date de revue se chargent."""
    legacy = _finding(seed_store()).to_item()
    legacy.pop("risk_review_at")
    legacy.pop("risk_review_by")
    loaded = Finding.from_item(legacy)
    assert loaded.risk_review_at is None
    assert loaded.risk_review_by is None
