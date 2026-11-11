"""Méthode de vérification de domaine paramétrable (EF-ONB-03, idée #33).

La doc officielle de `CreateTargetDomain` impose `verificationMethod` parmi
`DNS_TXT | HTTP_ROUTE | PRIVATE_VPC`. `HTTP_ROUTE` ne demande **aucun accès
DNS** : il suffit de publier un jeton sur une route de l'application. C'est ce
qui permet de vérifier un domaine de démonstration sans acheter de zone DNS.
"""

from __future__ import annotations

import json

from rempart.api.app import lambda_handler
from rempart.api.routes.onboarding import (
    DEFAULT_VERIFICATION_METHOD,
    VERIFICATION_METHODS,
)
from tests.api.conftest import analyst_claims, make_event, seed_two_tenants
from tests.fakes import FakeSecurityAgentClient


def _onboard(store, sa, body: dict | None = None):
    event = make_event(
        "POST",
        "/v1/applications/app-t-a/onboarding",
        claims=analyst_claims(),
        body=body or {},
    )
    return lambda_handler(event, None, store=store, sa=sa)


def _body_of(resp) -> dict:
    return json.loads(resp["body"])


def test_dns_txt_reste_la_methode_par_defaut():
    store, sa = seed_two_tenants(), FakeSecurityAgentClient()
    resp = _onboard(store, sa)
    assert resp["statusCode"] == 201
    assert DEFAULT_VERIFICATION_METHOD == "DNS_TXT"
    payload = _body_of(resp)
    assert payload["verification_method"] == "DNS_TXT"
    assert sa.calls and sa.calls[0][0] == "create_target_domain"
    assert sa.calls[0][1]["verificationMethod"] == "DNS_TXT"


def test_http_route_ne_demande_aucun_acces_dns():
    """Le point qui évite d'acheter un domaine pour une démonstration."""
    store, sa = seed_two_tenants(), FakeSecurityAgentClient()
    resp = _onboard(store, sa, {"verification_method": "HTTP_ROUTE"})
    assert resp["statusCode"] == 201
    payload = _body_of(resp)

    assert payload["verification_method"] == "HTTP_ROUTE"
    assert sa.calls[0][1]["verificationMethod"] == "HTTP_ROUTE"
    instructions = payload["verification_instructions"][0]
    assert instructions["requires_dns_access"] is False
    assert instructions["method"] == "HTTP_ROUTE"
    # Le jeton et la route à publier doivent être actionnables par le client.
    assert instructions["details"]["routePath"]
    assert instructions["details"]["token"]


def test_private_vpc_est_accepte():
    store, sa = seed_two_tenants(), FakeSecurityAgentClient()
    resp = _onboard(store, sa, {"verification_method": "PRIVATE_VPC"})
    assert resp["statusCode"] == 201
    assert _body_of(resp)["verification_method"] == "PRIVATE_VPC"


def test_les_trois_methodes_documentees_sont_acceptees():
    """La liste acceptée doit rester alignée sur la doc AWS."""
    assert set(VERIFICATION_METHODS) == {"DNS_TXT", "HTTP_ROUTE", "PRIVATE_VPC"}


def test_methode_inconnue_refusee_avec_400():
    store, sa = seed_two_tenants(), FakeSecurityAgentClient()
    resp = _onboard(store, sa, {"verification_method": "CARRIER_PIGEON"})
    assert resp["statusCode"] == 400
    assert "CARRIER_PIGEON" in _body_of(resp)["error"]
    # Aucun appel AWS n'a été fait : on refuse avant de provisionner.
    assert not sa.calls


def test_la_casse_est_normalisee():
    store, sa = seed_two_tenants(), FakeSecurityAgentClient()
    resp = _onboard(store, sa, {"verification_method": "http_route"})
    assert resp["statusCode"] == 201
    assert _body_of(resp)["verification_method"] == "HTTP_ROUTE"


def test_dns_txt_donne_une_instruction_actionnable():
    store, sa = seed_two_tenants(), FakeSecurityAgentClient()
    payload = _body_of(_onboard(store, sa))
    instructions = payload["verification_instructions"][0]
    assert instructions["requires_dns_access"] is True
    assert instructions["details"]["dnsRecordType"] == "TXT"
    assert "TXT" in instructions["action"]


def test_un_domaine_par_instruction():
    """Chaque domaine du périmètre doit recevoir sa propre consigne."""
    store = seed_two_tenants()
    app = store.get_application("app-t-a")
    app.domains = ["shop.acme.com", "api.acme.com"]
    store.save_application(app)
    sa = FakeSecurityAgentClient()

    payload = _body_of(_onboard(store, sa, {"verification_method": "HTTP_ROUTE"}))
    assert len(payload["verification_instructions"]) == 2
    assert {i["domain"] for i in payload["verification_instructions"]} == {
        "shop.acme.com",
        "api.acme.com",
    }


def test_un_client_ne_peut_pas_mettre_en_service_un_autre_tenant():
    """Le cloisonnement tient aussi sur la mise en service (R9)."""
    from tests.api.conftest import client_claims

    store, sa = seed_two_tenants(), FakeSecurityAgentClient()
    event = make_event(
        "POST",
        "/v1/applications/app-t-b/onboarding",
        claims=client_claims("t-a"),
        body={"verification_method": "HTTP_ROUTE"},
    )
    resp = lambda_handler(event, None, store=store, sa=sa)
    assert resp["statusCode"] == 403
    assert not sa.calls
