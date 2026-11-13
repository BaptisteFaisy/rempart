"""IaC : le modèle de triage est câblé sur les Lambdas de l'orchestrateur.

Le triage se joue dans l'orchestrateur, pas dans l'API. Sans ces variables,
les Lambdas n'auraient aucun endpoint LLM et retomberaient sur le règleur —
c'est-à-dire que le « vrai modèle » ne serait jamais utilisé en production.

Défaut corrigé le 13/11/2026 : la clé était posée en **référence dynamique**
`resolve:ssm-secure` dans `Environment.Variables`. CloudFormation refuse cette
forme (« SSM Secure reference is not supported in [AWS::Lambda::Function/
Properties/Environment/Variables/…] »), le changeset échoue, et donc **le vrai
modèle n'a jamais pu être déployé**. Le test qui verrouillait cette référence
prouvait un template impossible à déployer. La Lambda lit désormais le
SecureString elle-même, au premier triage.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from aws_cdk import assertions

IAC_DIR = Path(__file__).resolve().parents[3] / "iac" / "control-plane"
if str(IAC_DIR) not in sys.path:
    sys.path.insert(0, str(IAC_DIR))

from app import build_app  # noqa: E402

PARAM_ENV = "REMPART_LLM_API_KEY_SSM_PARAM"


@pytest.fixture(scope="module")
def template() -> assertions.Template:
    """Synthèse unique pour les tests qui ne changent pas l'environnement.

    Une synthèse par test coûterait plusieurs secondes dès que le layer existe
    (136 Mo recopiés à chaque fois) : le budget CI est de 5 minutes.
    """
    app = build_app()
    app.synth()
    return assertions.Template.from_stack(app.node.find_child("RempartOrchestratorStack"))


def _envs(template: assertions.Template) -> list[dict[str, str]]:
    functions = template.find_resources("AWS::Lambda::Function")
    return [
        props["Properties"]["Environment"]["Variables"]
        for props in functions.values()
    ]


def _actions(statement: dict) -> list[str]:
    raw = statement.get("Action", [])
    return [raw] if isinstance(raw, str) else list(raw)


def _llm_key_statements(template: assertions.Template) -> list[dict]:
    """Instructions IAM qui donnent le droit de lire la clé du modèle."""
    statements = []
    for policy in template.find_resources("AWS::IAM::Policy").values():
        for statement in policy["Properties"]["PolicyDocument"]["Statement"]:
            if "ssm:GetParameter" in _actions(statement):
                statements.append(statement)
    return statements


def test_les_lambdas_du_triage_portent_l_endpoint_du_modele(template):
    for env in _envs(template):
        assert env.get("REMPART_LLM_BASE_URL", "").startswith("https://")


def test_aucune_reference_dynamique_dans_les_variables_d_environnement(template):
    """Garde de classe : CFN rejette `resolve:` dans les variables d'une Lambda.

    Ce test attrape le défaut au synth, pas au déploiement : il a coûté un
    changeset en échec et un « le LLM est câblé » qui n'a jamais tourné.
    """
    for env in _envs(template):
        rendered = json.dumps(env)
        assert "{{resolve:" not in rendered, (
            f"référence dynamique dans les variables d'environnement : {rendered}"
        )


def test_sans_parametre_ssm_aucune_cle_n_est_passee(template, monkeypatch):
    monkeypatch.delenv(PARAM_ENV, raising=False)
    for env in _envs(template):
        assert "REMPART_LLM_API_KEY" not in env
        assert PARAM_ENV not in env


def test_le_parametre_ssm_est_passe_par_nom_jamais_par_valeur(monkeypatch):
    monkeypatch.setenv(PARAM_ENV, "/rempart/dev/llm-key")
    app = build_app()
    app.synth()
    envs = _envs(assertions.Template.from_stack(app.node.find_child("RempartOrchestratorStack")))
    assert envs, "aucune Lambda orchestrateur synthétisée"
    for env in envs:
        assert env.get(PARAM_ENV) == "/rempart/dev/llm-key"
        # La valeur n'est jamais matérialisée : ni en clair, ni en référence.
        assert "REMPART_LLM_API_KEY" not in env
        assert "resolve:" not in json.dumps(env)


def test_un_seul_lambda_recoit_le_droit_de_lire_la_cle(monkeypatch):
    """Le droit de lire la clé ne doit pas être donné aux dix fonctions."""
    monkeypatch.setenv(PARAM_ENV, "/rempart/dev/llm-key")
    app = build_app()
    app.synth()
    built = assertions.Template.from_stack(app.node.find_child("RempartOrchestratorStack"))
    statements = _llm_key_statements(built)

    assert len(statements) == 1, f"{len(statements)} fonctions peuvent lire la clé"
    statement = statements[0]
    resources = statement.get("Resource", [])
    resources = [resources] if isinstance(resources, str) else resources
    assert any("/rempart/dev/llm-key" in str(r) for r in resources), resources
    # SecureString : il faut aussi le déchiffrement, limité au service SSM.
    kms = [
        s
        for policy in built.find_resources("AWS::IAM::Policy").values()
        for s in policy["Properties"]["PolicyDocument"]["Statement"]
        if "kms:Decrypt" in _actions(s)
    ]
    assert kms, "aucun kms:Decrypt : la SecureString ne pourra pas être lue"
    condition = json.dumps(kms[0].get("Condition", {}))
    assert "ssm." in condition and "ViaService" in condition, condition


def test_les_droits_continuum_sont_dans_une_politique_managee_partagee():
    """INCIDENT RÉEL (13 nov 2026) : les droits Continuum en `add_to_role_policy`
    faisaient déborder la politique inline du rôle (limite AWS : 10 240
    caractères). CDK la déplaçait alors dans une « OverflowPolicy » managed et
    **les autres instructions de la même politique disparaissaient du
    template** : les droits `ssm:GetParameter` de la clé du modèle ont été
    perdus de la sorte, sans la moindre erreur.

    Les droits Continuum doivent donc être une politique **gérée**, attachée
    aux rôles — et les droits de la clé du modèle doivent rester lisibles
    dans la politique inline du rôle qui trie.
    """
    app = build_app()
    app.synth()
    built = assertions.Template.from_stack(app.node.find_child("RempartOrchestratorStack"))

    managed = built.find_resources("AWS::IAM::ManagedPolicy")
    assert managed, "aucune politique gérée : les droits Continuum débordent l'inline"
    sa_policies = [
        policy
        for policy in managed.values()
        if "securityagent:StartPentestJob" in json.dumps(policy["Properties"])
    ]
    assert sa_policies, "les droits Continuum ne sont dans aucune politique gérée"
