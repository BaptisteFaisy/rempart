"""Pytest tests for CDK synthesis of Rempart control-plane stacks."""

from __future__ import annotations

import sys
from pathlib import Path

from aws_cdk import assertions

# Ensure iac/control-plane is on sys.path
IAC_DIR = Path(__file__).resolve().parents[3] / "iac" / "control-plane"
if str(IAC_DIR) not in sys.path:
    sys.path.insert(0, str(IAC_DIR))

from app import build_app  # noqa: E402

EXPECTED_TABLES = [
    "rempart-tenants",
    "rempart-applications",
    "rempart-test-configs",
    "rempart-runs",
    "rempart-findings",
    "rempart-decisions",
    "rempart-reports",
    "rempart-budget",
    "rempart-audit",
]

EXPECTED_GROUPS = [
    "platform_admin",
    "analyst",
    "account_manager",
    "client_security",
    "client_dev",
    "executive",
    "demo",
]


def test_synth_storage_stack():
    """Verify storage stack has 9 KMS-encrypted DynamoDB tables with PITR and TTL."""
    app = build_app()
    app.synth()
    stack = app.node.find_child("RempartStorageStack")
    template = assertions.Template.from_stack(stack)

    # 9 DynamoDB tables
    tables = template.find_resources("AWS::DynamoDB::Table")
    assert len(tables) == 9

    table_names = [props["Properties"].get("TableName") for props in tables.values()]
    for expected in EXPECTED_TABLES:
        assert expected in table_names

    # Check KMS encryption, TTL, and PITR on every table
    for logical_id, resource in tables.items():
        props = resource.get("Properties", {})
        assert props.get("PointInTimeRecoverySpecification", {}).get(
            "PointInTimeRecoveryEnabled"
        ) is True
        assert (
            props.get("TimeToLiveSpecification", {}).get("AttributeName")
            == "expire_at"
        )
        assert props.get("SSESpecification", {}).get("SSEEnabled") is True
        assert resource.get("DeletionPolicy") == "Retain"


def test_synth_identity_stack():
    """Verify identity stack contains UserPool, Client and the 7 role groups."""
    app = build_app()
    app.synth()
    stack = app.node.find_child("RempartIdentityStack")
    template = assertions.Template.from_stack(stack)

    template.resource_count_is("AWS::Cognito::UserPool", 1)
    template.resource_count_is("AWS::Cognito::UserPoolClient", 1)
    template.resource_count_is("AWS::Cognito::UserPoolGroup", 7)

    groups = template.find_resources("AWS::Cognito::UserPoolGroup")
    group_names = [g["Properties"]["GroupName"] for g in groups.values()]
    for role in EXPECTED_GROUPS:
        assert role in group_names


def test_synth_api_stack():
    """Verify API stack contains HttpApi, authorizer, and lambda integration."""
    app = build_app()
    app.synth()
    stack = app.node.find_child("RempartApiStack")
    template = assertions.Template.from_stack(stack)

    template.resource_count_is("AWS::ApiGatewayV2::Api", 1)
    template.resource_count_is("AWS::ApiGatewayV2::Authorizer", 1)
    template.resource_count_is("AWS::Lambda::Function", 1)

    # Check env variables in Lambda
    lambdas = template.find_resources("AWS::Lambda::Function")
    fn = list(lambdas.values())[0]
    env_vars = fn["Properties"]["Environment"]["Variables"]
    assert "REMPART_TABLE_PREFIX" in env_vars
    assert "REMPART_REGION" in env_vars
    assert "REMPART_HOURLY_RATE" in env_vars


def test_synth_orchestrator_stack():
    """Verify orchestrator stack contains Step Functions StateMachine and Lambdas."""
    app = build_app()
    app.synth()
    stack = app.node.find_child("RempartOrchestratorStack")
    template = assertions.Template.from_stack(stack)

    template.resource_count_is("AWS::StepFunctions::StateMachine", 1)
    # 6 task lambdas + 1 discovery lambda = 7
    lambdas = template.find_resources("AWS::Lambda::Function")
    assert len(lambdas) >= 7

    # EventBridge rules: 5-minute discovery + monthly schedule
    rules = template.find_resources("AWS::Events::Rule")
    assert len(rules) >= 2


def test_synth_portal_stack():
    """Verify portal stack contains S3 Bucket and CloudFront Distribution."""
    app = build_app()
    app.synth()
    stack = app.node.find_child("RempartPortalStack")
    template = assertions.Template.from_stack(stack)

    template.resource_count_is("AWS::S3::Bucket", 1)
    template.resource_count_is("AWS::CloudFront::Distribution", 1)


def test_synth_notifications_stack():
    """Verify notifications stack contains SES identity/configuration and lambda."""
    app = build_app()
    app.synth()
    stack = app.node.find_child("RempartNotificationsStack")
    template = assertions.Template.from_stack(stack)

    template.resource_count_is("AWS::SES::EmailIdentity", 1)
    template.resource_count_is("AWS::SES::ConfigurationSet", 1)
    template.resource_count_is("AWS::Lambda::Function", 1)
