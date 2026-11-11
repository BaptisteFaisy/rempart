"""Shared helpers for Rempart CDK stacks."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import aws_cdk as cdk
import aws_cdk.aws_dynamodb as ddb
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
LAMBDA_ASSET_EXCLUDES = [
    "tests/**",
    "**/__pycache__/**",
    "**/*.pyc",
    ".pytest_cache/**",
    ".ruff_cache/**",
    "pyproject.toml",
]


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
    """Layer des dépendances tierces, ou ``None`` s'il n'a pas été construit.

    Construit par ``scripts/build_lambda_layer.sh`` : il pose
    ``iac/control-plane/lambda-layer/python/`` avec les paquets installés pour
    ``manylinux2014_x86_64`` / CPython 3.12. Tant que le dossier n'existe pas,
    on renvoie ``None`` plutôt que de faire échouer le synth : les Lambdas qui
    n'ont pas besoin de dépendance tierce restent déployables.
    """
    python_dir = LAMBDA_LAYER_DIR / "python"
    if not python_dir.is_dir():
        return None
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
        point_in_time_recovery=True,
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
