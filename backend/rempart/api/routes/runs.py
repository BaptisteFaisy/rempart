"""Route handlers for Runs (test executions)."""

import uuid
from typing import Any

from rempart.api.context import ApiContext
from rempart.api.helpers import (
    Response,
    authorize,
    budget_verdict,
    current_month,
    error_response,
    get_store,
    load_or_404,
    require_principal,
)
from rempart.api.router import Router
from rempart.common.models import Application, Run, TestConfig
from rempart.common.timeutil import iso, utcnow


def _load_app_or_404(ctx: ApiContext, app_id: str) -> tuple[Application | None, Response | None]:
    return load_or_404(get_store(ctx).get_application, app_id, "Application")

def _load_run_or_404(ctx: ApiContext, run_id: str) -> tuple[Run | None, Response | None]:
    return load_or_404(get_store(ctx).get_run, run_id, "Run")

def _validate_tenant_gates(ctx: ApiContext, app: Application) -> Response | None:
    """Reject the run when the mandate is invalid or the budget is exhausted."""
    store = get_store(ctx)
    tenant = store.get_tenant(app.tenant_id)
    if not tenant or tenant.mandate_status != "valid":
        return error_response("Mandat de test non valide ou expiré", 403)

    state = store.get_budget(app.tenant_id, current_month())
    verdict = budget_verdict(ctx, state, tenant)
    if not verdict.allowed:
        return 400, {"error": "Budget mensuel épuisé", "budget_pct": verdict.pct}
    return None

def _load_config_or_error(
    ctx: ApiContext, app_id: str
) -> tuple[TestConfig | None, Response | None]:
    """Return the application's TestConfig, or the error blocking the run."""
    if not ctx.sa:
        return None, error_response("Security Agent client not available", 500)
    configs = get_store(ctx).list_configs(app_id)
    if not configs:
        return None, error_response("Application not onboarded (no TestConfig found)", 409)
    return configs[0], None

def _build_run(ctx: ApiContext, app: Application, config: TestConfig, job_id: str) -> Run:
    """Build the Run record for a freshly started Security Agent job."""
    return Run(
        run_id=job_id,
        config_id=config.config_id,
        app_id=app.app_id,
        tenant_id=app.tenant_id,
        trigger=ctx.body.get("trigger", "manual"),
        commit_from=ctx.body.get("commit_from", ""),
        commit_to=ctx.body.get("commit_to", ""),
        scope_decision=ctx.body.get("scope_decision", "minimal"),
        status="running",
        started_at=iso(utcnow()),
        ended_at=None,
        duration_s=None,
        task_hours=None,
        cost_usd=None,
    )

def post_run(ctx: ApiContext) -> tuple[int, dict[str, Any]]:
    """Trigger a new pentest run for an application, enforcing mandate and budget gates."""
    principal, err = require_principal(ctx)
    if err:
        return err
    app_id = ctx.path_params.get("id", "")
    app, err = _load_app_or_404(ctx, app_id)
    if err or not app:
        return err  # type: ignore[return-value]

    err = authorize(principal, app.tenant_id, write=True)
    if err:
        return err
    err = _validate_tenant_gates(ctx, app)
    if err:
        return err

    config, err = _load_config_or_error(ctx, app_id)
    if err or not config:
        return err  # type: ignore[return-value]

    if not app.agent_space_id:
        return error_response("Application non embarquée (pas d'agent space)", 409)

    # StartPentestJob exige ``agentSpaceId`` + ``pentestId`` ; réponse : ``pentestJobId``.
    job_resp = ctx.sa.start_pentest_job(app.agent_space_id, config.sa_pentest_id)
    job_id = job_resp.get("pentestJobId") or job_resp.get("jobId") or f"job-{uuid.uuid4().hex[:8]}"

    run = _build_run(ctx, app, config, job_id)
    store = get_store(ctx)
    store.save_run(run)
    ctx.audit("run.start", "run", run.run_id)
    return 201, run.to_item()

def get_app_runs(ctx: ApiContext) -> tuple[int, dict[str, Any]]:
    """List runs of an application."""
    principal, err = require_principal(ctx)
    if err:
        return err
    app_id = ctx.path_params.get("id", "")
    app, err = _load_app_or_404(ctx, app_id)
    if err or not app:
        return err  # type: ignore[return-value]

    err = authorize(principal, app.tenant_id, write=False)
    if err:
        return err

    runs = get_store(ctx).list_runs(app_id=app_id)
    return 200, {"runs": [r.to_item() for r in runs]}

def get_run_by_id(ctx: ApiContext) -> tuple[int, dict[str, Any]]:
    """Get details of a specific run."""
    principal, err = require_principal(ctx)
    if err:
        return err
    run_id = ctx.path_params.get("jobId", "")
    run, err = _load_run_or_404(ctx, run_id)
    if err or not run:
        return err  # type: ignore[return-value]

    err = authorize(principal, run.tenant_id, write=False)
    if err:
        return err
    return 200, run.to_item()

def stop_run(ctx: ApiContext) -> tuple[int, dict[str, Any]]:
    """Stop a running test job (R8 auto-stop or manual stop)."""
    principal, err = require_principal(ctx)
    if err:
        return err
    run_id = ctx.path_params.get("jobId", "")
    run, err = _load_run_or_404(ctx, run_id)
    if err or not run:
        return err  # type: ignore[return-value]

    err = authorize(principal, run.tenant_id, write=True)
    if err:
        return err

    if run.status not in ("queued", "running"):
        return error_response(f"Run '{run_id}' n'est pas en cours d'exécution", 409)

    app, err = _load_app_or_404(ctx, run.app_id)
    if err or not app:
        return err  # type: ignore[return-value]

    if ctx.sa and app.agent_space_id:
        # StopPentestJob exige ``agentSpaceId`` + ``pentestJobId``.
        ctx.sa.stop_pentest_job(app.agent_space_id, run_id)

    store = get_store(ctx)
    run.status = "stopped"
    run.ended_at = iso(utcnow())
    store.save_run(run)
    ctx.audit("run.stop", "run", run_id)
    return 200, run.to_item()

def register(router: Router) -> None:
    router.add("POST", "/v1/applications/:id/runs", post_run)
    router.add("GET", "/v1/applications/:id/runs", get_app_runs)
    router.add("GET", "/v1/runs/:jobId", get_run_by_id)
    router.add("POST", "/v1/runs/:jobId/stop", stop_run)
