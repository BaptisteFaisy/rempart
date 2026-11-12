"""Échelle : isolation par client et coût réel des lectures (piste #41).

50 clients × 20 applications × 500 failles : le test mesure l'**exactitude**
(rien d'un autre client dans les KPI, listes et journal d'audit) et le **coût**
(éléments parcourus proportionnels au client, comptés par un faux DynamoDB qui
respecte les conditions de clé), puis la conformité des GSI déclarés/utilisés.
"""

import ast
import re
from pathlib import Path
from typing import Any

import pytest

from rempart.api.routes.audit import belongs_to, tenant_object_ids
from rempart.common.models import (
    PRIORITIES,
    Application,
    Decision,
    Finding,
    Report,
    Run,
    Tenant,
    TestConfig,
)
from rempart.common.store import Store
from rempart.reports.metrics import compute_kpis
from tests.fakes import FakeDdbResource, FakeDdbTable, FakeStore

REPO_ROOT = Path(__file__).resolve().parents[3]
STORE_PATH = REPO_ROOT / "backend" / "rempart" / "common" / "store.py"
STORAGE_PATH = REPO_ROOT / "iac" / "control-plane" / "stacks" / "storage.py"

N_TENANTS = 50
APPS_PER_TENANT = 20
FINDINGS_PER_APP = 25  # 500 failles par client
RUNS_PER_TENANT = 12
PERIOD = "2026-11"

CREATED_AT = "2026-11-05T10:00:00Z"
CLOSED_AT = "2026-11-20T10:00:00Z"
DUE_AT = "2026-11-25T10:00:00Z"
STARTED_AT = "2026-11-03T08:00:00Z"


# --- Generators: deterministic data, identical structure for every tenant. ---
def _tenant(tenant_id: str) -> Tenant:
    return Tenant(
        tenant_id=tenant_id, name=f"Client {tenant_id}", aws_account_id="123456789012",
        region="eu-west-3", role_arn="arn:aws:iam::123456789012:role/rempart",
        external_id="ext-1", plan="continu", contacts=[{"email": f"ops@{tenant_id}.example"}],
        monthly_budget_hours=30.0, mandate_status="valid", created_at="2026-01-01T00:00:00Z",
    )


def _app_id(tenant_id: str, app_index: int) -> str:
    return f"app-{tenant_id}-{app_index:02d}"


def _application(tenant_id: str, app_index: int) -> Application:
    return Application(
        app_id=_app_id(tenant_id, app_index), tenant_id=tenant_id, name=f"App {app_index}",
        criticality="high", internet_exposed=True, data_types=["personal"],
        environment="staging" if app_index % 2 == 0 else "production", agent_space_id="space-1",
        domains=[f"app{app_index}.example.com"], repositories=["acme/app"], team="Core",
        ticket_channel="#app", context={}, created_at="2026-01-01T00:00:00Z",
    )


def _finding(tenant_id: str, app_index: int, finding_index: int) -> Finding:
    closed = finding_index % 2 == 0
    return Finding(
        finding_id=f"f-{tenant_id}-{app_index:02d}-{finding_index:02d}",
        app_id=_app_id(tenant_id, app_index), tenant_id=tenant_id,
        run_id=f"run-{tenant_id}-{app_index % RUNS_PER_TENANT:02d}",
        fingerprint=f"fp-{tenant_id}-{app_index:02d}-{finding_index:02d}",
        title=f"Faille {finding_index}", risk_type="IDOR", severity="High",
        confidence="High", priority=PRIORITIES[finding_index % 4],
        status="closed" if closed else "new", due_at=DUE_AT, ticket_url=None,
        remediation_pr_url=None, evidence={"param": "id"}, cvss={"score": 8.5},
        created_at=CREATED_AT, updated_at=CREATED_AT,
        closed_at=CLOSED_AT if closed else None, closed_by_run_id=None,
    )


def _run(tenant_id: str, run_index: int) -> Run:
    return Run(
        run_id=f"run-{tenant_id}-{run_index:02d}", config_id="cfg-1",
        app_id=_app_id(tenant_id, run_index % APPS_PER_TENANT), tenant_id=tenant_id,
        trigger="cicd", commit_from="aaaaaaa", commit_to="bbbbbbb", scope_decision="diff",
        status="completed", started_at=STARTED_AT, ended_at="2026-11-03T09:00:00Z",
        duration_s=3600.0 * (run_index + 1), task_hours=1.0, cost_usd=3.0,
    )


