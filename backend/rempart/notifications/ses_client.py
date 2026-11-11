"""Injectable SES client — same pattern as ``orchestrator.sa_client``.

Le client boto3 est créé paresseusement : importer ce module n'exige aucun
identifiant AWS, et les tests injectent un double via ``boto_client``.
L'adresse d'expédition est ``noreply@<REMPART_SES_FROM_DOMAIN>``, la seule
autorisée par la politique IAM de la stack CDK (``ses:FromAddress``).
"""

from __future__ import annotations

import os
from collections.abc import Sequence
from typing import Any

DEFAULT_REGION = "eu-west-3"
_CHARSET = "UTF-8"


class SesClient:
    """Thin wrapper over the boto3 ``ses`` client (``SendEmail`` API)."""

    def __init__(
        self,
        boto_client: Any = None,
        *,
        from_domain: str | None = None,
        configuration_set: str | None = None,
        region: str | None = None,
    ) -> None:
        self._client = boto_client
        self._from_domain = from_domain
        self._configuration_set = configuration_set
        self._region = region

    @property
    def client(self) -> Any:
        """Return the underlying boto3 client, creating it on first access."""
        if self._client is None:
            import boto3

            region = self._region or os.environ.get("REMPART_REGION") or DEFAULT_REGION
            self._client = boto3.client("ses", region_name=region)
        return self._client

    @property
    def from_address(self) -> str:
        """``noreply@<domaine>``, domaine lu dans l'environnement à l'appel."""
        domain = self._from_domain or os.environ.get("REMPART_SES_FROM_DOMAIN")
        if not domain:
            raise ValueError("REMPART_SES_FROM_DOMAIN is not set")
        return f"noreply@{domain}"

    @property
    def configuration_set(self) -> str | None:
        """Configuration set SES (livraison, TLS REQUIRE) lu dans l'environnement."""
        return (
            self._configuration_set
            or os.environ.get("REMPART_SES_CONFIGURATION_SET")
            or None
        )

    def send(
        self,
        to: str | Sequence[str],
        subject: str,
        body_html: str,
        body_text: str,
    ) -> dict[str, Any]:
        """Send one e-mail (HTML + plain text) and return the raw SES response."""
        recipients = [to] if isinstance(to, str) else list(to)
        if not recipients:
            raise ValueError("no recipient: refusing to send an empty e-mail")
        message: dict[str, Any] = {
            "Source": self.from_address,
            "Destination": {"ToAddresses": recipients},
            "Message": {
                "Subject": {"Data": subject, "Charset": _CHARSET},
                "Body": {
                    "Html": {"Data": body_html, "Charset": _CHARSET},
                    "Text": {"Data": body_text, "Charset": _CHARSET},
                },
            },
        }
        configuration_set = self.configuration_set
        if configuration_set:
            message["ConfigurationSetName"] = configuration_set
        return dict(self.client.send_email(**message))
