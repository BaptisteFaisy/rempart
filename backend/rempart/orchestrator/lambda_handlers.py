"""Adaptateurs Lambda des tâches de l'orchestrateur (CONTRACT-PHASE0 § 2).

Le CDK pointe vers ``rempart.orchestrator.lambda_handlers.<nom>``. Les tâches de
:mod:`rempart.orchestrator.tasks` ont la signature ``(payload, deps)`` : ce
module fournit la signature AWS ``(event, context)``, construit les dépendances
via :func:`build_deps` (point d'injection unique, § 2.5) et renvoie le ``dict``
produit par la tâche.

Aucune logique métier n'est dupliquée ici. Les deux seules valeurs ajoutées :
le compteur ``iterations`` qui plafonne la boucle de ``poll_run`` à 4 h (§ 3),
et la capture d'exception qui empêche Step Functions de rejouer à l'infini
(§ 2.4).
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from rempart.common.config import Settings
from rempart.common.store import Store

from . import tasks
from .discovery import DISCOVERY_WINDOW_MINUTES, discover_cicd_runs
from .github_client import GitHubClient, github_token_from_env
from .sa_client import SecurityAgentClient
from .task_types import Deps

LOGGER = logging.getLogger("rempart.orchestrator.lambda_handlers")

#: Jeton GitHub : `GITHUB_TOKEN_ENVS` et `github_token_from_env` vivent dans
#: `orchestrator/github_client.py`, partagés avec la revue de code (`review/`).

TaskFn = Callable[[dict[str, Any], Deps], dict[str, Any]]
DepsFactory = Callable[[], Deps]
HandlerFn = Callable[..., dict[str, Any]]


# --------------------------------------------------------------------------- #
# Construction des dépendances (contrat § 2.1 et § 2.5)
# --------------------------------------------------------------------------- #
def _github_token() -> str | None:
    """Premier jeton GitHub présent dans l'environnement, sinon ``None``."""
    return github_token_from_env()


def _model_client() -> Any:
    """Client Strands du triage, ou ``None`` si aucun endpoint LLM n'est configuré."""
    from rempart.triage.llm import build_model_client

    return build_model_client()


def _github_client(settings: Settings) -> GitHubClient | None:
    """Construit un ``GitHubClient`` seulement si un jeton est disponible."""
    token = _github_token()
    if token is None:
        return None
    return GitHubClient(token=token, api=settings.github_api)


def build_deps(settings: Settings | None = None) -> Deps:
    """Construit le ``Deps`` réel d'une invocation Lambda (zéro duplication).

    ``Store`` et ``SecurityAgentClient`` n'importent boto3 qu'au premier appel
    réseau : la construction reste donc sans effet de bord. Les tests passent
    leur propre fabrique via le paramètre ``deps_factory`` des handlers.
    """
    settings = settings or Settings.from_env()
    return Deps(
        store=Store(table_prefix=settings.table_prefix),
        sa=SecurityAgentClient(
            endpoint_url=settings.sa_endpoint_url,
            region=settings.region,
            role_arn=settings.sa_role_arn,
            external_id=settings.sa_external_id,
        ),
        settings=settings,
        github=_github_client(settings),
        # Modèle du triage : construit seulement si un endpoint LLM est
        # configuré (REMPART_LLM_BASE_URL / REMPART_LLM_API_KEY). Sans lui,
        # l'agent garde son repli déterministe — et la démo ne coûte rien.
        model_client=_model_client(),
    )


# --------------------------------------------------------------------------- #
# Adaptation générique (contrat § 2.2 à § 2.4)
# --------------------------------------------------------------------------- #
def _invoke(
    task_name: str,
    task: TaskFn,
    event: dict[str, Any] | None,
    deps_factory: DepsFactory | None = None,
) -> dict[str, Any]:
    """Exécute une tâche et rend toujours un ``dict``, sans jamais lever."""
    payload = dict(event or {})
    try:
        deps = (deps_factory or build_deps)()
        return task(payload, deps)
    except Exception as exc:  # noqa: BLE001 - § 2.4 : Step Functions rejouerait sinon
        LOGGER.exception("Tâche de l'orchestrateur en échec: %s", task_name)
        return {"task": task_name, "error": f"{type(exc).__name__}: {exc}"}


