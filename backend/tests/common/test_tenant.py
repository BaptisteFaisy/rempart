"""Tests for tenant isolation and RBAC authorization (EF-POR-01, ENF-SEC-01)."""

import pytest

from rempart.common.tenant import (
    AuthError,
    Principal,
    authorize_read,
    authorize_write,
    groups_from_claims,
    resolve_principal,
    user_id_from_claims,
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


# --------------------------------------------------------------------------- #
# D8 — formes réelles de la claim `cognito:groups` (incident du 2026-11-12)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "raw,expected",
    [
        (["analyst"], ["analyst"]),
        (["analyst", "client_dev"], ["analyst", "client_dev"]),
        ("analyst", ["analyst"]),
        ('["analyst"]', ["analyst"]),
        ('["analyst", "client_dev"]', ["analyst", "client_dev"]),
        ("analyst,client_dev", ["analyst", "client_dev"]),
        ("[platform_admin]", ["platform_admin"]),
        ("[platform_admin, analyst]", ["platform_admin", "analyst"]),
        ('["platform_admin"]', ["platform_admin"]),
        (" platform_admin , analyst ", ["platform_admin", "analyst"]),
        ("[]", []),
        ("[,]", []),
        ('["analyst"', []),
        (" analyst ", ["analyst"]),
        (None, []),
        ("", []),
        ("   ", []),
        ("[]", []),
        ('["analyst"', []),
        (42, []),
        ({"role": "analyst"}, []),
        ([None, "", "analyst"], ["analyst"]),
    ],
)
def test_groups_from_claims_accepts_real_shapes_and_fails_closed(raw, expected):
    """Liste, chaîne, chaîne JSON, CSV — et jamais d'interprétation hasardeuse."""
    assert groups_from_claims(raw) == expected


def test_groups_from_claims_never_yields_a_recognized_role_from_garbage():
    """Une entrée inutilisable ne doit jamais produire un rôle connu."""
    from rempart.common.tenant import ROLES

    for raw in ('{"role": "analyst"}', '["platform_admin"', "platform_admin]", 42, object()):
        assert not set(groups_from_claims(raw)) & set(ROLES), raw


@pytest.mark.parametrize(
    "groups",
    [
        '["platform_admin"]',
        "[platform_admin]",
        "platform_admin",
        "platform_admin,analyst",
        ["platform_admin"],
    ],
)
def test_resolve_principal_accepte_toutes_les_formes_reelles_de_groupes(groups):
    """Le cas réel qui cassait la production : `cognito:groups` en chaîne."""
    principal = resolve_principal({"sub": "u-1", "cognito:groups": groups})
    assert principal.role == "platform_admin"
    assert principal.user_id == "u-1"


def test_resolve_principal_falls_back_to_username_claim():
    principal = resolve_principal({"username": "u-2", "cognito:groups": ["analyst"]})
    assert principal.user_id == "u-2"
    assert principal.role == "analyst"


def test_resolve_principal_prefers_sub_over_username():
    principal = resolve_principal(
        {"sub": "u-stable", "username": "u-alias", "cognito:groups": ["analyst"]}
    )
    assert principal.user_id == "u-stable"


@pytest.mark.parametrize(
    "claims",
    [
        {},
        {"sub": "u-3"},
        {"sub": "u-3", "cognito:groups": '["pas-un-role"]'},
        {"sub": "u-3", "cognito:groups": '["platform_admin"'},
        {"username": "u-3", "cognito:groups": []},
    ],
)
def test_resolve_principal_refuses_without_a_recognized_role(claims):
    with pytest.raises(AuthError) as exc:
        resolve_principal(claims)
    assert exc.value.status_code == 401


@pytest.mark.parametrize(
    "claims,expected",
    [
        ({"sub": "s-1", "username": "u-1"}, "s-1"),
        ({"username": "u-1"}, "u-1"),
        ({"sub": ""}, None),
        ({}, None),
    ],
)
def test_user_id_from_claims_prefers_the_immutable_identifier(claims, expected):
    assert user_id_from_claims(claims) == expected
