"""Fakes de persistance : table DynamoDB minimale et Store en mémoire."""

import uuid
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
from rempart.common.store import DEFAULT_RETENTION_MONTHS, audit_in_range
from rempart.common.timeutil import iso, utcnow


def _parse_set_expression(expression: str) -> list[tuple[str, str]]:
    """Extrait les paires (nom, valeur) d'une expression ``SET #a = :b, …``."""
    if not expression.upper().startswith("SET"):
        return []
    pairs = []
    for part in expression[3:].split(","):
        if "=" not in part:
            continue
        name, value = (side.strip() for side in part.split("=", 1))
        pairs.append((name, value))
    return pairs


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

    def update_item(self, Key: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
        """Applique un ``SET`` simple sur l'élément trouvé (suffisant pour le TTL).

        Ne simule pas tout DynamoDB : gère ``ExpressionAttributeNames`` +
        ``ExpressionAttributeValues`` avec une expression ``SET #n = :v``.
        """
        names = kwargs.get("ExpressionAttributeNames") or {}
        values = kwargs.get("ExpressionAttributeValues") or {}
        updates = {names.get(k, k.lstrip("#")): values.get(v, v)
                   for k, v in _parse_set_expression(kwargs.get("UpdateExpression", ""))}
        for it in self.items:
            if all(it.get(k) == v for k, v in Key.items()):
                it.update(updates)
                return {}
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

    def __init__(
        self,
        ddb_resource: Any = None,
        table_prefix: str = "rempart-",
        retention_months: int = DEFAULT_RETENTION_MONTHS,
    ) -> None:
        self.retention_months = retention_months
        self.tenants: dict[str, Tenant] = {}
        self.applications: dict[str, Application] = {}
        self.configs: dict[str, TestConfig] = {}
        self.runs: dict[str, Run] = {}
        self.findings: dict[str, Finding] = {}
        self.decisions: list[Decision] = []
        self.reports: dict[str, Report] = {}
        self.budgets: dict[str, BudgetState] = {}
        self.audits: list[AuditEvent] = []
        self.expiries: dict[tuple[str, tuple], int] = {}

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

    def set_expire_at(self, table: str, key: dict[str, Any], epoch: int) -> None:
        """Même contrat que ``Store.set_expire_at`` (purge anticipée).

        Le fake n'a pas de moteur TTL : il enregistre l'échéance demandée dans
        ``self.expiries`` pour qu'un test puisse la vérifier.
        """
        self.expiries[(table, tuple(sorted(key.items())))] = epoch

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
        actor: str | None = None,
        action: str | None = None,
        since: str | None = None,
        until: str | None = None,
        limit: int = 100,
    ) -> list[AuditEvent]:
        res = list(self.audits)
        if object_type:
            res = [e for e in res if e.object_type == object_type]
        if object_id:
            res = [e for e in res if e.object_id == object_id]
        if actor:
            res = [e for e in res if e.actor == actor]
        if action:
            res = [e for e in res if e.action == action]
        if since or until:
            res = [e for e in res if audit_in_range(e.created_at, since, until)]
        return res[:limit]
