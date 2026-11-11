"""Route handlers for per-tenant correction policies (EF-ADM-01).

La politique de correction (délais par priorité, surcharges de la matrice,
seuil de blocage, tarif horaire) est paramétrable **par contrat** : chaque
tenant porte sa propre politique qui surmonte les valeurs globales par
défaut. Seule la plateforme (``platform_admin``) peut l'écrire ; les rôles
du tenant et les analystes peuvent la lire.
"""

from typing import Any

from rempart.api.context import ApiContext
from rempart.api.helpers import (
    Response,
    authorize,
    error_response,
    get_store,
    hourly_rate,
    load_tenant_or_404,
    require_principal,
)
from rempart.api.router import Router
from rempart.common.models import PRIORITIES, SEVERITIES, Tenant
from rempart.common.priority import DEFAULT_DUE_DAYS, resolve_due_days
from rempart.common.tenant import Principal

POLICY_KEYS = ("due_days", "matrix_overrides", "blocking_threshold", "hourly_rate")
DEFAULT_BLOCKING_THRESHOLD = "High"
POLICY_WRITER_ROLE = "platform_admin"


def _is_number(value: Any) -> bool:
    """True for a JSON number (bools excluded)."""
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _validate_due_days(raw: Any) -> tuple[dict[str, int | None] | None, Response | None]:
    """Validate ``{priority: positive int | null}``; null means "no deadline"."""
    if not isinstance(raw, dict):
        return None, error_response("policy.due_days must be an object", 400)
    validated: dict[str, int | None] = {}
    for key, value in raw.items():
        if key not in PRIORITIES:
            return None, error_response(f"policy.due_days: unknown priority '{key}'", 400)
        if value is None:
            validated[key] = None
        elif isinstance(value, int) and not isinstance(value, bool) and value > 0:
            validated[key] = value
        else:
            return None, error_response(
                f"policy.due_days.{key} must be a positive integer or null", 400
            )
    return validated, None


def _validate_matrix_overrides(raw: Any) -> tuple[dict[str, str] | None, Response | None]:
    """Validate ``{severity: priority}`` overrides of the priority matrix."""
    if not isinstance(raw, dict):
        return None, error_response("policy.matrix_overrides must be an object", 400)
    validated: dict[str, str] = {}
    for severity, priority in raw.items():
        if severity not in SEVERITIES:
            return None, error_response(
                f"policy.matrix_overrides: unknown severity '{severity}'", 400
            )
        if priority not in PRIORITIES:
            return None, error_response(
                f"policy.matrix_overrides.{severity} must be one of {list(PRIORITIES)}", 400
            )
        validated[severity] = priority
    return validated, None


def _validate_hourly_rate(raw: Any) -> tuple[float | None, Response | None]:
    """Validate a strictly positive hourly rate."""
    if not _is_number(raw):
        return None, error_response("policy.hourly_rate must be a number", 400)
    if raw <= 0:
        return None, error_response("policy.hourly_rate must be > 0", 400)
    return float(raw), None


def validate_policy(raw: Any) -> tuple[dict[str, Any] | None, Response | None]:
    """Validate a full policy payload (unknown keys rejected)."""
    if not isinstance(raw, dict):
        return None, error_response("policy must be an object", 400)
    unknown = sorted(key for key in raw if key not in POLICY_KEYS)
    if unknown:
        return None, error_response(f"Unknown policy keys: {', '.join(unknown)}", 400)

    policy: dict[str, Any] = {}
    if "due_days" in raw:
        policy["due_days"], err = _validate_due_days(raw["due_days"])
        if err:
            return None, err
    if "matrix_overrides" in raw:
        policy["matrix_overrides"], err = _validate_matrix_overrides(raw["matrix_overrides"])
        if err:
            return None, err
    if "blocking_threshold" in raw:
        threshold = raw["blocking_threshold"]
        if threshold not in SEVERITIES:
            return None, error_response(
                f"policy.blocking_threshold must be one of {list(SEVERITIES)}", 400
            )
        policy["blocking_threshold"] = threshold
    if "hourly_rate" in raw:
        policy["hourly_rate"], err = _validate_hourly_rate(raw["hourly_rate"])
        if err:
            return None, err
    return policy, None


def policy_write_forbidden(principal: Principal) -> Response | None:
    """Return the 403 response when the principal may not write a policy."""
    if principal.role != POLICY_WRITER_ROLE:
        return error_response(
            f"Only '{POLICY_WRITER_ROLE}' may write a tenant policy", 403
        )
    return None


def extract_policy_body(body: dict[str, Any]) -> tuple[Any, Response | None]:
    """Accept either a bare policy object or a ``{"policy": {...}}`` wrapper."""
    if "policy" not in body:
        return body, None
    extra = sorted(key for key in body if key != "policy")
    if extra:
        return None, error_response(f"Unknown body keys: {', '.join(extra)}", 400)
    return body["policy"], None


def effective_policy(ctx: ApiContext, policy: dict[str, Any] | None) -> dict[str, Any]:
    """Merge a stored tenant policy over the global default values."""
    stored = policy or {}
    return {
        "due_days": resolve_due_days(stored),
        "matrix_overrides": dict(stored.get("matrix_overrides") or {}),
        "blocking_threshold": stored.get("blocking_threshold", DEFAULT_BLOCKING_THRESHOLD),
        "hourly_rate": stored.get("hourly_rate", hourly_rate(ctx)),
    }


def policy_payload(ctx: ApiContext, tenant: Tenant) -> dict[str, Any]:
    """Build the representation shared by GET and PUT /policy."""
    return {
        "tenant_id": tenant.tenant_id,
        "policy": dict(tenant.policy or {}),
        "effective": effective_policy(ctx, tenant.policy),
    }


def get_policy(ctx: ApiContext) -> tuple[int, dict[str, Any]]:
    """Read a tenant's correction policy (analysts and tenant roles allowed)."""
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
    return 200, policy_payload(ctx, tenant)


def put_policy(ctx: ApiContext) -> tuple[int, dict[str, Any]]:
    """Replace a tenant's correction policy (platform_admin only)."""
    principal, err = require_principal(ctx)
    if err:
        return err
    tenant_id = ctx.path_params.get("id", "")
    err = authorize(principal, tenant_id, write=True)
    if err:
        return err
    err = policy_write_forbidden(principal)
    if err:
        return err

    tenant, err = load_tenant_or_404(get_store(ctx), tenant_id)
    if err or not tenant:
        return err  # type: ignore[return-value]

    raw, err = extract_policy_body(ctx.body)
    if err:
        return err
    policy, err = validate_policy(raw)
    if err:
        return err

    tenant.policy = policy or {}
    get_store(ctx).save_tenant(tenant)
    ctx.audit("tenant.policy_update", "tenant", tenant_id)
    return 200, policy_payload(ctx, tenant)


def get_defaults(ctx: ApiContext) -> tuple[int, dict[str, Any]]:
    """Return the global default correction policy values."""
    _, err = require_principal(ctx)
    if err:
        return err
    return 200, {
        "due_days": dict(DEFAULT_DUE_DAYS),
        "matrix_overrides": {},
        "blocking_threshold": DEFAULT_BLOCKING_THRESHOLD,
        "hourly_rate": hourly_rate(ctx),
    }


def register(router: Router) -> None:
    router.add("GET", "/v1/tenants/:id/policy", get_policy)
    router.add("PUT", "/v1/tenants/:id/policy", put_policy)
    router.add("GET", "/v1/settings/defaults", get_defaults)
