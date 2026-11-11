"""Runtime settings loaded from environment (REMPART_ prefix).

Les réglages `free_tier_only` et `max_task_hours_per_test` forment le
**garde-fou anti-facture** : tant qu'ils sont actifs, Rempart refuse de lancer
un test dont l'éligibilité au free tier n'est pas confirmée, et arrête un test
qui dépasse le plafond d'heures-tâches autorisé pour un seul test.
"""

import os
from dataclasses import dataclass

TRUE_VALUES = ("1", "true", "yes", "on")


def _bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in TRUE_VALUES


def _float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    try:
        return float(raw) if raw else default
    except ValueError:
        return default


@dataclass
class Settings:
    table_prefix: str = "rempart-"
    region: str = "eu-west-3"
    hourly_rate: float = 50.0
    github_api: str = "https://api.github.com"
    github_owner: str = ""
    sa_endpoint_url: str | None = None
    # Garde-fou anti-facture : aucun test réel sans éligibilité free tier
    # confirmée, et un plafond d'heures-tâches par test.
    free_tier_only: bool = True
    max_task_hours_per_test: float = 5.0

    @classmethod
    def from_env(cls) -> "Settings":
        """Load settings from environment variables prefixed with REMPART_."""
        return cls(
            table_prefix=os.environ.get("REMPART_TABLE_PREFIX", "rempart-"),
            region=os.environ.get("REMPART_REGION", "eu-west-3"),
            hourly_rate=_float("REMPART_HOURLY_RATE", 50.0),
            github_api=os.environ.get("REMPART_GITHUB_API", "https://api.github.com"),
            github_owner=os.environ.get("REMPART_GITHUB_OWNER", ""),
            sa_endpoint_url=os.environ.get("REMPART_SA_ENDPOINT_URL") or None,
            free_tier_only=_bool("REMPART_FREE_TIER_ONLY", True),
            max_task_hours_per_test=_float("REMPART_MAX_TASK_HOURS_PER_TEST", 5.0),
        )
