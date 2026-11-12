"""Step Functions task functions for the Rempart orchestrator (chapter 11.4).

Each task takes a ``payload`` dict (the Step Functions state) and a ``Deps``
bundle, and returns the next state dict. Tasks are pure with respect to AWS:
every AWS call goes through the injected ``SecurityAgentClient`` and every
write goes through the injected ``Store``, so the whole workflow is testable
without AWS.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from rempart.common.budget import (
    BudgetVerdict,
    consume,
    estimate_cost,
)
from rempart.common.fingerprint import fingerprint as make_fingerprint
from rempart.common.models import (
    Finding,
    Run,
    TestConfig,
)
from rempart.common.timeutil import iso, parse_iso, utcnow

from .findings_intake import collect_findings  # noqa: F401  (ré-export)
from .gates import budget_gate  # noqa: F401  (ré-export)
from .task_types import (
    TERMINAL_STATUSES,
    Deps,
)
from .task_types import (
    app_of as _app_of,
)
from .task_types import (
    month_now as _month_now,
)
from .task_types import (
    tenant_of as _tenant_of,
)
from .triage_dispatch import apply_proposals, load_findings, run_proposals


# --------------------------------------------------------------------------- #
def start_run(payload: dict[str, Any], deps: Deps) -> dict[str, Any]:
    """Start the Security Agent pentest job and record the run."""
    app = _app_of(deps, payload["app_id"])
    if app is None or not app.agent_space_id:
        return {**payload, "error": "unknown_application"}

    # StartPentestJob : agentSpaceId + pentestId requis ; réponse ``pentestJobId``.
    resp = deps.sa.start_pentest_job(app.agent_space_id, payload["pentest_id"])
    job_id = resp.get("pentestJobId") or resp.get("jobId") or f"job-{uuid.uuid4().hex[:8]}"
    run = Run(
        run_id=job_id,
        config_id=payload.get("config_id", ""),
        app_id=app.app_id,
        tenant_id=app.tenant_id,
        trigger=payload.get("trigger", "manual"),
        commit_from=payload.get("commit_from", ""),
        commit_to=payload.get("commit_to", ""),
        scope_decision=payload.get("scope_decision", "full"),
        status="running",
        started_at=iso(utcnow()),
        ended_at=None,
        duration_s=None,
        task_hours=None,
        cost_usd=None,
    )
    deps.store.save_run(run)
    return {**payload, "run_id": job_id}


# --------------------------------------------------------------------------- #
# 3. Poll run (budget auto-stop, R8)
# --------------------------------------------------------------------------- #


def _task_hours(deps: Deps, space_id: str, run_id: str) -> float:
    """Heures-tâches RÉELLEMENT consommées, sommées sur les tâches du job.

    INCIDENT RÉEL (12 nov. 2026) : on lisait ``taskHours`` sur la réponse de
    ``BatchGetPentestJobs``. Le modèle officiel de l'API (service
    ``securityagent`` 2025-09-06) ne déclare AUCUN ``taskHours`` sur
    ``PentestJob`` — seulement ``maxTaskHours``, un plafond. Les heures vives
    sont portées par ``TaskSummary.taskHours``, que rend
    ``ListPentestJobTasks``. Conséquence mesurée sur le banc réel : heures
    disponibles 0,005731 h côté service, ``run.task_hours = 0.0`` côté Rempart,
    donc coût nul, budget jamais consommé, auto-stop R8 inopérant et prévision
    EF-BUD-04 à zéro. Le double de test renvoyait ce champ inexistant : aucun
    test ne pouvait le voir.
    """
    tasks = deps.sa.list_pentest_job_tasks(space_id, pentest_job_id=run_id)
    total = 0.0
    for task in tasks:
        try:
            total += float(task.get("taskHours") or 0.0)
        except (TypeError, ValueError):
            continue
    return total


def _poll_job(deps: Deps, run: Run, space_id: str) -> tuple[str, float]:
    """Lit l'état du job côté Continuum et rend (statut, heures-tâches).

    BatchGetPentestJobs exige ``agentSpaceId`` + ``pentestJobIds`` (tableau) et
    ne donne que le statut ; les heures viennent de ``ListPentestJobTasks``.
    """
    jobs = deps.sa.batch_get_pentest_jobs(space_id, [run.run_id])
    job = jobs[0] if jobs else {}
    status = str(job.get("status", run.status)).lower()
    return status, _task_hours(deps, space_id, run.run_id)


def _consume_budget(deps: Deps, run: Run, task_hours: float) -> BudgetVerdict:
    """Consomme les heures-tâches sur le budget du mois et rend le verdict."""
    tenant = _tenant_of(deps, run.tenant_id)
    state = deps.store.get_budget(run.tenant_id, _month_now())
    new_state, verdict = consume(state, task_hours, tenant.monthly_budget_hours)
    deps.store.save_budget(new_state)
    return verdict


def _auto_stop_if_needed(
    deps: Deps,
    run: Run,
    space_id: str,
    status: str,
    task_hours: float,
    verdict: BudgetVerdict,
) -> tuple[str, bool]:
    """Arrête le test sur budget épuisé (R8) ou plafond par test dépassé.

    Deux freins indépendants : le budget mensuel du client, et un plafond dur
    d'heures-tâches pour UN test (`REMPART_MAX_TASK_HOURS_PER_TEST`, 5 h par
    défaut) qui borne la facture même si le budget mensuel est large.
    ``task_hours`` vient du poll en cours : la fiche du run n'est pas encore
    mise à jour à ce stade.
    """
    if status in TERMINAL_STATUSES:
        return status, False
    cap = deps.settings.max_task_hours_per_test
    over_cap = cap > 0 and task_hours > cap
    reason = "task_hour_cap" if over_cap else "budget"
    if not verdict.auto_stop and not over_cap:
        return status, False
    # StopPentestJob exige ``agentSpaceId`` + ``pentestJobId``.
    deps.sa.stop_pentest_job(space_id, run.run_id)
    deps.store.append_audit(
        "orchestrator", "run.auto_stopped", "run", run.run_id, reason
    )
    return "stopped", True


def _record_run_progress(
    deps: Deps, run: Run, status: str, task_hours: float
) -> None:
    """Reporte le statut, la durée et le coût estimé sur la fiche du test."""
    ended_at = iso(utcnow()) if status in TERMINAL_STATUSES else None
    duration = None
    if ended_at and run.started_at:
        duration = (parse_iso(ended_at) - parse_iso(run.started_at)).total_seconds()
    run.status = status
    run.task_hours = task_hours
    run.cost_usd = estimate_cost(task_hours, deps.settings.hourly_rate)
    run.ended_at = ended_at
    run.duration_s = duration
    deps.store.save_run(run)


def poll_run(payload: dict[str, Any], deps: Deps) -> dict[str, Any]:
    """Refresh the run status, consume task hours, stop the job on budget overrun."""
    run = deps.store.get_run(payload["run_id"])
    if run is None:
        return {**payload, "error": "unknown_run"}

    app = _app_of(deps, run.app_id)
    space_id = app.agent_space_id if app else None
    if not space_id:
        return {**payload, "error": "unknown_agent_space"}

    status, task_hours = _poll_job(deps, run, space_id)
    verdict = _consume_budget(deps, run, task_hours)
    status, stopped = _auto_stop_if_needed(
        deps, run, space_id, status, task_hours, verdict
    )
    _record_run_progress(deps, run, status, task_hours)

    return {
        **payload,
        "run_status": status,
        "task_hours": task_hours,
        "budget_pct": verdict.pct,
        "auto_stopped": stopped,
        "done": status in TERMINAL_STATUSES,
    }


# --------------------------------------------------------------------------- #
# 4. Collect findings (dedup, regression, priority)
# --------------------------------------------------------------------------- #
# --------------------------------------------------------------------------- #
# 5. Dispatch triage (guardrails applied by the triage module)
# --------------------------------------------------------------------------- #
def dispatch_triage(payload: dict[str, Any], deps: Deps) -> dict[str, Any]:
    """Run the triage agent, record decisions, queue critical/high findings."""
    app = _app_of(deps, payload["app_id"])
    if app is None:
        return {**payload, "error": "unknown_application"}

    finding_ids = payload.get("findings_created") or []
    findings = load_findings(deps, finding_ids)
    if not findings:
        return {**payload, "triaged": 0, "queued": []}

    proposals = run_proposals(deps, app, findings, finding_ids)
    queued, confirmed = apply_proposals(deps, proposals)

    return {
        **payload,
        "triaged": len(proposals),
        "queued": queued,
        "confirmed": confirmed,
    }


# --------------------------------------------------------------------------- #
# 6. Create tickets (EF-COR-01/02)
# --------------------------------------------------------------------------- #
def create_tickets(payload: dict[str, Any], deps: Deps) -> dict[str, Any]:
    """Open a GitHub issue for every confirmed finding, with its due date.

    A finding is eligible when its status is ``confirmed``: the triage agent
    always queues Critical and High findings for human validation (EF-TRI-05),
    so the ticket is created once the analyst has confirmed it.
    """
    app = _app_of(deps, payload["app_id"])
    if app is None:
        return {**payload, "error": "unknown_application"}
    if deps.github is None:
        return {**payload, "tickets": [], "reason": "no_github_client"}

    owner = deps.settings.github_owner
    repo = (app.repositories or [""])[0]
    repo_name = repo.split("/")[-1] if repo else ""
    if not owner or not repo_name:
        return {**payload, "tickets": [], "reason": "no_target_repo"}

    eligible = payload.get("confirmed") or None
    if eligible is None:
        eligible = [
            f.finding_id
            for f in deps.store.list_findings(app_id=app.app_id)
            if f.status == "confirmed"
        ]

    tickets: list[str] = []
    for finding_id in eligible:
        finding = deps.store.get_finding(finding_id)
        if finding is None or finding.ticket_url:
            continue
        body = _ticket_body(finding)
        issue = deps.github.create_issue(
            owner=owner,
            repo=repo_name,
            title=f"[{finding.priority}] {finding.title}",
            body=body,
            labels=["security", finding.priority.lower()],
        )
        finding.ticket_url = issue.get("html_url", "")
        finding.status = "in_remediation"
        finding.updated_at = iso(utcnow())
        deps.store.save_finding(finding)
        tickets.append(finding.ticket_url)

    return {**payload, "tickets": tickets}


def _ticket_body(finding: Finding) -> str:
    lines = [
        f"**Priority:** {finding.priority}",
        f"**Severity:** {finding.severity} (confidence {finding.confidence})",
        f"**Risk type:** {finding.risk_type}",
        f"**Due date:** {finding.due_at or 'next release'}",
        "",
        "### Summary",
        finding.evidence.get("description", ""),
        "",
        f"_Opened automatically by Rempart from test `{finding.run_id}`. "
        f"Finding id: `{finding.finding_id}`._",
    ]
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# 7. Request remediation (EF-COR-03)
# --------------------------------------------------------------------------- #
def request_remediation(payload: dict[str, Any], deps: Deps) -> dict[str, Any]:
    """Ask Security Agent for a remediation pull request (StartCodeRemediation).

    L'API documentée exige ``agentSpaceId`` + ``findingIds`` (tableau) avec
    ``pentestJobId`` ou ``codeReviewJobId`` (exclusifs) et répond avec un corps
    vide : la PR n'est donc pas renvoyée ; on marque le finding
    ``in_remediation`` et on retourne les identifiants de findings traités.
    """
    app = _app_of(deps, payload.get("app_id", ""))
    space_id = app.agent_space_id if app else None
    if not space_id:
        return {**payload, "remediation_prs": [], "reason": "unknown_agent_space"}

    started: list[str] = []
    for finding_id in payload.get("confirmed", []) or payload.get("queued", []):
        finding = deps.store.get_finding(finding_id)
        if finding is None or finding.remediation_pr_url:
            continue
        # NB : ne surtout pas exclure `status == "in_remediation"`. C'est
        # précisément l'état posé par create_tickets (cycle de vie § 11.5 :
        # Confirmée → En correction). L'exclure faisait que la pull request de
        # correction n'était JAMAIS demandée dans le parcours normal — bug
        # trouvé par le test de parcours complet.
        resp = deps.sa.start_code_remediation(
            space_id,
            [finding.finding_id],
            pentest_job_id=finding.run_id or None,
        )
        url = resp.get("remediationPrUrl") or resp.get("pullRequestUrl")
        if url:
            finding.remediation_pr_url = url
        finding.status = "in_remediation"
        finding.updated_at = iso(utcnow())
        deps.store.save_finding(finding)
        started.append(finding.finding_id)
    return {**payload, "remediation_prs": started}


# --------------------------------------------------------------------------- #
# 8. Close or reopen (EF-COR-04/05, EF-TRI-06)
# --------------------------------------------------------------------------- #
def close_or_reopen(payload: dict[str, Any], deps: Deps) -> dict[str, Any]:
    """Close findings that disappeared from the retest, reopen the ones still there."""
    app = _app_of(deps, payload["app_id"])
    if app is None:
        return {**payload, "error": "unknown_application"}

    run_id = payload.get("run_id") or payload.get("retest_run_id") or ""
    present = {
        make_fingerprint(
            app.app_id,
            str(raw.get("riskType") or raw.get("risk_type") or "Unknown"),
            str(raw.get("entryPoint") or raw.get("entry_point") or ""),
            raw.get("parameter"),
        )
        for raw in deps.sa.list_findings(app.agent_space_id or "", pentest_job_id=run_id)
    }

    closed: list[str] = []
    reopened: list[str] = []
    for finding in deps.store.list_findings(app_id=app.app_id):
        # "closed" is included: a finding that comes back is a regression
        # (EF-TRI-06) and must be reopened, not silently ignored.
        if finding.status not in ("in_remediation", "to_retest", "reopened", "closed"):
            continue
        if finding.fingerprint in present:
            if finding.status != "reopened":
                finding.status = "reopened"
                finding.closed_at = None
                finding.closed_by_run_id = None
                reopened.append(finding.finding_id)
        else:
            if finding.status == "closed":
                continue
            finding.status = "closed"
            finding.closed_at = iso(utcnow())
            finding.closed_by_run_id = run_id
            closed.append(finding.finding_id)
        finding.updated_at = iso(utcnow())
        deps.store.save_finding(finding)

    return {**payload, "closed": closed, "reopened": reopened}


def delivery_config(deps: Deps, app_id: str) -> TestConfig | None:
    """Return the 'delivery' test configuration of an application."""
    for config in deps.store.list_configs(app_id):
        if config.kind == "delivery":
            return config
    return None


def now_iso() -> str:
    """Current UTC timestamp in ISO-8601 (helper for step functions)."""
    return iso(utcnow())


def parse_dt(value: str) -> datetime:
    """Parse an ISO-8601 timestamp (helper for step functions)."""
    return parse_iso(value)
