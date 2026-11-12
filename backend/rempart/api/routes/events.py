"""Route handlers for CI/CD pipeline deployment events (no JWT, key-based auth).

Trois protections, dans cet ordre : clé partagée, **signature HMAC** du corps,
puis **limite de débit** par dépôt. Le webhook est le seul point d'entrée sans
jeton : c'est donc celui qui doit être le plus surveillé.
"""

import hashlib
import hmac
import json
import os
from typing import Any

from rempart.api.context import ApiContext
from rempart.api.helpers import error_response, get_store
from rempart.api.router import Router
from rempart.common import ratelimit

#: Longueur maximale d'un identifiant de dépôt (« owner/repo »).
MAX_REPOSITORY_LENGTH = 256
#: Champs du corps qui doivent être des chaînes quand ils sont présents.
STRING_FIELDS = ("repository", "commit_sha", "environment", "ref_name", "timestamp")


def _expected_key(ctx: ApiContext) -> str | None:
    """Resolve the shared pipeline key from settings attribute or environment."""
    if ctx.settings is not None:
        key = getattr(ctx.settings, "pipeline_key", None)
        if key:
            return str(key)
    return os.environ.get("REMPART_PIPELINE_KEY")

def _headers_get(ctx: ApiContext, name: str) -> str | None:
    """Case-insensitive header lookup (API Gateway v2 preserves original casing)."""
    for k, v in ctx.headers.items():
        if k.lower() == name.lower():
            return v
    return None

# Réponse unique et neutre : distinguer « clé absente » de « clé fausse »
# renseigne un appelant non authentifié sur la configuration du serveur
# (constat réel du 2026-11-12 sur l'API eu-north-1, où aucune clé n'était
# posée et où le message le disait à tout venant). La cause exacte reste
# tracée dans le journal d'audit, qui n'est lisible que par les rôles habilités.
DENIED_RESPONSE = "Clé pipeline invalide ou absente"


def _check_pipeline_key(ctx: ApiContext) -> tuple[int, dict[str, Any]] | None:
    """Return a 403 response when the pipeline shared key is missing or wrong."""
    expected = _expected_key(ctx)
    if not expected:
        ctx.audit("deployment_event.rejected", "pipeline", "unconfigured", result="denied")
        return error_response(DENIED_RESPONSE, 403)

    provided = _headers_get(ctx, "X-Rempart-Key")
    if not provided or provided != expected:
        ctx.audit("deployment_event.rejected", "pipeline", "unknown", result="denied")
        return error_response(DENIED_RESPONSE, 403)
    return None

def canonical_body(body: dict[str, Any]) -> bytes:
    """Forme canonique signée : JSON trié, séparateurs compacts, ASCII.

    Le client et le serveur canonicalisent de la même façon, donc la signature
    ne dépend ni de l'ordre des clés ni des espaces du JSON transmis.
    """
    return json.dumps(
        body, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")


def signature_of(body: dict[str, Any], key: str) -> str:
    """HMAC-SHA256 hexadécimal du corps canonique, avec la clé partagée."""
    return hmac.new(
        key.encode("utf-8"), canonical_body(body), hashlib.sha256
    ).hexdigest()


def _check_signature(ctx: ApiContext, key: str) -> tuple[int, dict[str, Any]] | None:
    """Refus neutre si la signature HMAC est absente ou fausse."""
    provided = _headers_get(ctx, "X-Rempart-Signature") or ""
    expected = signature_of(ctx.body, key)
    # `compare_digest` exige des chaînes ASCII : la signature est de l'hexadécimal.
    if not provided or not hmac.compare_digest(provided.strip().lower(), expected):
        ctx.audit("deployment_event.rejected", "pipeline", "bad_signature", result="denied")
        return error_response(DENIED_RESPONSE, 403)
    return None


def _validate_body(ctx: ApiContext) -> tuple[int, dict[str, Any]] | None:
    """Validation stricte du corps : types et longueurs, refus explicite."""
    if not isinstance(ctx.body, dict) or not ctx.body:
        return error_response("Corps JSON attendu : un objet non vide", 400)
    for field in STRING_FIELDS:
        if field in ctx.body and not isinstance(ctx.body[field], str):
            return error_response(f"`{field}` doit être une chaîne", 400)
    repository = ctx.body.get("repository", "")
    if not repository:
        return error_response("`repository` est requis", 400)
    if len(repository) > MAX_REPOSITORY_LENGTH:
        return error_response(
            f"`repository` dépasse {MAX_REPOSITORY_LENGTH} caractères", 400
        )
    return None


def _match_application(ctx: ApiContext, repository: str) -> tuple[str | None, str | None]:
    """Find the (tenant_id, app_id) owning the pushed repository, if any."""
    for app in get_store(ctx).list_applications():
        if repository and repository in (app.repositories or []):
            return app.tenant_id, app.app_id
    return None, None

def post_deployment_event(ctx: ApiContext) -> tuple[int, dict[str, Any]]:
    """Enregistre un événement de déploiement (clé + signature + débit)."""
    denied = _check_pipeline_key(ctx)
    if denied:
        return denied
    key = _expected_key(ctx) or ""
    denied = _check_signature(ctx, key)
    if denied:
        return denied
    invalid = _validate_body(ctx)
    if invalid:
        return invalid

    repository = ctx.body["repository"]
    if not ratelimit.allow(repository):
        ctx.audit("deployment_event.rate_limited", "repository", repository, result="denied")
        return error_response("Trop d'événements pour ce dépôt, réessayez plus tard", 429)
    tenant_id, app_id = _match_application(ctx, repository)

    ctx.audit(
        "deployment_event.received",
        "repository",
        repository or "unknown",
        result="ok",
    )

    return 202, {
        "received": True,
        "repository": repository,
        "commit_sha": ctx.body.get("commit_sha", ""),
        "environment": ctx.body.get("environment", ""),
        "ref_name": ctx.body.get("ref_name", ""),
        "timestamp": ctx.body.get("timestamp", ""),
        "tenant_id": tenant_id,
        "app_id": app_id,
    }

def register(router: Router) -> None:
    router.add("POST", "/v1/events/deployment", post_deployment_event)
