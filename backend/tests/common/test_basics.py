"""Unit tests for timeutil, fingerprint, and settings."""

from datetime import datetime

from rempart.common.config import Settings
from rempart.common.fingerprint import fingerprint
from rempart.common.timeutil import iso, parse_iso, utcnow


def test_timeutil_utcnow_iso_roundtrip():
    now = utcnow()
    assert now.tzinfo is not None
    s = iso(now)
    assert s.endswith("Z")
    parsed = parse_iso(s)
    assert parsed.tzinfo is not None
    assert int(parsed.timestamp()) == int(now.timestamp())


def test_timeutil_parse_iso_formats():
    dt1 = parse_iso("2026-11-10T23:00:00Z")
    dt2 = parse_iso("2026-11-10T23:00:00+00:00")
    assert dt1 == dt2
    naive = datetime(2026, 11, 10, 23, 0, 0)
    assert iso(naive) == "2026-11-10T23:00:00Z"


def test_fingerprint_deterministic_and_length():
    fp1 = fingerprint("app-1", "IDOR", "/orders/123", "order_id")
    fp2 = fingerprint("app-1", "IDOR", "/orders/123", "order_id")
    assert fp1 == fp2
    assert len(fp1) == 16
    assert isinstance(fp1, str)

    # parameter is optional
    fp3 = fingerprint("app-1", "SQLi", "/search")
    assert len(fp3) == 16
    assert fp3 != fp1


def test_settings_from_env(monkeypatch):
    monkeypatch.setenv("REMPART_TABLE_PREFIX", "custom-")
    monkeypatch.setenv("REMPART_REGION", "us-east-1")
    monkeypatch.setenv("REMPART_HOURLY_RATE", "75.5")
    monkeypatch.setenv("REMPART_GITHUB_OWNER", "my-org")
    monkeypatch.setenv("REMPART_SA_ENDPOINT_URL", "http://localhost:8000")

    s = Settings.from_env()
    assert s.table_prefix == "custom-"
    assert s.region == "us-east-1"
    assert s.hourly_rate == 75.5
    assert s.github_owner == "my-org"
    assert s.sa_endpoint_url == "http://localhost:8000"


def test_settings_default_values(monkeypatch):
    monkeypatch.delenv("REMPART_TABLE_PREFIX", raising=False)
    monkeypatch.delenv("REMPART_REGION", raising=False)
    monkeypatch.delenv("REMPART_HOURLY_RATE", raising=False)
    monkeypatch.delenv("REMPART_GITHUB_OWNER", raising=False)
    monkeypatch.delenv("REMPART_SA_ENDPOINT_URL", raising=False)

    s = Settings.from_env()
    assert s.table_prefix == "rempart-"
    assert s.region == "eu-west-3"
    assert s.hourly_rate == 50.0
    assert s.github_owner == ""
    assert s.sa_endpoint_url is None
