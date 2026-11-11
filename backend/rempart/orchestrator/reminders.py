"""Relances d'échéance (EF-COR-06) — « relancer avant et après l'échéance,
puis alerter le responsable de compte ».

Le balayeur tourne en boucle (EventBridge). Sans garde-fou, il renverrait la
même relance à chaque passage : c'est le bruit qui fait ignorer les alertes.

**Anti-spam sans toucher au modèle de données** : chaque relance est tracée
dans le journal d'audit existant (`append_audit` avec l'action
``finding.reminder_sent`` et le type de relance en ``result``). Avant de
relancer, on relit ce journal. Deux avantages : la trace est visible d'un
auditeur, et aucun champ n'est ajouté à `Finding`.

**Escalade** : `notifications.kinds` ne connaît qu'un seul kind d'échéance
(`DEADLINE_OVERDUE`). Plutôt que d'en inventer un second dans un module qui
n'est pas le sien, on réutilise ce kind et on marque l'escalade dans
l'événement (`"escalated": True`) et dans l'audit (`result="escalate"`).
Le gabarit actuel l'ignore ; un gabarit dédié pourra le lire plus tard.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from rempart.common.models import Finding
from rempart.common.timeutil import parse_iso, utcnow
from rempart.notifications import kinds

from .task_types import Deps

# Une faille fermée, écartée ou dont le risque est accepté ne se relance pas.
OPEN_STATUSES = frozenset(
    {"new", "pending_validation", "confirmed", "in_remediation", "to_retest", "reopened"}
)
REMINDER_ACTION = "finding.reminder_sent"
UPCOMING = "upcoming"
OVERDUE = "overdue"
ESCALATE = "escalate"
REMINDER_TYPES = (UPCOMING, OVERDUE, ESCALATE)

DEFAULT_BEFORE_DAYS = 2
DEFAULT_AFTER_DAYS = 2
SECONDS_PER_DAY = 86_400


def days_from_due(due_at: str | None, now: datetime) -> float | None:
    """Jours restants avant l'échéance (négatif = dépassée). ``None`` si P4."""
    if not due_at:
        return None
    try:
        return (parse_iso(due_at) - now).total_seconds() / SECONDS_PER_DAY
    except ValueError:
        return None


def classify(
    finding: Finding, now: datetime, before_days: int, after_days: int
) -> str | None:
    """Type de relance pour une faille, ou ``None`` si rien à signaler."""
    if finding.status not in OPEN_STATUSES:
        return None
    remaining = days_from_due(finding.due_at, now)
    if remaining is None:
        return None  # P4 : « prochaine version », aucune échéance datée
    if remaining < -after_days:
        return ESCALATE
    if remaining < 0:
        return OVERDUE
    if remaining <= before_days:
        return UPCOMING
    return None


def already_notified(deps: Deps, finding_id: str, reminder_type: str) -> bool:
    """Une relance de CE type a-t-elle déjà été envoyée pour cette faille ?"""
    events = deps.store.list_audit(
        object_type="finding", object_id=finding_id, action=REMINDER_ACTION, limit=100
    )
    return any(event.result == reminder_type for event in events)


def reminder_event(
    tenant_id: str, finding: Finding, reminder_type: str, remaining: float
) -> dict[str, Any]:
    """Événement au format attendu par ``notifications.handler.lambda_handler``."""
    days_overdue = max(0, int(round(-remaining)))
    return {
        "kind": kinds.DEADLINE_OVERDUE,
        "tenant_id": tenant_id,
        "app_id": finding.app_id,
        "finding_id": finding.finding_id,
        "finding_title": finding.title,
        "priority": finding.priority,
        "due_at": finding.due_at or "",
        "days_overdue": days_overdue,
        "escalated": reminder_type == ESCALATE,
        "reminder_type": reminder_type,
    }


def notify(deps: Deps, event: dict[str, Any]) -> None:
    """Envoie via le module notifications ; un échec ne casse jamais le balayage."""
    try:
        from rempart.notifications.handler import lambda_handler

        lambda_handler(event, None, store=deps.store)
    except Exception:  # noqa: BLE001 - une relance ratée ne bloque pas les autres
        deps.store.append_audit(
            "reminders", REMINDER_ACTION, "finding", str(event.get("finding_id")), "error"
        )


def scan_deadlines(
    deps: Deps,
    *,
    now: datetime | None = None,
    before_days: int = DEFAULT_BEFORE_DAYS,
    after_days: int = DEFAULT_AFTER_DAYS,
    tenant_id: str | None = None,
) -> dict[str, Any]:
    """Balaye les failles ouvertes et relance celles qui approchent ou dérapent.

    ``now`` est injectable : les tests ne dépendent jamais de l'heure réelle.
    ``tenant_id`` borne le balayage à un client (cloisonnement).
    """
    moment = now or utcnow()
    buckets: dict[str, list[str]] = {kind: [] for kind in REMINDER_TYPES}
    notified = 0

    findings = deps.store.list_findings(tenant_id=tenant_id, limit=1000)
    for finding in findings:
        reminder_type = classify(finding, moment, before_days, after_days)
        if reminder_type is None:
            continue
        buckets[reminder_type].append(finding.finding_id)
        if already_notified(deps, finding.finding_id, reminder_type):
            continue
        remaining = days_from_due(finding.due_at, moment) or 0.0
        event = reminder_event(
            finding.tenant_id, finding, reminder_type, remaining
        )
        notify(deps, event)
        deps.store.append_audit(
            "reminders",
            REMINDER_ACTION,
            "finding",
            finding.finding_id,
            reminder_type,
        )
        notified += 1

    return {
        "upcoming": buckets[UPCOMING],
        "overdue": buckets[OVERDUE],
        "escalate": buckets[ESCALATE],
        "notified": notified,
        "scanned_at": moment.isoformat(),
    }


def lambda_handler(event: dict[str, Any], context: Any = None) -> dict[str, Any]:
    """Point d'entrée planifié (EventBridge) : ne lève jamais."""
    from rempart.orchestrator.lambda_handlers import build_deps

    try:
        deps = build_deps()
        return scan_deadlines(
            deps,
            before_days=int((event or {}).get("before_days", DEFAULT_BEFORE_DAYS)),
            after_days=int((event or {}).get("after_days", DEFAULT_AFTER_DAYS)),
            tenant_id=(event or {}).get("tenant_id"),
        )
    except Exception as exc:  # noqa: BLE001 - un balayeur ne doit jamais planter
        return {"error": f"{type(exc).__name__}: {exc}", "notified": 0}
