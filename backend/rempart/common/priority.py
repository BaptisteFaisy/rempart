"""Deterministic priority matrix and due dates (chapter 12.2)."""

from dataclasses import dataclass
from datetime import datetime, timedelta

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
