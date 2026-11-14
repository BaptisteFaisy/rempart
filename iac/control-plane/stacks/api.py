"""API Gateway HTTP API stack for Rempart."""

from __future__ import annotations

import aws_cdk as cdk
import aws_cdk.aws_apigatewayv2 as apigwv2
import aws_cdk.aws_apigatewayv2_authorizers as authorizers
import aws_cdk.aws_apigatewayv2_integrations as integrations
import aws_cdk.aws_cognito as cognito
import aws_cdk.aws_dynamodb as ddb
import aws_cdk.aws_iam as iam
import aws_cdk.aws_s3 as s3
import aws_cdk.aws_stepfunctions as sfn
from constructs import Construct

from ._helpers import (
    DEFAULT_TABLE_PREFIX,
    create_python_lambda,
    grant_securityagent,
    runtime_layer,
    securityagent_policy,
)

# En-têtes réellement envoyés par le portail (jeton Cognito, corps JSON), par les
# pipelines CI/CD (clé partagée du webhook de déploiement) et par GitHub
# (signature + type d'événement du webhook de retest, idée #51). Un en-tête
# absent de cette liste est supprimé par le preflight : la route refuserait la
# signature avant même de l'avoir reçue.
CORS_ALLOW_HEADERS = [
    "Authorization",
    "Content-Type",
    "X-Rempart-Key",
    "X-Hub-Signature-256",
    "X-GitHub-Event",
    "X-GitHub-Delivery",
]
CORS_ALLOW_METHODS = [
    apigwv2.CorsHttpMethod.GET,
    apigwv2.CorsHttpMethod.POST,
    apigwv2.CorsHttpMethod.PUT,
    apigwv2.CorsHttpMethod.DELETE,
    apigwv2.CorsHttpMethod.OPTIONS,
]


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
        reports_bucket: s3.IBucket | None = None,
        portal_origins: list[str] | None = None,
        pipeline_key_param: str | None = None,
        github_webhook_secret_param: str | None = None,
        retest_machine: sfn.IStateMachine | None = None,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)
        self.portal_origins = list(portal_origins or [])
        self.retest_machine = retest_machine
        self.api_lambda = self._create_api_lambda(
            tables,
            table_prefix,
            hourly_rate,
            reports_bucket,
            pipeline_key_param,
            github_webhook_secret_param,
        )
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
        reports_bucket: s3.IBucket | None = None,
        pipeline_key_param: str | None = None,
        github_webhook_secret_param: str | None = None,
    ) -> cdk.aws_lambda.Function:
        fn = create_python_lambda(
            self,
            "RempartApiFunction",
            handler="rempart.api.app.lambda_handler",
            environment=self._environment(
                table_prefix,
                hourly_rate,
                reports_bucket,
                pipeline_key_param,
                github_webhook_secret_param,
            ),
            layers=self._layers(),
            timeout_seconds=30,
            memory_size=1024,
        )
        for table in tables.values():
            table.grant_read_write_data(fn)
        self._grant_retest_start(fn)
        if reports_bucket is not None:
            # EF-RAP-04 : le dossier de preuves doit être réellement conservé.
            reports_bucket.grant_read_write(fn)
        # L'onboarding parle à Continuum (domaine, espace, pentest) : sans ces
        # droits, il se fait refuser (mesuré le 13/11/2026). L'action est posée
        # APRÈS les autres droits : CDK fusionne les instructions d'une même
        # politique, et l'ordre évite qu'une instruction remplace la précédente.
        grant_securityagent(
            fn,
            securityagent_policy(
                self, account=self.account, region=self.region,
                id_="RempartApiSecurityAgentPolicy",
            ),
        )
        fn.add_to_role_policy(
            iam.PolicyStatement(
                sid="RempartAssumeOpsRole",
                actions=["sts:AssumeRole"],
                resources=["arn:aws:iam::*:role/rempart-ops-role"],
            )
        )
        return fn

    def _grant_retest_start(self, fn: cdk.aws_lambda.Function) -> None:
        """Idée #51 : une PR mergée doit pouvoir démarrer LE retest, et rien d'autre.

        La machine est fixée à la construction (celle du plan de contrôle), jamais
        lisible dans le corps de requête : sinon l'appelant choisirait l'ARN à
        exécuter dans le compte. Une seule action, une seule ressource.
        """
        if self.retest_machine is None:
            return
        self.retest_machine.grant_start_execution(fn)

    def _environment(
        self,
        table_prefix: str,
        hourly_rate: float,
        reports_bucket: s3.IBucket | None,
        pipeline_key_param: str | None,
        github_webhook_secret_param: str | None = None,
    ) -> dict[str, str]:
        """Variables d'environnement de la Lambda API (aucun secret en clair)."""
        environment = {
            "REMPART_TABLE_PREFIX": table_prefix,
            "REMPART_REGION": self.region,
            "REMPART_HOURLY_RATE": str(hourly_rate),
            # Garde-fous anti-facture : aucun test reel sans eligibilite
            # free tier confirmee, et un plafond d'heures-taches par test.
            "REMPART_FREE_TIER_ONLY": "1",
            "REMPART_MAX_TASK_HOURS_PER_TEST": "5",
            # CORS restreint aux origines réelles du portail (plus de `*`).
            "REMPART_CORS_ALLOW_ORIGINS": ",".join(self.portal_origins),
        }
        if reports_bucket is not None:
            environment["REMPART_REPORTS_BUCKET"] = reports_bucket.bucket_name
        # Les deux secrets de webhook (pipeline CI/CD, GitHub) portent le même
        # contrat : référencés depuis SSM SecureString, résolus par
        # CloudFormation au déploiement, JAMAIS écrits en clair dans le template.
        for env_name, param in (
            ("REMPART_PIPELINE_KEY", pipeline_key_param),
            ("REMPART_GITHUB_WEBHOOK_SECRET", github_webhook_secret_param),
        ):
            if param:
                environment[env_name] = self._ssm_reference(param)
        if self.retest_machine is not None:
            # Fixe côté serveur : le corps de requête ne choisit jamais un ARN.
            environment["REMPART_RETEST_MACHINE_ARN"] = (
                self.retest_machine.state_machine_arn
            )
        return environment

    @staticmethod
    def _ssm_reference(param: str) -> str:
        """Référence dynamique SSM SecureString (aucune valeur en clair)."""
        return cdk.CfnDynamicReference(
            cdk.CfnDynamicReferenceService.SSM_SECURE, param
        ).to_string()

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
                allow_headers=CORS_ALLOW_HEADERS,
                allow_methods=CORS_ALLOW_METHODS,
                allow_origins=self.portal_origins or ["*"],
                max_age=cdk.Duration.minutes(10),
            ),
        )
        integration = integrations.HttpLambdaIntegration("ApiLambdaIntegration", self.api_lambda)
        # INCIDENT RÉEL (12 nov. 2026) : la route `ANY /v1/{proxy+}` porte
        # l'autorisateur JWT, et ANY comprend OPTIONS — le preflight du
        # navigateur recevait donc 401 et AUCUN appel cross-origin du portail
        # CloudFront n'aboutissait. Cette route OPTIONS explicite, sans
        # autorisateur, laisse API Gateway répondre 204 avec les en-têtes CORS.
        api.add_routes(
            path="/v1/{proxy+}",
            methods=[apigwv2.HttpMethod.OPTIONS],
            integration=integration,
        )
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
        # Idée #51 : le webhook GitHub, second point d'entrée sans jeton. Mêmes
        # règles que celui du pipeline CI/CD — l'authentification vit dans le
        # code (secret SSM + HMAC sur les octets bruts du corps), donc AUCUN
        # autorisateur JWT ici : GitHub ne possède pas de jeton Cognito, et un
        # 401 sur ce chemin signifierait que la boucle de retest ne peut jamais
        # se fermer toute seule.
        api.add_routes(
            path="/v1/events/github",
            methods=[apigwv2.HttpMethod.POST],
            integration=integration,
        )
        return api
