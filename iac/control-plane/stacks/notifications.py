"""SES notifications stack for Rempart.

Trois modes d'identité, du gratuit au complet :

1. **``from_email``** — une adresse exacte. C'est le **sandbox SES** : aucun
   domaine à acheter, la vérification se fait par un simple clic sur l'e-mail
   reçu. Gratuit, suffisant pour la démonstration et pour un MSP qui démarre.
2. **``from_domain``** — un domaine possédé, vérifié par enregistrement DNS.
   Nécessite d'acheter la zone (~15 $/an), mais c'est le mode production :
   tous les destinataires peuvent être servis, pas seulement des adresses
   vérifiées une à une.
3. **ni l'un ni l'autre** — la stack se déploie quand même (ConfigurationSet +
   Lambda), sans identité. Les envois échoueront tant qu'aucune identité n'est
   ajoutée, mais rien n'est cassé et rien ne coûte : c'est ce qui permet de
   déployer l'infrastructure avant d'avoir choisi l'adresse d'expédition.

L'ancienne version codait en dur ``rempart.example.com``, un domaine que
personne ne possède : l'identité restait en ``PENDING`` pour toujours et la
condition IAM ``ses:FromAddress`` bloquait tout envoi.
"""

from __future__ import annotations

import aws_cdk as cdk
import aws_cdk.aws_iam as iam
import aws_cdk.aws_ses as ses
from constructs import Construct

from ._helpers import create_python_lambda, runtime_layer

CONFIGURATION_SET_NAME = "rempart-notifications"
DEFAULT_FROM_USER = "noreply"


def resolve_from_address(from_email: str | None, from_domain: str | None) -> str | None:
    """Adresse d'expédition effective, ou ``None`` si aucune identité configurée."""
    if from_email:
        return from_email
    if from_domain:
        return f"{DEFAULT_FROM_USER}@{from_domain}"
    return None


class NotificationsStack(cdk.Stack):
    """Provisions SES identity/configuration set and the notification Lambda."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        from_email: str | None = None,
        from_domain: str | None = None,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)
        self.from_address = resolve_from_address(from_email, from_domain)
        self.email_identity = self._create_identity(from_email, from_domain)
        self.configuration_set = ses.ConfigurationSet(
            self,
            "RempartConfigurationSet",
            configuration_set_name=CONFIGURATION_SET_NAME,
            tls_policy=ses.ConfigurationSetTlsPolicy.REQUIRE,
        )
        self.notification_lambda = self._create_lambda()
        cdk.CfnOutput(
            self,
            "NotificationLambdaArn",
            value=self.notification_lambda.function_arn,
            description="Rempart notification Lambda ARN",
        )
        cdk.CfnOutput(
            self,
            "SesFromAddress",
            value=self.from_address or "(aucune identité configurée)",
            description="Adresse d'expédition SES effective",
        )

    def _create_identity(
        self, from_email: str | None, from_domain: str | None
    ) -> ses.EmailIdentity | None:
        """Identité SES si une adresse ou un domaine est fourni, sinon rien."""
        if from_email:
            return ses.EmailIdentity(
                self, "RempartEmailIdentity", identity=ses.Identity.email(from_email)
            )
        if from_domain:
            return ses.EmailIdentity(
                self, "RempartEmailIdentity", identity=ses.Identity.domain(from_domain)
            )
        return None

    def _layers(self) -> list:
        """Layer des dépendances tierces (mémoïsé)."""
        if not hasattr(self, "_runtime_layer_cache"):
            layer = runtime_layer(self, "RempartRuntimeLayer")
            self._runtime_layer_cache = [layer] if layer else []
        return self._runtime_layer_cache

    def _ses_policy(self) -> iam.PolicyStatement:
        """Permission d'envoi, bornée à l'adresse d'expédition quand elle existe."""
        statement = iam.PolicyStatement(
            actions=["ses:SendEmail", "ses:SendRawEmail", "ses:SendTemplatedEmail"],
            resources=["*"],
        )
        if self.from_address:
            # Sans identité configurée, on n'ajoute PAS de condition vide : elle
            # interdirait tout envoi de façon invisible.
            statement.add_condition(
                "StringEquals", {"ses:FromAddress": self.from_address}
            )
        return statement

    def _create_lambda(self) -> cdk.aws_lambda.Function:
        environment = {
            "REMPART_SES_CONFIGURATION_SET": self.configuration_set.configuration_set_name,
            "REMPART_REGION": self.region,
        }
        if self.from_address:
            # Une adresse exacte prime sur le domaine (voir ses_client.from_address).
            environment["REMPART_SES_FROM_ADDRESS"] = self.from_address
        fn = create_python_lambda(
            self,
            "NotificationFunction",
            handler="rempart.notifications.handler.lambda_handler",
            environment=environment,
            layers=self._layers(),
            timeout_seconds=60,
            memory_size=512,
        )
        fn.add_to_role_policy(self._ses_policy())
        return fn
