#!/usr/bin/env python3
"""Serveur de démonstration 100 % local — zéro AWS, zéro euro.

Sert l'API `rempart.api` (routes du chapitre 14) sur `127.0.0.1:8000` en
réutilisant **le vrai** `lambda_handler` et le jeu de données figé
`demo/seed/demo-dataset.json` (produit par `scripts/seed_demo.py`, seule source
de vérité). Aucun compte AWS, aucune credential, aucun appel réseau sortant :
le `Store` est le `FakeStore` en mémoire et le client Security Agent est le
`FakeSecurityAgentClient`.

Chaque requête HTTP est traduite en événement **API Gateway HTTP API v2**, puis
passée à `lambda_handler(event, context, store=…, sa=…, settings=…)` : le code
exercé est donc exactement celui qui tournera en Lambda.

⚠️ MODE DÉMO, PAS UNE AUTHENTIFICATION. Les en-têtes `X-Demo-Role` (défaut
`platform_admin`) et `X-Demo-Tenant` sont traduits en claims Cognito
synthétiques (`cognito:groups`, `sub`, `custom:tenant_id`) pour que
`resolve_principal` et l'isolation par tenant s'appliquent comme en production.
N'importe qui peut se déclarer `platform_admin` : ce serveur ne doit jamais être
exposé au-delà de `127.0.0.1`.

Usage :
    python3 scripts/serve_local.py                 # http://127.0.0.1:8000
    python3 scripts/serve_local.py --port 9000     # autre port
    python3 scripts/serve_local.py --dataset autre.json
    python3 scripts/serve_local.py --check         # vérifie et sort (CI)

Documentation : `scripts/README-local-demo.md`.
"""

# Les imports dépendent des `sys.path.insert` ci-dessous (script hors package) :
# le fichier est chargé par chemin, pas comme module du package `rempart`.

from __future__ import annotations

import argparse
import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "scripts"))  # seed_demo.py : source du jeu figé

from rempart.api.app import get_router, lambda_handler
from rempart.common.config import Settings
from rempart.common.models import (
    Application,
    AuditEvent,
    BudgetState,
    Decision,
    Finding,
    Report,
    Run,
    Tenant,
    TestConfig,
)
from seed_demo import build_dataset, summarise
from tests.fakes_sa import FakeSecurityAgentClient
from tests.fakes_store import FakeStore

DEFAULT_DATASET = ROOT / "demo" / "seed" / "demo-dataset.json"
DEMO_ROLE_HEADER = "x-demo-role"
DEMO_TENANT_HEADER = "x-demo-tenant"
# Le portail envoie aussi X-Rempart-Role / X-Rempart-Tenant : on les accepte
# comme alias pour ne pas imposer deux conventions d'en-tête.
LEGACY_ROLE_HEADER = "x-rempart-role"
LEGACY_TENANT_HEADER = "x-rempart-tenant"
DEFAULT_ROLE = "platform_admin"
DEFAULT_DEMO_TENANT = "demo-a"
CLIENT_SCOPED_ROLES = ("client_security", "client_dev", "executive", "demo")

CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS",
    "Access-Control-Allow-Headers": (
        "Content-Type, Authorization, X-Demo-Role, X-Demo-Tenant, "
        "X-Rempart-Role, X-Rempart-Tenant"
    ),
    "Access-Control-Max-Age": "600",
}
PREFLIGHT_STATUS = 204
# (« suffixe de route », « paramètre de mois ») : l'API lit le mois courant,
# le jeu de démonstration est figé — voir `pin_demo_clock`.
CLOCK_RULES = (("/kpis", "period"), ("/budget", "month"))

# (modèle, méthode de sauvegarde) : même table que `seed_demo.load_into_store`,
# appliquée à un store injecté (FakeStore) au lieu de DynamoDB.
_SAVERS: dict[str, tuple[Any, str]] = {
    "tenants": (Tenant.from_item, "save_tenant"),
    "applications": (Application.from_item, "save_application"),
    "test_configs": (TestConfig.from_item, "save_config"),
    "runs": (Run.from_item, "save_run"),
    "findings": (Finding.from_item, "save_finding"),
    "decisions": (Decision.from_item, "save_decision"),
    "budget": (BudgetState.from_item, "save_budget"),
    "reports": (Report.from_item, "save_report"),
    # L'audit fait partie des collections versionnées depuis le 12/11/2026.
    "audit": (AuditEvent.from_item, "save_audit"),
}


