"""Tests du handler Lambda de notifications — contrat § 4 et ENF-SEC-05."""

from __future__ import annotations

from typing import Any

import pytest

from rempart.notifications import kinds
from rempart.notifications.handler import lambda_handler
from tests.notifications.conftest import PORTAL, RecordingSes, make_store

# Événement complet : chaque kind y puise ses propres champs.
BASE_EVENT: dict[str, Any] = {
    "tenant_id": "t-1",
    "app_id": "app-1",
    "finding_title": "SQL injection on /login",
    "finding_id": "f-1",
    "priority": "P1",
    "due_at": "2026-11-20T00:00:00Z",
    "blocking_threshold": "P2",
    "days_overdue": 3,
    "threshold_percent": 80,
    "hours_used": 16.0,
    "month": "2026-11",
    "period": "2026-W45",
    "tests_run": 4,
    "findings_opened": 2,
    "findings_closed": 1,
    "overdue": 1,
}

# Détails d'exploitation glissés dans l'événement : ils ne doivent JAMAIS
# atteindre un e-mail (ENF-SEC-05), même si le producteur les envoie.
EXPLOITATION_LEAK = {
    "steps_to_reproduce": "Step 1: curl -X POST https://shop.acme.test/login -d \"a=b\"",
    "verification_script": "sqlmap -u https://shop.acme.test/login --batch",
    "evidence": {"request": "GET /admin HTTP/1.1", "payload": "' OR 1=1 --"},
}
LEAK_TOKENS = ("curl ", "sqlmap", "OR 1=1", "Step 1", "GET /admin")

# Destinataires attendus avec CONTACTS de conftest, par kind.
EXPECTED: dict[str, list[str]] = {
    kinds.CRITICAL_FINDING_CONFIRMED: ["alice@acme.test", "bob@acme.test"],
    kinds.DELIVERY_BLOCKED: ["alice@acme.test", "bob@acme.test"],
    kinds.DEADLINE_OVERDUE: ["alice@acme.test", "bob@acme.test", "erin@acme.test"],
    kinds.BUDGET_THRESHOLD: ["bob@acme.test", "carol@acme.test"],
    kinds.WEEKLY_DIGEST: ["alice@acme.test", "bob@acme.test", "carol@acme.test"],
}


def _event(kind: str, **extra: Any) -> dict[str, Any]:
    return {"kind": kind, **BASE_EVENT, **extra}


def _addresses(ses: RecordingSes) -> list[str]:
    return [m["to"] for m in ses.sent]


@pytest.mark.parametrize("kind", sorted(EXPECTED))
def test_kind_sends_to_tenant_contacts(store: Any, ses: RecordingSes, kind: str) -> None:
    result = lambda_handler(_event(kind), None, store=store, ses=ses)
    assert result == {"sent": len(EXPECTED[kind]), "skipped": 0, "errors": []}
    assert _addresses(ses) == EXPECTED[kind]


@pytest.mark.parametrize("kind", sorted(kinds.EF_NOT_01_KINDS))
def test_body_mentions_client_application_priority_deadline_portal(
    store: Any, ses: RecordingSes, kind: str
) -> None:
    lambda_handler(_event(kind), None, store=store, ses=ses)
    for message in ses.sent:
        combined = f"{message['subject']}\n{message['html']}\n{message['text']}"
        assert "Acme" in combined  # client
        assert "ShopLite" in combined or "All applications" in combined  # application
        assert PORTAL in combined  # lien portail
        if kind == kinds.BUDGET_THRESHOLD:
            assert "80%" in combined and "2026-11" in combined  # le seuil
        else:
            assert "SQL injection on /login" in combined  # la faille
            assert "P1" in combined  # priorité
            assert "2026-11-20" in combined  # échéance


@pytest.mark.parametrize("kind", sorted(EXPECTED))
def test_no_exploitation_details_ever_reach_email(
    store: Any, ses: RecordingSes, kind: str
) -> None:
    """ENF-SEC-05 : preuves, étapes et scripts restent hors des e-mails."""
    result = lambda_handler(_event(kind, **EXPLOITATION_LEAK), None, store=store, ses=ses)
    assert result["errors"] == [] and result["sent"] > 0
    for message in ses.sent:
        combined = f"{message['subject']}\n{message['html']}\n{message['text']}"
        for token in LEAK_TOKENS:
            assert token not in combined, f"{kind}: {token!r} a fui dans l'e-mail"


def test_unknown_kind_is_skipped_without_crash(store: Any, ses: RecordingSes) -> None:
    result = lambda_handler(_event("totally_unknown_kind"), None, store=store, ses=ses)
    assert result == {"sent": 0, "skipped": 1, "errors": []}
    assert ses.sent == []


