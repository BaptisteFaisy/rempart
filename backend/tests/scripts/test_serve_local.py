"""Tests du serveur de démonstration local (scripts/serve_local.py).

Aucune socket n'est ouverte : on teste directement la traduction
requête HTTP -> événement API Gateway v2, le mapping des en-têtes de démo en
claims Cognito, le preflight CORS, la route inconnue (404) et le mode --check.
"""

import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts" / "serve_local.py"

# Le serveur vit hors du package `rempart` : chargement par chemin explicite.
_spec = importlib.util.spec_from_file_location("serve_local", SCRIPT)
assert _spec and _spec.loader
serve_local = importlib.util.module_from_spec(_spec)
sys.modules["serve_local"] = serve_local
_spec.loader.exec_module(serve_local)


@pytest.fixture
def store():
    """Un FakeStore chargé avec le jeu figé versionné."""
    return serve_local.store_from_dataset(serve_local.load_dataset())


@pytest.fixture
def env(store):
    """Les trois dépendances injectées dans lambda_handler."""
    return store, serve_local.FakeSecurityAgentClient(), serve_local.Settings()


def _body(response):
    return json.loads(response["body"])


def test_build_event_maps_get_with_query_params():
    event = serve_local.build_event(
        "GET", "/v1/findings", query={"status": "new", "priority": "P1"}
    )
    assert event["version"] == "2.0"
    assert event["rawPath"] == "/v1/findings"
    assert event["requestContext"]["http"]["method"] == "GET"
    assert event["queryStringParameters"] == {"status": "new", "priority": "P1"}
    assert event["body"] is None
    assert event["isBase64Encoded"] is False


def test_build_event_maps_post_with_json_body():
    payload = {"action": "confirmed", "justification": "verified IDOR"}
    event = serve_local.build_event(
        "POST", "/v1/findings/f-1/decision", body=json.dumps(payload).encode("utf-8")
    )
    assert event["requestContext"]["http"]["method"] == "POST"
    assert event["body"] == json.dumps(payload)
    assert json.loads(event["body"]) == payload


def test_demo_role_and_tenant_headers_become_cognito_claims():
    event = serve_local.build_event(
        "GET",
        "/v1/findings",
        headers={"X-Demo-Role": "client_security", "X-Demo-Tenant": "demo-b"},
    )
    claims = event["requestContext"]["authorizer"]["jwt"]["claims"]
    assert claims["cognito:groups"] == ["client_security"]
    assert claims["custom:tenant_id"] == "demo-b"
    assert claims["sub"] == "demo-client_security@local"


def test_default_demo_role_is_platform_admin():
    event = serve_local.build_event("GET", "/v1/tenants")
    claims = event["requestContext"]["authorizer"]["jwt"]["claims"]
    assert claims["cognito:groups"] == [serve_local.DEFAULT_ROLE]
    assert "custom:tenant_id" not in claims


def test_client_scoped_role_gets_default_demo_tenant():
    claims = serve_local.demo_claims({"x-demo-role": "demo"})
    assert claims["custom:tenant_id"] == serve_local.DEFAULT_DEMO_TENANT


def test_dispatch_serves_tenants_from_the_frozen_dataset(env):
    store, sa, settings = env
    response = serve_local.dispatch(store, sa, settings, method="GET", raw_path="/v1/tenants")
    assert response["statusCode"] == 200
    tenant_ids = {t["tenant_id"] for t in _body(response)["tenants"]}
    assert tenant_ids == {"demo-a", "demo-b"}


def test_dispatch_serves_findings_and_filters_by_tenant(env):
    store, sa, settings = env
    response = serve_local.dispatch(
        store, sa, settings, method="GET", raw_path="/v1/findings",
        query={"tenant_id": "demo-b"},
    )
    assert response["statusCode"] == 200
    findings = _body(response)["findings"]
    assert findings and all(f["tenant_id"] == "demo-b" for f in findings)


def test_dispatch_applies_demo_period_to_kpis(env):
    """Sans période explicite, les KPI lisent le mois figé du jeu (2026-10)."""
    store, sa, settings = env
    period = serve_local.demo_period(serve_local.load_dataset())
    response = serve_local.dispatch(
        store, sa, settings, method="GET", raw_path="/v1/tenants/demo-a/kpis", period=period
    )
    assert response["statusCode"] == 200
    payload = _body(response)
    assert payload["period"] == period
    assert payload["tests_total"] == 3
    assert payload["task_hours_used"] == pytest.approx(5.4)


