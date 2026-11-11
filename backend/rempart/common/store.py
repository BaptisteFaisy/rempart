"""DynamoDB store with Decimal serialization and table routing."""

import uuid
from decimal import Decimal
from typing import Any

from .models import (
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
from .timeutil import iso, parse_iso, utcnow


def _to_ddb(val: Any) -> Any:
    if isinstance(val, float):
        return Decimal(str(val))
    if isinstance(val, dict):
        return {k: _to_ddb(v) for k, v in val.items()}
    if isinstance(val, list):
        return [_to_ddb(v) for v in val]
    return val


def _from_ddb(val: Any) -> Any:
    if isinstance(val, Decimal):
        return float(val) if ("." in str(val) or "e" in str(val).lower()) else int(val)
    if isinstance(val, dict):
        return {k: _from_ddb(v) for k, v in val.items()}
    if isinstance(val, list):
        return [_from_ddb(v) for v in val]
    return val


def audit_in_range(created_at: str, since: str | None, until: str | None) -> bool:
    """Return True when ``created_at`` falls inside the inclusive [since, until] window.

    Shared by ``Store`` and ``FakeStore`` so both implementations filter the
    audit journal exactly the same way (EF-ADM-02).
    """
    if not since and not until:
        return True
    try:
        ts = parse_iso(created_at)
        return not ((since and ts < parse_iso(since)) or (until and ts > parse_iso(until)))
    except ValueError:
        return False


class Store:
    """DynamoDB-backed persistence layer for Rempart."""

    def __init__(self, ddb_resource: Any = None, table_prefix: str = "rempart-") -> None:
        self._table_prefix = table_prefix
        self._ddb = ddb_resource

    def _get_resource(self) -> Any:
        if self._ddb is None:
            import boto3

            self._ddb = boto3.resource("dynamodb")
        return self._ddb

    def _table(self, name: str) -> Any:
        return self._get_resource().Table(f"{self._table_prefix}{name}")

    def save_tenant(self, t: Tenant) -> Tenant:
        self._table("tenants").put_item(Item=_to_ddb(t.to_item()))
        return t

    def get_tenant(self, tenant_id: str) -> Tenant | None:
        res = self._table("tenants").get_item(Key={"tenant_id": tenant_id})
        item = res.get("Item")
        return Tenant.from_item(_from_ddb(item)) if item else None

    def list_tenants(self) -> list[Tenant]:
        res = self._table("tenants").scan()
        return [Tenant.from_item(_from_ddb(it)) for it in res.get("Items", [])]

    def save_application(self, a: Application) -> Application:
        self._table("applications").put_item(Item=_to_ddb(a.to_item()))
        return a

    def get_application(self, app_id: str) -> Application | None:
        res = self._table("applications").get_item(Key={"app_id": app_id})
        item = res.get("Item")
        return Application.from_item(_from_ddb(item)) if item else None

    def list_applications(self, tenant_id: str | None = None) -> list[Application]:
        res = self._table("applications").scan()
        items = res.get("Items", [])
        if tenant_id:
            items = [it for it in items if it.get("tenant_id") == tenant_id]
        return [Application.from_item(_from_ddb(it)) for it in items]

    def save_config(self, c: TestConfig) -> TestConfig:
        self._table("test-configs").put_item(Item=_to_ddb(c.to_item()))
        return c

    def list_configs(self, app_id: str) -> list[TestConfig]:
        res = self._table("test-configs").scan()
        items = [it for it in res.get("Items", []) if it.get("app_id") == app_id]
        return [TestConfig.from_item(_from_ddb(it)) for it in items]

    def save_run(self, r: Run) -> Run:
        self._table("runs").put_item(Item=_to_ddb(r.to_item()))
        return r

    def get_run(self, run_id: str) -> Run | None:
        res = self._table("runs").get_item(Key={"run_id": run_id})
        item = res.get("Item")
        return Run.from_item(_from_ddb(item)) if item else None

    def list_runs(
        self,
        app_id: str | None = None,
        tenant_id: str | None = None,
        status: str | None = None,
        limit: int = 50,
    ) -> list[Run]:
        res = self._table("runs").scan()
        items = res.get("Items", [])
        if app_id:
            items = [it for it in items if it.get("app_id") == app_id]
        if tenant_id:
            items = [it for it in items if it.get("tenant_id") == tenant_id]
        if status:
            items = [it for it in items if it.get("status") == status]
        return [Run.from_item(_from_ddb(it)) for it in items[:limit]]

    def save_finding(self, f: Finding) -> Finding:
        self._table("findings").put_item(Item=_to_ddb(f.to_item()))
        return f

    def get_finding(self, finding_id: str) -> Finding | None:
        res = self._table("findings").get_item(Key={"finding_id": finding_id})
        item = res.get("Item")
        return Finding.from_item(_from_ddb(item)) if item else None

    def list_findings(
        self,
        tenant_id: str | None = None,
        app_id: str | None = None,
        status: str | None = None,
        priority: str | None = None,
        limit: int = 100,
    ) -> list[Finding]:
        res = self._table("findings").scan()
        items = res.get("Items", [])
        if tenant_id:
            items = [it for it in items if it.get("tenant_id") == tenant_id]
        if app_id:
            items = [it for it in items if it.get("app_id") == app_id]
        if status:
            items = [it for it in items if it.get("status") == status]
        if priority:
            items = [it for it in items if it.get("priority") == priority]
        return [Finding.from_item(_from_ddb(it)) for it in items[:limit]]

    def find_by_fingerprint(self, app_id: str, fingerprint: str) -> Finding | None:
        res = self._table("findings").scan()
        for it in res.get("Items", []):
            if it.get("app_id") == app_id and it.get("fingerprint") == fingerprint:
                return Finding.from_item(_from_ddb(it))
        return None

    def save_decision(self, d: Decision) -> Decision:
        self._table("decisions").put_item(Item=_to_ddb(d.to_item()))
        return d

    def list_decisions(self, finding_id: str) -> list[Decision]:
        res = self._table("decisions").scan()
        items = [it for it in res.get("Items", []) if it.get("finding_id") == finding_id]
        return [Decision.from_item(_from_ddb(it)) for it in items]

    def save_report(self, r: Report) -> Report:
        self._table("reports").put_item(Item=_to_ddb(r.to_item()))
        return r

    def get_report(self, report_id: str) -> Report | None:
        res = self._table("reports").get_item(Key={"report_id": report_id})
        item = res.get("Item")
        return Report.from_item(_from_ddb(item)) if item else None

    def list_reports(self, tenant_id: str) -> list[Report]:
        res = self._table("reports").scan()
        items = [it for it in res.get("Items", []) if it.get("tenant_id") == tenant_id]
        return [Report.from_item(_from_ddb(it)) for it in items]

    def get_budget(self, tenant_id: str, month: str) -> BudgetState:
        res = self._table("budget").get_item(Key={"pk": f"{tenant_id}#{month}"})
        item = res.get("Item")
        if not item:
            return BudgetState(
                tenant_id=tenant_id,
                month=month,
                hours_used=0.0,
                thresholds_hit=[],
                auto_stop=False,
            )
        return BudgetState.from_item(_from_ddb(item))

    def save_budget(self, b: BudgetState) -> BudgetState:
        item = b.to_item()
        item["pk"] = f"{b.tenant_id}#{b.month}"
        self._table("budget").put_item(Item=_to_ddb(item))
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
        self._table("audit").put_item(Item=_to_ddb(evt.to_item()))
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
        res = self._table("audit").scan()
        items = res.get("Items", [])
        if object_type:
            items = [it for it in items if it.get("object_type") == object_type]
        if object_id:
            items = [it for it in items if it.get("object_id") == object_id]
        if actor:
            items = [it for it in items if it.get("actor") == actor]
        if action:
            items = [it for it in items if it.get("action") == action]
        if since or until:
            items = [it for it in items if audit_in_range(it.get("created_at", ""), since, until)]
        return [AuditEvent.from_item(_from_ddb(it)) for it in items[:limit]]
