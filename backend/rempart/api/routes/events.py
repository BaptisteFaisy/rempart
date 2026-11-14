"""Route handlers for CI/CD pipeline deployment events (no JWT, key-based auth).

Trois protections, dans cet ordre : clé partagée, **signature HMAC** du corps,
puis **limite de débit** par dépôt. Le webhook est le seul point d'entrée sans
jeton : c'est donc celui qui doit être le plus surveillé.

Les primitives de signature vivent dans :mod:`rempart.api.webhook_auth`, partagé
avec le webhook GitHub — une seule implémentation de la comparaison
constante-temps dans le produit, et les deux routes refusent de la même façon.
"""

from __future__ import annotations

from typing import Any

from rempart.api import webhook_auth as wh
from rempart.api.context import ApiContext
from rempart.api.helpers import (
    Response,
    application_for_repository,
    error_response,
    get_store,
)
from rempart.api.router import Router
from rempart.common import ratelimit

#: Champs du corps qui doivent être des chaînes quand ils sont présents.
STRING_FIELDS = ("repository", "commit_sha", "environment", "ref_name", "timestamp")
SECRET_ATTR = "pipeline_key"
SECRET_ENV = "REMPART_PIPELINE_KEY"

# Réponse unique et neutre : distinguer « clé absente » de « clé fausse »
# renseigne un appelant non authentifié sur la configuration du serveur
# (constat réel du 2026-11-12 sur l'API eu-north-1, où aucune clé n'était
# posée et où le message le disait à tout venant). La cause exacte reste
# tracée dans le journal d'audit, qui n'est lisible que par les rôles habilités.
DENIED_RESPONSE = "Clé pipeline invalide ou absente"

# Ré-exports : la forme canonique et la signature du corps canonique sont le
# contrat du client de test (`scripts/aws_bench_user.py`, tests d'endurcissement).
canonical_body = wh.canonical_body
signature_of = wh.signature_of


def _expected_key(ctx: ApiContext) -> str | None:
    """Resolve the shared pipeline key from settings attribute or environment."""
    return wh.resolve_secret(ctx.settings, SECRET_ATTR, SECRET_ENV)


def _check_pipeline_key(ctx: ApiContext) -> Response | None:
    """Return a 403 response when the pipeline shared key is missing or wrong."""
    expected = _expected_key(ctx)
    if not expected:
        return wh.deny(ctx, "deployment_event.rejected", "unconfigured", DENIED_RESPONSE)

    provided = wh.header_get(ctx.headers, "X-Rempart-Key")
    if not provided or provided != expected:
        return wh.deny(ctx, "deployment_event.rejected", "unknown", DENIED_RESPONSE)
    return None


def _check_signature(ctx: ApiContext, key: str) -> Response | None:
    """Refus neutre si la signature HMAC est absente ou fausse."""
    provided = wh.header_get(ctx.headers, "X-Rempart-Signature")
    if not wh.signature_matches(provided, signature_of(ctx.body, key)):
        return wh.deny(ctx, "deployment_event.rejected", "bad_signature", DENIED_RESPONSE)
    return None


def _validate_body(ctx: ApiContext) -> Response | None:
    """Validation stricte du corps : types et longueurs, refus explicite."""
    if not isinstance(ctx.body, dict) or not ctx.body:
        return error_response("Corps JSON attendu : un objet non vide", 400)
    for field in STRING_FIELDS:
        if field in ctx.body and not isinstance(ctx.body[field], str):
            return error_response(f"`{field}` doit être une chaîne", 400)
    if wh.repository_of(ctx.body.get("repository")) is None:
        return error_response(
            "`repository` est requis (owner/repo, "
            f"{wh.MAX_REPOSITORY_LENGTH} caractères maximum)",
            400,
        )
    return None


def _match_application(ctx: ApiContext, repository: str) -> tuple[str | None, str | None]:
    """Find the (tenant_id, app_id) owning the pushed repository, if any."""
    app = application_for_repository(get_store(ctx), repository)
    return (app.tenant_id, app.app_id) if app else (None, None)


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


__all__ = [
    "DENIED_RESPONSE",
    "STRING_FIELDS",
    "canonical_body",
    "post_deployment_event",
    "ratelimit",
    "register",
    "signature_of",
]
