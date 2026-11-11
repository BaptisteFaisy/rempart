"""Route handlers for Tenants."""

from typing import Any

from rempart.api.context import ApiContext
from rempart.api.helpers import (
    Response,
    authorize,
    can_read,
    error_response,
    get_store,
    load_tenant_or_404,
    parse_float,
    require_principal,
)
from rempart.api.router import Router
from rempart.api.routes.settings import policy_write_forbidden, validate_policy
from rempart.common.models import Tenant
from rempart.common.tenant import Principal
from rempart.common.timeutil import iso, utcnow

UPDATABLE_TENANT_FIELDS = (
    "name",
    "plan",
    "mandate_status",
    "contacts",
    "monthly_budget_hours",
    "policy",
)


def _validate_policy_field(
    body: dict[str, Any],
) -> tuple[dict[str, Any] | None, Response | None]:
    """Validate the optional ``policy`` field of a tenant body."""
    if "policy" not in body:
        return None, None
    return validate_policy(body["policy"])


def _build_tenant(tenant_id: str, body: dict[str, Any]) -> tuple[Tenant | None, Response | None]:
    """Build a Tenant from a validated request body."""
    policy, err = _validate_policy_field(body)
    if err:
        return None, err
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
        policy=policy or {},
    ), None


def _check_policy_writer(principal: Principal, body: dict[str, Any]) -> Response | None:
    """Reject non-platform_admin callers that submit a ``policy`` field."""
    if "policy" not in body:
        return None
    return policy_write_forbidden(principal)


def post_tenant(ctx: ApiContext) -> tuple[int, dict[str, Any]]:
    """Create a new tenant (MSP admin/analyst only; policy: admin only)."""
    principal, err = require_principal(ctx)
    if err:
        return err
    tenant_id = ctx.body.get("tenant_id")
    if not tenant_id:
        return error_response("Missing tenant_id in body", 400)
    err = authorize(principal, tenant_id, write=True)
    if err:
        return err
    err = _check_policy_writer(principal, ctx.body)
    if err:
        return err

    store = get_store(ctx)
    if store.get_tenant(tenant_id):
        return error_response(f"Tenant '{tenant_id}' already exists", 409)

    tenant, err = _build_tenant(tenant_id, ctx.body)
    if err or not tenant:
        return err  # type: ignore[return-value]
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


def _apply_scalar_updates(body: dict[str, Any], tenant: Tenant) -> Response | None:
    """Apply name/plan/mandate_status/monthly_budget_hours from the body."""
    for field_name in ("name", "plan", "mandate_status"):
        if field_name in body:
            setattr(tenant, field_name, str(body[field_name]))
    if "monthly_budget_hours" not in body:
        return None
    hours, err = parse_float(body, "monthly_budget_hours")
    if err:
        return err
    if hours is None or hours < 0:
        return error_response("monthly_budget_hours must be >= 0", 400)
    tenant.monthly_budget_hours = hours
    return None


def _apply_tenant_update(ctx: ApiContext, tenant: Tenant) -> Response | None:
    """Apply the mutable fields (including policy) of a tenant update."""
    body = ctx.body
    unknown = sorted(k for k in body if k not in UPDATABLE_TENANT_FIELDS)
    if unknown:
        return error_response(f"Unknown tenant fields: {', '.join(unknown)}", 400)
    if "contacts" in body:
        if not isinstance(body["contacts"], list):
            return error_response("contacts must be a list", 400)
        tenant.contacts = body["contacts"]

    err = _apply_scalar_updates(body, tenant)
    if err:
        return err

    policy, err = _validate_policy_field(body)
    if err:
        return err
    if policy is not None:
        tenant.policy = policy
    return None


def put_tenant(ctx: ApiContext) -> tuple[int, dict[str, Any]]:
    """Update a tenant; the correction policy stays platform_admin-only."""
    principal, err = require_principal(ctx)
    if err:
        return err
    tenant_id = ctx.path_params.get("id", "")
    err = authorize(principal, tenant_id, write=True)
    if err:
        return err
    err = _check_policy_writer(principal, ctx.body)
    if err:
        return err

    store = get_store(ctx)
    tenant, err = load_tenant_or_404(store, tenant_id)
    if err or not tenant:
        return err  # type: ignore[return-value]

    err = _apply_tenant_update(ctx, tenant)
    if err:
        return err
    store.save_tenant(tenant)
    ctx.audit("tenant.update", "tenant", tenant_id)
    return 200, tenant.to_item()


def register(router: Router) -> None:
    router.add("POST", "/v1/tenants", post_tenant)
    router.add("GET", "/v1/tenants", get_tenants)
    router.add("PUT", "/v1/tenants/:id", put_tenant)
    router.add("GET", "/v1/tenants/:id", get_tenant_by_id)