def _seed_tenant(store: Any, tenant_index: int) -> str:
    """Populate one tenant (20 applications, 500 findings, 12 runs)."""
    tenant_id = f"t-{tenant_index:02d}"
    store.save_tenant(_tenant(tenant_id))
    for app_index in range(APPS_PER_TENANT):
        store.save_application(_application(tenant_id, app_index))
        for finding_index in range(FINDINGS_PER_APP):
            store.save_finding(_finding(tenant_id, app_index, finding_index))
    for run_index in range(RUNS_PER_TENANT):
        store.save_run(_run(tenant_id, run_index))
    return tenant_id


def _seed_fleet(store: Any) -> None:
    """Populate the whole fleet: 50 tenants with the same structure."""
    for tenant_index in range(N_TENANTS):
        _seed_tenant(store, tenant_index)


def _seed_extras(store: Store) -> None:
    """2 configs, 13 rapports and 2 decisions of the client ``t-00``."""
    for i in range(2):
        store.save_config(TestConfig(
            config_id=f"cfg-{i}", app_id="app-t-00-00", sa_pentest_id="sa-1",
            kind="web", scope={}, risk_types=["IDOR"], blocking_threshold="P1",
            schedule=None,
        ))
    for month in range(13):
        store.save_report(Report(
            report_id=f"rep-{month}", tenant_id="t-00", period=PERIOD,
            s3_key=f"reports/{month}.pdf", kpis={}, created_at=CREATED_AT,
        ))
    for i in range(2):
        store.save_decision(Decision(
            decision_id=f"dec-{i}", finding_id="f-t-00-00-00", author_type="human",
            author="analyst", action="confirm", justification="ok", created_at=CREATED_AT,
        ))


# --- A DynamoDB fake that behaves like the real one and counts what it reads. ---
def _key_conditions(expr: Any) -> list[tuple[str, Any]]:
    """(attribute, value) pairs of a boto3 key condition: ``Key(a).eq(b)``,
    optionally conjoined (``& Key(c).eq(d)``) — the only shapes store.py emits.
    """
    if expr is None:
        return []
    data = expr.get_expression()
    parts = data["values"] if data["operator"] == "AND" else [expr]
    conditions = []
    for part in parts:
        key, value = part.get_expression()["values"]
        conditions.append((key.name, value))
    return conditions


class MeasuringDdbTable(FakeDdbTable):
    """Fake table honouring the GSI key condition and counting items read.

    ``scan`` returns and counts the whole table; ``query`` applies the key
    condition (as DynamoDB does on a GSI) and counts only the items returned.
    """

    PAGE_SIZE: int | None = None  # None = no pagination (the fake has no 1 MB cap)

    def __init__(self, name: str) -> None:
        super().__init__(name)
        self.reset_counters()

    def reset_counters(self) -> None:
        self.scan_calls = 0
        self.query_calls = 0
        self.items_scanned = 0
        self.items_queried = 0

    def _matching(self, kwargs: dict[str, Any]) -> list[dict[str, Any]]:
        """Items of the table matching the key condition of ``kwargs``."""
        conditions = _key_conditions(kwargs.get("KeyConditionExpression"))
        return [it for it in self.items if all(it.get(a) == v for a, v in conditions)]

    def scan(self, **kwargs: Any) -> dict[str, Any]:
        self.scan_calls += 1
        self.items_scanned += len(self.items)
        return super().scan(**kwargs)

    def query(self, **kwargs: Any) -> dict[str, Any]:
        self.query_calls += 1
        matched = self._matching(kwargs)
        if self.PAGE_SIZE is None:
            self.items_queried += len(matched)
            return {"Items": [dict(it) for it in matched]}
        start = int(kwargs.get("ExclusiveStartKey", {}).get("offset", 0))
        page = matched[start : start + self.PAGE_SIZE]
        self.items_queried += len(page)
        res: dict[str, Any] = {"Items": [dict(it) for it in page]}
        if start + self.PAGE_SIZE < len(matched):
            res["LastEvaluatedKey"] = {"offset": start + self.PAGE_SIZE}
        return res