def load_dataset(path: Path = DEFAULT_DATASET) -> dict[str, list[dict[str, Any]]]:
    """Charge le jeu figé versionné ; à défaut, le régénère avec `seed_demo`."""
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    print(f"[demo] {path} absent : jeu régénéré par seed_demo.build_dataset()")
    return build_dataset()


def store_from_dataset(dataset: dict[str, list[dict[str, Any]]]) -> FakeStore:
    """Charge le jeu dans un `FakeStore` en mémoire (aucune écriture AWS)."""
    store = FakeStore()
    for collection, items in dataset.items():
        if collection not in _SAVERS:
            # Collections dérivées (governance) : servies par les routes, qui
            # les recalculent depuis les entités chargées ci-dessous.
            continue
        from_item, method = _SAVERS[collection]
        for item in items:
            getattr(store, method)(from_item(item))
    return store


def demo_period(dataset: dict[str, list[dict[str, Any]]]) -> str:
    """Mois figé du jeu de démonstration (« 2026-10 » par défaut)."""
    budgets = dataset.get("budget") or []
    if budgets and budgets[0].get("month"):
        return str(budgets[0]["month"])
    return "2026-10"


def demo_claims(headers: dict[str, str]) -> dict[str, Any]:
    """Traduit les en-têtes de démo en claims Cognito (mode démo, pas d'auth)."""
    lowered = {k.lower(): v for k, v in headers.items()}
    role = lowered.get(DEMO_ROLE_HEADER) or lowered.get(LEGACY_ROLE_HEADER) or DEFAULT_ROLE
    tenant = lowered.get(DEMO_TENANT_HEADER) or lowered.get(LEGACY_TENANT_HEADER)
    if not tenant and role in CLIENT_SCOPED_ROLES:
        tenant = DEFAULT_DEMO_TENANT
    claims: dict[str, Any] = {"sub": f"demo-{role}@local", "cognito:groups": [role]}
    if tenant:
        claims["custom:tenant_id"] = tenant
    return claims


def build_event(
    method: str,
    raw_path: str,
    *,
    query: dict[str, str] | None = None,
    headers: dict[str, str] | None = None,
    body: bytes | str | None = None,
) -> dict[str, Any]:
    """Traduit une requête HTTP en événement API Gateway HTTP API v2."""
    lowered = {k.lower(): v for k, v in (headers or {}).items()}
    if isinstance(body, bytes):
        raw_body: str | None = body.decode("utf-8") if body else None
    else:
        raw_body = body
    return {
        "version": "2.0",
        "routeKey": f"{method.upper()} {raw_path}",
        "rawPath": raw_path,
        "rawQueryString": "",
        "queryStringParameters": query or None,
        "headers": lowered,
        "body": raw_body,
        "isBase64Encoded": False,
        "requestContext": {
            "http": {
                "method": method.upper(),
                "path": raw_path,
                "protocol": "HTTP/1.1",
                "sourceIp": "127.0.0.1",
            },
            "authorizer": {"jwt": {"claims": demo_claims(lowered)}},
        },
    }


def pin_demo_clock(raw_path: str, query: dict[str, str], period: str) -> dict[str, str]:
    """Fixe la période des routes KPI/budget sur le mois du jeu figé.

    En production le mois courant est le bon défaut ; le jeu de démonstration,
    lui, est figé sur octobre 2026. Sans cette retouche les cartes KPI du
    portail afficheraient des zéros. Un paramètre explicite reste prioritaire.
    """
    key = next((k for suffix, k in CLOCK_RULES if raw_path.endswith(suffix)), None)
    if key is None or key in query:
        return query
    return {**query, key: period}


def dispatch(
    store: FakeStore,
    sa: FakeSecurityAgentClient,
    settings: Settings,
    *,
    method: str,
    raw_path: str,
    query: dict[str, str] | None = None,
    headers: dict[str, str] | None = None,
    body: bytes | str | None = None,
    period: str = "2026-10",
) -> dict[str, Any]:
    """Traduit la requête puis appelle le vrai handler Lambda."""
    prepared = pin_demo_clock(raw_path, dict(query or {}), period)
    event = build_event(method, raw_path, query=prepared, headers=headers, body=body)
    return lambda_handler(event, None, store=store, sa=sa, settings=settings)


def preflight_response() -> tuple[int, dict[str, str], bytes]:
    """Répond au preflight CORS (le portail Vite en dev sert une autre origine)."""
    return PREFLIGHT_STATUS, dict(CORS_HEADERS), b""


def routes_served() -> list[str]:
    """Liste les routes servies, lues dans le registre du routeur de l'API."""
    return [f"{route.method:6} {route.pattern}" for route in get_router()._routes]