def test_missing_kind_is_skipped(store: Any, ses: RecordingSes) -> None:
    result = lambda_handler({"tenant_id": "t-1"}, None, store=store, ses=ses)
    assert result == {"sent": 0, "skipped": 1, "errors": []}
    assert ses.sent == []


def test_unknown_tenant_is_skipped(store: Any, ses: RecordingSes) -> None:
    result = lambda_handler(
        _event(kinds.CRITICAL_FINDING_CONFIRMED, tenant_id="t-404"), None, store=store, ses=ses
    )
    assert result == {"sent": 0, "skipped": 1, "errors": []}
    assert ses.sent == []


def test_no_eligible_contact_is_skipped(ses: RecordingSes) -> None:
    store = make_store(contacts=[{"name": "Carol", "email": "carol@acme.test", "role": "billing"}])
    result = lambda_handler(
        _event(kinds.CRITICAL_FINDING_CONFIRMED), None, store=store, ses=ses
    )
    assert result == {"sent": 0, "skipped": 1, "errors": []}
    assert ses.sent == []


def test_ses_failure_is_counted_never_raised(store: Any) -> None:
    ses = RecordingSes(fail_for=("alice@acme.test",))
    result = lambda_handler(
        _event(kinds.CRITICAL_FINDING_CONFIRMED), None, store=store, ses=ses
    )
    assert result["sent"] == 1
    assert result["skipped"] == 0
    assert len(result["errors"]) == 1
    assert "alice@acme.test" in result["errors"][0]
    assert _addresses(ses) == ["bob@acme.test"]  # les autres envois continuent


def test_all_sends_fail_still_returns(store: Any) -> None:
    ses = RecordingSes(fail_for=("alice@acme.test", "bob@acme.test"))
    result = lambda_handler(
        _event(kinds.CRITICAL_FINDING_CONFIRMED), None, store=store, ses=ses
    )
    assert result == {"sent": 0, "skipped": 0, "errors": result["errors"]}
    assert len(result["errors"]) == 2


def test_broken_store_never_escapes(ses: RecordingSes) -> None:
    class _BrokenStore:
        def get_tenant(self, tenant_id: str) -> Any:
            raise RuntimeError("DynamoDB unavailable")

    result = lambda_handler(
        _event(kinds.CRITICAL_FINDING_CONFIRMED), None, store=_BrokenStore(), ses=ses
    )
    assert result["sent"] == 0
    assert any("DynamoDB unavailable" in e for e in result["errors"])
    assert ses.sent == []


def test_none_event_is_skipped_not_fatal(ses: RecordingSes) -> None:
    result = lambda_handler(None, None, store=make_store(), ses=ses)  # type: ignore[arg-type]
    assert result == {"sent": 0, "skipped": 1, "errors": []}


def test_weekly_digest_kind_is_dispatched(store: Any, ses: RecordingSes) -> None:
    """EF-NOT-02 : le digest est rendable à la demande (aucun ordonnanceur)."""
    result = lambda_handler(_event(kinds.WEEKLY_DIGEST), None, store=store, ses=ses)
    assert result["sent"] == 3
    combined = ses.sent[0]["text"]
    assert "digest" in ses.sent[0]["subject"].lower()
    assert "2026-W45" in combined


def test_resolve_recipients_dedupes_and_skips_invalid() -> None:
    contacts = [
        {"email": "a@x.test"},
        {"email": "a@x.test"},
        {"name": "no email"},
        "not-a-dict",
        {"email": "  b@x.test  "},
    ]
    assert kinds.resolve_recipients(contacts, kinds.WEEKLY_DIGEST) == ["a@x.test", "b@x.test"]
    assert kinds.resolve_recipients(None, kinds.WEEKLY_DIGEST) == []


def test_role_filter_and_subscription() -> None:
    contacts = [
        {"email": "sec@x.test", "role": "security"},
        {"email": "bill@x.test", "role": "billing"},
        {"email": "boss@x.test", "role": "ceo"},  # rôle inconnu → reçoit tout
        {"email": "opt@x.test", "kinds": [kinds.DEADLINE_OVERDUE]},
    ]
    assert kinds.resolve_recipients(contacts, kinds.BUDGET_THRESHOLD) == [
        "bill@x.test",
        "boss@x.test",
    ]
    assert kinds.resolve_recipients(contacts, kinds.DEADLINE_OVERDUE) == [
        "sec@x.test",
        "boss@x.test",
        "opt@x.test",
    ]


def test_every_ef_not_01_kind_has_a_renderer() -> None:
    """Contrat : les quatre kinds d'EF-NOT-01 (+ le digest) sont dispatchés."""
    from rempart.notifications.handler import _RENDERERS

    assert set(_RENDERERS) == set(kinds.ALL_KINDS)
