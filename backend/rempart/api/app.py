"""AWS Lambda entrypoint for API Gateway HTTP API v2 (chapter 14)."""

import json
from dataclasses import dataclass, field
from typing import Any

from rempart.common.config import Settings
from rempart.common.store import Store
from rempart.common.tenant import AuthError, Principal, resolve_principal

from .context import ApiContext
from .router import Handler, Router
from .routes import register_all

_CORS_HEADERS = {
    "Content-Type": "application/json",
    "Access-Control-Allow-Origin": "*",
}

_router: Router | None = None

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

def _respond(status_code: int, body: dict[str, Any]) -> dict[str, Any]:
    """Wrap a status code and JSON body into an API Gateway v2 response."""
    return {
        "statusCode": status_code,
        "headers": dict(_CORS_HEADERS),
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

def _resolve_principal(event: dict[str, Any]) -> Principal | None:
    """Extract the authenticated principal from JWT claims, if present and valid."""
    claims = (
        event.get("requestContext", {})
        .get("authorizer", {})
        .get("jwt", {})
        .get("claims")
    )
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
    return SecurityAgentClient(endpoint_url=settings.sa_endpoint_url, region=settings.region)

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
    )

def _dispatch(handler: Handler, ctx: ApiContext) -> dict[str, Any]:
    """Run a handler and convert its outcome (or exception) into a response."""
    try:
        status_code, payload = handler(ctx)
    except AuthError as exc:
        return _respond(exc.status_code, {"error": str(exc)})
    except Exception as exc:  # pragma: no cover - defensive catch-all
        return _respond(500, {"error": f"Internal server error: {exc}"})
    return _respond(status_code, payload)

def lambda_handler(
    event: dict[str, Any],
    context: Any = None,
    *,
    store: Any = None,
    sa: Any = None,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Handle an API Gateway HTTP API v2 request, dispatching to the matched route."""
    settings = settings or Settings.from_env()
    if store is None:
        store = Store(table_prefix=settings.table_prefix)
    if sa is None:
        sa = _default_sa(settings)

    request = _parse_request(event)
    body, body_error = _parse_body(request.body)
    if body_error:
        return _respond(400, {"error": "Invalid JSON body"})

    matched = get_router().match(request.method, request.raw_path)
    if not matched:
        return _respond(404, {"error": f"No route matches {request.method} {request.raw_path}"})

    handler, path_params = matched
    ctx = _build_context(event, request, body, path_params, store, sa, settings)
    return _dispatch(handler, ctx)
