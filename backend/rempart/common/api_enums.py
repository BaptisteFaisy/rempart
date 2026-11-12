"""Normalisation des énumérations de l'API AWS Security Agent vers le modèle interne.

INCIDENT RÉEL (12 nov. 2026, banc réel sur le modèle officiel `securityagent`
2025-09-06) : la vraie API renvoie ses énumérations en **MAJUSCULES**
(`RiskLevel` = `CRITICAL`/`HIGH`/…, `ConfidenceLevel` = `HIGH`/`MEDIUM`/…), alors
que le modèle interne de Rempart (`common/models.py`) les déclare en casse
« Title » (`SEVERITIES = ("Critical", "High", …)`). La matrice de priorité
compare `severity == "Critical"` : aucune valeur réelle ne correspondait, donc
**toutes** les failles réelles tombaient en P4 sans échéance, et le garde-fou
EF-TRI-05 (`HIGH_SEVERITIES = {"Critical", "High"}`) ne se déclenchait jamais —
un modèle pouvait écarter seul un Critical comme faux positif.

Mesure sur 21 failles réelles, mêmes données, deux casses :

===============================  ========  ==================
                                 API réelle  doubles de test
===============================  ========  ==================
failles classées P1/P2                    0                  19
échéances contractuelles posées           0                  19
garde-fou EF-TRI-05 déclenché             0                   5
===============================  ========  ==================

La normalisation se fait **à la frontière** (intake), jamais en profondeur :
le reste du code continue de manipuler les valeurs internes de `models.py`.
Les tables ci-dessous sont totales — toute valeur officielle y figure, et un
test les compare à la fixture `tests/fixtures/securityagent_shapes.json`
(extrait du modèle botocore officiel) pour qu'aucune nouvelle valeur ne passe
inaperçue.
"""

from __future__ import annotations

from .models import CONFIDENCES, SEVERITIES

# `RiskLevel` officiel → `SEVERITIES` interne.
RISK_LEVEL_TO_SEVERITY: dict[str, str] = {
    "CRITICAL": "Critical",
    "HIGH": "High",
    "MEDIUM": "Medium",
    "LOW": "Low",
    # Un niveau inconnu ou purement informatif ne doit jamais être surévalué :
    # il retombe sur la sévérité la plus basse, donc P4 (aucune échéance).
    "INFORMATIONAL": "Informational",
    "UNKNOWN": "Informational",
}

# `ConfidenceLevel` officiel → `CONFIDENCES` interne. `UNCONFIRMED` et
# `FALSE_POSITIVE` sont ramenés à « Low » : dans les deux cas la matrice exigera
# une validation humaine plutôt que de faire confiance à l'agent.
CONFIDENCE_TO_INTERNAL: dict[str, str] = {
    "HIGH": "High",
    "MEDIUM": "Medium",
    "LOW": "Low",
    "UNCONFIRMED": "Low",
    "FALSE_POSITIVE": "Low",
}

DEFAULT_SEVERITY = "Medium"
DEFAULT_CONFIDENCE = "Medium"


def normalize_severity(raw: object, default: str = DEFAULT_SEVERITY) -> str:
    """Sévérité interne (`SEVERITIES`) depuis une valeur de l'API réelle.

    Accepte les deux casses : la normalisation est idempotente, donc une valeur
    déjà interne (« Critical », produite par un jeu de démonstration) ressort
    inchangée. Toute valeur non reconnue retombe sur `default` — jamais sur une
    sévérité inventée.
    """
    if not isinstance(raw, str) or not raw.strip():
        return default
    text = raw.strip()
    mapped = RISK_LEVEL_TO_SEVERITY.get(text.upper())
    if mapped is not None:
        return mapped
    return text if text in SEVERITIES else default


def normalize_confidence(raw: object, default: str = DEFAULT_CONFIDENCE) -> str:
    """Confiance interne (`CONFIDENCES`) depuis une valeur de l'API réelle."""
    if not isinstance(raw, str) or not raw.strip():
        return default
    text = raw.strip()
    mapped = CONFIDENCE_TO_INTERNAL.get(text.upper())
    if mapped is not None:
        return mapped
    return text if text in CONFIDENCES else default


__all__ = [
    "CONFIDENCE_TO_INTERNAL",
    "DEFAULT_CONFIDENCE",
    "DEFAULT_SEVERITY",
    "RISK_LEVEL_TO_SEVERITY",
    "normalize_confidence",
    "normalize_severity",
]
