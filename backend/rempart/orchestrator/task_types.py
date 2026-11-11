"""Types et helpers partagés par les tâches de l'orchestrateur.

Module isolé pour éviter tout import circulaire entre ``tasks``,
``findings_intake`` et ``triage_dispatch`` : ces trois modules dépendent de
celui-ci, jamais l'inverse.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from rempart.common.config import Settings
from rempart.common.models import Application, Tenant
from rempart.common.timeutil import utcnow

SENSITIVE_DATA_TYPES = ("personal", "payment", "health")
TERMINAL_STATUSES = ("completed", "failed", "stopped")


@dataclass
class Deps:
    """Dependencies injected in every task (store, AWS client, settings)."""

    store: Any
    sa: Any
    settings: Settings = None  # type: ignore[assignment]
    github: Any = None
    model_client: Any = None

    def __post_init__(self) -> None:
        if self.settings is None:
            self.settings = Settings()


def tenant_of(deps: Deps, tenant_id: str) -> Tenant | None:
    return deps.store.get_tenant(tenant_id)


def app_of(deps: Deps, app_id: str) -> Application | None:
    return deps.store.get_application(app_id)


def month_now() -> str:
    return utcnow().strftime("%Y-%m")


def sensitive_data(app: Application) -> bool:
    """True si l'application traite des données personnelles, de paiement ou de santé."""
    return any(dt in SENSITIVE_DATA_TYPES for dt in (app.data_types or []))


def exposed_critical(app: Application) -> bool:
    """True si l'application est exposée à Internet ET de criticité haute."""
    return bool(app.internet_exposed) and app.criticality == "high"
