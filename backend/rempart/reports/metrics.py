"""Deterministic KPI computation and month freezing for Rempart (ENF-IA-01).

Every figure produced here is computed by plain Python from the timestamps and
states stored in the Store.  No language model ever takes part in a number.
"""

import statistics
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from rempart.common.models import PRIORITIES, Application, Finding, Run
from rempart.common.store import Store
from rempart.common.timeutil import iso, parse_iso

CLOSED_STATUS = "closed"
OPEN_STATUSES = (
    "new",
    "pending_validation",
    "confirmed",
    "in_remediation",
    "to_retest",
    "reopened",
)
FINISHED_RUN_STATUSES = ("completed", "failed", "blocked")
MAX_FETCH = 1000


# --------------------------------------------------------------------------- #
# Period helpers
# --------------------------------------------------------------------------- #
def period_bounds(period: str) -> tuple[datetime, datetime]:
    """Return the [start, end) UTC bounds of a 'YYYY-MM' period."""
    year, month = int(period[0:4]), int(period[5:7])
    start = datetime(year, month, 1, tzinfo=timezone.utc)
    if month == 12:
        end = datetime(year + 1, 1, 1, tzinfo=timezone.utc)
    else:
        end = datetime(year, month + 1, 1, tzinfo=timezone.utc)
    return start, end


def first_business_day(year: int, month: int) -> datetime:
    """Return the first weekday (Mon-Fri) of the given month."""
    day = datetime(year, month, 1, tzinfo=timezone.utc)
    while day.weekday() >= 5:
        day += timedelta(days=1)
    return day


def freeze_date(period: str) -> datetime:
    """Return the first business day of the month following 'period' (chapter 8.5)."""
    year, month = int(period[0:4]), int(period[5:7])
    if month == 12:
        return first_business_day(year + 1, 1)
    return first_business_day(year, month + 1)


def _ts(value: str | None) -> datetime | None:
    """Parse an ISO timestamp, tolerating None and malformed values."""
    if not value:
        return None
    try:
        return parse_iso(value)
    except Exception:
        return None


def within_period(value: str | None, start: datetime, end: datetime) -> bool:
    """True when the ISO timestamp falls inside [start, end).

    Public because :mod:`rempart.reports.evidence` reuses the exact same
    period filtering as the KPIs (no duplicated time logic).
    """
    moment = _ts(value)
    return moment is not None and start <= moment < end


def _days_between(start_iso: str | None, end_iso: str | None) -> float | None:
    """Return the number of days between two ISO timestamps."""
    start, end = _ts(start_iso), _ts(end_iso)
    if start is None or end is None:
        return None
    return max(0.0, (end - start).total_seconds() / 86400.0)


# --------------------------------------------------------------------------- #
# Scope gathering
# --------------------------------------------------------------------------- #
@dataclass
class Scope:
    """Everything the KPI computation needs, already filtered by period."""

    apps: list[Application]
    apps_by_id: dict[str, Application]
    runs: list[Run]
    detected: list[Finding]
    closed: list[Finding]
    open_findings: list[Finding]
    all_findings: list[Finding]
    start: datetime
    end: datetime


def gather_scope(store: Store, tenant_id: str | None, period: str) -> Scope:
    """Collect applications, runs and findings of the tenant for the period."""
    start, end = period_bounds(period)
    apps = store.list_applications(tenant_id=tenant_id)
    runs = [
        r
        for r in store.list_runs(tenant_id=tenant_id, limit=MAX_FETCH)
        if within_period(r.started_at, start, end)
    ]
    all_findings = store.list_findings(tenant_id=tenant_id, limit=MAX_FETCH)
    detected = [f for f in all_findings if within_period(f.created_at, start, end)]
    closed = [f for f in all_findings if within_period(f.closed_at, start, end)]
    open_findings = [f for f in all_findings if f.status in OPEN_STATUSES]
    return Scope(
        apps=apps,
        apps_by_id={a.app_id: a for a in apps},
        runs=runs,
        detected=detected,
        closed=closed,
        open_findings=open_findings,
        all_findings=all_findings,
        start=start,
        end=end,
    )


