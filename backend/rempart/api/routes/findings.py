"""Route handlers for Findings, Decisions, and Remediations."""

import uuid
from typing import Any

from rempart.api.context import ApiContext
from rempart.api.helpers import (
    Response,
    authorize,
    error_response,
    get_store,
    load_or_404,
    require_principal,
)
from rempart.api.router import Router
from rempart.common.models import FINDING_STATUSES, Decision, Finding
from rempart.common.tenant import Principal
from rempart.common.timeutil import iso, utcnow

CLIENT_SCOPED_ROLES = ("client_security", "client_dev", "executive", "demo")

def _resolve_tenant_filter(principal: Principal, requested: str | None) -> tuple[str | None, bool]:
    """Return (effective_tenant_filter, denied)."""
    if principal.role in CLIENT_SCOPED_ROLES:
        own = principal.tenant_id
        if requested is not None and requested != own:
            return None, True
        return own, False
    return requested, False

def _load_finding_or_error(
    ctx: ApiContext, finding_id: str
) -> tuple[Finding | None, Response | None]:
    return load_or_404(get_store(ctx).get_finding, finding_id, "Finding")

def _check_app_filter(ctx: ApiContext, principal: Principal, app_id: str) -> Response | None:
    """Authorize the optional app_id filter against the application's tenant."""
    app, _err = load_or_404(get_store(ctx).get_application, app_id, "Application")
    if not app:
        return None
    return authorize(principal, app.tenant_id, write=False)

def get_findings(ctx: ApiContext) -> tuple[int, dict[str, Any]]:
    """List findings with optional filters, enforcing tenant isolation."""
    principal, err = require_principal(ctx)
    if err:
        return err

    tenant_filter, denied = _resolve_tenant_filter(principal, ctx.query.get("tenant_id"))
    if denied:
        return error_response("Filtrage inter-tenants non autorisé", 403)

    app_id = ctx.query.get("app_id")
    if app_id:
        err = _check_app_filter(ctx, principal, app_id)
        if err:
            return err

    findings = get_store(ctx).list_findings(
        tenant_id=tenant_filter,
        app_id=app_id,
        status=ctx.query.get("status"),
        priority=ctx.query.get("priority"),
    )
    return 200, {"findings": [f.to_item() for f in findings]}

def get_finding_by_id(ctx: ApiContext) -> tuple[int, dict[str, Any]]:
    """Get a single finding by id, checking tenant authorization."""
    principal, err = require_principal(ctx)
    if err:
        return err
    finding_id = ctx.path_params.get("id", "")
    finding, err = _load_finding_or_error(ctx, finding_id)
    if err or not finding:
        return err  # type: ignore[return-value]

    err = authorize(principal, finding.tenant_id, write=False)
    if err:
        return err
    return 200, finding.to_item()

def _build_decision(
    ctx: ApiContext, finding_id: str, action: str, justification: str
) -> Decision:
    """Build the human decision record for a finding."""
    return Decision(
        decision_id=f"dec-{uuid.uuid4().hex[:12]}",
        finding_id=finding_id,
        author_type="human",
        author=ctx.principal.user_id if ctx.principal else "anonymous",
        action=action,
        justification=justification,
        created_at=iso(utcnow()),
    )

def _apply_decision_status(store: Any, finding: Finding, action: str) -> None:
    """Mirror a decision action onto the finding status when it maps to one."""
    if action in FINDING_STATUSES and finding.status != action:
        finding.status = action
        finding.updated_at = iso(utcnow())
        store.save_finding(finding)

def post_decision(ctx: ApiContext) -> tuple[int, dict[str, Any]]:
    """Record a human decision (confirm, false positive, risk accepted) on a finding."""
    principal, err = require_principal(ctx)
    if err:
        return err
    finding_id = ctx.path_params.get("id", "")
    finding, err = _load_finding_or_error(ctx, finding_id)
    if err or not finding:
        return err  # type: ignore[return-value]

    err = authorize(principal, finding.tenant_id, write=True)
    if err:
        return err

    action = ctx.body.get("action", "")
    if not action:
        return error_response("Missing 'action' in body", 400)

    store = get_store(ctx)
    decision = _build_decision(ctx, finding_id, action, ctx.body.get("justification", ""))
    store.save_decision(decision)
    _apply_decision_status(store, finding, action)

    ctx.audit("finding.decision", "finding", finding_id)
    return 201, {"decision": decision.to_item(), "finding": finding.to_item()}

def post_remediation(ctx: ApiContext) -> tuple[int, dict[str, Any]]:
    """Request a code remediation PR for a confirmed finding via Security Agent."""
    principal, err = require_principal(ctx)
    if err:
        return err
    finding_id = ctx.path_params.get("id", "")
    finding, err = _load_finding_or_error(ctx, finding_id)
    if err or not finding:
        return err  # type: ignore[return-value]

    err = authorize(principal, finding.tenant_id, write=True)
    if err:
        return err
    if not ctx.sa:
        return error_response("Security Agent client not available", 500)

    evidence = finding.evidence if isinstance(finding.evidence, dict) else {}
    sa_finding_id = evidence.get("sa_finding_id", finding_id)
    resp = ctx.sa.start_code_remediation(sa_finding_id)

    store = get_store(ctx)
    finding.remediation_pr_url = resp.get("remediationPrUrl")
    finding.status = "in_remediation"
    finding.updated_at = iso(utcnow())
    store.save_finding(finding)

    ctx.audit("finding.remediation", "finding", finding_id)
    return 201, {"finding": finding.to_item(), "remediation": resp}

def register(router: Router) -> None:
    router.add("GET", "/v1/findings", get_findings)
    router.add("GET", "/v1/findings/:id", get_finding_by_id)
    router.add("POST", "/v1/findings/:id/decision", post_decision)
    router.add("POST", "/v1/findings/:id/remediation", post_remediation)
