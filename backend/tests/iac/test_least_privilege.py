"""Moindre privilège du rôle inter-comptes (idée #30, ENF-SEC-02, § 15.2).

Sur un produit de sécurité, c'est le test d'infrastructure le plus important :
le rôle que le CLIENT accorde au MSP définit ce que le MSP peut faire dans son
compte. Une action de trop, un `Resource: "*"` non justifié, une condition
`sts:ExternalId` absente, et le cloisonnement multi-tenant ne vaut plus rien.

Ces tests verrouillent la politique au lieu de la décrire : un écart fait
échouer la CI en nommant précisément l'action ajoutée ou retirée.
"""

from __future__ import annotations

from typing import Any

import pytest

from tests.iac.test_client_template import load_template

# Annexe A du cahier des charges : les 16 actions, et pas une de plus.
ANNEX_A_ACTIONS = {
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
}

# Un rôle qui pilote des tests n'a aucune raison de toucher à IAM.
FORBIDDEN_IAM_PREFIXES = (
    "iam:Put", "iam:Create", "iam:Attach", "iam:Detach", "iam:Delete",
    "iam:Update", "iam:PassRole", "iam:AddUserToGroup",
)


def _resources(template: dict[str, Any]) -> dict[str, Any]:
    return template.get("Resources", {})


def _roles(template: dict[str, Any]) -> dict[str, Any]:
    return {
        name: body
        for name, body in _resources(template).items()
        if body.get("Type") == "AWS::IAM::Role"
    }


def _statements(role: dict[str, Any]) -> list[dict[str, Any]]:
    policies = role.get("Properties", {}).get("Policies", [])
    out: list[dict[str, Any]] = []
    for policy in policies:
        document = policy.get("PolicyDocument", {})
        statements = document.get("Statement", [])
        out.extend(statements if isinstance(statements, list) else [statements])
    return out


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    return value if isinstance(value, list) else [str(value)]


def _ops_role(template: dict[str, Any]) -> dict[str, Any]:
    roles = _roles(template)
    assert "RempartOpsRole" in roles, "le rôle d'exploitation a été renommé"
    return roles["RempartOpsRole"]


def _granted_actions(template: dict[str, Any]) -> set[str]:
    actions: set[str] = set()
    for statement in _statements(_ops_role(template)):
        if statement.get("Effect") == "Allow":
            actions.update(_as_list(statement.get("Action")))
    return actions


def test_grants_exactly_the_sixteen_annex_a_actions():
    granted = _granted_actions(load_template())
    missing = ANNEX_A_ACTIONS - granted
    extra = granted - ANNEX_A_ACTIONS
    assert not missing, f"actions de l'annexe A manquantes : {sorted(missing)}"
    assert not extra, (
        f"actions accordées EN PLUS de l'annexe A : {sorted(extra)} — "
        "un rôle de pilotage de tests ne doit rien pouvoir faire d'autre"
    )


@pytest.mark.parametrize("action", sorted(ANNEX_A_ACTIONS))
def test_every_granted_action_is_a_securityagent_action(action):
    """Aucune action d'un autre service ne doit se glisser dans le rôle."""
    assert action.startswith("securityagent:"), action
    granted = _granted_actions(load_template())
    assert all(a.startswith("securityagent:") for a in granted), sorted(granted)


def test_no_wildcard_action_is_granted():
    for statement in _statements(_ops_role(load_template())):
        for action in _as_list(statement.get("Action")):
            assert "*" not in action, (
                f"action avec joker interdite dans un rôle moindre privilège : {action}"
            )


def test_no_iam_write_permission():
    granted = _granted_actions(load_template())
    offenders = [a for a in granted if a.startswith(FORBIDDEN_IAM_PREFIXES)]
    assert offenders == [], f"le rôle d'exploitation ne doit pas toucher IAM : {offenders}"


def test_trust_requires_external_id_and_the_msp_orchestrator_role():
    """ENF-SEC-02 : identifiant externe unique par client, sessions courtes."""
    trust = _ops_role(load_template())["Properties"]["AssumeRolePolicyDocument"]
    statements = trust["Statement"]
    assert statements, "relation de confiance vide"
    statement = statements[0]

    assert statement["Action"] == "sts:AssumeRole"
    principal = statement["Principal"]
    assert "*" not in _as_list(principal.get("AWS")), (
        "un principal large permettrait à n'importe quel compte d'assumer le rôle"
    )

    condition = statement.get("Condition", {})
    string_equals = condition.get("StringEquals", {})
    assert "sts:ExternalId" in string_equals, (
        "sans condition sts:ExternalId, le rôle est exposé au problème du "
        "confused deputy : n'importe qui connaissant l'ARN peut l'assumer"
    )


def test_github_oidc_role_is_scoped_to_one_repository():
    roles = _roles(load_template())
    assert "GitHubOidcRole" in roles, "le rôle OIDC GitHub a été renommé"
    trust = roles["GitHubOidcRole"]["Properties"]["AssumeRolePolicyDocument"]
    statement = trust["Statement"][0]

    assert statement["Action"] == "sts:AssumeRoleWithWebIdentity"
    condition = statement.get("Condition", {})
    string_equals = condition.get("StringEquals", {})
    string_like = condition.get("StringLike", {})

    assert string_equals.get("token.actions.githubusercontent.com:aud") == (
        "sts.amazonaws.com"
    ), "audience OIDC non bornée : n'importe quel jeton GitHub serait accepté"
    subject = string_like.get("token.actions.githubusercontent.com:sub")
    assert subject and "repo:" in str(subject), (
        f"le rôle doit être borné à un dépôt précis, obtenu : {subject}"
    )
    assert str(subject).endswith(":*") or ":ref" in str(subject)


def test_pipeline_role_can_only_write_its_own_log_group():
    """Le rôle du pipeline ne doit pas écrire ailleurs que dans ses journaux."""
    roles = _roles(load_template())
    assert "GitHubOidcRole" in roles
    for statement in _statements(roles["GitHubOidcRole"]):
        if statement.get("Effect") != "Allow":
            continue
        for action in _as_list(statement.get("Action")):
            if action.startswith("logs:"):
                resources = _as_list(statement.get("Resource"))
                assert resources, "une action logs: sans Resource borné"
                assert "*" not in resources, (
                    f"écriture dans tous les groupes de journaux : {resources}"
                )


def test_resource_wildcard_is_limited_to_securityagent():
    """`Resource: "*"` n'est toléré que pour securityagent, jamais ailleurs.

    AWS Continuum ne documente pas de granularité par ressource pour ces
    actions ; le joker y est donc subi, pas choisi. Tout autre service doit
    avoir un Resource borné.
    """
    for statement in _statements(_ops_role(load_template())):
        actions = _as_list(statement.get("Action"))
        resources = _as_list(statement.get("Resource"))
        if "*" in resources:
            assert all(a.startswith("securityagent:") for a in actions), (
                f"Resource: \"*\" accordé à un service autre que securityagent : {actions}"
            )


def test_template_declares_no_unmanaged_role():
    """Deux rôles seulement : exploitation et pipeline OIDC. Pas de rôle fantôme."""
    assert set(_roles(load_template())) == {"RempartOpsRole", "GitHubOidcRole"}
