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


def _origins(name: str) -> tuple[str, ...]:
    """Liste d'origines séparées par des virgules, normalisée (sans `/` final)."""
    raw = os.environ.get(name) or ""
    return tuple(
        origin[:-1] if origin.endswith("/") else origin
        for origin in (part.strip() for part in raw.split(","))
        if origin
    )


@dataclass
class Settings:
    table_prefix: str = "rempart-"
    region: str = "eu-west-3"
    hourly_rate: float = 50.0
    github_api: str = "https://api.github.com"
    github_owner: str = ""
    sa_endpoint_url: str | None = None
    # EF-RAP-04 : bucket où le dossier de preuves est réellement téléversé.
    # Absent = aucun stockage configuré : la route répond 501 au lieu de
    # renvoyer 201 avec une clé S3 qui ne pointe vers rien.
    reports_bucket: str | None = None
    # Origines autorisées pour CORS (liste séparée par des virgules). Vide =
    # comportement historique `*`, réservé au développement local
    # (`scripts/serve_local.py`) : en production l'IaC pose la liste réelle.
    cors_allow_origins: tuple[str, ...] = ()
    # Clé partagée du webhook CI/CD (`POST /v1/events/deployment`). Jamais
    # écrite en clair dans le template : l'IaC la lit depuis SSM.
    pipeline_key: str | None = None
    # Garde-fou anti-facture : aucun test réel sans éligibilité free tier
    # confirmée, et un plafond d'heures-tâches par test.
    free_tier_only: bool = True
    max_task_hours_per_test: float = 5.0
    # EF-ORC-05 : quota AWS de tests simultanés par compte et par région.
    concurrent_test_quota: int = 5

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
            reports_bucket=os.environ.get("REMPART_REPORTS_BUCKET") or None,
            cors_allow_origins=_origins("REMPART_CORS_ALLOW_ORIGINS"),
            pipeline_key=os.environ.get("REMPART_PIPELINE_KEY") or None,
            free_tier_only=_bool("REMPART_FREE_TIER_ONLY", True),
            max_task_hours_per_test=_float("REMPART_MAX_TASK_HOURS_PER_TEST", 5.0),
            concurrent_test_quota=int(
                _float("REMPART_CONCURRENT_TEST_QUOTA", 5.0)
            ),
        )
