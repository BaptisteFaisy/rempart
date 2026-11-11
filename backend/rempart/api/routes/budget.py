"""Route handlers for Budget state and limits."""

from typing import Any

from rempart.api.context import ApiContext
from rempart.api.helpers import (
    Response,
    authorize,
    budget_payload,
    budget_verdict,
    current_month,
    error_response,
    get_store,
    load_tenant_or_404,
    parse_float,
    require_principal,
)
from rempart.api.router import Router
from rempart.common.models import BudgetState, Tenant


def _validate_budget_update(body: dict[str, Any]) -> tuple[float | None, Response | None]:
    """Validate ``monthly_budget_hours`` from the body; None when absent."""
    if "monthly_budget_hours" not in body:
        return None, None
    value, err = parse_float(body, "monthly_budget_hours")
    if err:
        return None, err
    if value is not None and value < 0:
        return None, error_response("monthly_budget_hours must be >= 0", 400)
    return value, None

def _apply_budget_update(ctx: ApiContext, tenant: Tenant) -> Response | None:
    """Persist a monthly budget limit change on the tenant, if requested."""
    new_budget, err = _validate_budget_update(ctx.body)
    if err:
        return err
    if new_budget is None:
        return None
    store = get_store(ctx)
    tenant.monthly_budget_hours = new_budget
    store.save_tenant(tenant)
    ctx.audit("tenant.budget_update", "tenant", tenant.tenant_id)
    return None

def _apply_consumption_update(ctx: ApiContext, state: BudgetState, month: str) -> Response | None:
    """Apply hours_used / auto_stop from the body and persist the state."""
    changed = False
    if "hours_used" in ctx.body:
        hours, err = parse_float(ctx.body, "hours_used")
        if err:
            return err
        state.hours_used = hours
        changed = True
    if "auto_stop" in ctx.body:
        state.auto_stop = bool(ctx.body["auto_stop"])
        changed = True

    if changed:
        store = get_store(ctx)
        store.save_budget(state)
        ctx.audit("budget.update", "budget", f"{state.tenant_id}#{month}")
    return None

def get_budget(ctx: ApiContext) -> tuple[int, dict[str, Any]]:
    """Get the budget consumption and verdict for a tenant's month."""
    principal, err = require_principal(ctx)
    if err:
        return err
    tenant_id = ctx.path_params.get("id", "")
    err = authorize(principal, tenant_id, write=False)
    if err:
        return err

    store = get_store(ctx)
    tenant, err = load_tenant_or_404(store, tenant_id)
    if err or not tenant:
        return err  # type: ignore[return-value]

    month = ctx.query.get("month") or current_month()
    state = store.get_budget(tenant_id, month)
    return 200, budget_payload(state, tenant, budget_verdict(ctx, state, tenant))

def put_budget(ctx: ApiContext) -> tuple[int, dict[str, Any]]:
    """Update budget limits or consumption state for a tenant's month."""
    principal, err = require_principal(ctx)
    if err:
        return err
    tenant_id = ctx.path_params.get("id", "")
    err = authorize(principal, tenant_id, write=True)
    if err:
        return err

    store = get_store(ctx)
    tenant, err = load_tenant_or_404(store, tenant_id)
    if err or not tenant:
        return err  # type: ignore[return-value]

    err = _apply_budget_update(ctx, tenant)
    if err:
        return err

    month = ctx.body.get("month") or current_month()
    state = store.get_budget(tenant_id, month)
    err = _apply_consumption_update(ctx, state, month)
    if err:
        return err

    return 200, budget_payload(state, tenant, budget_verdict(ctx, state, tenant))

def register(router: Router) -> None:
    router.add("GET", "/v1/tenants/:id/budget", get_budget)
    router.add("PUT", "/v1/tenants/:id/budget", put_budget)
