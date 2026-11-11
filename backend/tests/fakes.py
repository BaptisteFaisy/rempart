"""Test fakes for Rempart unit and integration tests."""

import uuid
from dataclasses import dataclass
from typing import Any

from rempart.common.models import (
    Application,
    AuditEvent,
    BudgetState,
    Decision,
    Finding,
    Report,
    Run,
    Tenant,
    TestConfig,
)
from rempart.common.timeutil import iso, utcnow


class FakeDdbTable:
    """Minimal fake DynamoDB Table supporting put_item, get_item, scan, query."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.items: list[dict[str, Any]] = []

    def put_item(self, Item: dict[str, Any]) -> dict[str, Any]:
        # Simple upsert based on single key guess or append
        self.items.append(dict(Item))
        return {}

    def get_item(self, Key: dict[str, Any]) -> dict[str, Any]:
        for it in reversed(self.items):
            if all(it.get(k) == v for k, v in Key.items()):
                return {"Item": dict(it)}
        return {}

    def scan(self, **kwargs: Any) -> dict[str, Any]:
        return {"Items": [dict(it) for it in self.items]}

    def query(self, **kwargs: Any) -> dict[str, Any]:
        return {"Items": [dict(it) for it in self.items]}


class FakeDdbResource:
    """Minimal boto3 DynamoDB resource fake."""

    def __init__(self) -> None:
        self.tables: dict[str, FakeDdbTable] = {}

    def Table(self, name: str) -> FakeDdbTable:
        if name not in self.tables:
            self.tables[name] = FakeDdbTable(name)
        return self.tables[name]


class FakeStore:
    """Dict-backed in-memory store exposing the exact same public API as Store."""

    def __init__(self, ddb_resource: Any = None, table_prefix: str = "rempart-") -> None:
        self.tenants: dict[str, Tenant] = {}
        self.applications: dict[str, Application] = {}
        self.configs: dict[str, TestConfig] = {}
        self.runs: dict[str, Run] = {}
        self.findings: dict[str, Finding] = {}
        self.decisions: list[Decision] = []
        self.reports: dict[str, Report] = {}
        self.budgets: dict[str, BudgetState] = {}
        self.audits: list[AuditEvent] = []

    def save_tenant(self, t: Tenant) -> Tenant:
        self.tenants[t.tenant_id] = t
        return t

    def get_tenant(self, tenant_id: str) -> Tenant | None:
        return self.tenants.get(tenant_id)

    def list_tenants(self) -> list[Tenant]:
        return list(self.tenants.values())

    def save_application(self, a: Application) -> Application:
        self.applications[a.app_id] = a
        return a

    def get_application(self, app_id: str) -> Application | None:
        return self.applications.get(app_id)

    def list_applications(self, tenant_id: str | None = None) -> list[Application]:
        apps = list(self.applications.values())
        if tenant_id:
            apps = [a for a in apps if a.tenant_id == tenant_id]
        return apps

    def save_config(self, c: TestConfig) -> TestConfig:
        self.configs[c.config_id] = c
        return c

    def list_configs(self, app_id: str) -> list[TestConfig]:
        return [c for c in self.configs.values() if c.app_id == app_id]

    def save_run(self, r: Run) -> Run:
        self.runs[r.run_id] = r
        return r

    def get_run(self, run_id: str) -> Run | None:
        return self.runs.get(run_id)

    def list_runs(
        self,
        app_id: str | None = None,
        tenant_id: str | None = None,
        status: str | None = None,
        limit: int = 50,
    ) -> list[Run]:
        res = list(self.runs.values())
        if app_id:
            res = [r for r in res if r.app_id == app_id]
        if tenant_id:
            res = [r for r in res if r.tenant_id == tenant_id]
        if status:
            res = [r for r in res if r.status == status]
        return res[:limit]

    def save_finding(self, f: Finding) -> Finding:
        self.findings[f.finding_id] = f
        return f

    def get_finding(self, finding_id: str) -> Finding | None:
        return self.findings.get(finding_id)

    def list_findings(
        self,
        tenant_id: str | None = None,
        app_id: str | None = None,
        status: str | None = None,
        priority: str | None = None,
        limit: int = 100,
    ) -> list[Finding]:
        res = list(self.findings.values())
        if tenant_id:
            res = [f for f in res if f.tenant_id == tenant_id]
        if app_id:
            res = [f for f in res if f.app_id == app_id]
        if status:
            res = [f for f in res if f.status == status]
        if priority:
            res = [f for f in res if f.priority == priority]
        return res[:limit]

    def find_by_fingerprint(self, app_id: str, fingerprint: str) -> Finding | None:
        for f in self.findings.values():
            if f.app_id == app_id and f.fingerprint == fingerprint:
                return f
        return None

    def save_decision(self, d: Decision) -> Decision:
        self.decisions.append(d)
        return d

    def list_decisions(self, finding_id: str) -> list[Decision]:
        return [d for d in self.decisions if d.finding_id == finding_id]

    def save_report(self, r: Report) -> Report:
        self.reports[r.report_id] = r
        return r

    def get_report(self, report_id: str) -> Report | None:
        return self.reports.get(report_id)

    def list_reports(self, tenant_id: str) -> list[Report]:
        return [r for r in self.reports.values() if r.tenant_id == tenant_id]

    def get_budget(self, tenant_id: str, month: str) -> BudgetState:
        key = f"{tenant_id}#{month}"
        if key not in self.budgets:
            return BudgetState(
                tenant_id=tenant_id,
                month=month,
                hours_used=0.0,
                thresholds_hit=[],
                auto_stop=False,
            )
        return self.budgets[key]

    def save_budget(self, b: BudgetState) -> BudgetState:
        key = f"{b.tenant_id}#{b.month}"
        self.budgets[key] = b
        return b

    def append_audit(
        self,
        actor: str,
        action: str,
        object_type: str,
        object_id: str,
        result: str = "ok",
    ) -> AuditEvent:
        evt = AuditEvent(
            audit_id=f"audit-{uuid.uuid4().hex[:12]}",
            actor=actor,
            action=action,
            object_type=object_type,
            object_id=object_id,
            result=result,
            created_at=iso(utcnow()),
        )
        self.audits.append(evt)
        return evt

    def list_audit(
        self,
        object_type: str | None = None,
        object_id: str | None = None,
        limit: int = 100,
    ) -> list[AuditEvent]:
        res = list(self.audits)
        if object_type:
            res = [e for e in res if e.object_type == object_type]
        if object_id:
            res = [e for e in res if e.object_id == object_id]
        return res[:limit]


class FakeSecurityAgentClient:
    """Scriptable fake for AWS Security Agent API (section 11.6)."""

    def __init__(
        self,
        boto_client: Any = None,
        endpoint_url: str | None = None,
        region: str = "eu-west-3",
    ) -> None:
        self.spaces: dict[str, dict[str, Any]] = {}
        self.domains: dict[str, dict[str, Any]] = {}
        self.pentests: dict[str, dict[str, Any]] = {}
        self.jobs: dict[str, dict[str, Any]] = {}
        self.findings_by_job: dict[str, list[dict[str, Any]]] = {}
        self.job_outcomes: dict[str, str] = {}  # job_id -> "COMPLETED" | "FAILED"
        self.default_outcome = "COMPLETED"  # scénario par défaut des jobs
        self.task_hours = 1.5
        self.duration_seconds = 3600.0

    def set_job_outcome(self, job_id: str, status: str) -> None:
        """Script the final status of a job ('COMPLETED' or 'FAILED')."""
        self.job_outcomes[job_id] = status

    def create_agent_space(self, name: str, **kw: Any) -> dict[str, Any]:
        space_id = f"space-{uuid.uuid4().hex[:8]}"
        obj = {"agentSpaceId": space_id, "name": name, **kw}
        self.spaces[space_id] = obj
        return obj

    def create_target_domain(self, space_id: str, domain: str, **kw: Any) -> dict[str, Any]:
        domain_id = f"dom-{uuid.uuid4().hex[:8]}"
        obj = {"domainId": domain_id, "domain": domain, "spaceId": space_id, **kw}
        self.domains[domain_id] = obj
        return obj

    def verify_target_domain(self, space_id: str, domain_id: str) -> dict[str, Any]:
        return {"domainId": domain_id, "status": "VERIFIED"}

    def create_pentest(self, space_id: str, config: dict[str, Any]) -> dict[str, Any]:
        pentest_id = f"pt-{uuid.uuid4().hex[:8]}"
        obj = {"pentestId": pentest_id, "spaceId": space_id, "config": config}
        self.pentests[pentest_id] = obj
        return obj

    def start_pentest_job(self, pentest_id: str, **kw: Any) -> dict[str, Any]:
        job_id = f"job-{uuid.uuid4().hex[:8]}"
        job = {"jobId": job_id, "pentestId": pentest_id, "status": "RUNNING"}
        self.jobs[job_id] = job
        return {"jobId": job_id}

    def stop_pentest_job(self, job_id: str) -> dict[str, Any]:
        if job_id in self.jobs:
            self.jobs[job_id]["status"] = "STOPPED"
        return {"jobId": job_id, "status": "STOPPED"}

    def batch_get_pentest_jobs(self, job_ids: list[str]) -> list[dict[str, Any]]:
        result = []
        for jid in job_ids:
            job = self.jobs.get(jid, {})
            status = job.get("status", "RUNNING")
            if status == "RUNNING":
                # scénario scripté : bascule dans l'état final au premier poll
                status = self.job_outcomes.get(jid, self.default_outcome)
                if jid in self.jobs:
                    self.jobs[jid]["status"] = status
            result.append(
                {
                    "jobId": jid,
                    "status": status,
                    "taskHours": self.task_hours,
                    "durationSeconds": self.duration_seconds,
                }
            )
        return result

    def list_pentests(self, space_id: str) -> list[dict[str, Any]]:
        return [p for p in self.pentests.values() if p.get("spaceId") == space_id]

    def list_findings(self, job_id: str) -> list[dict[str, Any]]:
        return self.findings_by_job.get(job_id, [])

    def seed_finding(
        self,
        job_id: str,
        *,
        severity: str,
        confidence: str,
        risk_type: str,
        entry_point: str,
        parameter: str | None = None,
        title: str = "Test Finding",
        description: str = "Detailed description",
    ) -> dict[str, Any]:
        f = {
            "findingId": f"sa-f-{uuid.uuid4().hex[:8]}",
            "title": title,
            "severity": severity,
            "confidence": confidence,
            "riskType": risk_type,
            "entryPoint": entry_point,
            "parameter": parameter,
            "description": description,
            "cvss": {"score": 7.5},
        }
        self.findings_by_job.setdefault(job_id, []).append(f)
        return f

    def update_finding(self, finding_id: str, **kw: Any) -> dict[str, Any]:
        return {"findingId": finding_id, "status": kw.get("status", "UPDATED")}

    def start_code_remediation(self, finding_id: str, **kw: Any) -> dict[str, Any]:
        return {
            "findingId": finding_id,
            "remediationPrUrl": f"https://github.com/rempart/demo/pull/{uuid.uuid4().hex[:4]}",
            "status": "IN_PROGRESS",
        }


class FakeModelClient:
    """Fake Bedrock / LLM client returning canned responses."""

    def __init__(self, canned_response: str = '{"status": "ok"}') -> None:
        self.canned_response = canned_response
        self.calls: list[dict[str, Any]] = []

    def invoke(self, prompt: str, **kwargs: Any) -> str:
        self.calls.append({"prompt": prompt, "kwargs": kwargs})
        return self.canned_response


class FakeGitHub:
    """In-memory GitHub client fake."""

    def __init__(self, token: str = "fake-token", api: str = "https://api.github.com") -> None:
        self.token = token
        self.api = api
        self.issues: list[dict[str, Any]] = []

    def create_issue(
        self,
        owner: str,
        repo: str,
        title: str,
        body: str,
        labels: list[str],
    ) -> dict[str, Any]:
        issue_number = len(self.issues) + 1
        url = f"https://github.com/{owner}/{repo}/issues/{issue_number}"
        issue = {
            "number": issue_number,
            "owner": owner,
            "repo": repo,
            "title": title,
            "body": body,
            "labels": labels,
            "state": "open",
            "html_url": url,
            "comments": [],
        }
        self.issues.append(issue)
        return {"html_url": url, "number": issue_number}

    def close_issue(self, owner: str, repo: str, number: int, comment: str) -> None:
        for it in self.issues:
            if it["owner"] == owner and it["repo"] == repo and it["number"] == number:
                it["state"] = "closed"
                it["comments"].append(comment)
                return


@dataclass
class FakeS3Object:
    key: str
    body: bytes
    content_type: str


class FakeS3:
    """In-memory S3 client fake for report uploads."""

    def __init__(self) -> None:
        self.objects: dict[str, FakeS3Object] = {}

    def put_object(
        self,
        Bucket: str,
        Key: str,
        Body: bytes | str,
        ContentType: str = "application/octet-stream",
        **kwargs: Any,
    ) -> dict[str, Any]:
        data = Body.encode("utf-8") if isinstance(Body, str) else Body
        self.objects[f"{Bucket}/{Key}"] = FakeS3Object(
            key=Key,
            body=data,
            content_type=ContentType,
        )
        return {"ETag": f'"{uuid.uuid4().hex}"'}

    def get_object(self, Bucket: str, Key: str) -> dict[str, Any]:
        obj = self.objects.get(f"{Bucket}/{Key}")
        if not obj:
            raise KeyError(f"Key not found: {Key}")
        return {"Body": obj.body, "ContentType": obj.content_type}
