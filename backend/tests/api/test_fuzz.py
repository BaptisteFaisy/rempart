"""Fuzz léger et déterministe des routes principales : aucune 500.

Le principe : une entrée hostile ou malformée ne doit JAMAIS produire une
erreur interne (500). Elle est rejetée par un 4xx — avec une réponse JSON — ou,
pour les lectures inoffensives, répond 200. Ce fuzz n'est pas exhaustif : il
balaye un échantillon représentatif de mauvaises formes sur les routes les plus
exposées.
"""

from __future__ import annotations

import json

import pytest

from rempart.api.app import lambda_handler
from tests.api.conftest import make_event, platform_admin_claims, seed_two_tenants

#: (méthode, chemin, corps) — le corps est envoyé tel quel (valeurs exotiques).
BAD_BODIES = [
    "pas du json",
    "",
    None,
    [],
    [1, 2, 3],
    42,
    '"juste une chaîne json"',
    {"tenant_id": 1},  # mauvais type de champ
    {"a" * 1000: "b"},  # clé géante
    {"name": "x" * 100_000},  # valeur géante
]

EVERYTHING_BUT_500 = (200, 201, 202, 204, 400, 401, 403, 404, 405, 429)

READ_PATHS = [
    "/v1/tenants",
    "/v1/tenants/demo-a",
    "/v1/tenants/demo-a/forecast",
    "/v1/tenants/demo-a/evidence",
    "/v1/tenants/demo-a/industrialization",
    "/v1/audit",
    "/v1/findings",
    "/v1/fleet/kpis",
]


def _status(event) -> int:
    response = lambda_handler(event, None, store=seed_two_tenants(), sa=None)
    return int(response["statusCode"])


@pytest.mark.parametrize("body", BAD_BODIES)
@pytest.mark.parametrize(
    "path", ["/v1/tenants", "/v1/findings", "/v1/tenants/demo-a/forecast"]
)
def test_pas_de_500_avec_un_corps_malforme(path, body):
    method = "POST" if path == "/v1/tenants" else "GET"
    event = make_event(method, path, body=body, claims=platform_admin_claims())
    assert _status(event) in EVERYTHING_BUT_500


def test_pas_de_500_sur_les_lectures_anonymes():
    for path in READ_PATHS:
        event = make_event("GET", path)  # aucun claim
        assert _status(event) in EVERYTHING_BUT_500, path


def test_pas_de_500_sur_la_traversee_de_chemin():
    for path in (
        "/v1/tenants/../secrets",
        "/v1/tenants/%2e%2e%2fsecrets",
        "/v1/tenants/demo-a/forecast?period=../../etc/passwd",
        "/v1/audit?object_id=..%2F..%2F",
    ):
        event = make_event("GET", path)
        assert _status(event) in EVERYTHING_BUT_500, path


def test_une_methode_non_supportee_est_refusee_sans_500():
    for path in ("/v1/tenants", "/v1/findings"):
        event = make_event("PATCH", path, claims=platform_admin_claims())
        assert _status(event) in EVERYTHING_BUT_500


def test_la_reponse_est_toujours_du_json_valide():
    """Même un rejet doit être un JSON lisible, jamais une traceback."""
    event = make_event("POST", "/v1/tenants", body="pas du json", claims=platform_admin_claims())
    response = lambda_handler(event, None, store=seed_two_tenants(), sa=None)
    json.loads(response["body"])  # lève si non-JSON
