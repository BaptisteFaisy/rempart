"""Route handlers for monthly Reports (built deterministically, ENF-IA-01)."""

from typing import Any

from rempart.api.context import ApiContext
from rempart.api.helpers import (
    authorize,
    current_month,
    get_store,
    load_or_404,
    load_tenant_or_404,
    require_principal,
)
from rempart.api.router import Router
from rempart.reports.monthly import build_monthly_report


def post_report(ctx: ApiContext) -> tuple[int, dict[str, Any]]:
    """Generate and persist a monthly report for a tenant."""
    principal, err = require_principal(ctx)
    if err:
        return err
    tenant_id = ctx.path_params.get("id", "")
    err = authorize(principal, tenant_id, write=True)
    if err:
        return err

    store = get_store(ctx)
    _tenant, err = load_tenant_or_404(store, tenant_id)
    if err:
        return err

    period = ctx.body.get("period") or current_month()
    report = build_monthly_report(store=store, tenant_id=tenant_id, period=period)
    ctx.audit("report.create", "report", report.report_id)
    return 201, report.to_item()

def get_report_by_id(ctx: ApiContext) -> tuple[int, dict[str, Any]]:
    """Retrieve a stored report by id."""
    principal, err = require_principal(ctx)
    if err:
        return err
    report_id = ctx.path_params.get("id", "")
    store = get_store(ctx)
    report, err = load_or_404(store.get_report, report_id, "Report")
    if err or not report:
        return err  # type: ignore[return-value]

    err = authorize(principal, report.tenant_id, write=False)
    if err:
        return err
    return 200, report.to_item()

def register(router: Router) -> None:
    router.add("POST", "/v1/tenants/:id/reports", post_report)
    router.add("GET", "/v1/reports/:id", get_report_by_id)
