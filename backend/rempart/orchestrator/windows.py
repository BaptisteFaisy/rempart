"""Fenêtres de test par application (EF-ORC-08, chapitre 15.1).

« Par défaut les tests visent la préproduction. Un test en production exige
une fenêtre convenue. » Aucun test complet ne part en production hors d'une
fenêtre définie sur l'application.

Format d'une fenêtre (voir la docstring de ``Application``) :
``{"days": ["mon", "tue"], "start": "22:00", "end": "06:00",
"environment": "production"}`` — heures en **UTC**, ``days`` liste les jours
où la fenêtre démarre (vide/absent = tous les jours), ``start > end`` traverse
minuit et ``start == end`` couvre 24 h.

La logique est **pure** : ``is_within_window`` reçoit l'instant à évaluer en
paramètre, jamais l'horloge système — les tests sont déterministes.
"""

from __future__ import annotations

from datetime import datetime, time
from typing import Any

DAY_NAMES = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")


def _parse_hhmm(value: Any) -> time | None:
    """Convertit ``"HH:MM"`` en ``time`` ; ``None`` si le format est invalide."""
    if not isinstance(value, str):
        return None
    parts = value.strip().split(":")
    if len(parts) != 2:
        return None
    try:
        hour, minute = int(parts[0]), int(parts[1])
    except ValueError:
        return None
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return None
    return time(hour, minute)


def _window_days(window: dict[str, Any]) -> frozenset[int] | None:
    """Jours de démarrage de la fenêtre (index ``weekday``), ``None`` = tous.

    Une liste vide ou absente couvre les sept jours ; un nom de jour non
    reconnu ne correspond à rien (plutôt que d'ouvrir la fenêtre en grand).
    """
    raw = window.get("days")
    if not isinstance(raw, list) or not raw:
        return None
    return frozenset(
        DAY_NAMES.index(name.strip().lower()[:3])
        for name in raw
        if isinstance(name, str) and name.strip().lower()[:3] in DAY_NAMES
    )


def _covers_moment(window: dict[str, Any], moment: datetime) -> bool:
    """True si ``moment`` tombe dans la fenêtre, minuit traversé compris."""
    start = _parse_hhmm(window.get("start"))
    end = _parse_hhmm(window.get("end"))
    if start is None or end is None:
        return False
    days = _window_days(window)
    weekday = moment.weekday()
    clock = moment.time()
    today_ok = days is None or weekday in days
    yesterday_ok = days is None or (weekday - 1) % 7 in days
    if start == end:
        return today_ok  # fenêtre de 24 h
    if start < end:
        return today_ok and start <= clock < end
    # Traverse minuit : commencée ce soir, ou finie ce matin (ouverte la veille).
    return (today_ok and clock >= start) or (yesterday_ok and clock < end)


def _applies_to(window: dict[str, Any], environment: str | None) -> bool:
    """True si la fenêtre vise l'environnement testé (absent = tous)."""
    if environment is None:
        return True
    wanted = str(window.get("environment") or "").strip().lower()
    return not wanted or wanted == environment.strip().lower()


def is_within_window(
    windows: list[dict[str, Any]] | None,
    moment: datetime,
    *,
    environment: str | None = None,
) -> bool:
    """True si ``moment`` tombe dans au moins une fenêtre applicable.

    ``windows`` vient de ``Application.test_windows`` ; ``environment`` filtre
    les fenêtres qui ciblent explicitement un autre environnement. Une liste
    vide ne couvre jamais rien : à l'appelant de décider si c'est bloquant.
    """
    return any(
        _covers_moment(window, moment)
        for window in windows or []
        if isinstance(window, dict) and _applies_to(window, environment)
    )
