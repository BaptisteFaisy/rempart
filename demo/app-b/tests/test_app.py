"""Tests for BookWorm demo app (Client B)."""

import importlib.util
from pathlib import Path
import pytest

_APP_PATH = Path(__file__).resolve().parents[1] / "app.py"
_SPEC = importlib.util.spec_from_file_location("app_b", _APP_PATH)
_MOD = importlib.util.module_from_spec(_SPEC)
assert _SPEC and _SPEC.loader
_SPEC.loader.exec_module(_MOD)
create_app = _MOD.create_app


@pytest.fixture
def client():
    app = create_app({"TESTING": True})
    with app.test_client() as c:
        yield c


def test_health(client):
    res = client.get("/health")
    assert res.status_code == 200
    assert res.get_json()["app"] == "BookWorm"


def test_sqli_vulnerable(client, monkeypatch):
    monkeypatch.setenv("VULN_SQLI", "1")
    payload = "' UNION SELECT id, username, role, api_key FROM users --"
    res = client.get(f"/search?q={payload}")
    assert res.status_code == 200
    data = res.get_json()
    titles = [item.get("title") for item in data["results"]]
    assert "alice" in titles or "bob" in titles


def test_sqli_fixed(client, monkeypatch):
    monkeypatch.setenv("VULN_SQLI", "0")
    payload = "' UNION SELECT id, username, role, api_key FROM users --"
    res = client.get(f"/search?q={payload}")
    assert res.status_code == 200
    assert res.get_json()["count"] == 0


def test_admin_route_vulnerable(client, monkeypatch):
    monkeypatch.setenv("VULN_ADMIN", "1")
    res = client.get("/admin/users")
    assert res.status_code == 200
    assert len(res.get_json()["users"]) >= 2


def test_admin_route_fixed_unauthorized(client, monkeypatch):
    monkeypatch.setenv("VULN_ADMIN", "0")
    res = client.get("/admin/users")
    assert res.status_code == 401


def test_admin_route_fixed_authorized(client, monkeypatch):
    monkeypatch.setenv("VULN_ADMIN", "0")
    res = client.get("/admin/users", headers={"X-Admin-Token": "secret-admin-token"})
    assert res.status_code == 200
    assert len(res.get_json()["users"]) >= 2
