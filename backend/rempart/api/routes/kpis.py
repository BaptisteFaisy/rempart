"""Route handlers for KPI endpoints (deterministic metrics only, ENF-IA-01)."""

from typing import Any

from rempart.api.context import ApiContext
from rempart.api.helpers import (
    authorize,
    current_month,
    error_response,
    get_store,
    load_tenant_or_404,
    require_principal,
)
from rempart.api.router import Router
from rempart.reports.metrics import compute_kpis

MSP_ROLES = ("platform_admin", "analyst", "account_manager")

def get_tenant_kpis(ctx: ApiContext) -> tuple[int, dict[str, Any]]:
    """Compute deterministic KPIs for a single tenant over a given period."""
    principal, err = require_principal(ctx)
    if err:
        return err
    tenant_id = ctx.path_params.get("id", "")
    err = authorize(principal, tenant_id, write=False)
    if err:
        return err

    store = get_store(ctx)
    _tenant, err = load_tenant_or_404(store, tenant_id)
    if err:
        return err

    period = ctx.query.get("period") or current_month()
    return 200, compute_kpis(store, tenant_id=tenant_id, period=period)

def get_fleet_kpis(ctx: ApiContext) -> tuple[int, dict[str, Any]]:
    """Fleet-wide KPIs, restricted to MSP roles (client_* and demo get 403)."""
    principal, err = require_principal(ctx)
    if err:
        return err
    if principal.role not in MSP_ROLES:
        return error_response(
            "Accès réservé aux rôles MSP (platform_admin, analyst, account_manager)", 403
        )

    period = ctx.query.get("period") or current_month()
    return 200, compute_kpis(get_store(ctx), tenant_id=None, period=period)

def register(router: Router) -> None:
    router.add("GET", "/v1/tenants/:id/kpis", get_tenant_kpis)
    router.add("GET", "/v1/fleet/kpis", get_fleet_kpis)
