"""Route handlers for CI/CD pipeline deployment events (no JWT, key-based auth)."""

import os
from typing import Any

from rempart.api.context import ApiContext
from rempart.api.helpers import error_response, get_store
from rempart.api.router import Router


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

def _match_application(ctx: ApiContext, repository: str) -> tuple[str | None, str | None]:
    """Find the (tenant_id, app_id) owning the pushed repository, if any."""
    for app in get_store(ctx).list_applications():
        if repository and repository in (app.repositories or []):
            return app.tenant_id, app.app_id
    return None, None

def post_deployment_event(ctx: ApiContext) -> tuple[int, dict[str, Any]]:
    """Record a deployment event sent by a CI/CD pipeline (authenticated by shared key)."""
    denied = _check_pipeline_key(ctx)
    if denied:
        return denied

    repository = ctx.body.get("repository", "")
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
