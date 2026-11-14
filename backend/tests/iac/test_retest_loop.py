"""Boucle de retest verifiée dans le gabarit (idée #51) : route, droit, routage.

Trois choses qu'un test unitaire ne peut pas voir et qui, ratées, rendent la
boucle silencieusement inopérante :

1. la route `/v1/events/github` ne doit porter **aucun** autorisateur JWT — GitHub
   n'a pas de jeton Cognito ; avec un autorisateur, la boucle ne se ferme jamais
   et le symptôme visible est un banal 401 ;
2. la Lambda API doit avoir `states:StartExecution`, **restreint à sa machine** :
   sans le droit, le démarrage échoue côté AWS après un 202 parfaitement trompeur ;
   avec un joker, une route publique pourrait exécuter n'importe quelle machine
   du compte ;
3. le routage `trigger == "retest"` doit vivre **à l'intérieur** du cas « run
   terminé ». Placé avant, un job arrêté par le garde-fou de budget atteindrait
   `close_or_reopen` sur un run vide — et `close_or_reopen` fermerait alors des
   failles encore présentes, sans preuve. C'est le pire défaut possible pour un
   produit de sécurité : déclarer corrigé ce qui ne l'est pas.

Précédent d'import : `test_least_privilege.py` réutilise `load_template` du test
voisin plutôt que de dupliquer le chargeur.
"""

from __future__ import annotations

import json
from functools import lru_cache
from typing import Any

from tests.iac.test_api_cors_and_reports import _routes, _template

GITHUB_ROUTE = "POST /v1/events/github"
MACHINE_LOGICAL_ID = "PentestLifecycleMachineC8C093F8"


@lru_cache(maxsize=None)
def _api_template() -> dict[str, Any]:
    """Gabarit de la stack API, mémoïsé : la synthèse CDK coûte cher en secondes."""
    return _template("RempartApiStack").to_json()


@lru_cache(maxsize=None)
def _orchestrator_template() -> dict[str, Any]:
    return _template("RempartOrchestratorStack").to_json()


def _api_routes() -> dict[str, dict]:
    """Routes de l'API (objet Template, pas son JSON : ``_routes`` attend celui-là)."""
    return _routes(_template("RempartApiStack"))


def _statements(template: dict[str, Any], resource_type: str) -> list[dict[str, Any]]:
    """Toutes les instructions de politique des ressources du type donné."""
    out: list[dict[str, Any]] = []
    for body in template.get("Resources", {}).values():
        if body.get("Type") != resource_type:
            continue
        document = body.get("Properties", {}).get("PolicyDocument", {})
        statements = document.get("Statement", [])
        out.extend(statements if isinstance(statements, list) else [statements])
    return out


def _definition(template: dict[str, Any], logical_id: str) -> dict[str, Any]:
    """Définition de la machine, en JSON parsé.

    CDK l'émet en `Fn::Join` avec des références (partition, ARNs de Lambda) :
    les fragments non textuels sont remplacés par un littéral, ce qui rend le
    JSON lisible sans perdre la structure des états — c'est la structure qui
    nous intéresse, pas les ARNs.
    """
    raw = template["Resources"][logical_id]["Properties"]["DefinitionString"]
    parts = raw.get("Fn::Join", [[], []])[1] if isinstance(raw, dict) else [raw]
    text = "".join(part if isinstance(part, str) else "aws" for part in parts)
    return json.loads(text)


def _choice(definition: dict[str, Any], state_name: str) -> dict[str, Any]:
    states = definition["States"]
    assert state_name in states, f"état « {state_name} » absent : {sorted(states)}"
    return states[state_name]


# --------------------------------------------------------------------------- #
# La route
# --------------------------------------------------------------------------- #
def test_la_route_github_existe_et_ne_porte_aucun_autorisateur():
    """Sans cette route, le webhook GitHub est un 404 — et rien d'autre ne le dit."""
    routes = _api_routes()
    assert GITHUB_ROUTE in routes, sorted(routes)
    props = routes[GITHUB_ROUTE]
    assert props.get("AuthorizerId") in (None, ""), "l'autorisateur JWT bloquerait GitHub"
    assert props.get("AuthorizationType") == "NONE"


def test_la_route_github_nest_pas_la_seule_porte_des_events():
    """Le webhook CI/CD du client reste intact : deux portes, deux secrets distincts."""
    routes = _api_routes()
    assert "POST /v1/events/deployment" in routes


# --------------------------------------------------------------------------- #
# Le droit
# --------------------------------------------------------------------------- #
def test_la_lambda_api_peut_demarrer_lexecution_et_rien_dautre():
    """`states:StartExecution`, une seule fois, sur une ressource précise."""
    grants = [
        statement
        for statement in _statements(_api_template(), "AWS::IAM::Policy")
        if "states:StartExecution" in json.dumps(statement.get("Action"))
    ]
    assert len(grants) == 1, grants
    assert grants[0]["Action"] == "states:StartExecution"
    assert grants[0]["Resource"] != "*", (
        "un joker laisserait une route publique choisir quelle machine exécuter"
    )


def test_le_droit_porte_sur_la_machine_de_vie_dun_test():
    """L'ARN est celui de `RempartPentestLifecycle` : le retest passe les gardes-fous."""
    template = _api_template()
    grant = [
        statement
        for statement in _statements(template, "AWS::IAM::Policy")
        if "states:StartExecution" in json.dumps(statement.get("Action"))
    ][0]
    export = json.dumps(grant["Resource"])
    assert "PentestLifecycleMachine" in export, export


