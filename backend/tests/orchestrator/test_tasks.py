"""Tests for the orchestrator tasks (chapters 9.2, 9.4, 21 R6/R7/R8/R12)."""

from rempart.common.models import Application, Finding, Tenant
from rempart.orchestrator.tasks import (
    Deps,
    budget_gate,
    close_or_reopen,
    collect_findings,
    create_tickets,
    dispatch_triage,
    poll_run,
    request_remediation,
    start_run,
)
from tests.fakes import FakeGitHub, FakeSecurityAgentClient, FakeStore

MONTHLY_BUDGET = 10.0


def _seed(store=None, mandate="valid", budget=MONTHLY_BUDGET):
    store = store or FakeStore()
    store.save_tenant(
        Tenant(
            tenant_id="t-1",
            name="Acme",
            aws_account_id="123456789012",
            region="eu-west-3",
            role_arn="arn:aws:iam::123456789012:role/rempart",
            external_id="ext",
            plan="continu",
            contacts=[],
            monthly_budget_hours=budget,
            mandate_status=mandate,
            created_at="2026-11-01T00:00:00Z",
        )
    )
    store.save_application(
        Application(
            app_id="app-1",
            tenant_id="t-1",
            name="ShopLite",
            criticality="high",
            internet_exposed=True,
            data_types=["personal"],
            environment="staging",
            agent_space_id="space-1",
            domains=["shop.acme.com"],
            repositories=["acme/shop"],
            team="Core",
            ticket_channel="github",
            context={},
            created_at="2026-11-01T00:00:00Z",
        )
    )
    return store


def _deps(store=None, github=None):
    store = store or _seed()
    return Deps(store=store, sa=FakeSecurityAgentClient(), github=github)


def test_budget_gate_refuses_without_mandate():
    store = _seed(mandate="pending")
    deps = _deps(store)
    out = budget_gate({"tenant_id": "t-1", "app_id": "app-1"}, deps)
    assert out["allowed"] is False
    assert out["reason"] == "mandate_invalid"


def test_budget_gate_allows_with_valid_mandate():
    deps = _deps()
    out = budget_gate({"tenant_id": "t-1", "app_id": "app-1"}, deps)
    assert out["allowed"] is True


def test_start_run_records_running_run():
    deps = _deps()
    out = start_run(
        {"app_id": "app-1", "tenant_id": "t-1", "pentest_id": "pt-1", "trigger": "manual"},
        deps,
    )
    run = deps.store.get_run(out["run_id"])
    assert run is not None
    assert run.status == "running"
    assert run.trigger == "manual"


def test_poll_run_updates_hours_and_cost():
    deps = _deps()
    out = start_run({"app_id": "app-1", "tenant_id": "t-1", "pentest_id": "pt-1"}, deps)
    job_id = out["run_id"]
    deps.sa.set_job_outcome(job_id, "COMPLETED")
    out = poll_run({"app_id": "app-1", "tenant_id": "t-1", "run_id": job_id}, deps)
    run = deps.store.get_run(job_id)
    assert run is not None
    assert out["task_hours"] >= 0


def test_collect_findings_computes_priority_and_skips_duplicates():
    deps = _deps()
    deps.sa.jobs["job-1"] = {"jobId": "job-1", "status": "COMPLETED"}
    deps.sa.seed_finding(
        job_id="job-1",
        title="IDOR on orders",
        severity="Critical",
        confidence="High",
        risk_type="IDOR",
        entry_point="/orders/{id}",
    )
    out = collect_findings({"app_id": "app-1", "tenant_id": "t-1", "run_id": "job-1"}, deps)
    assert len(out["findings_created"]) == 1
    finding = deps.store.get_finding(out["findings_created"][0])
    assert finding.priority == "P1"
    assert finding.due_at is not None

    out2 = collect_findings({"app_id": "app-1", "tenant_id": "t-1", "run_id": "job-1"}, deps)
    assert out2["duplicates_skipped"] == 1
    assert out2["findings_created"] == []


def test_dispatch_triage_records_agent_decision():
    deps = _deps()
    deps.sa.jobs["job-1"] = {"jobId": "job-1", "status": "COMPLETED"}
    deps.sa.seed_finding(
        job_id="job-1",
        title="SQL injection",
        severity="Critical",
        confidence="Medium",
        risk_type="SQLI",
        entry_point="/search",
    )
    collected = collect_findings(
        {"app_id": "app-1", "tenant_id": "t-1", "run_id": "job-1"}, deps
    )
    out = dispatch_triage(
        {
            "app_id": "app-1",
            "tenant_id": "t-1",
            "run_id": "job-1",
            "findings_created": collected["findings_created"],
        },
        deps,
    )
    assert out["triaged"] >= 1
    finding = deps.store.get_finding(collected["findings_created"][0])
    assert finding.status in ("pending_validation", "confirmed")
    assert deps.store.list_decisions(finding.finding_id)