# --------------------------------------------------------------------------- #
# Individual KPI computations
# --------------------------------------------------------------------------- #
def run_duration_hours(run: Run) -> float | None:
    """Duration of a run in hours (duration_s first, timestamps otherwise)."""
    if run.duration_s is not None and run.duration_s >= 0:
        return run.duration_s / 3600.0
    start, end = _ts(run.started_at), _ts(run.ended_at)
    if start is None or end is None:
        return None
    return max(0.0, (end - start).total_seconds() / 3600.0)


def delivery_to_result_hours(scope: Scope) -> float:
    """Median duration (hours) of the delivery (cicd) runs of the period."""
    durations = [
        hours
        for hours in (
            run_duration_hours(r)
            for r in scope.runs
            if r.trigger == "cicd" and r.status in FINISHED_RUN_STATUSES
        )
        if hours is not None
    ]
    if not durations:
        return 0.0
    return round(float(statistics.median(durations)), 2)


def critical_blocked_before_prod(scope: Scope) -> float:
    """Ratio of P1/P2 findings stopped before production.

    A P1/P2 finding counts as stopped when it was detected in pre-production
    (the application environment is `staging`) or when its delivery run was
    blocked by the CI/CD gate.
    """
    serious = [f for f in scope.detected if f.priority in ("P1", "P2")]
    if not serious:
        return 0.0
    blocked_runs = {r.run_id for r in scope.runs if r.status == "blocked"}
    stopped = 0
    for finding in serious:
        app = scope.apps_by_id.get(finding.app_id)
        in_preprod = bool(app and app.environment == "staging")
        if in_preprod or finding.run_id in blocked_runs:
            stopped += 1
    return round(stopped / len(serious), 4)


def mean_time_to_fix_days_by_priority(scope: Scope) -> dict[str, float]:
    """Average (closed_at - created_at) in days per priority, for the period."""
    buckets: dict[str, list[float]] = {p: [] for p in PRIORITIES}
    for finding in scope.closed:
        if finding.priority not in buckets:
            continue
        days = _days_between(finding.created_at, finding.closed_at)
        if days is not None:
            buckets[finding.priority].append(days)
    return {
        priority: round(statistics.mean(values), 2) if values else 0.0
        for priority, values in buckets.items()
    }


def sla_compliance(scope: Scope) -> float:
    """Ratio of findings closed before their due date (deadline-tracked closures)."""
    tracked = [f for f in scope.closed if f.due_at and f.closed_at]
    if not tracked:
        return 1.0
    on_time = 0
    for finding in tracked:
        due, closed_at = _ts(finding.due_at), _ts(finding.closed_at)
        if due is not None and closed_at is not None and closed_at <= due:
            on_time += 1
    return round(on_time / len(tracked), 4)


def coverage(scope: Scope) -> float:
    """Ratio of applications covered by at least one test during the period."""
    if not scope.apps:
        return 0.0
    tested = {r.app_id for r in scope.runs}
    return round(len({a.app_id for a in scope.apps if a.app_id in tested}) / len(scope.apps), 4)


def reopen_rate(scope: Scope) -> float:
    """Ratio of reopened findings over the findings closed in the period."""
    closed_count = len(scope.closed)
    reopened = 0
    for finding in scope.all_findings:
        if finding.status == "reopened":
            reopened += 1
        elif finding.closed_at and _ts(finding.updated_at or "") > _ts(finding.closed_at):
            reopened += 1  # state changed after the closure proof
    if closed_count == 0:
        return 0.0
    return round(min(1.0, reopened / closed_count), 4)


def findings_open_by_priority(scope: Scope) -> dict[str, int]:
    """Snapshot of the still open findings, grouped by priority."""
    counts = {p: 0 for p in PRIORITIES}
    for finding in scope.open_findings:
        if finding.priority in counts:
            counts[finding.priority] += 1
    return counts


