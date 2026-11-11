"""Le code déployé dans les Lambdas doit être le VRAI code, pas un placeholder.

Régression gardée : `create_python_lambda` utilisait `Code.from_inline` avec un
corps factice (`return {'statusCode': 200, 'body': 'ok'}`). Le synth passait,
le déploiement réussissait, et **toutes** les fonctions ne faisaient rien. Ni
`cdk synth` ni les tests unitaires ne le voyaient : seul un test sur le
template synthétisé l'attrape.
"""

from __future__ import annotations

import sys
from pathlib import Path

import aws_cdk as cdk
import pytest
from aws_cdk import assertions

# `iac/control-plane` doit être sur sys.path pour importer les stacks.
IAC_DIR = Path(__file__).resolve().parents[3] / "iac" / "control-plane"
if str(IAC_DIR) not in sys.path:
    sys.path.insert(0, str(IAC_DIR))

from stacks.api import ApiStack  # noqa: E402
from stacks.identity import IdentityStack  # noqa: E402
from stacks.notifications import NotificationsStack  # noqa: E402
from stacks.orchestrator import OrchestratorStack  # noqa: E402
from stacks.storage import StorageStack  # noqa: E402

PLACEHOLDER_MARKERS = ("Placeholder code for Rempart", "body': 'ok'", 'body": "ok"')
ENV = {"account": "123456789012", "region": "eu-west-3"}


def _template(stack: cdk.Stack) -> assertions.Template:
    return assertions.Template.from_stack(stack)


def _build_api_stack() -> ApiStack:
    app = cdk.App()
    env = cdk.Environment(**ENV)
    storage = StorageStack(app, "Storage", env=env)
    identity = IdentityStack(app, "Identity", env=env)
    return ApiStack(
        app,
        "Api",
        env=env,
        user_pool=identity.user_pool,
        user_pool_client=identity.user_pool_client,
        tables=storage.tables,
        table_prefix=storage.table_prefix,
    )


def _build_orchestrator_stack() -> OrchestratorStack:
    app = cdk.App()
    env = cdk.Environment(**ENV)
    storage = StorageStack(app, "Storage", env=env)
    return OrchestratorStack(
        app,
        "Orchestrator",
        env=env,
        tables=storage.tables,
        table_prefix=storage.table_prefix,
    )


def _lambda_resources(template: assertions.Template) -> dict:
    return template.find_resources("AWS::Lambda::Function")


@pytest.mark.parametrize(
    "stack_factory",
    [_build_api_stack, _build_orchestrator_stack, lambda: NotificationsStack(
        cdk.App(), "Notif", env=cdk.Environment(**ENV))],
    ids=["api", "orchestrator", "notifications"],
)
def test_no_lambda_ships_inline_placeholder_code(stack_factory):
    template = _template(stack_factory())
    functions = _lambda_resources(template)
    assert functions, "aucune Lambda synthétisée : le test ne prouve rien"
    for logical_id, resource in functions.items():
        code = resource["Properties"].get("Code", {})
        assert "ZipFile" not in code, (
            f"{logical_id} embarque du code inline (ZipFile) : c'était le "
            f"placeholder qui déployait des fonctions vides"
        )


@pytest.mark.parametrize(
    "stack_factory",
    [_build_api_stack, _build_orchestrator_stack],
    ids=["api", "orchestrator"],
)
def test_lambda_code_comes_from_a_bundled_asset(stack_factory):
    """Le code doit venir d'un asset (S3Bucket + S3Key), donc de backend/."""
    template = _template(stack_factory())
    for logical_id, resource in _lambda_resources(template).items():
        code = resource["Properties"].get("Code", {})
        assert code.get("S3Bucket"), f"{logical_id} n'a pas de S3Bucket (asset absent)"
        assert code.get("S3Key"), f"{logical_id} n'a pas de S3Key (asset absent)"


@pytest.mark.parametrize(
    "stack_factory",
    [_build_api_stack, _build_orchestrator_stack],
    ids=["api", "orchestrator"],
)
def test_lambda_tracing_is_active(stack_factory):
    """ENF-OBS-01 : les traces doivent être activées sur chaque fonction."""
    template = _template(stack_factory())
    for logical_id, resource in _lambda_resources(template).items():
        tracing = resource["Properties"].get("TracingConfig", {})
        assert tracing.get("Mode") == "Active", f"{logical_id} sans tracing X-Ray actif"


def test_backend_asset_contains_the_rempart_package():
    """L'asset pointé doit réellement contenir le package `rempart`."""
    from stacks._helpers import BACKEND_DIR

    assert (BACKEND_DIR / "rempart" / "__init__.py").is_file(), (
        f"{BACKEND_DIR}/rempart/__init__.py introuvable : l'asset Lambda "
        f"serait vide et les handlers impossibles à résoudre"
    )
    for relative in ("api/app.py", "orchestrator/lambda_handlers.py"):
        assert (BACKEND_DIR / "rempart" / relative).is_file(), relative


def test_placeholder_string_is_gone_from_helpers():
    """Garde explicite : la chaîne du placeholder ne doit plus exister."""
    from pathlib import Path

    from stacks import _helpers

    source = Path(_helpers.__file__).read_text(encoding="utf-8")
    for marker in PLACEHOLDER_MARKERS:
        assert marker not in source, f"le placeholder « {marker} » est revenu"
