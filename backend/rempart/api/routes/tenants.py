"""Route handlers for Tenants."""

from typing import Any

from rempart.api.context import ApiContext
from rempart.api.helpers import (
    authorize,
    can_read,
    error_response,
    get_store,
    load_tenant_or_404,
    require_principal,
)
from rempart.api.router import Router
from rempart.common.models import Tenant
from rempart.common.timeutil import iso, utcnow


def _build_tenant(tenant_id: str, body: dict[str, Any]) -> Tenant:
    """Build a Tenant from a validated request body."""
    return Tenant(
        tenant_id=tenant_id,
        name=body.get("name", tenant_id),
        aws_account_id=body.get("aws_account_id", ""),
        region=body.get("region", "eu-west-3"),
        role_arn=body.get("role_arn", ""),
        external_id=body.get("external_id", ""),
        plan=body.get("plan", "essentiel"),
        contacts=body.get("contacts", []),
        monthly_budget_hours=float(body.get("monthly_budget_hours", 20.0)),
        mandate_status=body.get("mandate_status", "pending"),
        created_at=body.get("created_at") or iso(utcnow()),
    )

def post_tenant(ctx: ApiContext) -> tuple[int, dict[str, Any]]:
    """Create a new tenant (MSP admin/analyst only)."""
    principal, err = require_principal(ctx)
    if err:
        return err
    tenant_id = ctx.body.get("tenant_id")
    if not tenant_id:
        return error_response("Missing tenant_id in body", 400)
    err = authorize(principal, tenant_id, write=True)
    if err:
        return err

    store = get_store(ctx)
    if store.get_tenant(tenant_id):
        return error_response(f"Tenant '{tenant_id}' already exists", 409)

    tenant = _build_tenant(tenant_id, ctx.body)
    store.save_tenant(tenant)
    ctx.audit("tenant.create", "tenant", tenant_id)
    return 201, tenant.to_item()

def get_tenants(ctx: ApiContext) -> tuple[int, dict[str, Any]]:
    """List tenants visible to caller."""
    principal, err = require_principal(ctx)
    if err:
        return err
    visible = [
        tenant.to_item()
        for tenant in get_store(ctx).list_tenants()
        if can_read(principal, tenant.tenant_id)
    ]
    return 200, {"tenants": visible}

def get_tenant_by_id(ctx: ApiContext) -> tuple[int, dict[str, Any]]:
    """Retrieve a single tenant by tenant_id."""
    principal, err = require_principal(ctx)
    if err:
        return err
    tenant_id = ctx.path_params.get("id", "")
    err = authorize(principal, tenant_id, write=False)
    if err:
        return err

    tenant, err = load_tenant_or_404(get_store(ctx), tenant_id)
    if err or not tenant:
        return err  # type: ignore[return-value]
    return 200, tenant.to_item()

def register(router: Router) -> None:
    router.add("POST", "/v1/tenants", post_tenant)
    router.add("GET", "/v1/tenants", get_tenants)
    router.add("GET", "/v1/tenants/:id", get_tenant_by_id)
