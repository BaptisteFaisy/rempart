"""Cognito identity stack for Rempart."""

from __future__ import annotations

import aws_cdk as cdk
import aws_cdk.aws_cognito as cognito
from constructs import Construct

ROLES = (
    "platform_admin",
    "analyst",
    "account_manager",
    "client_security",
    "client_dev",
    "executive",
    "demo",
)


class IdentityStack(cdk.Stack):
    """Provisions Cognito UserPool, UserPoolClient and the 7 role groups."""

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.user_pool = cognito.UserPool(
            self,
            "RempartUserPool",
            user_pool_name="rempart-users",
            self_sign_up_enabled=False,
            sign_in_aliases=cognito.SignInAliases(email=True, username=False),
            auto_verify=cognito.AutoVerifiedAttrs(email=True),
            password_policy=cognito.PasswordPolicy(
                min_length=12,
                require_symbols=True,
                require_digits=True,
                require_uppercase=True,
                require_lowercase=True,
            ),
            custom_attributes={
                "tenant_id": cognito.StringAttribute(mutable=True),
            },
            removal_policy=cdk.RemovalPolicy.RETAIN,
        )

        self.user_pool_client = self.user_pool.add_client(
            "RempartWebClient",
            user_pool_client_name="rempart-portal-client",
            generate_secret=False,
            auth_flows=cognito.AuthFlow(
                user_password=True,
                user_srp=True,
            ),
            supported_identity_providers=[
                cognito.UserPoolClientIdentityProvider.COGNITO,
            ],
            read_attributes=cognito.ClientAttributes().with_custom_attributes("tenant_id"),
            write_attributes=cognito.ClientAttributes().with_custom_attributes("tenant_id"),
        )

        self.groups: dict[str, cognito.CfnUserPoolGroup] = {}
        for idx, role in enumerate(ROLES):
            self.groups[role] = cognito.CfnUserPoolGroup(
                self,
                f"Group{role.title().replace('_', '')}",
                user_pool_id=self.user_pool.user_pool_id,
                group_name=role,
                description=f"Rempart role group: {role}",
                precedence=idx,
            )
