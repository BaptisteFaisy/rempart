"""Runtime settings loaded from environment (REMPART_ prefix)."""

import os
from dataclasses import dataclass


@dataclass
class Settings:
    table_prefix: str = "rempart-"
    region: str = "eu-west-3"
    hourly_rate: float = 50.0
    github_api: str = "https://api.github.com"
    github_owner: str = ""
    sa_endpoint_url: str | None = None

    @classmethod
    def from_env(cls) -> "Settings":
        """Load settings from environment variables prefixed with REMPART_."""
        raw_rate = os.environ.get("REMPART_HOURLY_RATE")
        rate = float(raw_rate) if raw_rate else 50.0
        return cls(
            table_prefix=os.environ.get("REMPART_TABLE_PREFIX", "rempart-"),
            region=os.environ.get("REMPART_REGION", "eu-west-3"),
            hourly_rate=rate,
            github_api=os.environ.get("REMPART_GITHUB_API", "https://api.github.com"),
            github_owner=os.environ.get("REMPART_GITHUB_OWNER", ""),
            sa_endpoint_url=os.environ.get("REMPART_SA_ENDPOINT_URL") or None,
        )
