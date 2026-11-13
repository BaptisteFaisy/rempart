"""AWS Lambda entrypoint for API Gateway HTTP API v2 (chapter 14)."""

import json
import logging
from dataclasses import dataclass, field
from typing import Any

from rempart.common.config import Settings
from rempart.common.store import Store
from rempart.common.tenant import AuthError, Principal, resolve_principal

from .context import ApiContext
from .router import Handler, Router
from .routes import register_all

LOGGER = logging.getLogger("rempart.api")

_BASE_HEADERS = {"Content-Type": "application/json"}
# Origine par défaut quand aucune liste n'est configurée (`serve_local.py`) :
# le serveur de démonstration locale n'est jamais exposé au-delà de 127.0.0.1.
_WILDCARD_ORIGIN = "*"
_CORS_PREFLIGHT_HEADERS = {
    "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS",
    "Access-Control-Allow-Headers": "Authorization, Content-Type, X-Rempart-Key",
    "Access-Control-Max-Age": "600",
}

_router: Router | None = None
# Diagnostic D8 : une seule trace de la forme d'authorizer par processus.
_AUTHORIZER_SHAPE_LOGGED = False


def _origin_header(origin: str | None, settings: Settings | None) -> str | None:
    """Origine à renvoyer : écho si autorisée, `*` si aucune liste configurée."""
    allowed = tuple(getattr(settings, "cors_allow_origins", ()) or ())
    if not allowed:
        return _WILDCARD_ORIGIN
    if origin and origin.rstrip("/") in {item.rstrip("/") for item in allowed}:
        return origin
    return None


def _headers_for(
    origin: str | None, settings: Settings | None, preflight: bool = False
) -> dict[str, str]:
    """En-têtes de réponse, CORS restreint aux origines réellement autorisées."""
    headers = dict(_BASE_HEADERS)
    value = _origin_header(origin, settings)
    if value:
        headers["Access-Control-Allow-Origin"] = value
    if preflight:
        headers.update(_CORS_PREFLIGHT_HEADERS)
    return headers

@dataclass
class _Request:
    """Request fields extracted from an API Gateway HTTP API v2 event."""

    method: str = "GET"
    raw_path: str = "/"
    query: dict[str, str] = field(default_factory=dict)
    headers: dict[str, str] = field(default_factory=dict)
    body: Any = None

def get_router() -> Router:
    """Return the singleton Router with every route module registered."""
    global _router
    if _router is None:
        router = Router()
        register_all(router)
        _router = router
    return _router

def _respond(
    status_code: int,
    body: dict[str, Any],
    origin: str | None = None,
    settings: Settings | None = None,
    preflight: bool = False,
) -> dict[str, Any]:
    """Wrap a status code and JSON body into an API Gateway v2 response."""
    return {
        "statusCode": status_code,
        "headers": _headers_for(origin, settings, preflight=preflight),
        "body": json.dumps(body),
    }

def _parse_request(event: dict[str, Any]) -> _Request:
    """Extract method, path, query, headers, and raw body from the event."""
    request_context = event.get("requestContext", {})
    return _Request(
        method=request_context.get("http", {}).get("method", "GET"),
        raw_path=event.get("rawPath", "/"),
        query=event.get("queryStringParameters") or {},
        headers=event.get("headers") or {},
        body=event.get("body"),
    )

def _authorizer_of(event: dict[str, Any]) -> dict[str, Any]:
    """Le bloc `requestContext.authorizer` de l'événement, jamais `None`."""
    context = event.get("requestContext") or {}
    authorizer = context.get("authorizer") if isinstance(context, dict) else None
    return authorizer if isinstance(authorizer, dict) else {}


def _claims_of(authorizer: dict[str, Any]) -> dict[str, Any]:
    """Les claims JWT, dans les deux emplacements produits par API Gateway.

    HTTP API (v2) place les claims dans `authorizer.jwt.claims` ; d'autres
    configurations (REST API, authorizer Lambda) les exposent directement dans
    `authorizer.claims`. Les deux sont acceptées : ne regarder qu'un seul
    chemin ferait un 401 silencieux en production.
    """
    jwt = authorizer.get("jwt")
    if isinstance(jwt, dict) and isinstance(jwt.get("claims"), dict):
        return jwt["claims"]
    claims = authorizer.get("claims")
    return claims if isinstance(claims, dict) else {}


def _shape_of(value: Any) -> str:
    """Forme d'une claim, sans jamais en révéler le contenu.

    Donne juste de quoi reconnaître le format transmis (longueur, premier
    caractère, présence de guillemets) — suffisant pour diagnostiquer, assez
    pauvre pour ne rien divulguer.
    """
    if not isinstance(value, str):
        return type(value).__name__
    first = value[:1] or "-"
    return f"str(len={len(value)},first={first},quoted={'\"' in value})"


def _log_authorizer_shape_once(authorizer: dict[str, Any]) -> None:
    """Journalise UNE fois par processus la FORME de l'authorizer.

    Seulement des noms de clés, jamais de valeurs : un jeton ou un `sub` dans
    les journaux serait une fuite. L'objectif est de trancher sans ambiguïté,
    dans CloudWatch, entre « claims absentes » et « claims dans une autre
    forme » quand un appel authentifié est refusé.
    """
    global _AUTHORIZER_SHAPE_LOGGED
    if _AUTHORIZER_SHAPE_LOGGED:
        return
    _AUTHORIZER_SHAPE_LOGGED = True
    jwt = authorizer.get("jwt")
    claims = _claims_of(authorizer)
    # `print` et non `LOGGER.info` : la Lambda n'émet pas les messages INFO par
    # défaut (niveau WARNING), et ce diagnostic doit être lisible tel quel dans
    # CloudWatch pour trancher en une lecture. Aucune VALEUR n'est imprimée.
    print(
        "REMPART_DIAG authorizer_keys="
        f"{sorted(authorizer)} jwt_keys={sorted(jwt) if isinstance(jwt, dict) else None} "
        f"claim_keys={sorted(claims)} "
        f"groups_type={type(claims.get('cognito:groups')).__name__} "
        f"groups_shape={_shape_of(claims.get('cognito:groups'))} "
        f"has_sub={'sub' in claims}",
        flush=True,
    )
    LOGGER.warning(
        "Forme de l'authorizer (clés uniquement) : authorizer=%s jwt=%s claims=%s",
        sorted(authorizer),
        sorted(jwt) if isinstance(jwt, dict) else None,
        sorted(claims),
    )


