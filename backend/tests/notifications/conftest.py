"""Fixtures partagées des tests de notifications — sans réseau ni AWS."""

from __future__ import annotations

from typing import Any

import pytest

from rempart.common.models import Application, Tenant
from tests.fakes_store import FakeStore

PORTAL = "https://portal.rempart.test"

# Alice : rôle security ; Bob : sans rôle (reçoit tout) ; Carol : rôle billing ;
# Dave : sans e-mail (ignoré) ; Bob en double (dédupliqué) ;
# Erin : souscription explicite limitée à deadline_overdue.
CONTACTS: list[dict[str, Any]] = [
    {"name": "Alice", "email": "alice@acme.test", "role": "security"},
    {"name": "Bob", "email": "bob@acme.test"},
    {"name": "Carol", "email": "carol@acme.test", "role": "billing"},
    {"name": "Dave"},
    {"name": "Bob again", "email": "bob@acme.test"},
    {"name": "Erin", "email": "erin@acme.test", "kinds": ["deadline_overdue"]},
]


class RecordingSes:
    """Double de ``SesClient`` : enregistre les envois, échoue à la demande."""

    def __init__(self, fail_for: tuple[str, ...] = ()) -> None:
        self.sent: list[dict[str, str]] = []
        self.fail_for = set(fail_for)

    def send(self, to: str, subject: str, body_html: str, body_text: str) -> dict[str, Any]:
        if to in self.fail_for:
            raise RuntimeError("SES throttling")
        self.sent.append({"to": to, "subject": subject, "html": body_html, "text": body_text})
        return {"MessageId": f"msg-{len(self.sent)}"}


def make_store(contacts: list[dict[str, Any]] | None = None) -> FakeStore:
    """Store pré-rempli : tenant ``t-1`` (Acme) et application ``app-1`` (ShopLite)."""
    store = FakeStore()
    store.save_tenant(
        Tenant(
            tenant_id="t-1",
            name="Acme",
            aws_account_id="123456789012",
            region="eu-west-3",
            role_arn="arn:aws:iam::123456789012:role/rempart",
            external_id="ext",
            plan="continu",
            contacts=CONTACTS if contacts is None else contacts,
            monthly_budget_hours=20.0,
            mandate_status="valid",
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
            domains=["shop.acme.test"],
            repositories=["acme/shop"],
            team="Core",
            ticket_channel="github",
            context={},
            created_at="2026-11-01T00:00:00Z",
        )
    )
    return store


@pytest.fixture(autouse=True)
def portal_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Lien portail déterministe pour tous les tests de la zone."""
    monkeypatch.setenv("REMPART_PORTAL_URL", PORTAL)


@pytest.fixture()
def store() -> FakeStore:
    return make_store()


@pytest.fixture()
def ses() -> RecordingSes:
    return RecordingSes()
