"""Deterministic priority matrix and due dates (chapter 12.2)."""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

DEFAULT_DUE_DAYS: dict[str, int | None] = {"P1": 7, "P2": 30, "P3": 90, "P4": None}
_ORDER = ("P4", "P3", "P2", "P1")


@dataclass
class PriorityResult:
    priority: str
    needs_validation: bool


def _base_priority(
    severity: str,
    confidence: str,
    exposed_critical: bool,
) -> tuple[str, bool]:
    is_high_conf = confidence == "High"
    if severity == "Critical":
        if is_high_conf:
            return "P1", False
        return ("P1" if exposed_critical else "P2"), True

    if severity == "High":
        if is_high_conf:
            return ("P1" if exposed_critical else "P2"), False
        return ("P2" if exposed_critical else "P3"), True

    if severity == "Medium":
        if is_high_conf:
            return ("P2" if exposed_critical else "P3"), False
        return ("P3" if exposed_critical else "P4"), False

    return "P4", False


def _bump_priority(p: str) -> str:
    idx = _ORDER.index(p)
    return _ORDER[min(idx + 1, len(_ORDER) - 1)]


def compute_priority(
    severity: str,
    confidence: str,
    *,
    exposed_critical: bool,
    sensitive_data: bool,
) -> PriorityResult:
    """Compute priority from matrix with sensitive data bump capped at P1."""
    base, needs_val = _base_priority(severity, confidence, exposed_critical)
    final = _bump_priority(base) if sensitive_data else base
    return PriorityResult(priority=final, needs_validation=needs_val)


def due_date(
    priority: str,
    created_at: datetime,
    due_days: dict[str, int | None] | None = None,
) -> datetime | None:
    """Return due date datetime or None for P4 / missing schedule."""
    mapping = DEFAULT_DUE_DAYS if due_days is None else due_days
    days = mapping.get(priority)
    if days is None:
        return None
    return created_at + timedelta(days=days)


@dataclass
class PolicyPriorityResult:
    """Priority plus the contract-level remediation delay that applies to it."""

    priority: str
    needs_validation: bool
    due_days: int | None


def _clean_due_days(raw: Any) -> dict[str, int | None]:
    """Keep only well-formed ``{P1..P4: positive int | None}`` entries."""
    if not isinstance(raw, dict):
        return {}
    return {
        key: value
        for key, value in raw.items()
        if key in DEFAULT_DUE_DAYS
        and (value is None or (isinstance(value, int) and not isinstance(value, bool)))
    }


def resolve_due_days(policy: Mapping[str, Any] | None = None) -> dict[str, int | None]:
    """Merge a policy's ``due_days`` over the global default schedule."""
    overrides = _clean_due_days((policy or {}).get("due_days"))
    return {**DEFAULT_DUE_DAYS, **overrides}


def _override_base(policy: Mapping[str, Any] | None, severity: str, base: str) -> str:
    """Apply ``matrix_overrides[severity]`` when it names a known priority."""
    overrides = (policy or {}).get("matrix_overrides")
    if not isinstance(overrides, dict):
        return base
    override = overrides.get(severity)
    return str(override) if override in _ORDER else base


def compute_priority_with_policy(
    severity: str,
    confidence: str,
    *,
    exposed_critical: bool,
    sensitive_data: bool,
    policy: Mapping[str, Any] | None = None,
) -> PolicyPriorityResult:
    """Compute priority honouring a tenant's contract policy (EF-ADM-01).

    ``policy["matrix_overrides"]`` maps a severity to the base priority that
    replaces the global matrix cell; the sensitive-data bump still applies
    afterwards (capped at P1). ``policy["due_days"]`` overrides the global
    remediation delays and is resolved for the resulting priority.
    """
    base, needs_val = _base_priority(severity, confidence, exposed_critical)
    base = _override_base(policy, severity, base)
    final = _bump_priority(base) if sensitive_data else base
    return PolicyPriorityResult(
        priority=final,
        needs_validation=needs_val,
        due_days=resolve_due_days(policy).get(final),
    )
