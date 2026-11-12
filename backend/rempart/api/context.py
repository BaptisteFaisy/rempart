"""API invocation context and helper functions (chapter 14)."""

from dataclasses import dataclass, field
from typing import Any

from rempart.common.config import Settings
from rempart.common.models import AuditEvent
from rempart.common.store import Store
from rempart.common.tenant import Principal


@dataclass
class ApiContext:
    """Carries request metadata, authenticated principal, and injected services."""

    principal: Principal | None
    path_params: dict[str, str] = field(default_factory=dict)
    query: dict[str, str] = field(default_factory=dict)
    body: dict[str, Any] = field(default_factory=dict)
    headers: dict[str, str] = field(default_factory=dict)
    store: Store | None = None
    settings: Settings | None = None
    sa: Any = None
    # Client S3 du dossier de preuves (EF-RAP-04) : `None` quand aucun bucket
    # n'est configuré — la route répond alors 501 au lieu d'annoncer une clé
    # qui ne pointe vers rien.
    s3: Any = None
    # Origine de la requête, pour un CORS restreint aux origines autorisées.
    origin: str | None = None

    def audit(
        self,
        action: str,
        obj_type: str,
        obj_id: str,
        result: str = "ok",
    ) -> AuditEvent | None:
        """Helper to record an audit trail entry if store is present."""
        if not self.store:
            return None
        actor = self.principal.user_id if self.principal else "anonymous"
        return self.store.append_audit(
            actor=actor,
            action=action,
            object_type=obj_type,
            object_id=obj_id,
            result=result,
        )
