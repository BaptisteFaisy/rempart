"""Triage agent orchestration (Strands / AgentCore with deterministic fallback)."""

from typing import Any

from rempart.common.models import Application, Decision, Finding

from .guardrails import HIGH_SEVERITIES, compute_finding_priority, enforce
from .memory import MemoryMatch, memory_match
from .prompts import SYSTEM_PROMPT, format_finding_for_prompt
from .proposal import TriageProposal
from .tools import (
    TriageContext,
    get_application_context,
    get_finding_detail,
    get_past_decisions,
    search_known_findings,
    submit_triage_proposal,
)


def _strands_available() -> bool:
    try:
        import strands  # noqa: F401
        return True
    except ImportError:
        return False


def _is_real_strands_model(model_client: Any) -> bool:
    """Verify model_client is an actual Strands Model instance (not None or simple fake)."""
    if model_client is None:
        return False
    try:
        from strands.models.model import Model

        return isinstance(model_client, Model)
    except ImportError:
        return False


def _build_strands_tools(ctx: TriageContext) -> list[Any]:
    """Wrap read/write triage tools with @strands.tool binding TriageContext."""
    from strands import tool

    @tool
    def tool_get_application_context() -> dict[str, Any]:
        """Get application metadata, criticality, exposure, and data classification."""
        return get_application_context(ctx)

    @tool
    def tool_search_known_findings(
        app_id: str,
        risk_type: str | None = None,
        entry_point: str | None = None,
    ) -> list[dict[str, Any]]:
        """Search known findings for the application."""
        return search_known_findings(ctx, app_id, risk_type=risk_type, entry_point=entry_point)

    @tool
    def tool_get_finding_detail(finding_id: str) -> dict[str, Any]:
        """Get full details and evidence for a specific finding."""
        return get_finding_detail(ctx, finding_id)

    @tool
    def tool_get_past_decisions(
        app_id: str,
        fingerprint: str | None = None,
    ) -> list[dict[str, Any]]:
        """Get past analyst triage decisions, optionally for one finding fingerprint."""
        return get_past_decisions(ctx, app_id, fingerprint=fingerprint)

    @tool
    def tool_submit_triage_proposal(proposal: dict[str, Any]) -> dict[str, Any]:
        """Submit a structured triage proposal conforming to Annexe B."""
        return submit_triage_proposal(ctx, proposal)

    return [
        tool_get_application_context,
        tool_search_known_findings,
        tool_get_finding_detail,
        tool_get_past_decisions,
        tool_submit_triage_proposal,
    ]


def _find_duplicate(finding: Finding, existing: Finding | None) -> str | None:
    """Return the existing finding_id if this finding duplicates an open/known finding."""
    if (
        existing is not None
        and existing.status != "closed"
        and existing.finding_id != finding.finding_id
    ):
        return existing.finding_id
    return None


def _detect_regression(existing: Finding | None) -> bool:
    """Return True when the fingerprint matches a previously closed finding."""
    return existing is not None and existing.status == "closed"


def _resolve_proposed_status(
    existing: Finding | None,
    needs_validation: bool,
    match: MemoryMatch | None,
) -> str:
    """Determine proposed status: analyst decision memory (EF-TRI-09) wins over defaults."""
    if match is not None:
        return match.proposed_status
    proposed_status = "TO_VERIFY" if needs_validation else "CONFIRMED"
    if existing is not None and existing.status == "false_positive":
        proposed_status = "LIKELY_FALSE_POSITIVE"
    return proposed_status


def _entry_point(finding: Finding) -> Any:
    return finding.evidence.get("entry_point", "") if isinstance(finding.evidence, dict) else ""


def _build_plain_summary(finding: Finding, app: Application, priority: str) -> str:
    """Build a non-technical 3-sentence summary for stakeholders."""
    entry_pt = _entry_point(finding)
    return (
        f"Une vulnérabilité de type {finding.risk_type} ({finding.severity}) a été détectée "
        f"sur {app.name}. "
        f"Le point d'entrée concerné est {entry_pt or 'non spécifié'}. "
        f"Une correction priorisée {priority} est recommandée."
    )


def _build_technical_summary(finding: Finding) -> str:
    """Build a concise technical summary from finding attributes."""
    entry_pt = _entry_point(finding)
    return (
        f"{finding.title} — risk_type={finding.risk_type}, severity={finding.severity}, "
        f"confidence={finding.confidence}, entry_point={entry_pt}."
    )