def test_dispatch_rejects_write_for_read_only_demo_role(env):
    store, sa, settings = env
    response = serve_local.dispatch(
        store, sa, settings, method="POST", raw_path="/v1/tenants",
        headers={"X-Demo-Role": "demo"},
        body=json.dumps({"tenant_id": "demo-c"}),
    )
    assert response["statusCode"] == 403


def test_unknown_route_returns_404(env):
    store, sa, settings = env
    response = serve_local.dispatch(store, sa, settings, method="GET", raw_path="/v1/nope")
    assert response["statusCode"] == 404
    assert "No route matches" in _body(response)["error"]


def test_preflight_returns_cors_headers():
    status, headers, body = serve_local.preflight_response()
    assert status == serve_local.PREFLIGHT_STATUS
    assert headers["Access-Control-Allow-Origin"] == "*"
    assert "X-Demo-Role" in headers["Access-Control-Allow-Headers"]
    assert "POST" in headers["Access-Control-Allow-Methods"]
    assert body == b""


def test_lambda_responses_are_returned_with_cors_headers(env):
    store, sa, settings = env
    response = serve_local.dispatch(store, sa, settings, method="GET", raw_path="/v1/tenants")
    assert response["headers"]["Access-Control-Allow-Origin"] == "*"


def test_routes_served_lists_the_chapter_14_routes():
    routes = serve_local.routes_served()
    assert any("GET" in r and "/v1/tenants" in r for r in routes)
    assert any("/v1/tenants/:id/kpis" in r for r in routes)
    assert any("events/deployment" in r for r in routes)


def test_check_mode_exits_zero_and_lists_routes():
    """`--check` démarre, valide deux routes, affiche les routes et sort en 0."""
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--check"],
        capture_output=True, text=True, timeout=120,
    )
    assert proc.returncode == 0, proc.stderr
    assert "route" in proc.stdout
    assert "/v1/tenants/:id/kpis" in proc.stdout
    assert "check  GET /v1/tenants -> 200" in proc.stdout


def test_unknown_dataset_falls_back_to_the_seed_generator(tmp_path):
    dataset = serve_local.load_dataset(tmp_path / "absent.json")
    assert {t["tenant_id"] for t in dataset["tenants"]} == {"demo-a", "demo-b"}


def test_committed_dataset_is_used_verbatim(tmp_path):
    """Le serveur sert le JSON versionné, pas une copie divergente."""
    dataset = serve_local.load_dataset()
    assert dataset == json.loads(serve_local.DEFAULT_DATASET.read_text(encoding="utf-8"))


def test_la_demo_locale_ne_tente_aucun_appel_reseau(monkeypatch, env):
    """PREUVE « 0 € » : la démo ne dépend d'aucun service distant.

    Toute connexion réseau est coupée pendant l'appel : si la démo répond
    encore, c'est qu'elle ne parle à aucun AWS — donc qu'elle ne facture rien.
    Le serveur de démo n'utilise qu'un `FakeStore` et un
    `FakeSecurityAgentClient`, tous deux en mémoire.
    """
    import socket

    def _blocked(*args, **kwargs):
        raise AssertionError("la démo a tenté une connexion réseau")

    monkeypatch.setattr(socket.socket, "connect", _blocked)
    monkeypatch.setattr(socket, "create_connection", _blocked)

    store, sa, settings = env
    paths = (
        "/v1/tenants",
        "/v1/tenants/demo-a/evidence",
        "/v1/tenants/demo-a/industrialization",
        "/v1/tenants/demo-a/forecast",
        "/v1/tenants/demo-a/policy",
        "/v1/audit",
    )
    for path in paths:
        response = serve_local.dispatch(
            store, sa, settings, method="GET", raw_path=path,
            headers={"X-Demo-Role": "platform_admin"},
        )
        assert response["statusCode"] == 200, (path, response["statusCode"])


def test_le_dossier_de_preuves_de_la_demo_est_scelle_et_verifiable(env):
    """La démo locale montre la même preuve que la production : une empreinte."""
    store, sa, settings = env
    response = serve_local.dispatch(
        store, sa, settings, method="GET", raw_path="/v1/tenants/demo-a/evidence",
        headers={"X-Demo-Role": "platform_admin"},
    )
    pack = _body(response)
    digest = pack["integrity"]["digest"]
    assert len(digest) == 64
    payload = {k: v for k, v in pack.items() if k not in ("integrity", "s3_key")}
    canonical = json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False, default=str)
    assert hashlib.sha256(canonical.encode("utf-8")).hexdigest() == digest
