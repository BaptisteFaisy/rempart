"""DynamoDB store with Decimal serialization and table routing."""

import uuid
from decimal import Decimal
from typing import Any

from boto3.dynamodb.conditions import Key

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


DEFAULT_RETENTION_MONTHS = 13
SECONDS_PER_DAY = 86_400
DAYS_PER_MONTH = 30.4375  # 365.25 / 12 : assez précis pour une rétention
EXPIRE_AT_ATTRIBUTE = "expire_at"


def ttl_epoch(created_at: str | None, retention_months: int = DEFAULT_RETENTION_MONTHS) -> int:
    """Instant (epoch secondes) où DynamoDB TTL doit supprimer l'élément.

    ENF-DATA-01 : conservation de 13 mois par défaut. Sans ``created_at``
    lisible, on part de maintenant — mieux vaut une date de péremption que
    pas du tout, sinon l'élément ne serait jamais purgé.
    """
    try:
        base = parse_iso(created_at) if created_at else utcnow()
    except ValueError:
        base = utcnow()
    return int(base.timestamp() + retention_months * DAYS_PER_MONTH * SECONDS_PER_DAY)


def contract_end_epoch(months: int = 1) -> int:
    """Échéance de suppression en fin de contrat : 30 jours (ENF-DATA-01)."""
    return int(utcnow().timestamp() + months * DAYS_PER_MONTH * SECONDS_PER_DAY)


