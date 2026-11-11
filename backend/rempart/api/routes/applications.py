"""Route handlers for Applications."""

import uuid
from typing import Any

from rempart.api.context import ApiContext
from rempart.api.helpers import (
    authorize,
    error_response,
    get_store,
    load_or_404,
    require_principal,
)
from rempart.api.router import Router
from rempart.common.models import Application
from rempart.common.timeutil import iso, utcnow


def _build_application(tenant_id: str, body: dict[str, Any]) -> Application:
    """Build an Application from a validated request body."""
    app_id = body.get("app_id") or f"app-{uuid.uuid4().hex[:8]}"
    return Application(
        app_id=app_id,
        tenant_id=tenant_id,
        name=body.get("name", app_id),
        criticality=body.get("criticality", "medium"),
        internet_exposed=bool(body.get("internet_exposed", False)),
        data_types=body.get("data_types", ["none"]),
        environment=body.get("environment", "staging"),
        agent_space_id=body.get("agent_space_id"),
        domains=body.get("domains", []),
        repositories=body.get("repositories", []),
        team=body.get("team", ""),
        ticket_channel=body.get("ticket_channel", "github"),
        context=body.get("context", {}),
        created_at=body.get("created_at") or iso(utcnow()),
    )

def post_application(ctx: ApiContext) -> tuple[int, dict[str, Any]]:
    """Create a new application under a tenant."""
    principal, err = require_principal(ctx)
    if err:
        return err
    tenant_id = ctx.path_params.get("id", "")
    err = authorize(principal, tenant_id, write=True)
    if err:
        return err

    store = get_store(ctx)
    if not store.get_tenant(tenant_id):
        return error_response(f"Tenant '{tenant_id}' not found", 404)

    app = _build_application(tenant_id, ctx.body)
    store.save_application(app)
    ctx.audit("application.create", "application", app.app_id)
    return 201, app.to_item()

def get_application_by_id(ctx: ApiContext) -> tuple[int, dict[str, Any]]:
    """Get application details by id."""
    principal, err = require_principal(ctx)
    if err:
        return err
    app_id = ctx.path_params.get("id", "")
    store = get_store(ctx)
    app, err = load_or_404(store.get_application, app_id, "Application")
    if err or not app:
        return err  # type: ignore[return-value]

    err = authorize(principal, app.tenant_id, write=False)
    if err:
        return err
    return 200, app.to_item()

def register(router: Router) -> None:
    router.add("POST", "/v1/tenants/:id/applications", post_application)
    router.add("GET", "/v1/applications/:id", get_application_by_id)