def _build_justification(
    finding: Finding, app: Application, match: MemoryMatch | None = None
) -> str:
    """Build the deterministic priority and context justification, plus memory citation."""
    base = (
        f"Sévérité {finding.severity}, confiance {finding.confidence}, "
        f"exposition={app.internet_exposed}, criticité={app.criticality}."
    )
    if match is not None:
        return f"{base} {match.justification()}"
    return base


def _index_known_findings(known_findings: list[Finding], app_id: str) -> dict[str, Finding]:
    return {kf.fingerprint: kf for kf in known_findings if kf.app_id == app_id}


def _deterministic_proposal(
    finding: Finding,
    app: Application,
    known_by_fp: dict[str, Finding],
    match: MemoryMatch | None = None,
) -> TriageProposal:
    """Compute a deterministic fallback triage proposal for a single finding."""
    existing = known_by_fp.get(finding.fingerprint)
    is_regression = _detect_regression(existing)
    duplicate_of = _find_duplicate(finding, existing)
    p_res = compute_finding_priority(finding, app)
    proposed_status = _resolve_proposed_status(existing, p_res.needs_validation, match)
    needs_human = p_res.needs_validation or finding.severity in HIGH_SEVERITIES

    return TriageProposal(
        finding_id=finding.finding_id,
        duplicate_of=duplicate_of,
        is_regression=is_regression,
        proposed_status=proposed_status,
        priority=p_res.priority,
        plain_summary=_build_plain_summary(finding, app, p_res.priority),
        technical_summary=_build_technical_summary(finding),
        references=[finding.risk_type] if finding.risk_type else [],
        justification=_build_justification(finding, app, match),
        needs_human_validation=needs_human,
    )


def _deterministic_triage(
    findings: list[Finding],
    app: Application,
    known_findings: list[Finding],
    past_decisions: list[Decision],
    store: Any = None,
) -> list[TriageProposal]:
    known_by_fp = _index_known_findings(known_findings, app.app_id)

    proposals: list[TriageProposal] = []
    for f in findings:
        match = memory_match(
            f, known_findings=known_findings, past_decisions=past_decisions, store=store
        )
        prop = _deterministic_proposal(f, app, known_by_fp, match)
        proposals.append(prop)
        if f.fingerprint not in known_by_fp:
            known_by_fp[f.fingerprint] = f
    return proposals


def _run_strands_agent(ctx: TriageContext, model_client: Any) -> list[TriageProposal]:
    from strands import Agent

    tools = _build_strands_tools(ctx)
    agent = Agent(model=model_client, tools=tools, system_prompt=SYSTEM_PROMPT)
    formatted_findings = "\n\n".join(format_finding_for_prompt(f.to_item()) for f in ctx.findings)
    app_name = ctx.app.name if ctx.app else ""
    app_id = ctx.app.app_id if ctx.app else ""
    prompt = (
        f"Triage the following findings for application '{app_name}' (app_id={app_id}). "
        f"Use your tools to inspect application context, known findings, and past decisions, "
        f"then call tool_submit_triage_proposal for each finding.\n\n{formatted_findings}"
    )
    agent(prompt)
    return list(ctx.proposals)


def run_triage(
    *,
    findings: list[Finding],
    app: Application,
    known_findings: list[Finding],
    past_decisions: list[Decision],
    deps: Any = None,
    model_client: Any = None,
) -> list[TriageProposal]:
    """Run triage on a batch of findings and enforce deterministic guardrails on every proposal.

    Uses Strands Agent if strands-agents is available and a real Strands Model is provided.
    Otherwise falls back to deterministic rule-based triage.
    """
    if not findings:
        return []

    store = getattr(deps, "store", None) if deps is not None else None
    ctx = TriageContext(
        store=store,
        app=app,
        findings=findings,
        known_findings=known_findings,
        past_decisions=past_decisions,
    )

    if _strands_available() and _is_real_strands_model(model_client):
        raw_proposals = _run_strands_agent(ctx, model_client)
    else:
        raw_proposals = _deterministic_triage(
            findings, app, known_findings, past_decisions, store=store
        )

    proposals_by_id = {p.finding_id: p for p in raw_proposals}
    known_by_fp = _index_known_findings(known_findings, app.app_id)

    enforced: list[TriageProposal] = []
    for f in findings:
        prop = proposals_by_id.get(f.finding_id)
        if prop is None:
            match = memory_match(
                f, known_findings=known_findings, past_decisions=past_decisions, store=store
            )
            prop = _deterministic_proposal(f, app, known_by_fp, match)
        enforced.append(enforce(prop, f, app, known_findings=known_findings, store=store))
    return enforced
