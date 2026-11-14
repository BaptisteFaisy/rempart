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
    # Corps **brut** de la requête, tel qu'arrivé. Indispensable au webhook
    # GitHub : sa signature porte sur ces octets, pas sur un JSON ré-écrit —
    # hacher le dictionnaire analysé donnerait une signature différente.
    raw_body: str | None = None
    # Démarreur d'exécutions de la machine de retest (idée #51). `None` quand
    # aucune machine n'est configurée : la route pose l'état et le dit, au lieu
    # d'annoncer un retest qui ne partira jamais.
    retest: Any = None

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
