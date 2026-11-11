"""Notification kinds — EF-NOT-01 / EF-NOT-02 (cahier des charges § 9.6).

Un kind = une constante. Aucune chaîne magique n'est répétée ailleurs : le
handler, les gabarits et les producteurs d'événements importent ces noms.
"""

from __future__ import annotations

# EF-NOT-01 (M) — les quatre événements qui déclenchent un e-mail.
CRITICAL_FINDING_CONFIRMED = "critical_finding_confirmed"
DELIVERY_BLOCKED = "delivery_blocked"
DEADLINE_OVERDUE = "deadline_overdue"
BUDGET_THRESHOLD = "budget_threshold"

# EF-NOT-02 (S) — résumé hebdomadaire. Le gabarit et le kind existent, mais
# aucun ordonnanceur ne le déclenche en phase 0.
WEEKLY_DIGEST = "weekly_digest"

EF_NOT_01_KINDS: tuple[str, ...] = (
    CRITICAL_FINDING_CONFIRMED,
    DELIVERY_BLOCKED,
    DEADLINE_OVERDUE,
    BUDGET_THRESHOLD,
)
ALL_KINDS: tuple[str, ...] = (*EF_NOT_01_KINDS, WEEKLY_DIGEST)

# Rôles de contact (facultatif dans ``Tenant.contacts``). Un contact **sans**
# rôle, ou avec un rôle inconnu ci-dessous, reçoit tous les kinds : une
# notification ne doit jamais disparaître silencieusement.
ROLE_BILLING = "billing"
ROLE_SECURITY = "security"
ROLE_MANAGER = "manager"

_SECURITY_KINDS = frozenset(
    {CRITICAL_FINDING_CONFIRMED, DELIVERY_BLOCKED, DEADLINE_OVERDUE, WEEKLY_DIGEST}
)
_BUDGET_KINDS = frozenset({BUDGET_THRESHOLD, WEEKLY_DIGEST})

KINDS_BY_ROLE: dict[str, frozenset[str]] = {
    ROLE_SECURITY: _SECURITY_KINDS,
    ROLE_MANAGER: _SECURITY_KINDS,
    ROLE_BILLING: _BUDGET_KINDS,
}


def resolve_recipients(contacts: list[dict[str, object]] | None, kind: str) -> list[str]:
    """Adresses e-mail d'un tenant pour un kind, dédupliquées, ordre conservé.

    Règles (contrat § 4) :
    - un contact sans ``email`` est ignoré ;
    - un contact qui précise ``role`` ne reçoit que les kinds de ce rôle
      (rôle inconnu → tout reçoit, pas de perte silencieuse) ;
    - un contact qui précise ``kinds`` ne reçoit que ceux-là.
    """
    recipients: list[str] = []
    for contact in contacts or []:
        if not isinstance(contact, dict):
            continue
        email = str(contact.get("email") or "").strip()
        if not email or email in recipients:
            continue
        if not _contact_wants(contact, kind):
            continue
        recipients.append(email)
    return recipients


def _contact_wants(contact: dict[str, object], kind: str) -> bool:
    """Filtre par souscription explicite (``kinds``) puis par rôle (``role``)."""
    wanted = contact.get("kinds")
    if isinstance(wanted, (list, tuple, set)) and wanted and kind not in wanted:
        return False
    role = str(contact.get("role") or "").strip().lower()
    allowed = KINDS_BY_ROLE.get(role)
    return allowed is None or kind in allowed
