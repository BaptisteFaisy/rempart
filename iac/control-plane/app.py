"""Rempart control-plane CDK app entrypoint."""

from __future__ import annotations

import os

import aws_cdk as cdk
from stacks.api import ApiStack
from stacks.identity import IdentityStack
from stacks.notifications import NotificationsStack
from stacks.orchestrator import OrchestratorStack
from stacks.portal import PortalStack
from stacks.storage import StorageStack

DEFAULT_ACCOUNT = "123456789012"
DEFAULT_REGION = "eu-west-3"


def build_app() -> cdk.App:
    """Build and wire all Rempart control-plane stacks (callable from tests)."""
    app = cdk.App()

    env = cdk.Environment(
        account=os.environ.get("CDK_DEFAULT_ACCOUNT", DEFAULT_ACCOUNT),
        region=os.environ.get("CDK_DEFAULT_REGION", DEFAULT_REGION),
    )

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
    PortalStack(app, "RempartPortalStack", env=env)
    NotificationsStack(app, "RempartNotificationsStack", env=env)

    # Cross-stack dependency ordering
    api.add_dependency(storage)
    api.add_dependency(identity)
    orchestrator.add_dependency(storage)

    return app


if __name__ == "__main__":
    build_app().synth()
