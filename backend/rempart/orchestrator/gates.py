"""Gardes d'entrée d'un test : mandat, free tier, quota, fenêtre, budget.

Isolées de :mod:`rempart.orchestrator.tasks` pour rester sous la limite de
500 lignes par fichier. `budget_gate` est ré-exporté par ``tasks`` : le contrat
public (nom du handler, forme du payload) ne change pas.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from rempart.common.budget import check_budget
from rempart.common.models import Tenant
from rempart.common.timeutil import parse_iso, utcnow

from .concurrency import can_start, quota_of
from .task_types import Deps, app_of, month_now, tenant_of
from .windows import is_within_window

# Alias locaux pour rester lisible dans ce module.
_tenant_of = tenant_of
_app_of = app_of
_month_now = month_now


# --------------------------------------------------------------------------- #
# 1. Budget gate (R8, R12) + fenêtres de test (EF-ORC-08)
# --------------------------------------------------------------------------- #
def _test_kind(payload: dict[str, Any]) -> str:
    """Type du test visé : ``delivery`` (porte CI/CD) ou ``full`` (test complet).

    ``kind`` vient du payload quand la machine à états le porte ; un
    déclenchement CI/CD est la porte de livraison (la découverte ne suit que
    des configurations ``delivery``). Dans le doute, le test est traité comme
    complet : en production, il exigera une fenêtre plutôt que de passer.
    """
    kind = str(payload.get("kind") or "").strip().lower()
    if kind:
        return kind
    return "delivery" if payload.get("trigger") == "cicd" else "full"


def _refuse_outside_window(
    payload: dict[str, Any], deps: Deps, now: datetime | None
) -> dict[str, Any] | None:
    """EF-ORC-08 : refuse un test complet en production hors fenêtre convenue.

    Renvoie le payload de refus, ou ``None`` quand le test peut partir. Les
    tests en préproduction et la porte CI/CD (``delivery``) ne sont pas
    concernés : bloquer une livraison n'attend pas une fenêtre. L'instant
    évalué est injectable (``now`` ou ``payload["moment"]``) pour des tests
    déterministes ; à défaut, l'heure UTC courante.
    """
    app_id = str(payload.get("app_id") or "")
    app = _app_of(deps, app_id)
    environment = str(
        payload.get("environment") or (app.environment if app else "") or ""
    ).strip().lower()
    if _test_kind(payload) != "full" or environment != "production":
        return None

    moment = now
    if moment is None:
        moment = parse_iso(str(payload["moment"])) if payload.get("moment") else utcnow()
    windows = app.test_windows if app else []
    if is_within_window(windows, moment, environment=environment):
        return None

    deps.store.append_audit(
        "orchestrator", "run.refused_outside_window", "app", app_id, "denied"
    )
    return {**payload, "allowed": False, "reason": "outside_test_window"}


def _refuse(
    payload: dict[str, Any],
    deps: Deps,
    tenant_id: str,
    reason: str,
    audit_action: str,
) -> dict[str, Any]:
    """Refus tracé dans l'audit : aucun garde-fou ne refuse en silence."""
    deps.store.append_audit(
        "orchestrator", audit_action, "tenant", tenant_id, "denied"
    )
    return {**payload, "allowed": False, "reason": reason}


def _refuse_kill_switch(
    payload: dict[str, Any], deps: Deps, tenant_id: str
) -> dict[str, Any] | None:
    """Coupe-circuit global : quand il est levé, aucun test ne démarre (R8).

    Indépendant du mandat, du free tier, du quota, de la fenêtre et du budget :
    c'est un arrêt d'urgence côté exploitation, évalué avant tout autre garde.
    """
    if not deps.settings.kill_switch:
        return None
    return _refuse(payload, deps, tenant_id, "kill_switch", "run.refused_kill_switch")


def _refuse_mandate(
    payload: dict[str, Any], deps: Deps, tenant: Tenant, tenant_id: str
) -> dict[str, Any] | None:
    """Pas de mandat valide, pas de test (article 323-1 : c'est un délit)."""
    if tenant.mandate_status == "valid":
        return None
    return _refuse(payload, deps, tenant_id, "mandate_invalid", "run.refused_mandate")


def _refuse_free_tier(
    payload: dict[str, Any], deps: Deps, tenant: Tenant, tenant_id: str
) -> dict[str, Any] | None:
    """Garde-fou anti-facture : 50 $/heure-tâche hors free tier."""
    if not deps.settings.free_tier_only or tenant.free_tier_confirmed:
        return None
    return _refuse(
        payload, deps, tenant_id, "free_tier_not_confirmed", "run.refused_free_tier"
    )


def _refuse_quota(
    payload: dict[str, Any], deps: Deps, tenant_id: str
) -> dict[str, Any] | None:
    """EF-ORC-05 : 5 tests simultanés par compte et par région (quota AWS).

    Refuser ici évite un échec côté AWS que personne ne rejouerait ; la machine
    A remet le run en file au lieu de le perdre.
    """
    allowed, running = can_start(
        deps.store, tenant_id, limit=quota_of(deps.settings)
    )
    if allowed:
        return None
    refused = _refuse(
        payload, deps, tenant_id, "concurrency_quota_reached", "run.refused_quota"
    )
    return {**refused, "running": running}


def _refuse_budget(
    payload: dict[str, Any], deps: Deps, tenant: Tenant, tenant_id: str
) -> dict[str, Any] | None:
    """Budget mensuel épuisé : on refuse de partir (R8)."""
    state = deps.store.get_budget(tenant_id, _month_now())
    verdict = check_budget(state, tenant.monthly_budget_hours, deps.settings.hourly_rate)
    if verdict.allowed:
        return None
    refused = _refuse(
        payload, deps, tenant_id, "budget_exceeded", "run.refused_budget"
    )
    return {**refused, "budget_pct": verdict.pct}


def budget_gate(
    payload: dict[str, Any], deps: Deps, now: datetime | None = None
) -> dict[str, Any]:
    """Refuse to start a test without a valid mandate or with an exhausted budget."""
    tenant_id = payload["tenant_id"]

    # Coupe-circuit global : évalué en tout premier, avant même la résolution
    # du tenant — quand il est levé, rien ne part, quel que soit le contexte.
    kill_switch = _refuse_kill_switch(payload, deps, tenant_id)
    if kill_switch is not None:
        return kill_switch

    tenant = _tenant_of(deps, tenant_id)
    if tenant is None:
        return {**payload, "allowed": False, "reason": "unknown_tenant"}

    for guard in (
        _refuse_mandate(payload, deps, tenant, tenant_id),
        _refuse_free_tier(payload, deps, tenant, tenant_id),
        _refuse_quota(payload, deps, tenant_id),
        _refuse_outside_window(payload, deps, now),
        _refuse_budget(payload, deps, tenant, tenant_id),
    ):
        if guard is not None:
            return guard

    state = deps.store.get_budget(tenant_id, _month_now())
    verdict = check_budget(state, tenant.monthly_budget_hours, deps.settings.hourly_rate)
    return {**payload, "allowed": True, "budget_pct": verdict.pct}


# --------------------------------------------------------------------------- #
# 2. Start run
