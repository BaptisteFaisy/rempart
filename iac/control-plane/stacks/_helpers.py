"""Shared helpers for Rempart CDK stacks."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import aws_cdk as cdk
import aws_cdk.aws_dynamodb as ddb
import aws_cdk.aws_iam as iam
import aws_cdk.aws_kms as kms
import aws_cdk.aws_lambda as _lambda
from constructs import Construct

PYTHON_RUNTIME = _lambda.Runtime.PYTHON_3_12
DEFAULT_TABLE_PREFIX = "rempart-"
DEFAULT_EXPIRE_AT_ATTRIBUTE = "expire_at"

# Racine du dépôt et du code Python déployé dans les Lambdas.
IAC_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = IAC_DIR.parent.parent
BACKEND_DIR = REPO_ROOT / "backend"
# Les dépendances tierces absentes du runtime Lambda, empaquetées dans un layer
# par scripts/build_lambda_layer.sh (dossier iac/control-plane/lambda-layer/).
LAMBDA_LAYER_DIR = IAC_DIR / "lambda-layer"
# Ni les tests, ni les caches, ni les artefacts locaux ne partent dans l'asset.
#
# MESURE du 13/11/2026 (poste de dev, venv posé dans backend/ par erreur) :
# chaque synthèse copiait 655 Mo de `.venv` dans un dossier temporaire, 111
# dossiers `cdk.out*` = **59 Go** laissés dans /tmp, disque à 100 %, suite de
# tests en ENOSPC. Un environnement virtuel n'est jamais du code déployé : il
# est exclu ici, et `tests/iac/test_asset_hygiene.py` le vérifie sur l'asset
# réel (pas seulement sur cette constante).
LAMBDA_ASSET_EXCLUDES = [
    # Le dossier ET son contenu : une exclusion `x/**` seule laisse passer les
    # fichiers cachés d'un dossier (`ignore` de CDK), donc on nomme les deux.
    "tests",
    "tests/**",
    "**/__pycache__",
    "**/__pycache__/**",
    "**/*.pyc",
    ".pytest_cache",
    ".pytest_cache/**",
    ".ruff_cache",
    ".ruff_cache/**",
    ".mypy_cache",
    ".mypy_cache/**",
    ".venv",
    ".venv/**",
    "**/.venv",
    "**/.venv/**",
    ".git",
    ".git/**",
    "pyproject.toml",
]


#: Opérations d'AWS Security Agent (Continuum) réellement appelées par le code.
#:
#: INCIDENT RÉEL (13 nov 2026) : aucune de ces permissions n'était accordée aux
#: Lambdas du plan de contrôle. Le premier test Continuum réel a échoué sur
#: « AccessDeniedException … not authorized to perform:
#: securityagent:StartPentestJob » : **le test ne pouvait pas démarrer**, quel
#: que soit le chemin. Le rôle du compte client (`rempart-ops-role`) porte la
#: même liste, pour le déploiement cross-account.
SECURITYAGENT_ACTIONS = (
    "securityagent:StartPentestJob",
    "securityagent:StopPentestJob",
    "securityagent:BatchGetPentestJobs",
    "securityagent:ListFindings",
    "securityagent:BatchGetFindings",
    "securityagent:ListPentestJobsForPentest",
    "securityagent:ListPentestJobTasks",
    "securityagent:BatchGetPentestJobTasks",
    "securityagent:ListAgentSpaces",
    "securityagent:BatchGetAgentSpaces",
    "securityagent:CreateAgentSpace",
    "securityagent:CreateTargetDomain",
    "securityagent:VerifyTargetDomain",
    "securityagent:BatchGetTargetDomains",
    "securityagent:ListTargetDomains",
    "securityagent:CreatePentest",
    "securityagent:UpdateFinding",
    "securityagent:StartCodeRemediation",
)


def securityagent_policy(
    scope: Construct, *, account: str, region: str, id_: str = "RempartSecurityAgentPolicy"
) -> iam.IManagedPolicy:
    """Politique gérée portant les droits Continuum, attachée aux rôles qui en ont besoin.

    PIEGE CDK (mesuré le 13/11/2026) : ces droits ajoutés en `add_to_role_policy`
    font déborder la politique inline du rôle (limite AWS : 10 240 caractères).
    CDK la déplace alors dans une « OverflowPolicy » managed, et **les autres
    instructions de la même politique disparaissent du template** — les droits
    `ssm:GetParameter` de la clé du modèle ont été perdus de la sorte, sans
    aucune erreur. Une politique gérée partagée évite le débordement : une
    seule fois les droits, et les politiques inline restent sous la limite.

    Les ressources sont celles du **propre** compte : le déploiement
    cross-account passe par le rôle d'opérateur du client (`rempart-ops-role`),
    assumé via `REMPART_SA_ROLE_ARN`.
    """
    return iam.ManagedPolicy(
        scope,
        id_,
        statements=[
            iam.PolicyStatement(
                sid="RempartSecurityAgent",
                actions=list(SECURITYAGENT_ACTIONS),
                resources=[f"arn:aws:securityagent:{region}:{account}:*"],
            )
        ],
    )


def grant_securityagent(fn: _lambda.Function, policy: iam.IManagedPolicy) -> None:
    """Attache la politique Continuum au rôle d'une Lambda."""
    fn.role.add_managed_policy(policy)


def create_kms_key(scope: Construct, id_: str, alias: str) -> kms.Key:
    """Create a KMS customer managed key with key rotation enabled."""
    return kms.Key(
        scope,
        id_,
        alias=alias,
        enable_key_rotation=True,
        removal_policy=cdk.RemovalPolicy.RETAIN,
    )


