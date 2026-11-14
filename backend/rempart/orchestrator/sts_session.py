"""Construction de noms de session STS pour AssumeRole.

Séparé du client AWS pour éviter de dupliquer les contraintes de validation :
`RoleSessionName` est obligatoire dans l'API STS (botocore le vérifie avant le
réseau), longueur 2–64, caractères `[A-Za-z0-9_+=,.@-]`.
"""

from __future__ import annotations

import re

_ALLOWED = re.compile(r"[^A-Za-z0-9_+=,.@-]+")
_MAX_LENGTH = 64
_DEFAULT = "rempart-control-plane"


def session_name(raw: object) -> str:
    """Nom STS valide, déterministe, et au plus 64 caractères."""
    cleaned = _ALLOWED.sub("-", str(raw or "")).strip("-._") or _DEFAULT
    return cleaned[:_MAX_LENGTH]


__all__ = ["session_name"]
