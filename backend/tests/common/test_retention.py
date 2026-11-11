"""Rétention des données (ENF-DATA-01) : 13 mois par défaut, 30 jours en fin de contrat.

Le TTL de DynamoDB ne supprime un élément que si l'attribut `expire_at` existe
et contient un epoch. Configurer `time_to_live_attribute` dans le CDK sans
jamais écrire l'attribut ne purge rien : les failles (données sensibles)
s'accumuleraient indéfiniment. Ces tests verrouillent l'écriture réelle.
"""

from __future__ import annotations

from datetime import datetime, timezone

from rempart.common.models import Application, Decision, Finding, Report, Run, Tenant
from rempart.common.store import (
    DEFAULT_RETENTION_MONTHS,
    EXPIRE_AT_ATTRIBUTE,
    Store,
    contract_end_epoch,
    ttl_epoch,
)
from tests.fakes_store import FakeDdbResource


def _store(retention_months: int = DEFAULT_RETENTION_MONTHS) -> tuple[Store, FakeDdbResource]:
    resource = FakeDdbResource()
    return Store(ddb_resource=resource, retention_months=retention_months), resource


def _tenant() -> Tenant:
    return Tenant(
        tenant_id="t-1",
        name="Acme",
        aws_account_id="123456789012",
        region="eu-west-3",
        role_arn="arn",
        external_id="ext",
        plan="continu",
        contacts=[],
        monthly_budget_hours=40.0,
        mandate_status="valid",
        created_at="2026-10-01T00:00:00Z",
    )


def _finding(created_at: str = "2026-10-05T10:00:00Z") -> Finding:
    return Finding(
        finding_id="f-1",
        app_id="app-1",
        tenant_id="t-1",
        run_id="run-1",
        fingerprint="fp-1",
        title="IDOR",
        risk_type="IDOR",
        severity="Critical",
        confidence="High",
        priority="P1",
        status="confirmed",
        due_at=None,
        ticket_url=None,
        remediation_pr_url=None,
        evidence={},
        cvss={},
        created_at=created_at,
        updated_at=created_at,
        closed_at=None,
        closed_by_run_id=None,
    )


def test_ttl_epoch_is_thirteen_months_after_creation():
    epoch = ttl_epoch("2026-10-01T00:00:00Z", 13)
    moment = datetime.fromtimestamp(epoch, tz=timezone.utc)
    # 13 × 30,4375 jours après le 1er octobre 2026 → fin octobre 2027.
    assert (moment.year, moment.month) == (2027, 10)
    assert moment > datetime(2027, 9, 1, tzinfo=timezone.utc)


def test_ttl_epoch_falls_back_to_now_on_unreadable_date():
    """Une date illisible ne doit pas produire un élément jamais purgé."""
    assert ttl_epoch("pas-une-date", 13) > 0
    assert ttl_epoch(None, 13) > 0


def _application() -> Application:
    return Application(
        app_id="app-1",
        tenant_id="t-1",
        name="Shop",
        criticality="high",
        internet_exposed=True,
        data_types=["personal"],
        environment="staging",
        agent_space_id="space-1",
        domains=["shop.example"],
        repositories=["demo/shop"],
        team="Core",
        ticket_channel="github",
        context={},
        created_at="2026-10-01T00:00:00Z",
    )


def _run() -> Run:
    return Run(
        run_id="run-1",
        config_id="cfg-1",
        app_id="app-1",
        tenant_id="t-1",
        trigger="cicd",
        commit_from="a",
        commit_to="b",
        scope_decision="full",
        status="completed",
        started_at="2026-10-05T09:00:00Z",
        ended_at="2026-10-05T10:00:00Z",
        duration_s=3600.0,
        task_hours=1.0,
        cost_usd=50.0,
    )


def _decision() -> Decision:
    return Decision(
        decision_id="d-1",
        finding_id="f-1",
        author_type="human",
        author="analyst",
        action="confirmed",
        justification="ok",
        created_at="2026-10-05T11:00:00Z",
    )


def _report() -> Report:
    return Report(
        report_id="rep-1",
        tenant_id="t-1",
        period="2026-10",
        s3_key="k",
        kpis={},
        created_at="2026-11-01T06:00:00Z",
    )


RETAINED_TABLES = ("tenants", "applications", "runs", "findings", "decisions", "reports")


def test_every_saved_entity_carries_an_expire_at():
    store, resource = _store()
    store.save_tenant(_tenant())
    store.save_application(_application())
    store.save_run(_run())
    store.save_finding(_finding())
    store.save_decision(_decision())
    store.save_report(_report())

    for table_name in RETAINED_TABLES:
        items = resource.Table(f"rempart-{table_name}").items
        assert items, f"aucun item écrit dans {table_name}"
        for item in items:
            assert EXPIRE_AT_ATTRIBUTE in item, f"{table_name} sans expire_at"
            assert isinstance(item[EXPIRE_AT_ATTRIBUTE], int)
            assert item[EXPIRE_AT_ATTRIBUTE] > 0


def test_retention_is_configurable_per_store():
    short, resource_short = _store(retention_months=1)
    long_, resource_long = _store(retention_months=24)
    short.save_finding(_finding())
    long_.save_finding(_finding())

    short_expiry = resource_short.Table("rempart-findings").items[0][EXPIRE_AT_ATTRIBUTE]
    long_expiry = resource_long.Table("rempart-findings").items[0][EXPIRE_AT_ATTRIBUTE]
    assert long_expiry > short_expiry


def test_normal_write_always_recomputes_the_expiry():
    """Une écriture métier recalcule l'échéance : c'est voulu.

    La purge anticipée en fin de contrat ne passe PAS par `save_*` (qui
    recalculerait 13 mois), mais par `set_expire_at`, testé ci-dessous.
    """
    store, resource = _store()
    store.save_finding(_finding())
    table = resource.Table("rempart-findings")
    first = table.items[-1][EXPIRE_AT_ATTRIBUTE]
    store.save_finding(_finding(created_at="2027-01-01T00:00:00Z"))
    assert table.items[-1][EXPIRE_AT_ATTRIBUTE] > first


def test_contract_end_shortens_the_expiry_explicitly():
    """ENF-DATA-01 : suppression sous 30 jours en fin de contrat."""
    store, resource = _store()
    store.save_finding(_finding())
    table = resource.Table("rempart-findings")
    assert table.items[0][EXPIRE_AT_ATTRIBUTE] > contract_end_epoch(months=1)

    store.set_expire_at("findings", {"finding_id": "f-1"}, contract_end_epoch(months=1))
    updated = table.items[0][EXPIRE_AT_ATTRIBUTE]
    now = datetime.now(tz=timezone.utc).timestamp()
    assert now < updated < now + 33 * 86_400


def test_contract_end_is_about_thirty_days_out():
    now = datetime.now(tz=timezone.utc).timestamp()
    epoch = contract_end_epoch(months=1)
    assert 28 * 86_400 < epoch - now < 33 * 86_400


def test_budget_state_also_expires():
    store, resource = _store()
    state = store.get_budget("t-1", "2026-10")
    store.save_budget(state)
    item = resource.Table("rempart-budget").items[0]
    assert EXPIRE_AT_ATTRIBUTE in item
    assert item[EXPIRE_AT_ATTRIBUTE] > 0
