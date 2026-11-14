"""Garde : le script de déploiement câble TOUJOURS le vrai modèle de triage.

INCIDENT (14/11/2026) : `REMPART_LLM_API_KEY_SSM_PARAM` n'était transmise que si
l'opérateur y pensait. Oubliée, le déploiement réussit sans la moindre erreur :
la Lambda de triage tourne, mais retombe **silencieusement** sur le règleur
déterministe — la production n'a plus d'agent LLM, et rien ne le signale. C'est
exactement la classe de défaut que les tests de template ne peuvent pas voir :
le template est correct *conditionnellement à un environnement*.

Ce test verrouille les deux moitiés du correctif dans le script lui-même :
un défaut explicite, et une preuve lisible côté AWS après déploiement.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
DEPLOY_SCRIPT = REPO_ROOT / "scripts" / "deploy_api.sh"
PARAM_ENV = "REMPART_LLM_API_KEY_SSM_PARAM"


def _script() -> str:
    return DEPLOY_SCRIPT.read_text(encoding="utf-8")


def test_le_script_exporte_le_parametre_avec_une_valeur_par_defaut():
    """Sans la variable du shell, le script doit quand même câbler la clé."""
    source = _script()
    # Forme réelle : `X="${REMPART_LLM_API_KEY_SSM_PARAM:-défaut}"` puis export.
    # Le défaut est ce qui couvre l'oubli de la variable d'environnement.
    assert re.search(rf"\{{{PARAM_ENV}:-[^}}\s]+\}}", source), (
        f"{PARAM_ENV} doit avoir une valeur par défaut dans le script "
        "(sinon un déploiement sans la variable perd le modèle en silence)"
    )
    assert re.search(rf"export {PARAM_ENV}=", source), f"{PARAM_ENV} doit être exportée"


def test_le_script_verifie_lexistence_du_parametre_avant_le_changeset():
    """Un paramètre absent se voit avant le déploiement, pas après."""
    source = _script()
    assert "prove_llm_param_exists" in source, (
        "le script doit vérifier que le paramètre SSM de la clé existe avant `cdk deploy`"
    )
    assert source.index("prove_llm_param_exists") < source.index("cdk deploy"), (
        "la vérification doit précéder le déploiement"
    )


def test_le_script_prouve_le_cablage_du_modele_apres_deploiement():
    """La preuve doit porter sur les DEUX moitiés : variable d'env et droits IAM."""
    source = _script()
    assert "prove_llm_wiring" in source, (
        "le script doit prouver après déploiement que le triage peut lire la clé"
    )
    proof = source[source.index("prove_llm_wiring") :]
    assert "REMPART_LLM_API_KEY_SSM_PARAM" in proof, "la preuve vérifie la variable d'environnement"
    assert "ssm:GetParameter" in proof, "la preuve vérifie le droit de lire le SecureString"
    assert "kms:Decrypt" in proof, "la preuve vérifie le déchiffrement de la SecureString"
    assert "PREUVE ÉCHEC" in proof, "un câblage absent doit être annoncé comme un échec"
