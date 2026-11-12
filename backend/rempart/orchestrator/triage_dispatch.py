"""Helpers behind the ``dispatch_triage`` task (chapter 11.4, step 5).

The task itself only orchestrates: these small functions collect the findings to
triage, ask the triage agent, record the resulting decision and apply the new
status. Keeping them separate makes each step readable, reusable and testable on
its own.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

from rempart.common.models import Application, Decision, Finding
from rempart.common.timeutil import iso, utcnow

if TYPE_CHECKING:  # pragma: no cover - annotation only, avoids an import cycle
    from .tasks import Deps


def load_findings(deps: Deps, finding_ids: list[str]) -> list[Finding]:
    """Load the findings to triage, skipping ids that no longer exist."""
    findings = [deps.store.get_finding(fid) for fid in finding_ids]
    return [f for f in findings if f is not None]


def run_proposals(
    deps: Deps, app: Application, findings: list[Finding], finding_ids: list[str]
) -> list[Any]:
    """Ask the triage agent for one proposal per finding.

    The agent also receives the findings already known for the application and
    the decisions taken so far, so it can spot duplicates and regressions.
    """
    from rempart.triage.agent import run_triage  # local import: optional dependency

    known = [
        f for f in deps.store.list_findings(app_id=app.app_id) if f.finding_id not in finding_ids
    ]
    past_decisions = deps.store.list_decisions(findings[0].finding_id)
    return run_triage(
        findings=findings,
        app=app,
        known_findings=known,
        past_decisions=past_decisions,
        deps=deps,
        model_client=deps.model_client,
    )


def record_decision(deps: Deps, finding: Finding, proposal: Any) -> None:
    """Persist the agent's decision on a finding."""
    deps.store.save_decision(
        Decision(
            decision_id=f"dec-{uuid.uuid4().hex[:8]}",
            finding_id=finding.finding_id,
            author_type="agent",
            author=f"triage-agent:{getattr(proposal, 'source', 'deterministic')}",
            action=proposal.proposed_status,
            justification=proposal.justification,
            created_at=iso(utcnow()),
        )
    )


def apply_finding_status(deps: Deps, finding: Finding, proposal: Any) -> None:
    """Apply the proposal's priority and status to the finding."""
    finding.priority = proposal.priority
    finding.status = "pending_validation" if proposal.needs_human_validation else "confirmed"
    finding.updated_at = iso(utcnow())
    deps.store.save_finding(finding)


def apply_proposals(deps: Deps, proposals: list[Any]) -> tuple[list[str], list[str]]:
    """Record every proposal and split the findings into queued and confirmed."""
    queued: list[str] = []
    confirmed: list[str] = []
    for proposal in proposals:
        finding = deps.store.get_finding(proposal.finding_id)
        if finding is None:
            continue
        record_decision(deps, finding, proposal)
        apply_finding_status(deps, finding, proposal)
        if proposal.needs_human_validation:
            queued.append(finding.finding_id)
        else:
            confirmed.append(finding.finding_id)
    return queued, confirmed
