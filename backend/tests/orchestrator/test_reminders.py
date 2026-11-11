"""Tests des relances d'échéance (EF-COR-06).

Le point critique est l'anti-spam : le balayeur tourne en boucle, donc une
faille en retard ne doit pas être relancée à chaque passage. L'heure est
toujours injectée — aucun test ne dépend de l'heure réelle.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from rempart.common.models import Finding
from rempart.orchestrator.reminders import (
    ESCALATE,
    OVERDUE,
    REMINDER_ACTION,
    UPCOMING,
    already_notified,
    classify,
    days_from_due,
    reminder_event,
    scan_deadlines,
)
from tests.fakes_store import FakeStore
from tests.integration.conftest import make_deps, seed_two_tenants

NOW = datetime(2026, 11, 10, 12, 0, 0, tzinfo=timezone.utc)


def _finding(
    finding_id: str,
    *,
    status: str = "in_remediation",
    due_at: str | None,
    tenant_id: str = "tenant-a",
    priority: str = "P1",
) -> Finding:
    return Finding(
        finding_id=finding_id,
        app_id="app-shop",
        tenant_id=tenant_id,
        run_id="run-1",
        fingerprint=f"fp-{finding_id}",
        title=f"Finding {finding_id}",
        risk_type="IDOR",
        severity="Critical",
        confidence="High",
        priority=priority,
        status=status,
        due_at=due_at,
        ticket_url=None,
        remediation_pr_url=None,
        evidence={},
        cvss={},
        created_at="2026-11-01T00:00:00Z",
        updated_at="2026-11-01T00:00:00Z",
        closed_at=None,
        closed_by_run_id=None,
    )


def _due_in(days: float) -> str:
    return (NOW + timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")


@pytest.fixture
def deps(monkeypatch) -> object:
    """Deps avec l'envoi neutralisé : on teste le routage, pas SES."""
    sent: list[dict] = []
    monkeypatch.setattr(
        "rempart.orchestrator.reminders.notify", lambda _deps, event: sent.append(event)
    )
    result = make_deps(seed_two_tenants())
    result.sent = sent  # type: ignore[attr-defined]
    return result


def test_days_from_due_is_negative_once_passed():
    assert days_from_due(_due_in(3), NOW) == pytest.approx(3, abs=0.01)
    assert days_from_due(_due_in(-2), NOW) == pytest.approx(-2, abs=0.01)
    assert days_from_due(None, NOW) is None
    assert days_from_due("pas-une-date", NOW) is None


def test_classify_upcoming_overdue_and_escalation():
    upcoming = _finding("f-1", due_at=_due_in(1))
    overdue = _finding("f-2", due_at=_due_in(-1))
    escalate = _finding("f-3", due_at=_due_in(-10))
    assert classify(upcoming, NOW, 2, 2) == UPCOMING
    assert classify(overdue, NOW, 2, 2) == OVERDUE
    assert classify(escalate, NOW, 2, 2) == ESCALATE


def test_classify_ignores_findings_that_need_no_reminder():
    assert classify(_finding("f-1", due_at=_due_in(20)), NOW, 2, 2) is None
    assert classify(_finding("f-2", due_at=None), NOW, 2, 2) is None
    for status in ("closed", "false_positive", "risk_accepted"):
        assert classify(_finding("f-3", status=status, due_at=_due_in(-5)), NOW, 2, 2) is None


def test_scan_notifies_each_category_once(deps):
    deps.store.save_finding(_finding("f-up", due_at=_due_in(1)))
    deps.store.save_finding(_finding("f-late", due_at=_due_in(-1)))
    deps.store.save_finding(_finding("f-old", due_at=_due_in(-10)))

    result = scan_deadlines(deps, now=NOW)

    assert result["upcoming"] == ["f-up"]
    assert result["overdue"] == ["f-late"]
    assert result["escalate"] == ["f-old"]
    assert result["notified"] == 3
    assert len(deps.sent) == 3