def risk_level(scope: Scope) -> str:
    """Deterministic risk level of the month (critical / moderate / low)."""
    open_counts = findings_open_by_priority(scope)
    if open_counts["P1"] > 0:
        return "critical"
    if open_counts["P2"] > 0 or sla_compliance(scope) < 0.9:
        return "moderate"
    return "low"


# --------------------------------------------------------------------------- #
# Deterministic detail blocks (Annexe C)
# --------------------------------------------------------------------------- #
def app_label(scope: Scope, app_id: str) -> str:
    """Human readable application label with a safe fallback."""
    app = scope.apps_by_id.get(app_id)
    return app.name if app else app_id


def new_findings_by_priority(scope: Scope) -> dict[str, int]:
    """Count of findings detected during the period, by priority."""
    counts = {p: 0 for p in PRIORITIES}
    for finding in scope.detected:
        if finding.priority in counts:
            counts[finding.priority] += 1
    return counts


def closed_findings_detail(scope: Scope) -> list[dict[str, Any]]:
    """Findings closed during the period, with the proof of closure."""
    detail = []
    for finding in scope.closed:
        proof = finding.remediation_pr_url or finding.ticket_url or finding.closed_by_run_id
        detail.append(
            {
                "finding_id": finding.finding_id,
                "title": finding.title,
                "priority": finding.priority,
                "application": app_label(scope, finding.app_id),
                "closed_at": finding.closed_at,
                "proof": proof or "",
            }
        )
    return detail


def overdue_findings_detail(scope: Scope, reference: datetime) -> list[dict[str, Any]]:
    """Still open findings whose due date has passed, with owner and new date."""
    detail = []
    for finding in scope.open_findings:
        due = _ts(finding.due_at)
        if due is None or due > reference:
            continue
        app = scope.apps_by_id.get(finding.app_id)
        detail.append(
            {
                "finding_id": finding.finding_id,
                "title": finding.title,
                "priority": finding.priority,
                "application": app_label(scope, finding.app_id),
                "owner": app.team if app else "",
                "due_at": finding.due_at,
                "new_target_date": finding.due_at,
            }
        )
    return detail


def tests_detail(scope: Scope) -> dict[str, Any]:
    """Number, type and blocked deliveries of the tests of the period."""
    by_trigger: dict[str, int] = {}
    for run in scope.runs:
        by_trigger[run.trigger] = by_trigger.get(run.trigger, 0) + 1
    return {
        "tests_total": len(scope.runs),
        "tests_blocked": sum(1 for r in scope.runs if r.status == "blocked"),
        "tests_by_type": by_trigger,
    }


def budget_detail(store: Store, tenant_id: str | None, scope: Scope) -> dict[str, Any]:
    """Consumed and remaining task hours for the tenant budget."""
    consumed = round(sum(r.task_hours or 0.0 for r in scope.runs), 2)
    monthly = 0.0
    if tenant_id:
        tenant = store.get_tenant(tenant_id)
        if tenant:
            monthly = float(tenant.monthly_budget_hours or 0.0)
    remaining = round(max(0.0, monthly - consumed), 2)
    pct = round(consumed / monthly * 100, 1) if monthly else 0.0
    return {
        "task_hours_used": consumed,
        "cost_usd": round(sum(r.cost_usd or 0.0 for r in scope.runs), 2),
        "monthly_budget_hours": monthly,
        "remaining_task_hours": remaining,
        "budget_used_pct": pct,
    }


