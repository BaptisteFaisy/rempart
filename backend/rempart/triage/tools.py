"""Triage tools for Bedrock AgentCore / Strands agent (chapter 12.3)."""

from dataclasses import dataclass, field
from typing import Any

from rempart.common.models import Application, Decision, Finding

from .proposal import TriageProposal

ALLOWED_PROPOSED_STATUSES = ("CONFIRMED", "TO_VERIFY", "LIKELY_FALSE_POSITIVE")


@dataclass
class TriageContext:
    """Context bundle handed to triage tools (store, app, findings, known, decisions)."""

    store: Any = None
    app: Application | None = None
    findings: list[Finding] = field(default_factory=list)
    known_findings: list[Finding] = field(default_factory=list)
    past_decisions: list[Decision] = field(default_factory=list)
    proposals: list[TriageProposal] = field(default_factory=list)


def _require_app(ctx: TriageContext) -> Application:
    if ctx.app is None:
        raise ValueError("triage context has no application")
    return ctx.app


def get_application_context(ctx: TriageContext) -> dict[str, Any]:
    """Retrieve metadata, criticality, exposure and data classification for the application."""
    app = _require_app(ctx)
    return {
        "app_id": app.app_id,
        "tenant_id": app.tenant_id,
        "name": app.name,
        "criticality": app.criticality,
        "internet_exposed": app.internet_exposed,
        "data_types": list(app.data_types),
        "environment": app.environment,
        "domains": list(app.domains),
        "repositories": list(app.repositories),
        "team": app.team,
        "ticket_channel": app.ticket_channel,
        "context": dict(app.context),
    }


def search_known_findings(
    ctx: TriageContext,
    app_id: str,
    risk_type: str | None = None,
    entry_point: str | None = None,
) -> list[dict[str, Any]]:
    """Search findings already known for the application (dedup and regression material)."""
    if not isinstance(app_id, str) or not app_id:
        raise ValueError("app_id must be a non-empty string")
    app = _require_app(ctx)
    if app_id != app.app_id:
        return []

    pool: list[Finding] = list(ctx.known_findings)
    if ctx.store is not None and hasattr(ctx.store, "list_findings"):
        pool.extend(ctx.store.list_findings(app_id=app_id))

    unique_by_id: dict[str, Finding] = {f.finding_id: f for f in pool}
    matches: list[dict[str, Any]] = []
    for f in unique_by_id.values():
        if f.app_id != app_id:
            continue
        if risk_type and f.risk_type.lower() != risk_type.lower():
            continue
        if entry_point:
            ep = f.evidence.get("entry_point", "") if isinstance(f.evidence, dict) else ""
            if entry_point.lower() not in ep.lower():
                continue
        matches.append(f.to_item())
    return matches


def get_finding_detail(ctx: TriageContext, finding_id: str) -> dict[str, Any]:
    """Retrieve full details, evidence and CVSS of one finding by identifier."""
    if not isinstance(finding_id, str) or not finding_id:
        raise ValueError("finding_id must be a non-empty string")
    for f in ctx.findings:
        if f.finding_id == finding_id:
            return f.to_item()
    for f in ctx.known_findings:
        if f.finding_id == finding_id:
            return f.to_item()
    if ctx.store is not None and hasattr(ctx.store, "get_finding"):
        stored = ctx.store.get_finding(finding_id)
        if stored:
            return stored.to_item()
    return {}


def get_past_decisions(ctx: TriageContext, app_id: str) -> list[dict[str, Any]]:
    """Retrieve historical triage and analyst decisions for the application."""
    if not isinstance(app_id, str) or not app_id:
        raise ValueError("app_id must be a non-empty string")
    app = _require_app(ctx)
    if app_id != app.app_id:
        return []

    res: list[dict[str, Any]] = [d.to_item() for d in ctx.past_decisions]
    if ctx.store is not None and hasattr(ctx.store, "list_decisions"):
        for f in ctx.known_findings:
            if f.app_id == app_id:
                for d in ctx.store.list_decisions(f.finding_id):
                    res.append(d.to_item())

    seen: set[str] = set()
    deduped: list[dict[str, Any]] = []
    for it in res:
        did = it.get("decision_id", "")
        if did and did not in seen:
            seen.add(did)
            deduped.append(it)
    return deduped


def submit_triage_proposal(ctx: TriageContext, proposal: dict[str, Any]) -> dict[str, Any]:
    """Validate and record a triage proposal.

    Only write-authorized tool of the triage agent (chapter 12.4): no finding is
    closed, no ticket is created, the proposal is only stored in the context.
    """
    if not isinstance(proposal, dict):
        return {"status": "error", "error": "proposal must be a dictionary"}

    prop_obj = TriageProposal.from_dict(proposal)
    if not prop_obj.finding_id:
        return {"status": "error", "error": "findingId is required"}
    if prop_obj.proposed_status not in ALLOWED_PROPOSED_STATUSES:
        return {
            "status": "error",
            "error": f"proposedStatus must be one of {list(ALLOWED_PROPOSED_STATUSES)}",
        }

    for idx, existing in enumerate(ctx.proposals):
        if existing.finding_id == prop_obj.finding_id:
            ctx.proposals[idx] = prop_obj
            return {"status": "ok", "action": "updated", "proposal": prop_obj.to_dict()}

    ctx.proposals.append(prop_obj)
    return {"status": "ok", "action": "created", "proposal": prop_obj.to_dict()}
