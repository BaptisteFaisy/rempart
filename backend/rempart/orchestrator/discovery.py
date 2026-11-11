"""Discovery of CI/CD-gate pentest jobs launched by Security Agent (EF-ORC-01).

Security Agent's CI/CD gate runs inside the client pipeline. Rempart does not
receive a callback for it, so the control plane polls the customer accounts
every five minutes and reconciles the jobs it finds with its own run ledger.
"""

from __future__ import annotations

from typing import Any

from rempart.common.models import Run
from rempart.common.timeutil import iso, parse_iso, utcnow

from .tasks import Deps

DISCOVERY_WINDOW_MINUTES = 5


def _job_started_at(job: dict[str, Any]) -> str:
    for key in ("startedAt", "startTime", "createdAt"):
        if job.get(key):
            return str(job[key])
    return iso(utcnow())


def _is_recent(job: dict[str, Any], since_minutes: int) -> bool:
    raw = job.get("startedAt") or job.get("startTime") or job.get("createdAt")
    if not raw:
        return False
    try:
        started = parse_iso(str(raw))
    except ValueError:
        return False
    return (utcnow() - started).total_seconds() <= since_minutes * 60


def discover_cicd_runs(deps: Deps, since_minutes: int = DISCOVERY_WINDOW_MINUTES) -> list[Run]:
    """Reconcile Security Agent CI/CD jobs with the Rempart run ledger.

    Returns the runs that were created by this discovery pass. Jobs already
    known (same ``run_id``) are left untouched, so the function is idempotent.
    """
    created: list[Run] = []
    for app in deps.store.list_applications():
        for config in deps.store.list_configs(app.app_id):
            if config.kind != "delivery":
                continue
            for job in _delivery_jobs(deps, app.agent_space_id, config.sa_pentest_id):
                if not _is_recent(job, since_minutes):
                    continue
                job_id = str(job.get("pentestJobId") or job.get("jobId") or job.get("id") or "")
                if not job_id or deps.store.get_run(job_id) is not None:
                    continue
                run = Run(
                    run_id=job_id,
                    config_id=config.config_id,
                    app_id=app.app_id,
                    tenant_id=app.tenant_id,
                    trigger="cicd",
                    commit_from=str(job.get("commitFrom") or job.get("commit_from") or ""),
                    commit_to=str(job.get("commitTo") or job.get("commit_to") or ""),
                    scope_decision=str(job.get("scopeDecision") or "deployed_range"),
                    status="running",
                    started_at=_job_started_at(job),
                    ended_at=None,
                    duration_s=None,
                    task_hours=None,
                    cost_usd=None,
                )
                deps.store.save_run(run)
                deps.store.append_audit(
                    "discovery", "run.discovered", "run", job_id, "cicd"
                )
                created.append(run)
    return created


def _delivery_jobs(deps: Deps, space_id: str | None, pentest_id: str) -> list[dict[str, Any]]:
    """List the jobs of a delivery pentest, tolerating API variations.

    ListPentestJobsForPentest exige ``agentSpaceId`` + ``pentestId`` et renvoie
    ``pentestJobSummaries`` (clé d'identité ``pentestJobId``).
    """
    if not space_id or not pentest_id:
        return []
    lister = getattr(deps.sa, "list_pentest_jobs_for_pentest", None)
    if lister is None:
        return []
    try:
        return list(lister(space_id, pentest_id))
    except Exception:  # noqa: BLE001 - a failed discovery must not break the loop
        return []
