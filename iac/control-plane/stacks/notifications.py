"""SES notifications stack for Rempart."""

from __future__ import annotations

import aws_cdk as cdk
import aws_cdk.aws_iam as iam
import aws_cdk.aws_ses as ses
from constructs import Construct

from ._helpers import create_python_lambda, runtime_layer


class NotificationsStack(cdk.Stack):
    """Provisions SES identity/configuration set and the notification Lambda."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        from_domain: str = "rempart.example.com",
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)
        self.email_identity = ses.EmailIdentity(
            self, "RempartEmailIdentity", identity=ses.Identity.domain(from_domain)
        )
        self.configuration_set = ses.ConfigurationSet(
            self,
            "RempartConfigurationSet",
            configuration_set_name="rempart-notifications",
            tls_policy=ses.ConfigurationSetTlsPolicy.REQUIRE,
        )
        self.notification_lambda = self._create_lambda(from_domain)
        cdk.CfnOutput(
            self,
            "NotificationLambdaArn",
            value=self.notification_lambda.function_arn,
            description="Rempart notification Lambda ARN",
        )

    def _layers(self) -> list:
        """Layer des dépendances tierces (mémoïsé) ; vide s'il n'est pas construit."""
        if not hasattr(self, "_runtime_layer_cache"):
            layer = runtime_layer(self, "RempartRuntimeLayer")
            self._runtime_layer_cache = [layer] if layer else []
        return self._runtime_layer_cache

    def _create_lambda(self, from_domain: str) -> cdk.aws_lambda.Function:
        fn = create_python_lambda(
            self,
            "NotificationFunction",
            handler="rempart.notifications.handler.lambda_handler",
            environment={
                "REMPART_SES_FROM_DOMAIN": from_domain,
                "REMPART_SES_CONFIGURATION_SET": self.configuration_set.configuration_set_name,
                "REMPART_REGION": self.region,
            },
            layers=self._layers(),
            timeout_seconds=60,
            memory_size=512,
        )
        fn.add_to_role_policy(
            iam.PolicyStatement(
                actions=["ses:SendEmail", "ses:SendRawEmail", "ses:SendTemplatedEmail"],
                resources=["*"],
                conditions={"StringEquals": {"ses:FromAddress": f"noreply@{from_domain}"}},
            )
        )
        return fn
