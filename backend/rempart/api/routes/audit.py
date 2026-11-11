"""Read-only route handlers for the audit journal (EF-ADM-02, ENF-SEC-06).

The journal is written everywhere through ``ctx.audit(...)`` /
``store.append_audit(...)``; this module only ever *reads* it. No write route
is registered on purpose: the trail must stay immutable (ENF-SEC-06).

``AuditEvent`` carries no tenant column, so an event belongs to a tenant
through the object it points at: the tenant itself, one of its applications,
runs, findings or reports, or ``"<tenant_id>#<month>"`` for budget entries.
"""

from typing import Any

from rempart.api.context import ApiContext
from rempart.api.helpers import (
    Response,
    authorize,
    error_response,
    get_store,
    load_tenant_or_404,
    require_principal,
)
from rempart.api.router import Router
from rempart.common.models import AuditEvent
from rempart.common.store import Store
from rempart.common.tenant import Principal
from rempart.common.timeutil import parse_iso

# Seuls ces rôles touchent au journal ; les autres (executive, demo) : 403.
FULL_ACCESS_ROLES = ("platform_admin", "analyst")
TENANT_SCOPED_ROLES = ("account_manager", "client_security", "client_dev")

DEFAULT_LIMIT = 50
MAX_LIMIT = 200
MAX_SCAN = 2000
SCOPED_OBJECT_LIMIT = 1000


def _journal_principal(ctx: ApiContext) -> tuple[Principal | None, Response | None]:
    """Authenticate, then reject roles that have no access to the journal at all."""
    principal, err = require_principal(ctx)
    if err:
        return None, err
    if principal.role not in FULL_ACCESS_ROLES + TENANT_SCOPED_ROLES:
        return None, error_response(
            f"Role '{principal.role}' has no access to the audit journal", 403
        )
    return principal, None


def _authorize_tenant(principal: Principal, tenant_id: str) -> Response | None:
    """Existing RBAC first, then the journal's narrower rule for scoped roles."""
    err = authorize(principal, tenant_id, write=False)
    if err:
        return err
    if principal.role in TENANT_SCOPED_ROLES and principal.tenant_id != tenant_id:
        return error_response("Filtrage inter-tenants non autorisé", 403)
    return None


def _requested_tenant(
    ctx: ApiContext, principal: Principal
) -> tuple[str | None, Response | None]:
    """Resolve the tenant scope of ``GET /v1/audit`` (``None`` means fleet-wide)."""
    requested = ctx.query.get("tenant_id") or None
    if principal.role in FULL_ACCESS_ROLES:
        return requested, None
    own = principal.tenant_id
    if not own:
        return None, error_response("Aucun tenant associé à ce compte", 403)
    if requested and requested != own:
        return None, error_response("Filtrage inter-tenants non autorisé", 403)
    err = _authorize_tenant(principal, own)
    if err:
        return None, err
    return own, None


def _parse_window(ctx: ApiContext) -> tuple[str | None, str | None, Response | None]:
    """Read the ``from`` / ``to`` bounds, rejecting malformed or reversed dates."""
    since = ctx.query.get("from") or None
    until = ctx.query.get("to") or None
    try:
        start = parse_iso(since) if since else None
        end = parse_iso(until) if until else None
    except ValueError:
        return None, None, error_response("'from' and 'to' must be ISO 8601 dates", 400)
    if start and end and start > end:
        return None, None, error_response("'from' must be before 'to'", 400)
    return since, until, None


def _parse_pagination(ctx: ApiContext) -> tuple[int, int, Response | None]:
    """Read ``limit`` / ``offset`` and cap the page size against runaway scans."""
    try:
        limit = int(ctx.query.get("limit") or DEFAULT_LIMIT)
        offset = int(ctx.query.get("offset") or 0)
    except (TypeError, ValueError):
        return 0, 0, error_response("limit and offset must be integers", 400)
    if limit < 1 or offset < 0:
        return 0, 0, error_response("limit must be >= 1 and offset >= 0", 400)
    return min(limit, MAX_LIMIT), offset, None


