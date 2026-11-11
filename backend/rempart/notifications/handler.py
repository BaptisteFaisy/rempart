"""Lambda handler for SES notifications — ``rempart.notifications.handler``.

Le nom ``lambda_handler`` est celui référencé par la stack CDK
(``iac/control-plane/stacks/notifications.py``). Contrat (CONTRACT-PHASE0 § 4) :

- distribue selon ``event["kind"]`` (constantes de ``kinds.py``) ;
- destinataires résolus depuis ``Tenant.contacts`` (filtrés par rôle/souscription) ;
- rend ``{"sent": n, "skipped": n, "errors": [...]}`` ;
- **aucune exception ne sort** : un échec d'envoi est journalisé et compté dans
  ``errors`` ; un kind inconnu ou un tenant sans destinataire → ``skipped`` ;
- store et client SES injectables (``store=``, ``ses=``) pour les tests.

Événement attendu::

    {"kind": "critical_finding_confirmed", "tenant_id": "t-1", ...champs du kind}
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from rempart.common.models import Application, Tenant

from . import kinds, templates
from .ses_client import SesClient

logger = logging.getLogger(__name__)

# Chaque rendu reçoit le store (nom d'application), le tenant (nom du client)
# et l'événement ; il rend (subject, body_html, body_text).
Renderer = Callable[[Any, Tenant, dict[str, Any]], tuple[str, str, str]]


def _application_name(store: Any, event: dict[str, Any]) -> str:
    """Nom de l'application cité dans le corps, résolu depuis le store si besoin."""
    if event.get("application_name"):
        return str(event["application_name"])
    app_id = event.get("app_id")
    if not app_id:
        return "unknown application"
    app: Application | None = store.get_application(str(app_id))
    return app.name if app else str(app_id)


def _render_critical(store: Any, tenant: Tenant, event: dict[str, Any]) -> tuple[str, str, str]:
    return templates.critical_finding_confirmed(
        client=tenant.name,
        application=_application_name(store, event),
        finding_title=str(event.get("finding_title", "Finding")),
        finding_id=str(event.get("finding_id", "")),
        priority=str(event.get("priority", "P1")),
        due_at=str(event.get("due_at", "")),
    )


def _render_blocked(store: Any, tenant: Tenant, event: dict[str, Any]) -> tuple[str, str, str]:
    return templates.delivery_blocked(
        client=tenant.name,
        application=_application_name(store, event),
        blocking_threshold=str(event.get("blocking_threshold", "")),
        finding_title=str(event.get("finding_title", "Finding")),
        priority=str(event.get("priority", "P1")),
        due_at=str(event.get("due_at", "")),
    )


def _render_overdue(store: Any, tenant: Tenant, event: dict[str, Any]) -> tuple[str, str, str]:
    return templates.deadline_overdue(
        client=tenant.name,
        application=_application_name(store, event),
        finding_title=str(event.get("finding_title", "Finding")),
        priority=str(event.get("priority", "P2")),
        due_at=str(event.get("due_at", "")),
        days_overdue=int(event.get("days_overdue", 0)),
    )


def _render_budget(store: Any, tenant: Tenant, event: dict[str, Any]) -> tuple[str, str, str]:
    return templates.budget_threshold(
        client=tenant.name,
        threshold_percent=int(event.get("threshold_percent", 0)),
        hours_used=float(event.get("hours_used") or 0.0),
        monthly_budget_hours=float(event.get("monthly_budget_hours", tenant.monthly_budget_hours)),
        month=str(event.get("month", "")),
    )


def _render_digest(store: Any, tenant: Tenant, event: dict[str, Any]) -> tuple[str, str, str]:
    return templates.weekly_digest(
        client=tenant.name,
        period=str(event.get("period", "")),
        tests_run=int(event.get("tests_run", 0)),
        findings_opened=int(event.get("findings_opened", 0)),
        findings_closed=int(event.get("findings_closed", 0)),
        overdue=int(event.get("overdue", 0)),
        hours_used=float(event.get("hours_used", 0.0)),
    )


_RENDERERS: dict[str, Renderer] = {
    kinds.CRITICAL_FINDING_CONFIRMED: _render_critical,
    kinds.DELIVERY_BLOCKED: _render_blocked,
    kinds.DEADLINE_OVERDUE: _render_overdue,
    kinds.BUDGET_THRESHOLD: _render_budget,
    kinds.WEEKLY_DIGEST: _render_digest,
}


def _send_all(
    ses: Any, recipients: list[str], email: tuple[str, str, str]
) -> tuple[int, list[str]]:
    """Envoie à chaque destinataire ; un échec est compté, jamais propagé."""
    subject, body_html, body_text = email
    sent = 0
    errors: list[str] = []
    for address in recipients:
        try:
            ses.send(address, subject, body_html, body_text)
            sent += 1
        except Exception as exc:  # contrat : une notification ne casse jamais rien
            logger.warning("SES send failed for %s: %s", address, exc)
            errors.append(f"{address}: {exc}")
    return sent, errors


def _process(event: dict[str, Any], store: Any, ses: Any) -> dict[str, Any]:
    """Cœur du traitement : résolution du tenant, rendu, envois."""
    kind = str(event.get("kind", ""))
    if kind not in _RENDERERS:
        logger.info("Unknown notification kind %r — skipped", kind)
        return {"sent": 0, "skipped": 1, "errors": []}

    tenant: Tenant | None = store.get_tenant(str(event.get("tenant_id", "")))
    if tenant is None:
        logger.warning("Tenant %r not found — skipped", event.get("tenant_id"))
        return {"sent": 0, "skipped": 1, "errors": []}

    recipients = kinds.resolve_recipients(tenant.contacts, kind)
    if not recipients:
        logger.info("No recipient for kind %r tenant %s — skipped", kind, tenant.tenant_id)
        return {"sent": 0, "skipped": 1, "errors": []}

    email = _RENDERERS[kind](store, tenant, event)
    sent, errors = _send_all(ses, recipients, email)
    return {"sent": sent, "skipped": 0, "errors": errors}


def lambda_handler(
    event: dict[str, Any],
    context: Any = None,
    *,
    store: Any = None,
    ses: Any = None,
) -> dict[str, Any]:
    """Point d'entrée Lambda : ne lève jamais, rend sent/skipped/errors."""
    try:
        if store is None:
            from rempart.common.config import Settings
            from rempart.common.store import Store

            store = Store(table_prefix=Settings.from_env().table_prefix)
        if ses is None:
            ses = SesClient()
        return _process(event or {}, store, ses)
    except Exception as exc:  # contrat : aucune exception ne sort du handler
        logger.exception("Notification handler failed")
        return {"sent": 0, "skipped": 0, "errors": [f"handler: {exc}"]}