def _as_int(value: Any) -> int:
    """Valeur d'état Step Functions convertie en entier (0 si absente/invalide)."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _count_iteration(event: dict[str, Any] | None, result: dict[str, Any]) -> dict[str, Any]:
    """Incrémente le compteur de boucle (240 × 60 s = 4 h, § 3).

    ``tasks.poll_run`` ne connaît pas ce compteur et ``tasks.py`` appartient à
    un autre agent : l'incrément est donc posé ici, dans l'adaptateur.
    """
    return {**result, "iterations": _as_int((event or {}).get("iterations")) + 1}


def _discover_task(payload: dict[str, Any], deps: Deps) -> dict[str, Any]:
    """Adapte ``discover_cicd_runs`` (liste de ``Run``) au ``dict`` du contrat."""
    since = _as_int(payload.get("since_minutes")) or DISCOVERY_WINDOW_MINUTES
    runs = discover_cicd_runs(deps, since_minutes=since)
    return {"discovered": len(runs), "run_ids": [run.run_id for run in runs]}


# --------------------------------------------------------------------------- #
# Les neuf handlers référencés par le CDK
# --------------------------------------------------------------------------- #
def budget_gate(
    event: dict[str, Any],
    context: Any = None,
    *,
    deps_factory: DepsFactory | None = None,
) -> dict[str, Any]:
    """Refuse un test sans mandat valide ou hors budget (R8, R12)."""
    return _invoke("budget_gate", tasks.budget_gate, event, deps_factory)


def start_run(
    event: dict[str, Any],
    context: Any = None,
    *,
    deps_factory: DepsFactory | None = None,
) -> dict[str, Any]:
    """Lance le job de test Security Agent et enregistre le run."""
    return _invoke("start_run", tasks.start_run, event, deps_factory)


def poll_run(
    event: dict[str, Any],
    context: Any = None,
    *,
    deps_factory: DepsFactory | None = None,
) -> dict[str, Any]:
    """Rafraîchit l'état du job et incrémente ``iterations`` (plafond 4 h)."""
    result = _invoke("poll_run", tasks.poll_run, event, deps_factory)
    return _count_iteration(event, result)


def collect_findings(
    event: dict[str, Any],
    context: Any = None,
    *,
    deps_factory: DepsFactory | None = None,
) -> dict[str, Any]:
    """Récolte les failles du run (déduplication, régressions, priorité)."""
    return _invoke("collect_findings", tasks.collect_findings, event, deps_factory)


def dispatch_triage(
    event: dict[str, Any],
    context: Any = None,
    *,
    deps_factory: DepsFactory | None = None,
) -> dict[str, Any]:
    """Fait statuer l'agent de triage et met en file les failles critiques."""
    return _invoke("dispatch_triage", tasks.dispatch_triage, event, deps_factory)


def create_tickets(
    event: dict[str, Any],
    context: Any = None,
    *,
    deps_factory: DepsFactory | None = None,
) -> dict[str, Any]:
    """Ouvre un ticket GitHub par faille confirmée, avec son échéance."""
    return _invoke("create_tickets", tasks.create_tickets, event, deps_factory)


def request_remediation(
    event: dict[str, Any],
    context: Any = None,
    *,
    deps_factory: DepsFactory | None = None,
) -> dict[str, Any]:
    """Demande une pull request de correction à Security Agent (EF-COR-03)."""
    return _invoke("request_remediation", tasks.request_remediation, event, deps_factory)


def close_or_reopen(
    event: dict[str, Any],
    context: Any = None,
    *,
    deps_factory: DepsFactory | None = None,
) -> dict[str, Any]:
    """Ferme avec preuve ou rouvre en cas de régression (EF-COR-04/05)."""
    return _invoke("close_or_reopen", tasks.close_or_reopen, event, deps_factory)


def discover_runs(
    event: dict[str, Any],
    context: Any = None,
    *,
    deps_factory: DepsFactory | None = None,
) -> dict[str, Any]:
    """Découvre les jobs CI/CD terminés et rend ``discovered`` + ``run_ids``."""
    return _invoke("discover_runs", _discover_task, event, deps_factory)


HANDLERS: dict[str, HandlerFn] = {
    "budget_gate": budget_gate,
    "start_run": start_run,
    "poll_run": poll_run,
    "collect_findings": collect_findings,
    "dispatch_triage": dispatch_triage,
    "create_tickets": create_tickets,
    "request_remediation": request_remediation,
    "close_or_reopen": close_or_reopen,
    "discover_runs": discover_runs,
}
