"""Tests for tenant isolation and RBAC authorization (EF-POR-01, ENF-SEC-01)."""

import pytest

from rempart.common.tenant import (
    AuthError,
    Principal,
    authorize_read,
    authorize_write,
    resolve_principal,
)


def test_resolve_principal_valid_claims():
    claims = {
        "sub": "user-123",
        "cognito:groups": ["client_security", "other"],
        "custom:tenant_id": "tenant-a",
    }
    p = resolve_principal(claims)
    assert p.user_id == "user-123"
    assert p.role == "client_security"
    assert p.tenant_id == "tenant-a"


def test_resolve_principal_missing_sub():
    with pytest.raises(AuthError) as exc:
        resolve_principal({"cognito:groups": ["platform_admin"]})
    assert exc.value.status_code == 401


def test_resolve_principal_unknown_role():
    with pytest.raises(AuthError) as exc:
        resolve_principal({"sub": "u-1", "cognito:groups": ["unknown_role"]})
    assert exc.value.status_code == 401


def test_authorize_read_rules():
    admin = Principal("u-admin", "platform_admin", None)
    analyst = Principal("u-analyst", "analyst", None)
    am = Principal("u-am", "account_manager", None)
    cs_a = Principal("u-cs", "client_security", "tenant-a")
    demo = Principal("u-demo", "demo", "demo")

    # Admins, analysts, and account managers can read any tenant
    authorize_read(admin, "tenant-b")
    authorize_read(analyst, "tenant-b")
    authorize_read(am, "tenant-b")

    # Client roles can only read their own tenant
    authorize_read(cs_a, "tenant-a")
    with pytest.raises(AuthError) as exc1:
        authorize_read(cs_a, "tenant-b")
    assert exc1.value.status_code == 403

    # Demo can only read demo tenant
    authorize_read(demo, "demo")
    with pytest.raises(AuthError) as exc2:
        authorize_read(demo, "tenant-a")
    assert exc2.value.status_code == 403


def test_authorize_write_rules():
    admin = Principal("u-admin", "platform_admin", None)
    analyst = Principal("u-analyst", "analyst", None)
    am = Principal("u-am", "account_manager", None)
    cs_a = Principal("u-cs", "client_security", "tenant-a")
    exec_a = Principal("u-ex", "executive", "tenant-a")
    demo = Principal("u-demo", "demo", "demo")

    # Admin and analyst can write to any tenant
    authorize_write(admin, "tenant-x")
    authorize_write(analyst, "tenant-x")

    # Client security can write to their own tenant
    authorize_write(cs_a, "tenant-a")
    with pytest.raises(AuthError) as exc1:
        authorize_write(cs_a, "tenant-b")
    assert exc1.value.status_code == 403

    # Account manager, executive, and demo have no write access
    for p in (am, exec_a, demo):
        with pytest.raises(AuthError) as exc:
            authorize_write(p, p.tenant_id or "tenant-a")
        assert exc.value.status_code == 403
