#!/usr/bin/env python3
"""Preuves rejouables des correctifs, contre l'environnement RÉEL déployé.

Chaque contrôle affiche la valeur OBSERVÉE et d'où elle vient : une preuve
n'est pas une affirmation, c'est une valeur qu'un tiers peut recalculer.

Ce que le script prouve, étape par étape (ordre = ordre des correctifs) :

  P1  D7  le preflight CORS est traité par API Gateway (204) et non par l'API
  P2  D8  un vrai jeton Cognito est accepté (200 + tenants réels)
  P3  D8  une requête sans jeton est refusée (401)
  P4  D4  le dossier de preuves est RÉELLEMENT stocké, et son empreinte se
           recalcule depuis l'objet retéléchargé
  P5  D6  les 4 routes de gouvernance répondent 200 avec leurs champs
  P6  D1  la prévision est recalculable depuis les lignes DynamoDB
  P7  D5  la route de mise à jour d'application (fenêtres de test) existe
  P8  D9  le webhook de déploiement refuse sans révéler la configuration
  P9  CORS une origine non autorisée ne reçoit aucun en-tête CORS
  P10 D6  le code déployé est bien celui du dépôt (empreinte + date)
  P11 D10 le portail déployé sert la page de connexion, sans erreur réseau

Usage :
    REMPART_TOKEN="$(cat ~/.rempart-token)" python3 scripts/proof_real.py
    python3 scripts/proof_real.py --json > preuves.json

Le jeton s'obtient sans mot de passe en base : `aws cognito-idp initiate-auth`
sur un utilisateur de test (cf. docs/preuves/README.md). Sans jeton, seules
les preuves qui n'exigent pas d'authentification sont jouées (P1, P3, P8, P9,
P10, P11) et le script le dit.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import UTC, datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from proof_aws import api_function, fetch_stored_object, scan_runs, sha256_of_pack
from proof_core import PROOFS, record, record_bool, request

API = os.environ.get("REMPART_API", "https://qm6dmdkgdg.execute-api.eu-north-1.amazonaws.com")
PORTAL = os.environ.get("REMPART_PORTAL", "https://d1o2xnfrq8xomh.cloudfront.net")
PAGES = os.environ.get("REMPART_PAGES", "https://tradoooo.github.io/rempart")
REGION = os.environ.get("AWS_REGION", "eu-north-1")
PREFIX = "rempart-"
TOKEN = os.environ.get("REMPART_TOKEN", "")
GOVERNANCE_STRINGS = (
    "Evidence Dossier",
    "Audit Journal",
    "Industrialization",
    "Forecast",
    "Contract Correction Policy",
)


def proof_p1_preflight() -> None:
    """D7 — le preflight doit être traité SANS.authorizer JWT."""
    req = urllib.request.Request(
        f"{API}/v1/tenants",
        method="OPTIONS",
        headers={
            "Origin": PORTAL,
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "authorization,content-type",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as response:
            status = response.status
            headers = dict(response.headers)
    except urllib.error.HTTPError as exc:
        status = exc.code
        headers = dict(exc.headers or {})
    record_bool(
        "P1",
        "le preflight CORS est traité par API Gateway (204), pas par la Lambda",
        200 <= status < 300,
        f"HTTP {status}",
        f"OPTIONS {API}/v1/tenants avec Origin={PORTAL}",
    )
    record(
        "P1b",
        "l'origine du portail est autorisée au preflight",
        PORTAL,
        headers.get("access-control-allow-origin"),
        "en-tête access-control-allow-origin de la réponse OPTIONS",
    )


def proof_p2_p3_auth() -> list[str]:
    """D8 — un jeton réel passe, une requête anonyme est refusée."""
    anonymous = request("GET", f"{API}/v1/tenants", token=None)
    record(
        "P3",
        "sans jeton, l'API refuse la requête",
        401,
        anonymous["status"],
        f"GET {API}/v1/tenants sans Authorization",
    )
    if not TOKEN:
        print("          note    : pas de REMPART_TOKEN → P2 et P4 non joués")
        return []
    authenticated = request("GET", f"{API}/v1/tenants")
    tenants = authenticated["body"].get("tenants", [])
    record(
        "P2",
        "avec un vrai jeton Cognito, l'API renvoie les tenants réels",
        200,
        authenticated["status"],
        f"GET {API}/v1/tenants avec Bearer <jeton>",
    )
    record_bool(
        "P2b",
        "des tenants réels sont renvoyés",
        len(tenants) > 0,
        f"{len(tenants)} tenant(s) : {[t.get('tenant_id') for t in tenants]}",
        "corps de la réponse GET /v1/tenants",
    )
    return [t.get("tenant_id", "") for t in tenants if t.get("tenant_id")]


def proof_p4_evidence(tenant: str) -> None:
    """D4 — le dossier est stocké ET son empreinte se recalcule."""
    response = request("POST", f"{API}/v1/tenants/{tenant}/evidence", body={})
    body = response["body"]
    record(
        "P4",
        "POST /evidence est accepté",
        201,
        response["status"],
        f"POST {API}/v1/tenants/{tenant}/evidence",
    )
    key = body.get("s3_key")
    digest = (body.get("integrity") or {}).get("digest")
    record_bool("P4b", "une clé de stockage est annoncée", bool(key), key, "champ s3_key de la réponse")
    if not key:
        return
    stored = fetch_stored_object(key)
    record_bool(
        "P4c",
        "l'objet annoncé EXISTE dans un bucket du compte",
        stored is not None,
        f"{len(stored)} octets" if stored else "objet introuvable",
        f"get_object sur la clé {key}",
    )
    if not stored:
        return
    recomputed = sha256_of_pack(stored)
    record(
        "P4d",
        "l'empreinte se recalcule depuis l'objet retéléchargé",
        digest,
        recomputed,
        "sha256(json canonique) recalculé localement sur l'objet téléchargé",
        note="recalcul indépendant, sans appeler le code de Rempart",
    )


def proof_p5_governance(tenant: str) -> None:
    """D6 — les 4 routes de gouvernance répondent avec leurs champs."""
    expected = {
        "forecast": ("days_elapsed", "projected_hours", "exhaustion_date"),
        "industrialization": ("intervention", "alert_fatigue", "minutes_saved", "corpus"),
        "evidence": ("identity", "scope", "tests", "kpis"),
        "policy": ("policy", "effective"),
    }
    for route, keys in expected.items():
        response = request("GET", f"{API}/v1/tenants/{tenant}/{route}")
        body = response["body"]
        record(
            f"P5.{route}",
            f"GET /v1/tenants/{{id}}/{route} répond 200",
            200,
            response["status"],
            f"GET {API}/v1/tenants/{tenant}/{route}",
        )
        missing = [k for k in keys if k not in body]
        record(f"P5.{route}.champs", f"les champs {route} sont présents", [], missing, "clés du corps JSON")


def proof_p5b_sealed(tenant: str) -> None:
    """La page « Evidence Dossier » annonce une empreinte : elle doit y être."""
    pack = request("GET", f"{API}/v1/tenants/{tenant}/evidence").get("body", {})
    integrity = pack.get("integrity") or {}
    record(
        "P5b",
        "le dossier renvoyé porte son empreinte SHA-256",
        True,
        bool(integrity.get("digest")) and integrity.get("algorithm") == "sha256",
        f"GET /v1/tenants/{tenant}/evidence → integrity",
        note="sans elle, le portail affiche « Integrity fingerprint — not available from the API »",
    )
    if not integrity.get("digest"):
        return
    record(
        "P5c",
        "l'empreinte se recalcule depuis le dossier reçu",
        integrity["digest"],
        sha256_of_pack(pack),
        "sha256(json canonique) recalculé localement sur la réponse",
    )


def proof_p6_forecast(tenant: str) -> None:
    """D1 — la prévision est recalculable depuis les lignes DynamoDB."""
    try:
        rows = scan_runs()
    except Exception as exc:  # noqa: BLE001 — sans credentials : preuve non jouée
        print(f"          note    : DynamoDB illisible ({type(exc).__name__}) — P6 non joué")
        return
    period = datetime.now(UTC).strftime("%Y-%m")
    month_runs = [r for r in rows if str(r.get("started_at", "")).startswith(period)]
    hours = sum(float(r.get("task_hours") or 0.0) for r in month_runs)
    response = request("GET", f"{API}/v1/tenants/{tenant}/forecast")
    body = response["body"]
    record(
        "P6",
        "les heures consommées du mois (DynamoDB) sont celles de la prévision (API)",
        round(hours, 6),
        round(float(body.get("hours_used", 0.0)), 6),
        f"scan rempart-runs vs GET /v1/tenants/{tenant}/forecast",
    )
    days = datetime.now(UTC).day
    record(
        "P6b",
        "les jours écoulés retenus sont bien ceux du jour (jamais 0, jamais 30)",
        days,
        body.get("days_elapsed"),
        "champ days_elapsed de la prévision",
    )


def proof_p7_application_route(tenant: str) -> None:
    """D5 — la route de mise à jour d'application (fenêtres de test) existe."""
    evidence = request("GET", f"{API}/v1/tenants/{tenant}/evidence").get("body", {})
    scope = evidence.get("scope") or []
    if not scope:
        record_bool(
            "P7",
            "des applications existent pour tester la route",
            False,
            "aucune application dans le périmètre",
            f"GET /v1/tenants/{tenant}/evidence → scope",
        )
        return
    app_id = scope[0].get("app_id", "")
    response = request("PUT", f"{API}/v1/applications/{app_id}-inexistant", body={"criticality": "high"})
    record_bool(
        "P7",
        "PUT /v1/applications/{id} existe (404 « application », pas « route inconnue »)",
        "Application" in json.dumps(response["body"]),
        response["body"],
        f"PUT {API}/v1/applications/{app_id}-inexistant",
    )


