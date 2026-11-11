"""Shared helpers for Rempart CDK stacks."""

from __future__ import annotations

from typing import Any

import aws_cdk as cdk
import aws_cdk.aws_dynamodb as ddb
import aws_cdk.aws_kms as kms
import aws_cdk.aws_lambda as _lambda
from constructs import Construct

PYTHON_RUNTIME = _lambda.Runtime.PYTHON_3_12
DEFAULT_TABLE_PREFIX = "rempart-"
DEFAULT_EXPIRE_AT_ATTRIBUTE = "expire_at"


def create_kms_key(scope: Construct, id_: str, alias: str) -> kms.Key:
    """Create a KMS customer managed key with key rotation enabled."""
    return kms.Key(
        scope,
        id_,
        alias=alias,
        enable_key_rotation=True,
        removal_policy=cdk.RemovalPolicy.RETAIN,
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
    **kwargs: Any,
) -> _lambda.Function:
    """Create a Python 3.12 Lambda function with standard settings."""
    # Inline code stub or asset code stub for synthesizer / packaging
    return _lambda.Function(
        scope,
        id_,
        runtime=PYTHON_RUNTIME,
        handler=handler,
        code=_lambda.Code.from_inline(
            "# Placeholder code for Rempart CDK deployment\n"
            "def lambda_handler(event, context):\n"
            "    return {'statusCode': 200, 'body': 'ok'}\n"
        ),
        timeout=cdk.Duration.seconds(timeout_seconds),
        memory_size=memory_size,
        environment=environment or {},
        **kwargs,
    )
