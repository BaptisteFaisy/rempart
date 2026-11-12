"""Route handlers for Applications (périmètre, fenêtres de test EF-ORC-08)."""

from __future__ import annotations

import re
import uuid
from typing import Any

from rempart.api.context import ApiContext
from rempart.api.helpers import (
    authorize,
    error_response,
    get_store,
    load_or_404,
    require_principal,
)
from rempart.api.router import Router
from rempart.common.models import Application
from rempart.common.timeutil import iso, utcnow
from rempart.orchestrator.windows import DAY_NAMES

HHMM = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
Response = tuple[int, dict[str, Any]]

# Champs modifiables par `PUT /v1/applications/{id}` et leur type attendu.
# `tenant_id`/`app_id` n'en font pas partie : déplacer une application d'un
# client à l'autre n'est pas une mise à jour, c'est une autre écriture.
UPDATABLE_FIELDS: dict[str, type | tuple[type, ...]] = {
    "name": str,
    "criticality": str,
    "environment": str,
    "team": str,
    "ticket_channel": str,
    "agent_space_id": (str, type(None)),
    "internet_exposed": bool,
    "data_types": list,
    "domains": list,
    "repositories": list,
    "context": dict,
}


def _build_application(tenant_id: str, body: dict[str, Any]) -> Application:
    """Build an Application from a validated request body."""
    app_id = body.get("app_id") or f"app-{uuid.uuid4().hex[:8]}"
    return Application(
        app_id=app_id,
        tenant_id=tenant_id,
        name=body.get("name", app_id),
        criticality=body.get("criticality", "medium"),
        internet_exposed=bool(body.get("internet_exposed", False)),
        data_types=body.get("data_types", ["none"]),
        environment=body.get("environment", "staging"),
        agent_space_id=body.get("agent_space_id"),
        domains=body.get("domains", []),
        repositories=body.get("repositories", []),
        team=body.get("team", ""),
        ticket_channel=body.get("ticket_channel", "github"),
        context=body.get("context", {}),
        created_at=body.get("created_at") or iso(utcnow()),
    )


def _validated_window(item: Any, index: int) -> tuple[dict[str, Any] | None, Response | None]:
    """Valide UNE fenêtre au format documenté par ``Application.test_windows``."""
    where = f"test_windows[{index}]"
    if not isinstance(item, dict):
        return None, error_response(f"{where} doit être un objet", 400)
    days = item.get("days") or []
    if not isinstance(days, list) or any(day not in DAY_NAMES for day in days):
        return None, error_response(
            f"{where}.days : abréviations anglaises de trois lettres attendues "
            f"({' ,'.join(DAY_NAMES)})",
            400,
        )
    for key in ("start", "end"):
        value = item.get(key)
        if not isinstance(value, str) or not HHMM.match(value.strip()):
            return None, error_response(f"{where}.{key} : format HH:MM (UTC) attendu", 400)
    environment = item.get("environment")
    if environment is not None and not isinstance(environment, str):
        return None, error_response(f"{where}.environment doit être une chaîne", 400)
    window: dict[str, Any] = {
        "days": list(days),
        "start": str(item["start"]).strip(),
        "end": str(item["end"]).strip(),
    }
    if environment:
        window["environment"] = environment
    return window, None


def validated_windows(raw: Any) -> tuple[list[dict[str, Any]] | None, Response | None]:
    """Valide la liste de fenêtres : `(liste, None)` ou `(None, erreur 400)`.

    EF-ORC-08 : un test complet en production exige une fenêtre convenue, et
    `orchestrator.windows.is_within_window([])` ne couvre jamais rien. Une
    fenêtre malformée enregistrée silencieusement bloquerait donc tous les
    tests en production sans message exploitable — d'où un refus explicite.
    """
    if raw is None:
        return [], None
    if not isinstance(raw, list):
        return None, error_response("`test_windows` doit être une liste de fenêtres", 400)
    windows: list[dict[str, Any]] = []
    for index, item in enumerate(raw):
        window, err = _validated_window(item, index)
        if err is not None:
            return None, err
        windows.append(window or {})
    return windows, None


def post_application(ctx: ApiContext) -> Response:
    """Create a new application under a tenant."""
    principal, err = require_principal(ctx)
    if err:
        return err
    tenant_id = ctx.path_params.get("id", "")
    err = authorize(principal, tenant_id, write=True)
    if err:
        return err

    store = get_store(ctx)
    if not store.get_tenant(tenant_id):
        return error_response(f"Tenant '{tenant_id}' not found", 404)

    windows, err = validated_windows(ctx.body.get("test_windows"))
    if err is not None or windows is None:
        return err  # type: ignore[return-value]

    app = _build_application(tenant_id, ctx.body)
    app.test_windows = windows
    store.save_application(app)
    ctx.audit("application.create", "application", app.app_id)
    return 201, app.to_item()


def get_application_by_id(ctx: ApiContext) -> Response:
    """Return one application by id, tenant-scoped."""
    principal, err = require_principal(ctx)
    if err:
        return err
    app_id = ctx.path_params.get("id", "")
    store = get_store(ctx)
    app, err = load_or_404(store.get_application, app_id, "Application")
    if err or not app:
        return err  # type: ignore[return-value]

    err = authorize(principal, app.tenant_id, write=False)
    if err:
        return err
    return 200, app.to_item()


def _apply_field(app: Application, name: str, value: Any) -> Response | None:
    """Affecte un champ après contrôle de type ; renvoie une 400 sinon."""
    expected = UPDATABLE_FIELDS[name]
    if not isinstance(value, expected):
        return error_response(f"`{name}` : type invalide (attendu {expected})", 400)
    setattr(app, name, value)
    return None


def put_application(ctx: ApiContext) -> Response:
    """Met à jour le périmètre d'une application, fenêtres de test comprises.

    Sans cette route, `test_windows` n'était posé par AUCUN chemin HTTP :
    `_build_application` l'ignorait, donc toute application créée via le portail
    avait une liste vide et `budget_gate` refusait chaque test complet en
    production (`outside_test_window`).
    """
    principal, err = require_principal(ctx)
    if err:
        return err
    app_id = ctx.path_params.get("id", "")
    store = get_store(ctx)
    app, err = load_or_404(store.get_application, app_id, "Application")
    if err or not app:
        return err  # type: ignore[return-value]
    err = authorize(principal, app.tenant_id, write=True)
    if err:
        return err

    if "test_windows" in ctx.body:
        windows, err = validated_windows(ctx.body.get("test_windows"))
        if err is not None or windows is None:
            return err  # type: ignore[return-value]
        app.test_windows = windows
    for name in UPDATABLE_FIELDS:
        if name in ctx.body:
            err = _apply_field(app, name, ctx.body[name])
            if err:
                return err

    store.save_application(app)
    ctx.audit("application.update", "application", app.app_id)
    return 200, app.to_item()


def register(router: Router) -> None:
    router.add("POST", "/v1/tenants/:id/applications", post_application)
    router.add("GET", "/v1/applications/:id", get_application_by_id)
    router.add("PUT", "/v1/applications/:id", put_application)
