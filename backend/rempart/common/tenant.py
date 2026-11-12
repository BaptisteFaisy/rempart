"""Tenant isolation and RBAC authorization (EF-POR-01, ENF-SEC-01)."""

import json
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


def _clean(items: Any) -> list[str]:
    """Chaînes non vides d'une liste ; tout autre élément est écarté.

    Un élément non textuel (``None``, ``42``, un dict) n'est jamais converti en
    chaîne : ``str(None)`` produirait un « groupe » nommé ``None``, ce qui
    n'existe pas et n'a aucune raison d'apparaître.
    """
    if not isinstance(items, (list, tuple)):
        return []
    return [item.strip() for item in items if isinstance(item, str) and item.strip()]


def groups_from_claims(raw: Any) -> list[str]:
    """Les groupes Cognito dans les TROIS formes réellement observées.

    INCIDENT RÉEL (12 nov. 2026, compte 710332178565, API eu-north-1) : avec un
    vrai jeton Cognito, l'API renvoyait 401 « Authentication required » alors
    que l'autorisateur JWT avait laissé passer la requête. Le code ne gérait que
    deux formes (`["platform_admin"]` et `"platform_admin"`) ; API Gateway peut
    sérialiser une claim multi-valeurs en **chaîne JSON** —
    ``'["platform_admin"]'`` — que `groups = [groups]` transformait en un groupe
    nommé `'["platform_admin"]'`, donc aucun rôle reconnu. Aucune forme ne doit
    être devinée : les trois sont acceptées, et toute valeur non reconnue donne
    une liste vide (échec fermé, jamais d'élévation de privilège).
    """
    if raw is None:
        return []
    if isinstance(raw, (list, tuple)):
        return _clean(raw)
    if not isinstance(raw, str):
        return []
    text = raw.strip()
    if not text:
        return []
    if text.startswith("["):
        try:
            return _clean(json.loads(text))
        except ValueError:
            return []
    return [part.strip() for part in text.split(",") if part.strip()]


def user_id_from_claims(jwt_claims: dict[str, Any]) -> str | None:
    """Identifiant stable du principal : `sub`, à défaut `username`.

    Un access token Cognito porte les deux ; l'ordre ne doit pas être une
    hypothèse, et `sub` reste préféré car c'est l'identifiant immuable.
    """
    for claim in ("sub", "username"):
        value = jwt_claims.get(claim)
        if value:
            return str(value)
    return None


def resolve_principal(jwt_claims: dict[str, Any]) -> Principal:
    """Resolve authenticated principal from Cognito JWT claims."""
    user_id = user_id_from_claims(jwt_claims)
    if not user_id:
        raise AuthError("Missing 'sub' claim in JWT", status_code=401)

    groups = groups_from_claims(jwt_claims.get("cognito:groups"))
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
