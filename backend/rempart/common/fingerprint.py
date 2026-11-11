"""Fingerprint calculation for findings."""

import hashlib


def fingerprint(
    app_id: str,
    risk_type: str,
    entry_point: str,
    parameter: str | None = None,
) -> str:
    """Compute sha256 hex fingerprint truncated to 16 characters.

    Enables cross-run deduplication and regression detection.
    """
    param_clean = parameter.strip() if parameter else ""
    raw = f"{app_id.strip()}:{risk_type.strip()}:{entry_point.strip()}:{param_clean}"
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return digest[:16]
