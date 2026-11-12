"""Tests du client SES injectable — jamais de boto3 réel, jamais de réseau."""

from __future__ import annotations

import sys
from typing import Any

import pytest

from rempart.notifications.ses_client import SesClient


class _BoomBoto3:
    """Double de module boto3 : tout accès prouve qu'il a été utilisé à tort."""

    def __getattr__(self, name: str) -> Any:
        raise AssertionError(f"boto3.{name} ne doit pas être appelé (client injecté)")


class _RecordingBotoClient:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def send_email(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs)
        return {"MessageId": "ses-msg-1"}


@pytest.fixture()
def ses_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("REMPART_SES_FROM_DOMAIN", "rempart.example.test")
    monkeypatch.setenv("REMPART_SES_CONFIGURATION_SET", "rempart-notifications")
    monkeypatch.setenv("REMPART_REGION", "eu-west-1")


@pytest.fixture()
def no_boto3(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "boto3", _BoomBoto3())


def test_injected_client_never_touches_boto3(ses_env: None, no_boto3: None) -> None:
    fake = _RecordingBotoClient()
    client = SesClient(boto_client=fake)
    result = client.send("ops@acme.test", "Subject", "<p>Html</p>", "Text")
    assert result == {"MessageId": "ses-msg-1"}
    assert len(fake.calls) == 1


def test_send_email_payload(ses_env: None, no_boto3: None) -> None:
    fake = _RecordingBotoClient()
    SesClient(boto_client=fake).send(
        ["a@acme.test", "b@acme.test"], "Subject", "<p>Html</p>", "Text body"
    )
    call = fake.calls[0]
    assert call["Source"] == "noreply@rempart.example.test"
    assert call["Destination"] == {"ToAddresses": ["a@acme.test", "b@acme.test"]}
    assert call["ConfigurationSetName"] == "rempart-notifications"
    message = call["Message"]
    assert message["Subject"] == {"Data": "Subject", "Charset": "UTF-8"}
    assert message["Body"]["Html"] == {"Data": "<p>Html</p>", "Charset": "UTF-8"}
    assert message["Body"]["Text"] == {"Data": "Text body", "Charset": "UTF-8"}


def test_configuration_set_omitted_when_unset(
    monkeypatch: pytest.MonkeyPatch, no_boto3: None
) -> None:
    monkeypatch.setenv("REMPART_SES_FROM_DOMAIN", "rempart.example.test")
    monkeypatch.delenv("REMPART_SES_CONFIGURATION_SET", raising=False)
    fake = _RecordingBotoClient()
    SesClient(boto_client=fake).send("a@acme.test", "S", "H", "T")
    assert "ConfigurationSetName" not in fake.calls[0]


def test_constructor_overrides_environment(ses_env: None, no_boto3: None) -> None:
    fake = _RecordingBotoClient()
    client = SesClient(
        boto_client=fake,
        from_domain="other.test",
        configuration_set="other-set",
        region="us-east-1",
    )
    assert client.from_address == "noreply@other.test"
    assert client.configuration_set == "other-set"
    client.send("a@acme.test", "S", "H", "T")
    assert fake.calls[0]["ConfigurationSetName"] == "other-set"


def test_missing_from_domain_raises(monkeypatch: pytest.MonkeyPatch, no_boto3: None) -> None:
    monkeypatch.delenv("REMPART_SES_FROM_DOMAIN", raising=False)
    with pytest.raises(ValueError, match="REMPART_SES_FROM_DOMAIN"):
        SesClient(boto_client=_RecordingBotoClient()).send("a@acme.test", "S", "H", "T")


def test_empty_recipient_raises(ses_env: None, no_boto3: None) -> None:
    with pytest.raises(ValueError, match="no recipient"):
        SesClient(boto_client=_RecordingBotoClient()).send([], "S", "H", "T")


def test_boto_client_created_lazily(ses_env: None, monkeypatch: pytest.MonkeyPatch) -> None:
    """Sans injection, boto3 n'est créé qu'au premier accès, avec la bonne région."""
    created: list[dict[str, Any]] = []
    fake = _RecordingBotoClient()

    class _FakeBoto3:
        @staticmethod
        def client(service: str, region_name: str) -> Any:
            created.append({"service": service, "region_name": region_name})
            return fake

    monkeypatch.setitem(sys.modules, "boto3", _FakeBoto3)
    client = SesClient()
    assert created == []  # rien à l'instanciation
    assert client.client is fake
    assert client.client is fake  # mis en cache
    assert created == [{"service": "ses", "region_name": "eu-west-1"}]


def test_region_defaults_when_env_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("REMPART_REGION", raising=False)
    monkeypatch.setenv("REMPART_SES_FROM_DOMAIN", "rempart.example.test")
    captured: dict[str, Any] = {}
    fake = _RecordingBotoClient()

    class _FakeBoto3:
        @staticmethod
        def client(service: str, region_name: str) -> Any:
            captured["region_name"] = region_name
            return fake

    monkeypatch.setitem(sys.modules, "boto3", _FakeBoto3)
    SesClient().send("a@acme.test", "S", "H", "T")
    assert captured["region_name"] == "eu-west-3"


# --------------------------------------------------------------------------- #
# Mode « adresse exacte » : le sandbox SES, gratuit (aucun domaine à acheter).
# Une adresse exacte prime sur le domaine — c'est le mode utilisé quand on ne
# possède pas de zone DNS, ce qui est le cas du déploiement de démonstration.
# --------------------------------------------------------------------------- #
def test_explicit_address_is_used_verbatim(monkeypatch):
    monkeypatch.delenv("REMPART_SES_FROM_DOMAIN", raising=False)
    monkeypatch.setenv("REMPART_SES_FROM_ADDRESS", "ops@msp.example")
    assert SesClient().from_address == "ops@msp.example"


def test_explicit_address_wins_over_domain(monkeypatch):
    monkeypatch.setenv("REMPART_SES_FROM_DOMAIN", "msp.example")
    monkeypatch.setenv("REMPART_SES_FROM_ADDRESS", "ops@msp.example")
    assert SesClient().from_address == "ops@msp.example"


def test_address_injected_in_constructor_wins_over_env(monkeypatch):
    monkeypatch.setenv("REMPART_SES_FROM_ADDRESS", "env@msp.example")
    client = SesClient(from_address="ctor@msp.example")
    assert client.from_address == "ctor@msp.example"


def test_missing_both_sources_explains_both_options(monkeypatch):
    """Le message d'erreur doit nommer les DEUX variables, sinon on cherche."""
    monkeypatch.delenv("REMPART_SES_FROM_ADDRESS", raising=False)
    monkeypatch.delenv("REMPART_SES_FROM_DOMAIN", raising=False)
    with pytest.raises(ValueError) as exc:
        SesClient().from_address
    assert "REMPART_SES_FROM_ADDRESS" in str(exc.value)
    assert "REMPART_SES_FROM_DOMAIN" in str(exc.value)