def test_create_tickets_opens_issue_with_due_date():
    github = FakeGitHub()
    deps = _deps(github=github)
    deps.settings.github_owner = "acme"
    deps.sa.jobs["job-1"] = {"jobId": "job-1", "status": "COMPLETED"}
    deps.sa.seed_finding(
        job_id="job-1",
        title="IDOR on orders",
        severity="Critical",
        confidence="High",
        risk_type="IDOR",
        entry_point="/orders/{id}",
    )
    collected = collect_findings(
        {"app_id": "app-1", "tenant_id": "t-1", "run_id": "job-1"}, deps
    )
    triage_out = dispatch_triage(
        {
            "app_id": "app-1",
            "tenant_id": "t-1",
            "run_id": "job-1",
            "findings_created": collected["findings_created"],
        },
        deps,
    )
    # Critical/High findings always wait for the analyst (EF-TRI-05).
    finding = deps.store.get_finding(collected["findings_created"][0])
    assert finding.status == "pending_validation"
    finding.status = "confirmed"
    deps.store.save_finding(finding)

    out = create_tickets(
        {
            "app_id": "app-1",
            "tenant_id": "t-1",
            "confirmed": triage_out.get("confirmed", []),
        },
        deps,
    )
    assert len(out["tickets"]) == 1
    assert github.issues
    assert "Due date" in github.issues[0]["body"]


def test_request_remediation_links_pull_request():
    deps = _deps()
    deps.sa.jobs["job-1"] = {"jobId": "job-1", "status": "COMPLETED"}
    deps.sa.seed_finding(
        job_id="job-1",
        title="IDOR",
        severity="High",
        confidence="High",
        risk_type="IDOR",
        entry_point="/orders/{id}",
    )
    collected = collect_findings(
        {"app_id": "app-1", "tenant_id": "t-1", "run_id": "job-1"}, deps
    )
    out = request_remediation(
        {
            "app_id": "app-1",
            "tenant_id": "t-1",
            "confirmed": collected["findings_created"],
        },
        deps,
    )
    assert len(out["remediation_prs"]) == 1
    finding = deps.store.get_finding(collected["findings_created"][0])
    assert finding.remediation_pr_url


def test_close_or_reopen_closes_when_gone_and_reopens_when_present():
    deps = _deps()
    deps.sa.jobs["job-1"] = {"jobId": "job-1", "status": "COMPLETED"}
    deps.sa.seed_finding(
        job_id="job-1",
        title="IDOR",
        severity="High",
        confidence="High",
        risk_type="IDOR",
        entry_point="/orders/{id}",
    )
    collected = collect_findings(
        {"app_id": "app-1", "tenant_id": "t-1", "run_id": "job-1"}, deps
    )
    finding = deps.store.get_finding(collected["findings_created"][0])
    finding.status = "in_remediation"
    deps.store.save_finding(finding)

    out = close_or_reopen({"app_id": "app-1", "tenant_id": "t-1", "run_id": "job-2"}, deps)
    assert out["closed"] == [finding.finding_id]
    closed = deps.store.get_finding(finding.finding_id)
    assert closed.status == "closed"
    assert closed.closed_by_run_id == "job-2"

    deps.sa.seed_finding(
        job_id="job-3",
        title="IDOR",
        severity="High",
        confidence="High",
        risk_type="IDOR",
        entry_point="/orders/{id}",
    )
    out2 = close_or_reopen({"app_id": "app-1", "tenant_id": "t-1", "run_id": "job-3"}, deps)
    assert out2["reopened"] == [finding.finding_id]
    assert deps.store.get_finding(finding.finding_id).status == "reopened"


def test_budget_auto_stop_stops_running_job():
    store = _seed(budget=0.01)
    deps = _deps(store)
    out = start_run({"app_id": "app-1", "tenant_id": "t-1", "pentest_id": "pt-1"}, deps)
    job_id = out["run_id"]
    deps.sa.set_job_outcome(job_id, "RUNNING")
    out = poll_run({"app_id": "app-1", "tenant_id": "t-1", "run_id": job_id}, deps)
    assert out["auto_stopped"] is True
    assert deps.store.get_run(job_id).status == "stopped"


def test_findings_are_scoped_to_application():
    deps = _deps()
    deps.sa.jobs["job-1"] = {"jobId": "job-1", "status": "COMPLETED"}
    deps.sa.seed_finding(
        job_id="job-1",
        title="XSS",
        severity="Low",
        confidence="Low",
        risk_type="XSS",
        entry_point="/render",
    )
    collect_findings({"app_id": "app-1", "tenant_id": "t-1", "run_id": "job-1"}, deps)
    findings = deps.store.list_findings(app_id="app-1")
    assert len(findings) == 1
    assert findings[0].tenant_id == "t-1"


def test_run_record_keeps_commit_range():
    deps = _deps()
    start_run(
        {
            "app_id": "app-1",
            "tenant_id": "t-1",
            "pentest_id": "pt-1",
            "trigger": "cicd",
            "commit_from": "aaa",
            "commit_to": "bbb",
        },
        deps,
    )
    runs = deps.store.list_runs(app_id="app-1")
    assert runs[0].commit_from == "aaa"
    assert runs[0].commit_to == "bbb"


def test_models_round_trip():
    deps = _deps()
    deps.sa.jobs["job-1"] = {"jobId": "job-1", "status": "COMPLETED"}
    deps.sa.seed_finding(
        job_id="job-1",
        title="SSRF",
        severity="Medium",
        confidence="High",
        risk_type="SSRF",
        entry_point="/fetch",
    )
    collected = collect_findings(
        {"app_id": "app-1", "tenant_id": "t-1", "run_id": "job-1"}, deps
    )
    finding = deps.store.get_finding(collected["findings_created"][0])
    assert finding.run_id == "job-1"
    assert finding.fingerprint
    assert isinstance(Finding.from_item(finding.to_item()), Finding)
