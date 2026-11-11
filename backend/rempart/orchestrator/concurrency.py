"""Quota de tests simultanés par compte client (EF-ORC-05).

La documentation AWS impose **5 tests simultanés par compte et par région**
(quota non ajustable — chapitre 11.1 du cahier des charges). Sans file
d'attente, un sixième test lancé en parallèle sur le même compte échoue côté
AWS, et l'échec n'est rejoué par personne : le client perd sa fenêtre de
livraison sans le savoir.

On compte donc les runs non terminés du tenant et on refuse quand la limite est
atteinte. La limite est configurable : tous les comptes n'ont pas le même
quota, et il peut être relevé par AWS sans que le code change.
"""

from __future__ import annotations

from typing import Any

# Quota AWS par compte et par région (non ajustable) — chapitre 11.1.
DEFAULT_CONCURRENT_TEST_QUOTA = 5

# Un run dans l'un de ces états occupe encore une place côté AWS.
BLOCKING_STATUSES = ("queued", "running")


def count_running(store: Any, tenant_id: str) -> int:
    """Nombre de tests du tenant qui occupent encore une place.

    Un test terminé, en échec ou arrêté ne bloque plus rien.
    """
    runs = store.list_runs(tenant_id=tenant_id, limit=1000)
    return sum(1 for run in runs if run.status in BLOCKING_STATUSES)


def can_start(
    store: Any, tenant_id: str, *, limit: int = DEFAULT_CONCURRENT_TEST_QUOTA
) -> tuple[bool, int]:
    """Rend ``(autorisé, occupation)``. Refuse quand le quota est atteint."""
    running = count_running(store, tenant_id)
    if limit <= 0:
        return True, running
    return running < limit, running


def quota_of(settings: Any) -> int:
    """Quota effectif : surcharge par les réglages, sinon le quota AWS."""
    value = getattr(settings, "concurrent_test_quota", None)
    if isinstance(value, int) and value > 0:
        return value
    return DEFAULT_CONCURRENT_TEST_QUOTA
