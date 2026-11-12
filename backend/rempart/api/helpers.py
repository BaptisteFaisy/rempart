"""Shared helpers for API route handlers (auth, errors, budget, lookups).

Every helper here replaces logic that used to be copy-pasted across route
modules, so that handlers stay small and the isolation rules (ENF-SEC-01)
are enforced from a single place.
"""

from collections.abc import Callable
from typing import Any

from rempart.api.context import ApiContext
from rempart.common.budget import DEFAULT_HOURLY_RATE, BudgetVerdict, check_budget
from rempart.common.models import BudgetState, Tenant
from rempart.common.store import Store
from rempart.common.tenant import (
    AuthError,
    Principal,
    authorize_read,
    authorize_write,
)
from rempart.common.timeutil import iso, utcnow

Response = tuple[int, dict[str, Any]]

def error_response(message: str, status_code: int) -> Response:
    """Build a standard ``{"error": message}`` response tuple."""
    return status_code, {"error": message}

def not_found(label: str, obj_id: str) -> Response:
    """Build the standard 404 response for a missing object."""
    return 404, {"error": f"{label} '{obj_id}' not found"}

def get_store(ctx: ApiContext) -> Store:
    """Return the injected store, raising if the API is misconfigured."""
    if not ctx.store:
        raise RuntimeError("Store not configured")
    return ctx.store

def require_principal(ctx: ApiContext) -> tuple[Principal | None, Response | None]:
    """Return (principal, None) or (None, 401 response) when unauthenticated."""
    if not ctx.principal:
        return None, error_response("Authentication required", 401)
    return ctx.principal, None

def authorize(principal: Principal, tenant_id: str, *, write: bool) -> Response | None:
    """Return None when allowed, else the 403 response for the denied access."""
    try:
        if write:
            authorize_write(principal, tenant_id)
        else:
            authorize_read(principal, tenant_id)
    except AuthError as exc:
        return error_response(str(exc), exc.status_code)
    return None

def can_read(principal: Principal, tenant_id: str) -> bool:
    """Return True when the principal may read the tenant (used for filtering)."""
    return authorize(principal, tenant_id, write=False) is None

def load_or_404(
    getter: Callable[[str], Any], obj_id: str, label: str
) -> tuple[Any | None, Response | None]:
    """Fetch an object via ``getter``; return (object, None) or (None, 404)."""
    obj = getter(obj_id)
    if not obj:
        return None, not_found(label, obj_id)
    return obj, None

def load_tenant_or_404(store: Store, tenant_id: str) -> tuple[Tenant | None, Response | None]:
    """Fetch a tenant or return the standard 404 response."""
    return load_or_404(store.get_tenant, tenant_id, "Tenant")

def current_month() -> str:
    """Return the current billing month as ``YYYY-MM``."""
    return iso(utcnow())[:7]

def hourly_rate(ctx: ApiContext) -> float:
    """Resolve the configured hourly rate, falling back to the default."""
    return ctx.settings.hourly_rate if ctx.settings else DEFAULT_HOURLY_RATE

def kill_switch_active(ctx: ApiContext) -> bool:
    """Coupe-circuit global : vrai quand aucun test ne doit démarrer.

    Exposé tel quel dans le payload du budget pour que le portail affiche le
    bandeau d'arrêt ; hors contexte (settings absent), on retombe sur ``False``
    comme tout réglage non configuré.
    """
    return bool(ctx.settings.kill_switch) if ctx.settings else False

def budget_verdict(ctx: ApiContext, state: BudgetState, tenant: Tenant) -> BudgetVerdict:
    """Evaluate a budget state against the tenant's monthly allowance."""
    return check_budget(state, tenant.monthly_budget_hours, hourly_rate(ctx))

def budget_payload(
    state: BudgetState,
    tenant: Tenant,
    verdict: BudgetVerdict,
    kill_switch: bool = False,
) -> dict[str, Any]:
    """Build the budget representation shared by GET and PUT /budget."""
    return {
        **state.to_item(),
        "monthly_budget_hours": tenant.monthly_budget_hours,
        "budget_pct": verdict.pct,
        "allowed": verdict.allowed,
        "auto_stop": verdict.auto_stop,
        "kill_switch": bool(kill_switch),
    }

def parse_float(body: dict[str, Any], field: str) -> tuple[float | None, Response | None]:
    """Read a numeric body field; return (value, None) or (None, 400)."""
    try:
        return float(body[field]), None
    except (TypeError, ValueError):
        return None, error_response(f"{field} must be a number", 400)
