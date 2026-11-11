"""Guardrails enforcing deterministic business rules on triage proposals (chapter 12.4)."""

import logging
from typing import Any

from rempart.common.models import Application, Finding
from rempart.common.priority import PriorityResult, compute_priority

from .proposal import TriageProposal

logger = logging.getLogger(__name__)

_SENSITIVE_DATA_TYPES = {"personal", "payment", "health"}
HIGH_SEVERITIES = {"Critical", "High"}


def _is_exposed_critical(app: Application) -> bool:
    return bool(app.internet_exposed and app.criticality.lower() == "high")


def _has_sensitive_data(app: Application) -> bool:
    types = {str(t).lower() for t in getattr(app, "data_types", [])}
    return bool(types & _SENSITIVE_DATA_TYPES)


def compute_finding_priority(finding: Finding, app: Application) -> PriorityResult:
    """Compute deterministic priority for a finding in its application context."""
    return compute_priority(
        finding.severity,
        finding.confidence,
        exposed_critical=_is_exposed_critical(app),
        sensitive_data=_has_sensitive_data(app),
    )


def _check_regression(
    finding: Finding,
    known_findings: list[Finding] | None,
    store: Any,
) -> bool:
    candidates: list[Finding] = []
    if known_findings is not None:
        candidates.extend(known_findings)
    if store is not None and hasattr(store, "list_findings"):
        stored = store.list_findings(app_id=finding.app_id)
        candidates.extend(stored)

    for kf in candidates:
        if kf.app_id == finding.app_id and kf.fingerprint == finding.fingerprint:
            if kf.status == "closed":
                return True
    return False


def _enforce_priority(
    proposal: TriageProposal,
    finding: Finding,
    app: Application,
) -> tuple[str, bool]:
    """Recompute matrix priority and log divergence if model priority differed."""
    p_result = compute_finding_priority(finding, app)
    if proposal.priority != p_result.priority:
        logger.warning(
            "Priority divergence for finding %s: proposal=%s matrix=%s. Matrix wins.",
            finding.finding_id,
            proposal.priority,
            p_result.priority,
        )
    return p_result.priority, p_result.needs_validation


def _enforce_false_positive_rule(
    proposal: TriageProposal,
    finding: Finding,
    needs_validation: bool,
) -> tuple[str, bool]:
    """ENF-IA-02: Critical/High false positive proposals require human verification."""
    final_status = proposal.proposed_status
    final_needs_human = proposal.needs_human_validation or needs_validation

    if proposal.proposed_status == "LIKELY_FALSE_POSITIVE" and finding.severity in HIGH_SEVERITIES:
        logger.warning(
            "Guardrail EF-TRI-05/ENF-IA-02 triggered on %s: false positive on %s overridden.",
            finding.finding_id,
            finding.severity,
        )
        final_status = "TO_VERIFY"
        final_needs_human = True

    return final_status, final_needs_human


def _enforce_regression(
    proposal: TriageProposal,
    finding: Finding,
    known_findings: list[Finding] | None,
    store: Any,
) -> bool:
    """ENF-IA-01 / R7: Preserve or detect regression against closed findings."""
    return proposal.is_regression or _check_regression(finding, known_findings, store)


def enforce(
    proposal: TriageProposal,
    finding: Finding,
    app: Application,
    *,
    known_findings: list[Finding] | None = None,
    store: Any = None,
) -> TriageProposal:
    """Apply deterministic safety guardrails on an AI triage proposal.

    1) Recompute priority deterministically via compute_priority. Matrix wins.
    2) EF-TRI-05 / ENF-IA-02: LIKELY_FALSE_POSITIVE on Critical/High severity forced
       to TO_VERIFY with needs_human_validation = True.
    3) Regression detection: if finding fingerprint matches a previously closed finding,
       mark is_regression = True.
    """
    final_priority, needs_validation = _enforce_priority(proposal, finding, app)
    final_status, final_needs_human = _enforce_false_positive_rule(
        proposal, finding, needs_validation
    )
    is_reg = _enforce_regression(proposal, finding, known_findings, store)

    return TriageProposal(
        finding_id=proposal.finding_id,
        duplicate_of=proposal.duplicate_of,
        is_regression=is_reg,
        proposed_status=final_status,
        priority=final_priority,
        plain_summary=proposal.plain_summary,
        technical_summary=proposal.technical_summary,
        references=list(proposal.references),
        justification=proposal.justification,
        needs_human_validation=final_needs_human,
    )