class PagedDdbTable(MeasuringDdbTable):
    """Same table, capped at ``PAGE_SIZE`` items per answer (the real 1 MB cap)."""

    PAGE_SIZE = 500


class MeasuringDdbResource(FakeDdbResource):
    """Fake boto3 resource handing out counting tables."""

    table_class: type[MeasuringDdbTable] = MeasuringDdbTable

    def Table(self, name: str) -> MeasuringDdbTable:  # noqa: N802 (boto3 API)
        if name not in self.tables:
            self.tables[name] = self.table_class(name)
        return self.tables[name]


class PagedDdbResource(MeasuringDdbResource):
    """Fake boto3 resource handing out paged counting tables."""

    table_class = PagedDdbTable


# --- Fixtures ---
@pytest.fixture(scope="module")
def fleet_store() -> FakeStore:
    """In-memory store holding the whole fleet (50 clients)."""
    store = FakeStore()
    _seed_fleet(store)
    return store


@pytest.fixture(scope="module")
def solo_store() -> FakeStore:
    """Same client, alone in its own store: the isolation oracle."""
    store = FakeStore()
    _seed_tenant(store, 0)
    return store


@pytest.fixture(scope="module")
def measured_store() -> tuple[Store, MeasuringDdbResource]:
    """Real ``Store`` on top of a counting DynamoDB fake."""
    ddb = MeasuringDdbResource()
    store = Store(ddb_resource=ddb, table_prefix="scale-")
    _seed_fleet(store)
    return store, ddb


# --- (a) Accuracy: a tenant's readings contain nothing from another tenant. ---
def test_kpis_of_a_tenant_match_the_ones_of_a_lone_tenant(fleet_store, solo_store):
    """Every tenant of the fleet gets exactly the KPIs it would get alone."""
    reference = compute_kpis(solo_store, tenant_id="t-00", period=PERIOD)
    for tenant_index in range(N_TENANTS):
        tenant_id = f"t-{tenant_index:02d}"
        kpis = compute_kpis(fleet_store, tenant_id=tenant_id, period=PERIOD)
        assert kpis == {**reference, "tenant_id": tenant_id}


def test_kpi_values_of_one_tenant_are_exact(solo_store):
    """Pin the computed figures: 500 findings, 260 closed, 240 open, 12 runs."""
    kpis = compute_kpis(solo_store, tenant_id="t-00", period=PERIOD)
    assert kpis["findings_closed"] == 260
    assert kpis["findings_open_total"] == 240
    assert kpis["findings_open_by_priority"] == {"P1": 0, "P2": 120, "P3": 0, "P4": 120}
    assert kpis["findings_new_by_priority"] == {"P1": 140, "P2": 120, "P3": 120, "P4": 120}
    assert kpis["tests_total"] == 12
    assert kpis["tests_blocked"] == 0
    assert kpis["coverage"] == 0.6
    assert kpis["sla_compliance"] == 1.0
    assert kpis["reopen_rate"] == 0.0
    assert kpis["critical_blocked_before_prod"] == 0.5
    assert kpis["delivery_to_result_hours"] == 6.5
    assert kpis["mean_time_to_fix_days_by_priority"] == {
        "P1": 15.0, "P2": 0.0, "P3": 15.0, "P4": 0.0,
    }
    assert kpis["task_hours_used"] == 12.0
    assert kpis["cost_usd"] == 36.0
    assert kpis["risk_level"] == "moderate"


def test_listings_of_a_tenant_contain_no_other_tenant(fleet_store):
    """The filtered listings return the tenant's rows only."""
    findings = fleet_store.list_findings(tenant_id="t-07", limit=1000)
    assert len(findings) == 500
    assert {f.tenant_id for f in findings} == {"t-07"}

    apps = fleet_store.list_applications(tenant_id="t-07")
    assert len(apps) == 20
    assert {a.tenant_id for a in apps} == {"t-07"}

    runs = fleet_store.list_runs(tenant_id="t-07", limit=1000)
    assert len(runs) == 12
    assert {r.tenant_id for r in runs} == {"t-07"}


