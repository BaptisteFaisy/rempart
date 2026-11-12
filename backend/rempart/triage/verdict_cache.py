"""Cache des verdicts du triage, par lot.

Évite de rappeler le modèle pour un LOT de failles déjà trié dans le même
processus — le cas réel est le rejeu (Step Functions qui relance une tâche, ou
un `dispatch_triage` exécuté deux fois pour le même run). Le modèle coûtant du
temps et de l'argent, on réutilise le verdict déjà obtenu.

Limites assumées, documentées honnêtement : ce cache est **en mémoire** (un
processus Lambda est éphémère, on ne promet donc aucune déduplication entre
deux invocations distinctes). La mémoire durable entre les runs, elle, vient
déjà du store via `past_decisions`.
"""

from __future__ import annotations

import copy
import threading
from typing import Any

_lock = threading.Lock()
_batches: dict[tuple[str, ...], list[Any]] = {}


def _key(fingerprints: list[str]) -> tuple[str, ...]:
    return tuple(sorted(fingerprints))


def get_batch(fingerprints: list[str]) -> list[Any] | None:
    """Les verdicts déjà calculés pour ce LOT exact de failles, ou ``None``."""
    with _lock:
        return copy.deepcopy(_batches.get(_key(fingerprints)))


def put_batch(fingerprints: list[str], proposals: list[Any]) -> None:
    """Mémorise les verdicts calculés pour ce lot."""
    with _lock:
        _batches[_key(fingerprints)] = copy.deepcopy(list(proposals))


def reset() -> None:
    """Vide le cache (tests)."""
    with _lock:
        _batches.clear()


__all__ = ["get_batch", "put_batch", "reset"]