def _with_ttl(entity: Any, retention_months: int) -> dict[str, Any]:
    """Sérialise une entité et lui ajoute l'attribut TTL attendu par DynamoDB.

    Un ``expire_at`` déjà présent n'est jamais écrasé : la suppression
    anticipée en fin de contrat doit rester possible.
    """
    item = _to_ddb(entity.to_item())
    if EXPIRE_AT_ATTRIBUTE not in item:
        item[EXPIRE_AT_ATTRIBUTE] = ttl_epoch(
            getattr(entity, "created_at", None), retention_months
        )
    return item


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

    def __init__(
        self,
        ddb_resource: Any = None,
        table_prefix: str = "rempart-",
        retention_months: int = DEFAULT_RETENTION_MONTHS,
    ) -> None:
        self._table_prefix = table_prefix
        self._ddb = ddb_resource
        # ENF-DATA-01 : durée de conservation, appliquée à chaque écriture.
        self._retention_months = retention_months

    def _get_resource(self) -> Any:
        if self._ddb is None:
            import boto3

            self._ddb = boto3.resource("dynamodb")
        return self._ddb

    def _table(self, name: str) -> Any:
        return self._get_resource().Table(f"{self._table_prefix}{name}")

    def _item(self, entity: Any) -> dict[str, Any]:
        """Sérialise une entité pour DynamoDB, avec son attribut TTL."""
        return _with_ttl(entity, self._retention_months)

    def _query_gsi(
        self,
        table: str,
        index: str,
        pk: str,
        pk_value: Any,
        sk: str | None = None,
        sk_value: Any = None,
    ) -> list[dict[str, Any]]:
        """Query a GSI by its (partition, optional sort) key and return raw items.

        Against real DynamoDB the key condition already narrows the read. The
        in-memory ``FakeDdbTable`` ignores the index and returns the whole
        table, so callers must keep their client-side filter afterwards: it is
        the authoritative filter and doubles as a no-op safety net in prod.
        """
        cond = Key(pk).eq(pk_value)
        if sk is not None:
            cond = cond & Key(sk).eq(sk_value)
        res = self._table(table).query(IndexName=index, KeyConditionExpression=cond)
        return res.get("Items", [])

    def save_tenant(self, t: Tenant) -> Tenant:
        self._table("tenants").put_item(Item=self._item(t))
        return t

    def get_tenant(self, tenant_id: str) -> Tenant | None:
        res = self._table("tenants").get_item(Key={"tenant_id": tenant_id})
        item = res.get("Item")
        return Tenant.from_item(_from_ddb(item)) if item else None

    def list_tenants(self) -> list[Tenant]:
        res = self._table("tenants").scan()
        return [Tenant.from_item(_from_ddb(it)) for it in res.get("Items", [])]

    def save_application(self, a: Application) -> Application:
        self._table("applications").put_item(Item=self._item(a))
        return a

    def get_application(self, app_id: str) -> Application | None:
        res = self._table("applications").get_item(Key={"app_id": app_id})
        item = res.get("Item")
        return Application.from_item(_from_ddb(item)) if item else None

    def list_applications(self, tenant_id: str | None = None) -> list[Application]:
        if tenant_id:
            items = self._query_gsi("applications", "tenant_id-index", "tenant_id", tenant_id)
            items = [it for it in items if it.get("tenant_id") == tenant_id]
        else:
            items = self._table("applications").scan().get("Items", [])
        return [Application.from_item(_from_ddb(it)) for it in items]

    def save_config(self, c: TestConfig) -> TestConfig:
        self._table("test-configs").put_item(Item=self._item(c))
        return c

    def list_configs(self, app_id: str) -> list[TestConfig]:
        items = self._query_gsi("test-configs", "app_id-index", "app_id", app_id)
        items = [it for it in items if it.get("app_id") == app_id]
        return [TestConfig.from_item(_from_ddb(it)) for it in items]

    def save_run(self, r: Run) -> Run:
        self._table("runs").put_item(Item=self._item(r))
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
        if tenant_id:
            items = self._query_gsi("runs", "tenant_id-index", "tenant_id", tenant_id)
        elif app_id:
            items = self._query_gsi("runs", "app_id-index", "app_id", app_id)
        else:
            items = self._table("runs").scan().get("Items", [])
        if tenant_id:
            items = [it for it in items if it.get("tenant_id") == tenant_id]
        if app_id:
            items = [it for it in items if it.get("app_id") == app_id]
        if status:
            items = [it for it in items if it.get("status") == status]
        return [Run.from_item(_from_ddb(it)) for it in items[:limit]]

    def save_finding(self, f: Finding) -> Finding:
        self._table("findings").put_item(Item=self._item(f))
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
        if tenant_id:
            items = self._query_gsi("findings", "tenant_id-index", "tenant_id", tenant_id)
        elif app_id:
            items = self._query_gsi("findings", "app_id-fingerprint-index", "app_id", app_id)
        else:
            items = self._table("findings").scan().get("Items", [])
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
        items = self._query_gsi(
            "findings",
            "app_id-fingerprint-index",
            "app_id",
            app_id,
            "fingerprint",
            fingerprint,
        )
        for it in items:
            if it.get("app_id") == app_id and it.get("fingerprint") == fingerprint:
                return Finding.from_item(_from_ddb(it))
        return None

    def save_decision(self, d: Decision) -> Decision:
        self._table("decisions").put_item(Item=self._item(d))
        return d

    def list_decisions(self, finding_id: str) -> list[Decision]:
        items = self._query_gsi("decisions", "finding_id-index", "finding_id", finding_id)
        items = [it for it in items if it.get("finding_id") == finding_id]
        return [Decision.from_item(_from_ddb(it)) for it in items]

    def save_report(self, r: Report) -> Report:
        self._table("reports").put_item(Item=self._item(r))
        return r

    def get_report(self, report_id: str) -> Report | None:
        res = self._table("reports").get_item(Key={"report_id": report_id})
        item = res.get("Item")
        return Report.from_item(_from_ddb(item)) if item else None

    def list_reports(self, tenant_id: str) -> list[Report]:
        items = self._query_gsi("reports", "tenant_id-index", "tenant_id", tenant_id)
        items = [it for it in items if it.get("tenant_id") == tenant_id]
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
        item.setdefault(EXPIRE_AT_ATTRIBUTE, ttl_epoch(f"{b.month}-01T00:00:00Z",
                                                       self._retention_months))
        self._table("budget").put_item(Item=_to_ddb(item))
        return b

    def set_expire_at(self, table: str, key: dict[str, Any], epoch: int) -> None:
        """Pose une échéance de purge explicite (fin de contrat : 30 jours).

        Les écritures métier (`save_*`) recalculent toujours `expire_at` à
        13 mois ; la suppression anticipée exigée par ENF-DATA-01 passe par ici.
        """
        self._table(table).update_item(
            Key=key,
            UpdateExpression=f"SET #{EXPIRE_AT_ATTRIBUTE} = :ttl",
            ExpressionAttributeNames={f"#{EXPIRE_AT_ATTRIBUTE}": EXPIRE_AT_ATTRIBUTE},
            ExpressionAttributeValues={":ttl": epoch},
        )

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
        self._table("audit").put_item(Item=self._item(evt))
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
        if object_id:
            items = self._query_gsi("audit", "object_id-index", "object_id", object_id)
        else:
            items = self._table("audit").scan().get("Items", [])
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