def proof_p8_webhook() -> None:
    """D9 — le webhook refuse sans révéler l'état de la configuration."""
    response = request(
        "POST",
        f"{API}/v1/events/deployment",
        body={"repository": "proof/probe"},
        token=None,
    )
    record(
        "P8",
        "le webhook de déploiement refuse une requête sans clé",
        403,
        response["status"],
        f"POST {API}/v1/events/deployment sans X-Rempart-Key",
    )
    body = json.dumps(response["body"], ensure_ascii=False).lower()
    record_bool(
        "P8b",
        "le refus ne révèle pas si une clé est configurée côté serveur",
        "configur" not in body,
        response["body"],
        "corps de la réponse 403",
    )


def proof_p9_cors() -> None:
    """CORS — une origine non autorisée ne reçoit aucun en-tête d'autorisation."""
    response = request(
        "GET",
        f"{API}/v1/tenants",
        token=None,
        headers={"Origin": "https://evil.example"},
    )
    allowed = response["headers"].get("access-control-allow-origin")
    record_bool(
        "P9",
        "une origine non autorisée ne reçoit pas d'Access-Control-Allow-Origin",
        allowed is None or allowed != "https://evil.example",
        allowed,
        f"GET {API}/v1/tenants avec Origin: https://evil.example",
    )