def test_audit_journal_of_a_tenant_shows_no_other_tenant(fleet_store):
    """ENF-SEC-01 : the tenant-scoped journal only shows the tenant's objects.

    ``AuditEvent`` carries no ``tenant_id``: attribution is rebuilt from the
    objects owned by the tenant (``api/routes/audit.py``).
    """
    seeded = [("finding", "f-t-00-00-00"), ("application", "app-t-00-00"),
              ("budget", "t-00#2026-11"), ("finding", "f-t-01-00-00"),
              ("finding", "f-inconnu")]  # object of no tenant: invisible everywhere
    for object_type, object_id in seeded:
        fleet_store.append_audit("system", "event", object_type, object_id)

    journal = fleet_store.list_audit(limit=100)
    scoped = {
        tenant: {e.object_id for e in journal
                 if belongs_to(e, tenant, tenant_object_ids(fleet_store, tenant))}
        for tenant in ("t-00", "t-01")
    }

    assert scoped["t-00"] == {"f-t-00-00-00", "app-t-00-00", "t-00#2026-11"}
    assert scoped["t-01"] == {"f-t-01-00-00"}
    assert "f-inconnu" not in scoped["t-00"] | scoped["t-01"]


# --- (b) Cost: a tenant-scoped read must not walk the whole fleet. ---
def test_tenant_scoped_reads_never_scan_the_fleet(measured_store):
    """KPI of one client: indexed reads, zero scan, 500 findings read."""
    store, ddb = measured_store
    findings_table = ddb.Table("scale-findings")
    runs_table = ddb.Table("scale-runs")
    apps_table = ddb.Table("scale-applications")
    for table in (findings_table, runs_table, apps_table):
        table.reset_counters()

    kpis = compute_kpis(store, tenant_id="t-00", period=PERIOD)

    assert kpis["findings_closed"] == 260
    assert findings_table.scan_calls == 0
    assert findings_table.items_scanned == 0
    assert findings_table.query_calls == 1
    assert findings_table.items_queried == 500
    assert runs_table.scan_calls == 0
    assert runs_table.items_queried == 12
    assert apps_table.scan_calls == 0
    assert apps_table.items_queried == 20


def test_every_indexed_read_costs_its_own_result(measured_store):
    """configs / reports / decisions: one query per object, never a scan."""
    store, ddb = measured_store
    _seed_extras(store)
    cases = [("scale-test-configs", lambda: store.list_configs("app-t-00-00"), 2),
             ("scale-reports", lambda: store.list_reports("t-00"), 13),
             ("scale-decisions", lambda: store.list_decisions("f-t-00-00-00"), 2)]

    for table_name, read, expected in cases:
        table = ddb.Table(table_name)
        table.reset_counters()

        assert len(read()) == expected
        assert table.scan_calls == 0
        assert table.items_queried == expected


def test_fleet_read_still_costs_the_whole_table(measured_store):
    """Fleet-wide read (no tenant): a scan remains, and it is expensive."""
    store, ddb = measured_store
    findings_table = ddb.Table("scale-findings")
    findings_table.reset_counters()

    everything = store.list_findings(limit=25_000)

    assert len(everything) == N_TENANTS * APPS_PER_TENANT * FINDINGS_PER_APP
    assert findings_table.scan_calls == 1
    assert findings_table.items_scanned == 25_000


def test_scoped_read_is_fifty_times_cheaper_than_the_fleet(measured_store):
    """The regression guard: 500 items read for a tenant, 25 000 for the fleet."""
    store, ddb = measured_store
    findings_table = ddb.Table("scale-findings")

    findings_table.reset_counters()
    store.list_findings(tenant_id="t-00", limit=1000)
    scoped_items = findings_table.items_queried

    findings_table.reset_counters()
    store.list_findings(limit=25_000)
    fleet_items = findings_table.items_scanned

    assert scoped_items == 500
    assert fleet_items == 25_000
    assert scoped_items * N_TENANTS == fleet_items


def test_real_store_and_fake_store_agree_on_the_kpis(measured_store, fleet_store):
    """The indexed path returns exactly what the in-memory path returns."""
    store, _ddb = measured_store
    for tenant_index in (0, 17, 49):
        tenant_id = f"t-{tenant_index:02d}"
        assert compute_kpis(store, tenant_id=tenant_id, period=PERIOD) == compute_kpis(
            fleet_store, tenant_id=tenant_id, period=PERIOD
        )


