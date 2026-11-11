"""Tests for ShopLite demo application — covering vulnerable and secure modes."""

import pytest
from app import create_app


@pytest.fixture
def client_vuln(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("VULN_IDOR", "1")
    app = create_app({"TESTING": True})
    return app.test_client()


@pytest.fixture
def client_fixed(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("VULN_IDOR", "0")
    app = create_app({"TESTING": True})
    return app.test_client()


def test_health_check(client_vuln):
    resp = client_vuln.get("/health")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "ok"
    assert data["service"] == "shoplite"
    assert data["idor_active"] is True


def test_list_orders_missing_auth(client_vuln):
    resp = client_vuln.get("/orders")
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "missing_user_id_header"


def test_list_orders_alice(client_vuln):
    resp = client_vuln.get("/orders", headers={"X-User-Id": "usr-alice"})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["user_id"] == "usr-alice"
    assert len(data["orders"]) == 2
    order_ids = {o["id"] for o in data["orders"]}
    assert order_ids == {"ord-101", "ord-102"}


def test_get_order_not_found(client_vuln):
    resp = client_vuln.get("/orders/ord-999", headers={"X-User-Id": "usr-alice"})
    assert resp.status_code == 404
    assert resp.get_json()["error"] == "not_found"


def test_idor_vulnerable_mode_allows_reading_foreign_order(client_vuln):
    # Alice requests Bob's order ord-201
    resp = client_vuln.get("/orders/ord-201", headers={"X-User-Id": "usr-alice"})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["order"]["id"] == "ord-201"
    assert data["order"]["user_id"] == "usr-bob"
    assert data["order"]["item"] == "Mechanical Keyboard"


def test_idor_fixed_mode_blocks_foreign_order_with_403(client_fixed):
    # Own order: OK
    resp_own = client_fixed.get("/orders/ord-101", headers={"X-User-Id": "usr-alice"})
    assert resp_own.status_code == 200
    assert resp_own.get_json()["order"]["id"] == "ord-101"

    # Foreign order: 403 Forbidden
    resp_foreign = client_fixed.get("/orders/ord-201", headers={"X-User-Id": "usr-alice"})
    assert resp_foreign.status_code == 403
    data = resp_foreign.get_json()
    assert data["error"] == "forbidden"
