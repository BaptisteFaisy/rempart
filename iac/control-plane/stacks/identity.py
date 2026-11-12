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

# Domaine Cognito **gratuit** (préfixe `*.auth.<region>.amazoncognito.com`).
# Un domaine personnalisé (`custom_domain_name`) exigerait un certificat ACM et
# donc un domaine acheté : interdit par la contrainte 0 €.
DOMAIN_PREFIX = "rempart"

# Valeur par défaut du paramètre CDK PortalUrl : la distribution CloudFront
# actuelle (voir docs/portal-deployment.md). Convention : SANS slash final —
# les deux variantes (avec/sans) sont dérivées dans `_build_client`.
DEFAULT_PORTAL_URL = "https://d1o2xnfrq8xomh.cloudfront.net"


class IdentityStack(cdk.Stack):
    """Provisions Cognito UserPool, free hosted domain, OAuth client, 7 groups."""

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # L'URL publique du portail est déclarée UNE fois (paramètre CDK) pour
        # ne pas la coder en dur ; surchargeable : cdk deploy RempartIdentityStack
        # --parameters PortalUrl=https://autre-hote
        portal_url = cdk.CfnParameter(
            self,
            "PortalUrl",
            type="String",
            default=DEFAULT_PORTAL_URL,
            description=(
                "URL publique du portail (CloudFront), sans slash final. "
                "Sert aux callback/logout URLs du client OAuth."
            ),
        ).value_as_string

        self.user_pool = self._build_user_pool()
        # API CDK ≥ 2.x : le préfixe gratuit passe par `CognitoDomainOptions`
        # (`custom_domain` = domaine personnalisé payant, jamais utilisé ici).
        self.user_pool_domain = self.user_pool.add_domain(
            "RempartAuthDomain",
            cognito_domain=cognito.CognitoDomainOptions(domain_prefix=DOMAIN_PREFIX),
        )
        self.user_pool_client = self._build_client(portal_url)
        self.groups = self._build_groups()

        # NB : `domain_name` ne renvoie que le préfixe (Ref CFN) ; l'hôte OIDC
        # complet d'un domaine gratuit est `<préfixe>.auth.<région>.amazoncognito.com`.
        cdk.CfnOutput(
            self,
            "CognitoDomainUrl",
            value=f"https://{DOMAIN_PREFIX}.auth.{cdk.Aws.REGION}.amazoncognito.com",
            description="Hôte OIDC (authorize/token/logout) du User Pool.",
        )
        cdk.CfnOutput(
            self,
            "UserPoolClientId",
            value=self.user_pool_client.user_pool_client_id,
            description="Client ID public du portail (sans secret).",
        )

    def _build_user_pool(self) -> cognito.UserPool:
        """User Pool `rempart-users` : inscription fermée, e-mail vérifié."""
        return cognito.UserPool(
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

    def _build_client(self, portal_url: str) -> cognito.UserPoolClient:
        """Client SPA public : authorization-code + PKCE, sans secret.

        Note CDK/CloudFormation : modifier les `AllowedOAuthFlows` d'un client
        **existant** exige `AllowedOAuthFlowsUserPoolClient=true`. Depuis
        aws-cdk-lib ≥ 2.1xx l'API est unifiée sous `o_auth=OAuthSettings(...)`
        (les anciens `o_auth_flows`/`o_auth_scopes`/`callback_urls` ont disparu) ;
        le L2 positionne `AllowedOAuthFlowsUserPoolClient` automatiquement dès
        qu'un flux OAuth est déclaré (vérifié en réel sur
        `7qr971kfs2jlj5i2d065mb1fbl`) : aucune propriété supplémentaire ici.
        """
        # Racine avec ET sans slash final : le navigateur peut atterrir sur
        # l'une ou l'autre après la redirection Cognito.
        redirect_urls = [portal_url, f"{portal_url}/"]
        return self.user_pool.add_client(
            "RempartWebClient",
            user_pool_client_name="rempart-portal-client",
            generate_secret=False,
            auth_flows=cognito.AuthFlow(
                user_password=True,
                user_srp=True,
            ),
            o_auth=cognito.OAuthSettings(
                flows=cognito.OAuthFlows(authorization_code_grant=True),
                scopes=[
                    cognito.OAuthScope.OPENID,
                    cognito.OAuthScope.EMAIL,
                    cognito.OAuthScope.PROFILE,
                ],
                callback_urls=redirect_urls,
                logout_urls=redirect_urls,
            ),
            supported_identity_providers=[
                cognito.UserPoolClientIdentityProvider.COGNITO,
            ],
            read_attributes=cognito.ClientAttributes().with_custom_attributes("tenant_id"),
            write_attributes=cognito.ClientAttributes().with_custom_attributes("tenant_id"),
        )

    def _build_groups(self) -> dict[str, cognito.CfnUserPoolGroup]:
        """Les 7 groupes de rôles lus par `resolve_principal` (cognito:groups)."""
        groups: dict[str, cognito.CfnUserPoolGroup] = {}
        for idx, role in enumerate(ROLES):
            groups[role] = cognito.CfnUserPoolGroup(
                self,
                f"Group{role.title().replace('_', '')}",
                user_pool_id=self.user_pool.user_pool_id,
                group_name=role,
                description=f"Rempart role group: {role}",
                precedence=idx,
            )
        return groups