def test_lenvironnement_connait_larn_de_la_machine():
    """La route ne lit l'ARN nulle part ailleurs : pas dans le corps de requête."""
    variables = _lambda_environment(_api_template())
    arn = json.dumps(variables["REMPART_RETEST_MACHINE_ARN"])
    assert "PentestLifecycleMachine" in arn, arn


def _lambda_environment(template: dict[str, Any]) -> dict[str, Any]:
    """Variables d'environnement de la Lambda API.

    CDK ne pose pas de `FunctionName` (nom généré) : la jointure se fait donc sur
    l'identifiant logique, `RempartApiFunction…`.
    """
    for logical_id, body in template.get("Resources", {}).items():
        if body.get("Type") != "AWS::Lambda::Function":
            continue
        if not logical_id.startswith("RempartApiFunction"):
            continue
        return body["Properties"]["Environment"]["Variables"]
    raise AssertionError("la Lambda API est introuvable dans le gabarit")


# --------------------------------------------------------------------------- #
# Aucun secret en clair
# --------------------------------------------------------------------------- #
def test_le_secret_github_nest_jamais_ecrit_dans_le_template():
    """Non configuré = absent ; configuré = référence SSM. Jamais la valeur."""
    variables = _lambda_environment(_api_template())
    assert "REMPART_GITHUB_WEBHOOK_SECRET" not in variables


def test_le_secret_configured_vient_de_ssm_securestring(monkeypatch):
    """La valeur est résolue par CloudFormation au déploiement, hors du gabarit."""
    monkeypatch.setenv(
        "REMPART_GITHUB_WEBHOOK_SECRET_SSM_PARAM", "/rempart/github-webhook-secret"
    )
    # Synthèse fraîche : le cache de `_api_template` porte la configuration sans
    # paramètre, qui est justement ce que le test d'avant vérifie.
    variables = _lambda_environment(_template("RempartApiStack").to_json())
    value = variables["REMPART_GITHUB_WEBHOOK_SECRET"]
    assert value == "{{resolve:ssm-secure:/rempart/github-webhook-secret}}", value
    assert "github-webhook-secret" in value


# --------------------------------------------------------------------------- #
# Le routage du retest
# --------------------------------------------------------------------------- #
def test_la_machine_a_peut_fermer_une_faille_apres_un_retest():
    """`trigger == "retest"` mène à `CloseOrReopen`, sinon la boucle reste ouverte."""
    definition = _definition(_orchestrator_template(), MACHINE_LOGICAL_ID)
    routing = _choice(definition, "RetestRouting")
    first = routing["Choices"][0]
    assert first["Variable"] == "$.trigger"
    assert first["StringEquals"] == "retest"
    assert first["Next"] == "CloseOrReopen"
    assert routing["Default"] == "CollectFindings", (
        "un run ordinaire doit continuer à trier, pas fermer"
    )
    assert _choice(definition, "CloseOrReopen")["Type"] == "Task"


def test_le_routage_est_atteint_seulement_un_run_termine():
    """Le garde-fou de budget arrête un job : un job arrêté ne doit fermer RIEN."""
    definition = _definition(_orchestrator_template(), MACHINE_LOGICAL_ID)
    completed = _choice(definition, "IsRunCompleted")
    branch = [c for c in completed["Choices"] if c.get("StringEquals") == "completed"]
    assert branch and branch[0]["Next"] == "RetestRouting", completed
    assert completed["Default"] == "PentestNotCompleted"
    assert _choice(definition, "PentestNotCompleted")["Type"] == "Fail"


def test_la_machine_c_de_retest_existe_toujours():
    """Déclenchée à la main ou par le planificateur : la fermeture a deux chemins."""
    template = _orchestrator_template()
    names = {
        body["Properties"].get("StateMachineName")
        for body in template["Resources"].values()
        if body.get("Type") == "AWS::StepFunctions::StateMachine"
    }
    assert {"RempartPentestLifecycle", "RempartRetestClose", "RempartCicdIntake"} <= names


#: États du bloc de fermeture partagé (`_close_block`) : la tâche, le choix
#: d'issue et les trois issues possibles.
CLOSE_BLOCK = {
    "CloseOrReopen",
    "RetestOutcome",
    "ClosedWithProof",
    "RegressionReopened",
    "NoChange",
}
CLOSE_BLOCK_ORDERED = sorted(CLOSE_BLOCK)


def _close_block_of(template: dict[str, Any], logical_id: str) -> list[str]:
    """Les états de fermeture présents dans une machine, triés."""
    definition = _definition(template, logical_id)
    return sorted(set(definition["States"]) & CLOSE_BLOCK)


def test_le_bloc_de_fermeture_na_une_seule_implementation():
    """Machine A (branche retest) et machine C portent le même bloc, état par état.

    Deux implémentations de la fermeture, c'est deux endroits où se tromper la
    preuve de fermeture (EF-COR-04) et la réouverture en régression (EF-TRI-06).
    La porte CI/CD, elle, ne doit contenir aucun état de fermeture : elle découvre
    des failles, elle n'en corrige aucune.
    """
    template = _orchestrator_template()
    named = {}
    for logical_id, body in template["Resources"].items():
        if body.get("Type") != "AWS::StepFunctions::StateMachine":
            continue
        named[body["Properties"]["StateMachineName"]] = _close_block_of(
            template, logical_id
        )
    assert named["RempartRetestClose"] == CLOSE_BLOCK_ORDERED
    assert named["RempartPentestLifecycle"] == CLOSE_BLOCK_ORDERED, (
        "la branche retest de la machine A doit fermer exactement comme la machine C"
    )
    assert named["RempartCicdIntake"] == [], named
