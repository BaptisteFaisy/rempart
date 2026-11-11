"""API Gateway HTTP API stack for Rempart."""

from __future__ import annotations

import aws_cdk as cdk
import aws_cdk.aws_apigatewayv2 as apigwv2
import aws_cdk.aws_apigatewayv2_authorizers as authorizers
import aws_cdk.aws_apigatewayv2_integrations as integrations
import aws_cdk.aws_cognito as cognito
import aws_cdk.aws_dynamodb as ddb
import aws_cdk.aws_iam as iam
from constructs import Construct

from ._helpers import DEFAULT_TABLE_PREFIX, create_python_lambda, runtime_layer


class ApiStack(cdk.Stack):
    """Provisions HTTP API v2, JWT authorizer, and the main Rempart API Lambda."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        user_pool: cognito.IUserPool,
        user_pool_client: cognito.IUserPoolClient,
        tables: dict[str, ddb.ITable],
        table_prefix: str = DEFAULT_TABLE_PREFIX,
        hourly_rate: float = 50.0,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)
        self.api_lambda = self._create_api_lambda(tables, table_prefix, hourly_rate)
        self.jwt_authorizer = self._create_authorizer(user_pool, user_pool_client)
        self.http_api = self._create_http_api()

    def _layers(self) -> list:
        """Layer des dépendances tierces (mémoïsé) ; vide s'il n'est pas construit."""
        if not hasattr(self, "_runtime_layer_cache"):
            layer = runtime_layer(self, "RempartRuntimeLayer")
            self._runtime_layer_cache = [layer] if layer else []
        return self._runtime_layer_cache

    def _create_api_lambda(
        self,
        tables: dict[str, ddb.ITable],
        table_prefix: str,
        hourly_rate: float,
    ) -> cdk.aws_lambda.Function:
        fn = create_python_lambda(
            self,
            "RempartApiFunction",
            handler="rempart.api.app.lambda_handler",
            environment={
                "REMPART_TABLE_PREFIX": table_prefix,
                "REMPART_REGION": self.region,
                "REMPART_HOURLY_RATE": str(hourly_rate),
                # Garde-fous anti-facture : aucun test reel sans eligibilite
                # free tier confirmee, et un plafond d'heures-taches par test.
                "REMPART_FREE_TIER_ONLY": "1",
                "REMPART_MAX_TASK_HOURS_PER_TEST": "5",
            },
            layers=self._layers(),
            timeout_seconds=30,
            memory_size=1024,
        )
        for table in tables.values():
            table.grant_read_write_data(fn)
        fn.add_to_role_policy(
            iam.PolicyStatement(
                actions=["sts:AssumeRole"],
                resources=["arn:aws:iam::*:role/rempart-ops-role"],
            )
        )
        return fn

    def _create_authorizer(
        self,
        user_pool: cognito.IUserPool,
        user_pool_client: cognito.IUserPoolClient,
    ) -> authorizers.HttpJwtAuthorizer:
        issuer = f"https://cognito-idp.{self.region}.amazonaws.com/{user_pool.user_pool_id}"
        return authorizers.HttpJwtAuthorizer(
            "CognitoAuthorizer",
            jwt_issuer=issuer,
            jwt_audience=[user_pool_client.user_pool_client_id],
        )

    def _create_http_api(self) -> apigwv2.HttpApi:
        api = apigwv2.HttpApi(
            self,
            "RempartHttpApi",
            api_name="rempart-control-plane-api",
            cors_preflight=apigwv2.CorsPreflightOptions(
                allow_headers=["*"],
                allow_methods=[apigwv2.CorsHttpMethod.ANY],
                allow_origins=["*"],
                max_age=cdk.Duration.days(1),
            ),
        )
        integration = integrations.HttpLambdaIntegration("ApiLambdaIntegration", self.api_lambda)
        api.add_routes(
            path="/v1/{proxy+}",
            methods=[apigwv2.HttpMethod.ANY],
            integration=integration,
            authorizer=self.jwt_authorizer,
        )
        api.add_routes(
            path="/v1/events/deployment",
            methods=[apigwv2.HttpMethod.POST],
            integration=integration,
        )
        return api
