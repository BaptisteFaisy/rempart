"""Rate-limiter en mémoire pour le webhook CI/CD.

Limite le nombre d'événements acceptés par fenêtre, par dépôt. C'est un garde
contre le « flood » d'un pipeline mal configuré (et contre l'abus du seul
point d'entrée sans jeton).

Limite assumée : ce limiteur est **par instance Lambda**. Deux instances chaudes
simultanées ont chacune leur compteur. Pour une démo c'est suffisant ; la
version réellement distribuée (compteur atomique DynamoDB) est notée ici comme
suite.
"""

from __future__ import annotations

import os
import threading
import time

WINDOW_SECONDS = float(os.environ.get("REMPART_WEBHOOK_WINDOW", "60"))
MAX_PER_WINDOW = int(os.environ.get("REMPART_WEBHOOK_LIMIT", "30"))

_lock = threading.Lock()
_timestamps: dict[str, list[float]] = {}


def _now() -> float:
    return time.monotonic()


def allow(key: str, *, limit: int | None = None, window_s: float | None = None) -> bool:
    """Vrai si la clé peut envoyer un événement de plus dans la fenêtre."""
    limit = limit if limit is not None else MAX_PER_WINDOW
    window_s = window_s if window_s is not None else WINDOW_SECONDS
    moment = _now()
    with _lock:
        stamps = _timestamps.get(key, [])
        stamps = [t for t in stamps if moment - t < window_s]
        if len(stamps) >= limit:
            _timestamps[key] = stamps
            return False
        stamps.append(moment)
        _timestamps[key] = stamps
        return True


def reset() -> None:
    """Vide tous les compteurs (tests)."""
    with _lock:
        _timestamps.clear()


__all__ = ["MAX_PER_WINDOW", "WINDOW_SECONDS", "allow", "reset"]