def test_second_scan_does_not_notify_again(deps):
    """Le garde-fou central : un balayeur en boucle ne harcèle personne."""
    deps.store.save_finding(_finding("f-late", due_at=_due_in(-1)))

    first = scan_deadlines(deps, now=NOW)
    second = scan_deadlines(deps, now=NOW)

    assert first["notified"] == 1
    assert second["notified"] == 0
    assert len(deps.sent) == 1
    # La faille reste pourtant listée comme en retard : l'état ne change pas.
    assert second["overdue"] == ["f-late"]


def test_escalation_is_notified_separately_from_the_first_reminder(deps):
    """Passer de « en retard » à « très en retard » mérite une nouvelle alerte."""
    deps.store.save_finding(_finding("f-1", due_at=_due_in(-1)))
    assert scan_deadlines(deps, now=NOW)["notified"] == 1

    later = NOW + timedelta(days=10)  # l'échéance est maintenant loin derrière
    result = scan_deadlines(deps, now=later)
    assert result["escalate"] == ["f-1"]
    assert result["notified"] == 1
    assert len(deps.sent) == 2


def test_reminder_is_audited_with_its_type(deps):
    deps.store.save_finding(_finding("f-1", due_at=_due_in(-1)))
    scan_deadlines(deps, now=NOW)

    events = [e for e in deps.store.list_audit() if e.action == REMINDER_ACTION]
    assert len(events) == 1
    assert events[0].result == OVERDUE
    assert events[0].object_id == "f-1"
    assert already_notified(deps, "f-1", OVERDUE) is True
    assert already_notified(deps, "f-1", ESCALATE) is False


def test_event_carries_what_the_notification_template_needs(deps):
    # -1 jour avec after_days=2 : simple retard, pas encore une escalade.
    deps.store.save_finding(_finding("f-1", due_at=_due_in(-1), priority="P1"))
    scan_deadlines(deps, now=NOW)

    event = deps.sent[0]
    assert event["kind"] == "deadline_overdue"
    assert event["tenant_id"] == "tenant-a"
    assert event["finding_title"] == "Finding f-1"
    assert event["priority"] == "P1"
    assert event["days_overdue"] == 1
    assert event["escalated"] is False
    assert event["reminder_type"] == OVERDUE


def test_escalated_event_is_flagged_for_the_account_manager():
    event = reminder_event("tenant-a", _finding("f-1", due_at=_due_in(-10)), ESCALATE, -10.0)
    assert event["escalated"] is True
    assert event["reminder_type"] == ESCALATE
    assert event["days_overdue"] == 10


def test_scan_can_be_scoped_to_one_tenant(deps):
    deps.store.save_finding(_finding("f-a", due_at=_due_in(-1), tenant_id="tenant-a"))
    deps.store.save_finding(_finding("f-b", due_at=_due_in(-1), tenant_id="tenant-b"))

    result = scan_deadlines(deps, now=NOW, tenant_id="tenant-a")
    assert result["overdue"] == ["f-a"]
    assert result["notified"] == 1


def test_scan_never_touches_another_tenant(deps):
    deps.store.save_finding(_finding("f-a", due_at=_due_in(-1), tenant_id="tenant-a"))
    scan_deadlines(deps, now=NOW, tenant_id="tenant-a")

    audited = [e for e in deps.store.list_audit() if e.action == REMINDER_ACTION]
    assert audited and all(e.object_id == "f-a" for e in audited)


def test_upcoming_reminder_does_not_block_a_closed_finding(deps):
    deps.store.save_finding(_finding("f-closed", status="closed", due_at=_due_in(-1)))
    result = scan_deadlines(deps, now=NOW)
    assert result["notified"] == 0
    assert result["overdue"] == []


def test_empty_store_is_not_an_error():
    from rempart.orchestrator.task_types import Deps
    from tests.fakes import FakeSecurityAgentClient

    empty = Deps(store=FakeStore(), sa=FakeSecurityAgentClient())
    result = scan_deadlines(empty, now=NOW)
    assert result["notified"] == 0
    assert result["upcoming"] == [] and result["overdue"] == [] and result["escalate"] == []