def _resolve_principal(event: dict[str, Any]) -> Principal | None:
    """Extract the authenticated principal from JWT claims, if present and valid."""
    authorizer = _authorizer_of(event)
    _log_authorizer_shape_once(authorizer)
    claims = _claims_of(authorizer)
    if not claims:
        return None
    try:
        return resolve_principal(claims)
    except AuthError:
        return None

def _default_sa(settings: Settings) -> Any:
    """Lazily build the real Security Agent client; None if orchestrator is absent."""
    try:
        from rempart.orchestrator.sa_client import SecurityAgentClient
    except ImportError:
        return None
    return SecurityAgentClient(
        endpoint_url=settings.sa_endpoint_url,
        region=settings.region,
        role_arn=settings.sa_role_arn,
        external_id=settings.sa_external_id,
    )

def _parse_body(raw: Any) -> tuple[dict[str, Any], bool]:
    """Return (parsed_body, had_error) from the raw API Gateway v2 body field."""
    if not raw:
        return {}, False
    if isinstance(raw, dict):
        return raw, False
    try:
        parsed = json.loads(raw)
    except (ValueError, TypeError):
        return {}, True
    if not isinstance(parsed, dict):
        return {}, True
    return parsed, False

def _build_context(
    event: dict[str, Any],
    request: _Request,
    body: dict[str, Any],
    path_params: dict[str, str],
    store: Any,
    sa: Any,
    settings: Settings,
    s3: Any = None,
) -> ApiContext:
    """Assemble the ApiContext handed to a route handler."""
    return ApiContext(
        principal=_resolve_principal(event),
        path_params=path_params,
        query=request.query,
        body=body,
        headers=request.headers,
        store=store,
        settings=settings,
        sa=sa,
        s3=s3,
        origin=_origin_of(request),
    )

def _dispatch(handler: Handler, ctx: ApiContext) -> dict[str, Any]:
    """Run a handler and convert its outcome (or exception) into a response."""
    origin = ctx.origin
    settings = ctx.settings
    try:
        status_code, payload = handler(ctx)
    except AuthError as exc:
        return _respond(exc.status_code, {"error": str(exc)}, origin, settings)
    except Exception as exc:  # pragma: no cover - defensive catch-all
        return _respond(500, {"error": f"Internal server error: {exc}"}, origin, settings)
    return _respond(status_code, payload, origin, settings)

def _default_s3(settings: Settings) -> Any:
    """Client S3 réel du dossier de preuves, `None` si aucun bucket configuré.

    `reports/evidence.upload_evidence_pack` lit `getattr(s3, "bucket_name", …)`
    puis appelle `put_object` : on lui donne donc un objet qui porte le nom du
    bucket configuré au lieu de le laisser retomber sur une valeur codée en dur.
    """
    bucket = getattr(settings, "reports_bucket", None)
    if not bucket:
        return None
    try:
        import boto3
    except ImportError:  # pragma: no cover - boto3 est toujours présent en Lambda
        return None
    return _ReportsBucket(boto3.client("s3", region_name=settings.region), bucket)


class _ReportsBucket:
    """Client S3 restreint à ce que le dossier de preuves utilise."""

    def __init__(self, client: Any, bucket_name: str) -> None:
        self._client = client
        self.bucket_name = bucket_name

    def put_object(self, **kwargs: Any) -> Any:
        """Téléversement réel dans le bucket configuré."""
        return self._client.put_object(**kwargs)


def _origin_of(request: "_Request") -> str | None:
    """Origine de la requête (en-tête `Origin`), insensible à la casse."""
    for key, value in request.headers.items():
        if key.lower() == "origin":
            return str(value)
    return None


def lambda_handler(
    event: dict[str, Any],
    context: Any = None,
    *,
    store: Any = None,
    sa: Any = None,
    s3: Any = None,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Handle an API Gateway HTTP API v2 request, dispatching to the matched route."""
    settings = settings or Settings.from_env()
    if store is None:
        store = Store(table_prefix=settings.table_prefix)
    if sa is None:
        sa = _default_sa(settings)

    request = _parse_request(event)
    origin = _origin_of(request)
    if request.method == "OPTIONS":
        # Preflight CORS : répondu sans authentification ni routage, sinon un
        # navigateur n'obtient jamais de 2xx et bloque tout appel cross-origin.
        return _respond(204, {}, origin, settings, preflight=True)
    if s3 is None:
        s3 = _default_s3(settings)

    body, body_error = _parse_body(request.body)
    if body_error:
        return _respond(400, {"error": "Invalid JSON body"}, origin, settings)

    matched = get_router().match(request.method, request.raw_path)
    if not matched:
        return _respond(
            404,
            {"error": f"No route matches {request.method} {request.raw_path}"},
            origin,
            settings,
        )

    handler, path_params = matched
    ctx = _build_context(event, request, body, path_params, store, sa, settings, s3)
    return _dispatch(handler, ctx)
