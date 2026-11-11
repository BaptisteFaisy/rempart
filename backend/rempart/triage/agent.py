"""Triage agent orchestration (Strands / AgentCore with deterministic fallback)."""

from typing import Any

from rempart.common.models import Application, Decision, Finding
from rempart.common.priority import compute_priority

from .guardrails import _has_sensitive_data, _is_exposed_critical, enforce
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
    def tool_get_past_decisions(app_id: str) -> list[dict[str, Any]]:
        """Get past analyst triage decisions for the application."""
        return get_past_decisions(ctx, app_id)

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


def _deterministic_proposal(
    finding: Finding,
    app: Application,
    known_by_fp: dict[str, Finding],
    decisions_by_finding: dict[str, list[Decision]],
) -> TriageProposal:
    """Compute a deterministic fallback triage proposal for a single finding."""
    existing = known_by_fp.get(finding.fingerprint)
    is_regression = existing is not None and existing.status == "closed"
    duplicate_of = (
        existing.finding_id
        if existing is not None
        and existing.status != "closed"
        and existing.finding_id != finding.finding_id
        else None
    )

    p_res = compute_priority(
        finding.severity,
        finding.confidence,
        exposed_critical=_is_exposed_critical(app),
        sensitive_data=_has_sensitive_data(app),
    )

    proposed_status = "TO_VERIFY" if p_res.needs_validation else "CONFIRMED"
    if existing is not None and existing.status == "false_positive":
        proposed_status = "LIKELY_FALSE_POSITIVE"

    if existing is not None:
        for dec in reversed(decisions_by_finding.get(existing.finding_id, [])):
            if dec.author_type == "human" and dec.action == "false_positive":
                proposed_status = "LIKELY_FALSE_POSITIVE"
                break

    entry_pt = finding.evidence.get("entry_point", "") if isinstance(finding.evidence, dict) else ""
    plain = (
        f"Une vulnérabilité de type {finding.risk_type} ({finding.severity}) a été détectée "
        f"sur {app.name}. "
        f"Le point d'entrée concerné est {entry_pt or 'non spécifié'}. "
        f"Une correction priorisée {p_res.priority} est recommandée."
    )
    tech = (
        f"{finding.title} — risk_type={finding.risk_type}, severity={finding.severity}, "
        f"confidence={finding.confidence}, entry_point={entry_pt}."
    )
    justif = (
        f"Sévérité {finding.severity}, confiance {finding.confidence}, "
        f"exposition={app.internet_exposed}, criticité={app.criticality}."
    )
    needs_human = p_res.needs_validation or finding.severity in ("Critical", "High")

    return TriageProposal(
        finding_id=finding.finding_id,
        duplicate_of=duplicate_of,
        is_regression=is_regression,
        proposed_status=proposed_status,
        priority=p_res.priority,
        plain_summary=plain,
        technical_summary=tech,
        references=[finding.risk_type] if finding.risk_type else [],
        justification=justif,
        needs_human_validation=needs_human,
    )


def _deterministic_triage(
    findings: list[Finding],
    app: Application,
    known_findings: list[Finding],
    past_decisions: list[Decision],
) -> list[TriageProposal]:
    known_by_fp: dict[str, Finding] = {}
    for kf in known_findings:
        if kf.app_id == app.app_id:
            known_by_fp[kf.fingerprint] = kf

    decisions_by_finding: dict[str, list[Decision]] = {}
    for dec in past_decisions:
        decisions_by_finding.setdefault(dec.finding_id, []).append(dec)

    proposals: list[TriageProposal] = []
    for f in findings:
        prop = _deterministic_proposal(f, app, known_by_fp, decisions_by_finding)
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
        raw_proposals = _deterministic_triage(findings, app, known_findings, past_decisions)

    proposals_by_id = {p.finding_id: p for p in raw_proposals}
    known_by_fp = {kf.fingerprint: kf for kf in known_findings if kf.app_id == app.app_id}
    decisions_by_finding: dict[str, list[Decision]] = {}
    for dec in past_decisions:
        decisions_by_finding.setdefault(dec.finding_id, []).append(dec)

    enforced: list[TriageProposal] = []
    for f in findings:
        prop = proposals_by_id.get(f.finding_id)
        if prop is None:
            prop = _deterministic_proposal(f, app, known_by_fp, decisions_by_finding)
        enforced.append(enforce(prop, f, app, known_findings=known_findings, store=store))
    return enforced