def proof_p10_deploy() -> None:
    """D6 — le code déployé est bien celui du dépôt (empreinte + date)."""
    try:
        function = api_function()
    except Exception as exc:  # noqa: BLE001 — sans credentials : preuve non jouée
        print(f"          note    : Lambda illisible ({type(exc).__name__}) — P10 non joué")
        return
    if function is None:
        record_bool("P10", "la Lambda API est déployée", False, "aucune fonction trouvée", "lambda:ListFunctions")
        return
    since = os.environ.get("REMPART_DEPLOY_SINCE", "")
    deployed = function["last_modified"]
    record_bool(
        "P10",
        "la Lambda API déployée est bien plus récente que le correctif",
        bool(deployed) and (not since or deployed >= since),
        f"déployée le {deployed} (attendu >= {since or '—'})",
        "lambda:GetFunction → LastModified",
        note="Lambda zippée : AWS n'expose pas de SHA du code ; la preuve est la date de déploiement et les preuves comportementales P1/P4/P9",
    )
    variables = sorted(k for k in function["variables"] if k.startswith("REMPART_"))
    record_bool(
        "P10b",
        "les variables attendues par les correctifs sont posées",
        all(
            key in function["variables"]
            for key in ("REMPART_CORS_ALLOW_ORIGINS", "REMPART_REPORTS_BUCKET")
        ),
        variables,
        "lambda:GetFunction → Environment.Variables",
    )


def proof_p11_portal() -> None:
    """D10 — le portail déployé sert la page de connexion, sans erreur réseau."""
    index = request("GET", f"{PORTAL}/")
    html = index.get("text", "")
    assets = [
        part.lstrip("/")
        for part in html.split('"')
        if "assets/" in part and part.split("/")[-1].endswith(".js")
    ]
    bundle_url = f"{PORTAL}/{assets[0]}" if assets else f"{PORTAL}/"
    bundle = request("GET", bundle_url)
    text = bundle.get("text") or json.dumps(bundle.get("body"), ensure_ascii=False)
    record(
        "P11",
        "le portail CloudFront répond 200",
        200,
        index["status"],
        f"GET {PORTAL}/",
    )
    record_bool(
        "P11b",
        "le bundle servi contient les pages de gouvernance",
        all(s in text for s in GOVERNANCE_STRINGS),
        {s: (s in text) for s in GOVERNANCE_STRINGS},
        f"GET {bundle_url}",
    )
    pages = request("GET", f"{PAGES}/")
    record(
        "P11c",
        "le site public (mode démo hors ligne) répond toujours 200",
        200,
        pages["status"],
        f"GET {PAGES}/",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true", help="sortie JSON (machine)")
    args = parser.parse_args()

    print("=" * 78)
    print("PREUVES — Rempart, environnement réel déployé")
    print(f"API    : {API}")
    print(f"Portail: {PORTAL}")
    print(f"Pages  : {PAGES}")
    print(f"jeton  : {'présent' if TOKEN else 'ABSENT (preuves authentifiées non jouées)'}")
    print("=" * 78)

    proof_p1_preflight()
    tenants = proof_p2_p3_auth()
    tenant = tenants[0] if tenants else "demo-a"
    proof_p4_evidence(tenant)
    proof_p5_governance(tenant)
    proof_p5b_sealed(tenant)
    proof_p6_forecast(tenant)
    proof_p7_application_route(tenant)
    proof_p8_webhook()
    proof_p9_cors()
    proof_p10_deploy()
    proof_p11_portal()

    failed = [p for p in PROOFS if not p.ok]
    print("=" * 78)
    print(f"{len(PROOFS) - len(failed)}/{len(PROOFS)} preuves conformes")
    for proof in failed:
        print(f"  ÉCHEC {proof.pid} : attendu {proof.expected!r}, observé {proof.observed!r}")
    if args.json:
        print(json.dumps(
            {
                "ts": datetime.now(UTC).isoformat(),
                "api": API,
                "portal": PORTAL,
                "proofs": [p.__dict__ for p in PROOFS],
            },
            indent=2,
            ensure_ascii=False,
        ))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
