"""Tests for the client account CloudFormation template."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

TEMPLATE_PATH = (
    Path(__file__).resolve().parents[3]
    / "iac"
    / "client-account"
    / "rempart-client.template.yaml"
)

EXPECTED_ACTIONS = [
    "securityagent:StartPentestJob",
    "securityagent:StopPentestJob",
    "securityagent:BatchGetPentestJobs",
    "securityagent:ListFindings",
    "securityagent:BatchGetFindings",
    "securityagent:ListIntegratedResources",
    "securityagent:ListPentestJobsForPentest",
    "securityagent:ListPentestJobTasks",
    "securityagent:BatchGetPentestJobTasks",
    "securityagent:ListPentests",
    "securityagent:BatchGetPentests",
    "securityagent:ListDiscoveredEndpoints",
    "securityagent:UpdateFinding",
    "securityagent:StartCodeRemediation",
    "securityagent:ListAgentSpaces",
    "securityagent:BatchGetAgentSpaces",
]


class _CfnSafeLoader(yaml.SafeLoader):
    """SafeLoader that handles CloudFormation intrinsic tags gracefully."""


def _generic_cfn_constructor(loader: yaml.SafeLoader, node: yaml.Node) -> Any:
    if isinstance(node, yaml.ScalarNode):
        return loader.construct_scalar(node)
    if isinstance(node, yaml.SequenceNode):
        return loader.construct_sequence(node)
    if isinstance(node, yaml.MappingNode):
        return loader.construct_mapping(node)
    return None


for tag in [
    "!Ref",
    "!Sub",
    "!GetAtt",
    "!Join",
    "!Select",
    "!Split",
    "!FindInMap",
    "!Base64",
    "!Cidr",
    "!And",
    "!Equals",
    "!If",
    "!Not",
    "!Or",
    "!Condition",
]:
    _CfnSafeLoader.add_constructor(tag, _generic_cfn_constructor)


def load_template() -> dict[str, Any]:
    with open(TEMPLATE_PATH, encoding="utf-8") as f:
        return yaml.load(f, Loader=_CfnSafeLoader)


def test_template_parameters():
    tmpl = load_template()
    params = tmpl.get("Parameters", {})
    expected_params = [
        "MspAccountId",
        "MspOrchestratorRoleName",
        "ExternalId",
        "GitHubOrg",
        "GitHubRepo",
    ]
    for p in expected_params:
        assert p in params, f"Missing parameter {p}"
    assert params["MspOrchestratorRoleName"].get("Default") == "rempart-orchestrator"


def test_ops_role_trust_and_actions():
    tmpl = load_template()
    resources = tmpl.get("Resources", {})
    ops_role = resources.get("RempartOpsRole")
    assert ops_role is not None
    assert ops_role.get("Type") == "AWS::IAM::Role"

    props = ops_role["Properties"]
    assume_doc = props["AssumeRolePolicyDocument"]
    stmt = assume_doc["Statement"][0]
    assert stmt["Effect"] == "Allow"
    assert stmt["Action"] == "sts:AssumeRole"

    # Verify ExternalId condition
    cond = stmt["Condition"]["StringEquals"]
    assert "sts:ExternalId" in cond
    assert cond["sts:ExternalId"] == "ExternalId"

    # Verify 16 securityagent actions
    policies = props["Policies"]
    sec_policy = next(p for p in policies if p["PolicyName"] == "RempartSecurityAgentPolicy")
    actions = sec_policy["PolicyDocument"]["Statement"][0]["Action"]
    assert len(actions) == 16
    for exp in EXPECTED_ACTIONS:
        assert exp in actions


def test_github_oidc_role():
    tmpl = load_template()
    resources = tmpl.get("Resources", {})
    oidc_role = resources.get("GitHubOidcRole")
    assert oidc_role is not None
    assert oidc_role.get("Type") == "AWS::IAM::Role"

    stmt = oidc_role["Properties"]["AssumeRolePolicyDocument"]["Statement"][0]
    assert stmt["Action"] == "sts:AssumeRoleWithWebIdentity"
    cond = stmt["Condition"]
    assert "token.actions.githubusercontent.com:aud" in cond["StringEquals"]
    assert "token.actions.githubusercontent.com:sub" in cond["StringLike"]


def test_log_group_and_budget():
    tmpl = load_template()
    resources = tmpl.get("Resources", {})
    log_group = resources.get("PipelineLogGroup")
    assert log_group is not None
    assert log_group["Type"] == "AWS::Logs::LogGroup"
    assert log_group["Properties"]["RetentionInDays"] == 400
    assert log_group["Properties"]["LogGroupName"] == "/rempart/pipeline"

    budget = resources.get("ClientMonthlyBudget")
    assert budget is not None
    assert budget["Type"] == "AWS::Budgets::Budget"
    notifs = budget["Properties"]["NotificationsWithSubscribers"]
    thresholds = [n["Notification"]["Threshold"] for n in notifs]
    assert 50 in thresholds
    assert 80 in thresholds
    assert 100 in thresholds


def test_outputs():
    tmpl = load_template()
    outputs = tmpl.get("Outputs", {})
    assert "OpsRoleArn" in outputs
    assert "GitHubOidcRoleArn" in outputs
    assert "ExternalId" in outputs