def tenant_object_ids(store: Store, tenant_id: str) -> dict[str, set[str]]:
    """Map ``object_type`` -> identifiers owned by the tenant."""
    return {
        "tenant": {tenant_id},
        "application": {a.app_id for a in store.list_applications(tenant_id)},
        "run": {
            r.run_id
            for r in store.list_runs(tenant_id=tenant_id, limit=SCOPED_OBJECT_LIMIT)
        },
        "finding": {
            f.finding_id
            for f in store.list_findings(tenant_id=tenant_id, limit=SCOPED_OBJECT_LIMIT)
        },
        "report": {r.report_id for r in store.list_reports(tenant_id)},
    }


def belongs_to(event: AuditEvent, tenant_id: str, index: dict[str, set[str]]) -> bool:
    """Return True when the audit event is attributable to the tenant."""
    if event.object_type == "budget":
        return event.object_id.split("#", 1)[0] == tenant_id
    return event.object_id in index.get(event.object_type, frozenset())


def _scan_journal(
    store: Store,
    *,
    object_type: str | None,
    object_id: str | None,
    actor: str | None,
    action: str | None,
    since: str | None,
    until: str | None,
) -> list[AuditEvent]:
    """Fetch the bounded, filtered journal, newest first (stable for pagination)."""
    events = store.list_audit(
        object_type=object_type,
        object_id=object_id,
        actor=actor,
        action=action,
        since=since,
        until=until,
        limit=MAX_SCAN,
    )
    return sorted(events, key=lambda e: (e.created_at, e.audit_id), reverse=True)


def _journal_page(ctx: ApiContext, *, tenant_id: str | None) -> tuple[int, dict[str, Any]]:
    """Shared body of both routes: filters, tenant scoping, then one page."""
    since, until, err = _parse_window(ctx)
    if err:
        return err
    limit, offset, err = _parse_pagination(ctx)
    if err:
        return err

    store = get_store(ctx)
    events = _scan_journal(
        store,
        object_type=ctx.query.get("object_type") or None,
        object_id=ctx.query.get("object_id") or None,
        actor=ctx.query.get("actor") or None,
        action=ctx.query.get("action") or None,
        since=since,
        until=until,
    )
    truncated = len(events) >= MAX_SCAN
    if tenant_id:
        index = tenant_object_ids(store, tenant_id)
        events = [e for e in events if belongs_to(e, tenant_id, index)]

    page = events[offset : offset + limit]
    end = offset + limit
    return 200, {
        "events": [e.to_item() for e in page],
        "count": len(page),
        "total": len(events),
        "limit": limit,
        "offset": offset,
        "next_offset": end if end < len(events) else None,
        "scan_truncated": truncated,
    }


def get_audit_journal(ctx: ApiContext) -> tuple[int, dict[str, Any]]:
    """``GET /v1/audit`` — paginated journal; fleet-wide or restricted to a tenant."""
    principal, err = _journal_principal(ctx)
    if err:
        return err
    tenant_id, err = _requested_tenant(ctx, principal)
    if err:
        return err
    return _journal_page(ctx, tenant_id=tenant_id)


def get_tenant_audit_journal(ctx: ApiContext) -> tuple[int, dict[str, Any]]:
    """``GET /v1/tenants/{id}/audit`` — the journal of a single client."""
    principal, err = _journal_principal(ctx)
    if err:
        return err
    tenant_id = ctx.path_params.get("id", "")
    err = _authorize_tenant(principal, tenant_id)
    if err:
        return err
    _tenant, err = load_tenant_or_404(get_store(ctx), tenant_id)
    if err:
        return err
    return _journal_page(ctx, tenant_id=tenant_id)


def register(router: Router) -> None:
    """Register the read-only audit routes (ENF-SEC-06: nothing writable here)."""
    router.add("GET", "/v1/audit", get_audit_journal)
    router.add("GET", "/v1/tenants/:id/audit", get_tenant_audit_journal)