def runtime_layer(scope: Construct, id_: str) -> _lambda.ILayerVersion | None:
    """Layer des dépendances tierces — **fail fast** s'il n'est pas construit.

    Construit par ``scripts/build_lambda_layer.sh`` : il pose
    ``iac/control-plane/lambda-layer/python/`` avec les paquets installés pour
    ``manylinux2014_x86_64`` / CPython 3.12.

    INCIDENT RÉEL (11 nov 2026, compte 710332178565) : cette fonction rendait
    ``None`` silencieusement quand le dossier était absent. Le ``cdk deploy`` a
    donc créé 11 Lambdas avec ``layers=[]``, et la première invocation a échoué
    en ``Runtime.ImportModuleError: No module named 'requests'`` (et ``fpdf``
    pour l'API). Le synth passait, le déploiement réussissait, et TOUTES les
    fonctions étaient mortes — exactement le même angle mort que le placeholder
    inline corrigé ailleurs. On lève donc une erreur explicite.

    Échappatoire pour la synthèse sans déploiement (tests, ``cdk synth``,
    revue de template) : ``REMPART_ALLOW_MISSING_LAYER=1``. Cette variable ne
    doit JAMAIS être posée pour un vrai déploiement.
    """
    python_dir = LAMBDA_LAYER_DIR / "python"
    if not python_dir.is_dir():
        if os.environ.get("REMPART_ALLOW_MISSING_LAYER") == "1":
            return None
        raise RuntimeError(
            "Layer des dépendances Lambda absent : "
            f"{LAMBDA_LAYER_DIR}/python introuvable.\n"
            "Sans lui, les Lambdas se déploient mais échouent à l'invocation "
            "(ImportModuleError sur requests / fpdf / strands).\n"
            "Construis-le d'abord :  ./scripts/build_lambda_layer.sh\n"
            "Pour synthétiser sans déployer (tests, cdk synth) : "
            "REMPART_ALLOW_MISSING_LAYER=1"
        )
    return _lambda.LayerVersion(
        scope,
        id_,
        code=_lambda.Code.from_asset(str(LAMBDA_LAYER_DIR)),
        compatible_runtimes=[PYTHON_RUNTIME],
        description="Rempart runtime deps (fpdf2, requests, strands-agents)",
    )


def create_encrypted_table(
    scope: Construct,
    id_: str,
    table_name: str,
    partition_key: ddb.Attribute,
    sort_key: ddb.Attribute | None = None,
    encryption_key: kms.IKey | None = None,
    time_to_live_attribute: str = DEFAULT_EXPIRE_AT_ATTRIBUTE,
) -> ddb.Table:
    """Create a DynamoDB table with KMS encryption, PITR, TTL and RETAIN policy."""
    encryption = (
        ddb.TableEncryption.CUSTOMER_MANAGED
        if encryption_key is not None
        else ddb.TableEncryption.AWS_MANAGED
    )
    return ddb.Table(
        scope,
        id_,
        table_name=table_name,
        partition_key=partition_key,
        sort_key=sort_key,
        billing_mode=ddb.BillingMode.PAY_PER_REQUEST,
        point_in_time_recovery_specification=ddb.PointInTimeRecoverySpecification(
            point_in_time_recovery_enabled=True
        ),
        time_to_live_attribute=time_to_live_attribute,
        removal_policy=cdk.RemovalPolicy.RETAIN,
        encryption=encryption,
        encryption_key=encryption_key,
    )


def handler_reference(module: str, function: str) -> str:
    """Render the ``Handler`` value of a Lambda function (``module.function``)."""
    return f"{module}.{function}"


def split_handler(handler: str) -> tuple[str, str]:
    """Split a Lambda ``Handler`` value into ``(module, function)``."""
    module, _, function = handler.rpartition(".")
    return module, function


def create_python_lambda(
    scope: Construct,
    id_: str,
    handler: str,
    environment: dict[str, str] | None = None,
    timeout_seconds: int = 30,
    memory_size: int = 512,
    layers: list[_lambda.ILayerVersion] | None = None,
    **kwargs: Any,
) -> _lambda.Function:
    """Create a Python 3.12 Lambda running the REAL ``backend/`` code.

    L'asset pointe vers ``backend/`` (racine du package ``rempart``) : le
    handler ``rempart.api.app.lambda_handler`` y est donc résoluble. Un
    placeholder inline ne suffirait pas — il déploierait des fonctions vides.

    Les dépendances tierces absentes du runtime Lambda (``fpdf2`` pour les
    rapports PDF, ``requests`` pour les tickets GitHub, ``strands-agents``
    pour l'agent de tri) viennent d'un layer construit par
    ``scripts/build_lambda_layer.sh``. Sans layer, les modules qui n'en ont
    pas besoin fonctionnent quand même ; les autres lèvent à l'import, ce qui
    est visible immédiatement au lieu d'échouer silencieusement.
    """
    return _lambda.Function(
        scope,
        id_,
        runtime=PYTHON_RUNTIME,
        handler=handler,
        code=_lambda.Code.from_asset(str(BACKEND_DIR), exclude=LAMBDA_ASSET_EXCLUDES),
        timeout=cdk.Duration.seconds(timeout_seconds),
        memory_size=memory_size,
        environment=environment or {},
        layers=layers or [],
        tracing=_lambda.Tracing.ACTIVE,
        **kwargs,
    )