class DemoRequestHandler(BaseHTTPRequestHandler):
    """Traduit chaque requête HTTP en événement API Gateway v2."""

    server_version = "RempartDemo/1.0"

    def do_OPTIONS(self) -> None:
        self._respond(*preflight_response())

    def do_GET(self) -> None:
        self._forward("GET")

    def do_POST(self) -> None:
        self._forward("POST")

    def do_PUT(self) -> None:
        self._forward("PUT")

    def do_DELETE(self) -> None:
        self._forward("DELETE")

    def _read_body(self) -> bytes:
        length = int(self.headers.get("Content-Length") or 0)
        return self.rfile.read(length) if length else b""

    def _forward(self, method: str) -> None:
        url = urlsplit(self.path)
        query = {name: values[-1] for name, values in parse_qs(url.query).items()}
        response = dispatch(
            self.server.store,
            self.server.sa,
            self.server.settings,
            method=method,
            raw_path=url.path,
            query=query,
            headers=dict(self.headers.items()),
            body=self._read_body(),
            period=self.server.period,
        )
        body = (response.get("body") or "").encode("utf-8")
        self._respond(response["statusCode"], response.get("headers") or {}, body)

    def _respond(self, status: int, headers: dict[str, str], body: bytes) -> None:
        self.send_response(status)
        for name, value in {**CORS_HEADERS, **headers}.items():
            self.send_header(name, value)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if body:
            self.wfile.write(body)

    def log_message(self, format: str, *args: Any) -> None:
        print(f"[demo] {format % args}")


class DemoServer(ThreadingHTTPServer):
    """Serveur local portant les dépendances injectées dans le handler."""

    daemon_threads = True

    def __init__(
        self,
        address: tuple[str, int],
        store: FakeStore,
        sa: FakeSecurityAgentClient,
        settings: Settings,
        period: str,
    ) -> None:
        super().__init__(address, DemoRequestHandler)
        self.store = store
        self.sa = sa
        self.settings = settings
        self.period = period


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Serveur de démonstration Rempart 100 % local (zéro AWS)."
    )
    parser.add_argument("--host", default="127.0.0.1", help="interface d'écoute")
    parser.add_argument("--port", type=int, default=8000, help="port d'écoute")
    parser.add_argument(
        "--dataset", type=Path, default=DEFAULT_DATASET, help="jeu de données JSON"
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="ne sert rien : vérifie deux routes, affiche les routes et sort",
    )
    return parser.parse_args(argv)


def run_check(dataset: dict[str, list[dict[str, Any]]]) -> int:
    """Vérifie le montage du jeu et deux routes, sans ouvrir de socket (CI)."""
    store = store_from_dataset(dataset)
    sa = FakeSecurityAgentClient()
    settings = Settings()
    period = demo_period(dataset)
    for line in routes_served():
        print(f"route  {line}")
    failures: list[str] = []
    for path in ("/v1/tenants", "/v1/findings"):
        response = dispatch(
            store, sa, settings, method="GET", raw_path=path, period=period,
            headers={DEMO_ROLE_HEADER: DEFAULT_ROLE},
        )
        payload = json.loads(response.get("body") or "{}")
        items = sum(len(v) for v in payload.values() if isinstance(v, list))
        print(f"check  GET {path} -> {response['statusCode']} ({items} item(s))")
        if response["statusCode"] != 200 or items == 0:
            failures.append(f"{path} -> {response['statusCode']}")
    if failures:
        print(f"[check] ÉCHEC : {', '.join(failures)}")
        return 1
    print(f"[check] OK : jeu de démonstration servi (période KPI {period}), zéro AWS.")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    # Sortie non tamponnée : le résumé est visible même derrière un redirect
    # (nohup, CI, journal de démonstration).
    sys.stdout.reconfigure(line_buffering=True)
    dataset = load_dataset(args.dataset)
    if args.check:
        return run_check(dataset)

    period = demo_period(dataset)
    print(summarise(dataset))
    print(f"\n[demo] période KPI/budget par défaut : {period} (mois du jeu figé)")
    print(
        f"[demo] API locale : http://{args.host}:{args.port} "
        f"({len(routes_served())} routes, jeu : {args.dataset})"
    )
    print(
        f"[demo] Mode DÉMO, pas une authentification : en-têtes X-Demo-Role "
        f"(défaut {DEFAULT_ROLE}) et X-Demo-Tenant. Aucun appel AWS."
    )
    server = DemoServer(
        (args.host, args.port),
        store_from_dataset(dataset),
        FakeSecurityAgentClient(),
        Settings(),
        period,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[demo] arrêt demandé.")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
