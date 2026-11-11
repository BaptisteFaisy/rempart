"""Tenant isolation and RBAC authorization (EF-POR-01, ENF-SEC-01)."""

from dataclasses import dataclass
from typing import Any

ROLES = (
    "platform_admin",
    "analyst",
    "account_manager",
    "client_security",
    "client_dev",
    "executive",
    "demo",
)


class AuthError(Exception):
    """Raised on authentication or authorization failure."""

    def __init__(self, message: str, status_code: int = 403):
        super().__init__(message)
        self.status_code = status_code


@dataclass
class Principal:
    user_id: str
    role: str
    tenant_id: str | None


def resolve_principal(jwt_claims: dict[str, Any]) -> Principal:
    """Resolve authenticated principal from Cognito JWT claims."""
    user_id = jwt_claims.get("sub")
    if not user_id:
        raise AuthError("Missing 'sub' claim in JWT", status_code=401)

    groups = jwt_claims.get("cognito:groups", [])
    if isinstance(groups, str):
        groups = [groups]

    role = next((g for g in groups if g in ROLES), None)
    if role is None:
        raise AuthError("No recognized Rempart role in claims", status_code=401)

    tenant_id = jwt_claims.get("custom:tenant_id")
    return Principal(user_id=str(user_id), role=role, tenant_id=tenant_id)


def authorize_read(p: Principal, tenant_id: str) -> None:
    """Enforce read permission for tenant resources."""
    if p.role in ("platform_admin", "analyst", "account_manager"):
        return
    if p.role in ("client_security", "client_dev", "executive"):
        if p.tenant_id == tenant_id:
            return
        raise AuthError(f"Principal not authorized to read tenant '{tenant_id}'", status_code=403)
    if p.role == "demo":
        if tenant_id == "demo":
            return
        raise AuthError("Demo role is restricted to 'demo' tenant", status_code=403)
    raise AuthError(f"Role '{p.role}' has no read access", status_code=403)


def authorize_write(p: Principal, tenant_id: str) -> None:
    """Enforce write permission for tenant resources."""
    if p.role in ("platform_admin", "analyst"):
        return
    if p.role in ("client_security", "client_dev"):
        if p.tenant_id == tenant_id:
            return
        raise AuthError(f"Principal not authorized to write tenant '{tenant_id}'", status_code=403)
    if p.role in ("account_manager", "executive", "demo"):
        raise AuthError(f"Role '{p.role}' has no write access", status_code=403)
    raise AuthError(f"Role '{p.role}' has no write access", status_code=403)