def test_finding_lookup_by_fingerprint_is_indexed(measured_store):
    """Fingerprint lookup hits the (app_id, fingerprint) GSI, no scan."""
    store, ddb = measured_store
    findings_table = ddb.Table("scale-findings")
    findings_table.reset_counters()

    found = store.find_by_fingerprint("app-t-03-04", "fp-t-03-04-07")

    assert found is not None
    assert found.finding_id == "f-t-03-04-07"
    assert findings_table.scan_calls == 0
    assert findings_table.query_calls == 1
    assert findings_table.items_queried == 1


def test_audit_lookup_by_object_is_indexed(measured_store):
    """Deadline reminders read the journal by object: indexed, no scan."""
    store, ddb = measured_store
    audit_table = ddb.Table("scale-audit")
    store.append_audit("system", "deadline_reminder", "finding", "f-t-03-04-07")
    store.append_audit("system", "finding_created", "finding", "f-t-03-04-07")
    store.append_audit("system", "finding_created", "finding", "f-t-03-04-08")
    audit_table.reset_counters()

    events = store.list_audit(
        object_type="finding", object_id="f-t-03-04-07", action="deadline_reminder"
    )

    assert len(events) == 1
    assert events[0].action == "deadline_reminder"
    assert audit_table.scan_calls == 0
    assert audit_table.query_calls == 1
    assert audit_table.items_queried == 2


def test_audit_period_read_remains_a_scan(measured_store):
    """Fleet journal read (no object): a scan remains — documented as such."""
    store, ddb = measured_store
    audit_table = ddb.Table("scale-audit")
    audit_table.reset_counters()

    store.list_audit(limit=10)

    assert audit_table.scan_calls == 1
    assert audit_table.query_calls == 0


def test_tenant_read_survives_the_one_megabyte_page_cap():
    """A client with 2 000 findings is read whole, page after page."""
    ddb = PagedDdbResource()
    store = Store(ddb_resource=ddb, table_prefix="paged-")
    for finding_index in range(2_000):
        store.save_finding(_finding("t-99", finding_index % APPS_PER_TENANT, finding_index))
    findings_table = ddb.Table("paged-findings")
    findings_table.reset_counters()

    findings = store.list_findings(tenant_id="t-99", limit=2_000)

    assert len(findings) == 2_000
    assert {f.tenant_id for f in findings} == {"t-99"}
    assert findings_table.scan_calls == 0
    assert findings_table.query_calls == 4
    assert findings_table.items_queried == 2_000


# --- (c) The GSI used by store.py must be the one declared in storage.py. ---
def _declared_gsis() -> dict[str, dict[str, tuple[str, str | None]]]:
    """{table: {index: (partition key, sort key)}} read from ``TABLE_SPECS``."""
    tree = ast.parse(STORAGE_PATH.read_text(encoding="utf-8"))
    node = next(n for n in tree.body if isinstance(n, ast.AnnAssign)
                and getattr(n.target, "id", "") == "TABLE_SPECS")
    specs = ast.literal_eval(node.value)
    return {name: {i: (pk, sk) for i, pk, sk in g} for _c, name, _pk, g in specs}


def _used_gsis() -> list[tuple[str, str, str, str | None]]:
    """(table, index, partition key, sort key) of every ``_query_gsi`` call."""
    src = STORE_PATH.read_text(encoding="utf-8")
    calls = re.findall(
        r'_query_gsi\(\s*"([^"]+)",\s*"([^"]+)",\s*"([^"]+)"(?:\s*,\s*[^,()]+,\s*"([^"]+)")?',
        src,
    )
    return [(table, index, pk, sk or None) for table, index, pk, sk in calls]


def test_declared_gsis_match_the_queries():
    """Every GSI queried by store.py is declared in storage.py, with its keys.

    A divergent name fails in production with a ``ValidationException``; the
    in-memory fake ignores the index, so it would never catch it.
    """
    declared = _declared_gsis()
    used = _used_gsis()
    assert used, "store.py n'appelle plus _query_gsi : ce test est à revoir"

    for table, index, pk, sk in used:
        assert index in declared.get(table, {}), f"{table} : index {index!r} non déclaré"
        assert declared[table][index][0] == pk, f"{table}.{index} : clé de partition divergente"
        if sk is not None:
            assert declared[table][index][1] == sk, f"{table}.{index} : clé de tri divergente"
