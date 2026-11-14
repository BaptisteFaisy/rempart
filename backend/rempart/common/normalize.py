"""Normalisation des valeurs écrites par un modèle de langage.

Pourquoi ce module est séparé : ces trois helpers étaient privés de
`triage/proposal.py`, et la revue de code (`review/`) a exactement le même
besoin — un commentaire du modèle porte un booléen (`blocking`) et une liste de
références. Une seule implémentation pour les deux, paramétrée par appelant.

INCIDENT MESURÉ (13/11/2026, production) : `bool("false")` vaut **True** en
Python. La décision stockée portait `isRegression: true` alors que le modèle
affirmait `false`. De même, un modèle imbrique volontiers une liste
(`references: ["item"]` au lieu de `["CWE-639"]`). Les valeurs sont donc
normalisées **à la frontière du modèle**, jamais crues.
"""

from __future__ import annotations

from typing import Any

#: Ce qu'un modèle peut écrire pour « faux » : la chaîne « false » est vraie en
#: Python (`bool("false")` → True), c'est exactement le piège mesuré le 13/11.
FALSEY = frozenset({"false", "no", "0", "none", "null", "", "nil"})


def as_bool(value: Any) -> bool:
    """Lit un booléen venu d'un modèle : vrai, faux, ou « false » en chaîne."""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        return value.strip().lower() not in FALSEY
    return bool(value)


def as_optional_id(value: Any) -> str | None:
    """Un identifiant absent : ``None``, pas la chaîne « false » ni ``False``."""
    if value is None or isinstance(value, bool):
        return None
    text = str(value).strip()
    if text.lower() in FALSEY:
        return None
    return text or None


def as_flat_strings(value: Any) -> list[str]:
    """Liste de références : chaînes, à plat, sans doublon ni entrée vide."""
    if not value:
        return []
    if isinstance(value, str):
        value = [value]
    flat: list[str] = []
    for item in value:
        if isinstance(item, (list, tuple, set)):
            flat.extend(as_flat_strings(item))
            continue
        text = str(item).strip()
        if text and text not in flat:
            flat.append(text)
    return flat


__all__ = ["FALSEY", "as_bool", "as_flat_strings", "as_optional_id"]