def applications_detail(scope: Scope) -> list[dict[str, Any]]:
    """Technical annex: one line per application of the contract."""
    detail = []
    for app in scope.apps:
        app_findings = [f for f in scope.open_findings if f.app_id == app.app_id]
        counts = {p: 0 for p in PRIORITIES}
        for finding in app_findings:
            if finding.priority in counts:
                counts[finding.priority] += 1
        app_runs = [r for r in scope.runs if r.app_id == app.app_id]
        last_test = max((r.started_at or "" for r in app_runs), default="")
        detail.append(
            {
                "app_id": app.app_id,
                "name": app.name,
                "criticality": app.criticality,
                "environment": app.environment,
                "open_by_priority": counts,
                "tests": len(app_runs),
                "last_test_at": last_test,
            }
        )
    return detail


def recommendations(scope: Scope) -> list[str]:
    """Deterministic recommendations derived from the period indicators."""
    out: list[str] = []
    open_counts = findings_open_by_priority(scope)
    if open_counts["P1"]:
        out.append(
            f"Traiter en priorité les {open_counts['P1']} faille(s) P1 encore ouverte(s) "
            "et leurs échéances contractuelles de 7 jours."
        )
    if open_counts["P2"]:
        out.append(
            f"Planifier la remédiation des {open_counts['P2']} faille(s) P2 sous 30 jours."
        )
    if scope.apps and coverage(scope) < 1.0:
        out.append(
            "Étendre le test continu aux applications du contrat non couvertes ce mois-ci."
        )
    if scope.runs and critical_blocked_before_prod(scope) < 0.8:
        out.append(
            "Renforcer la porte CI/CD : moins de 80 % des failles P1/P2 "
            "sont arretees avant production."
        )
    if sla_compliance(scope) < 0.9:
        out.append(
            "Réduire les dépassements d'échéance : le respect des SLA est inférieur à 90 %."
        )
    if not out:
        out.append(
            "Aucune action corrective urgente : maintenir la cadence de test en continu "
            "et le suivi des échéances."
        )
    return out


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #
def compute_kpis(store: Store, *, tenant_id: str | None, period: str) -> dict[str, Any]:
    """Compute the deterministic KPI set of 'period' ('YYYY-MM') for a tenant."""
    scope = gather_scope(store, tenant_id, period)
    open_counts = findings_open_by_priority(scope)
    return {
        "period": period,
        "tenant_id": tenant_id,
        "delivery_to_result_hours": delivery_to_result_hours(scope),
        "critical_blocked_before_prod": critical_blocked_before_prod(scope),
        "mean_time_to_fix_days_by_priority": mean_time_to_fix_days_by_priority(scope),
        "sla_compliance": sla_compliance(scope),
        "coverage": coverage(scope),
        "reopen_rate": reopen_rate(scope),
        "findings_open_by_priority": open_counts,
        "findings_closed": len(scope.closed),
        "tests_total": len(scope.runs),
        "tests_blocked": sum(1 for r in scope.runs if r.status == "blocked"),
        "task_hours_used": round(sum(r.task_hours or 0.0 for r in scope.runs), 2),
        "cost_usd": round(sum(r.cost_usd or 0.0 for r in scope.runs), 2),
        "findings_open_total": sum(open_counts.values()),
        "findings_new_by_priority": new_findings_by_priority(scope),
        "risk_level": risk_level(scope),
    }


def freeze_month(store: Store, tenant_id: str | None, period: str) -> dict[str, Any]:
    """Freeze the indicators of 'period' (chapter 8.5) and return the snapshot."""
    frozen_at = freeze_date(period)
    scope = gather_scope(store, tenant_id, period)
    kpis = compute_kpis(store, tenant_id=tenant_id, period=period)
    snapshot: dict[str, Any] = {
        **kpis,
        "frozen": True,
        "frozen_at": iso(frozen_at),
        "period_start": iso(scope.start),
        "period_end": iso(scope.end),
        "closed_findings": closed_findings_detail(scope),
        "overdue_findings": overdue_findings_detail(scope, frozen_at),
        "tests_detail": tests_detail(scope),
        "budget_detail": budget_detail(store, tenant_id, scope),
        "applications_detail": applications_detail(scope),
        "recommendations": recommendations(scope),
    }
    return snapshot
