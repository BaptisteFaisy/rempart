"""Rempart control-plane CDK app entrypoint.

`build_app()` est découpé en étapes nommées : chaque fonction reste sous la
limite de 50 lignes, et l'ordre de construction (storage → identity → api →
orchestrator → portal/notifications → observability) reste lisible.
"""

from __future__ import annotations

import os
from typing import Any

import aws_cdk as cdk
from stacks.api import ApiStack
from stacks.identity import IdentityStack
from stacks.notifications import NotificationsStack
from stacks.observability import ObservabilityStack
from stacks.orchestrator import OrchestratorStack
from stacks.portal import PortalStack
from stacks.storage import StorageStack

DEFAULT_ACCOUNT = "123456789012"
DEFAULT_REGION = "eu-west-3"


def target_environment() -> cdk.Environment:
    """Compte et région cibles, surchargeables par l'environnement CDK."""
    return cdk.Environment(
        account=os.environ.get("CDK_DEFAULT_ACCOUNT", DEFAULT_ACCOUNT),
        region=os.environ.get("CDK_DEFAULT_REGION", DEFAULT_REGION),
    )


def build_core_stacks(app: cdk.App, env: cdk.Environment) -> dict[str, Any]:
    """Storage, identité, API et orchestrateur : le cœur du plan de contrôle."""
    storage = StorageStack(app, "RempartStorageStack", env=env)
    identity = IdentityStack(app, "RempartIdentityStack", env=env)
    api = ApiStack(
        app,
        "RempartApiStack",
        env=env,
        user_pool=identity.user_pool,
        user_pool_client=identity.user_pool_client,
        tables=storage.tables,
        table_prefix=storage.table_prefix,
    )
    orchestrator = OrchestratorStack(
        app,
        "RempartOrchestratorStack",
        env=env,
        tables=storage.tables,
        table_prefix=storage.table_prefix,
    )
    return {"storage": storage, "identity": identity, "api": api, "orchestrator": orchestrator}


def build_edge_stacks(app: cdk.App, env: cdk.Environment) -> None:
    """Portail statique et notifications : sans dépendance sur le cœur."""
    PortalStack(app, "RempartPortalStack", env=env)
    NotificationsStack(app, "RempartNotificationsStack", env=env)


def build_observability(
    app: cdk.App, env: cdk.Environment, core: dict[str, Any]
) -> ObservabilityStack:
    """ENF-OBS-01 : alarmes sur chaque étape du parcours.

    `discover_runs` est traité à part des tâches d'orchestration : c'est lui qui
    révèle les tests lancés par la porte CI/CD du client (EF-ORC-01).
    """
    orchestrator = core["orchestrator"]
    task_lambdas = {
        name: fn for name, fn in orchestrator.lambdas.items() if name != "discover_runs"
    }
    return ObservabilityStack(
        app,
        "RempartObservabilityStack",
        env=env,
        api_function=core["api"].api_lambda,
        task_lambdas=task_lambdas,
        discovery_lambda=orchestrator.discovery_lambda,
        state_machines={
            "pentest_lifecycle": orchestrator.pentest_lifecycle,
            "cicd_intake": orchestrator.cicd_intake,
            "retest_close": orchestrator.retest_close,
        },
        tables=core["storage"].tables,
    )


def wire_dependencies(core: dict[str, Any], observability: ObservabilityStack) -> None:
    """Ordre de déploiement entre stacks."""
    core["api"].add_dependency(core["storage"])
    core["api"].add_dependency(core["identity"])
    core["orchestrator"].add_dependency(core["storage"])
    for stack in (core["api"], core["orchestrator"], core["storage"]):
        observability.add_dependency(stack)


def build_app() -> cdk.App:
    """Build and wire all Rempart control-plane stacks (callable from tests)."""
    app = cdk.App()
    env = target_environment()
    core = build_core_stacks(app, env)
    build_edge_stacks(app, env)
    observability = build_observability(app, env, core)
    wire_dependencies(core, observability)
    return app


if __name__ == "__main__":
    build_app().synth()
