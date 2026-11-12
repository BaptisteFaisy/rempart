"""IaC : le modèle de triage est câblé sur les Lambdas de l'orchestrateur.

Le triage se joue dans l'orchestrateur, pas dans l'API. Sans ces variables,
les Lambdas n'auraient aucun endpoint LLM et retomberaient sur le règleur —
c'est-à-dire que le « vrai modèle » ne serait jamais utilisé en production.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from aws_cdk import assertions

IAC_DIR = Path(__file__).resolve().parents[3] / "iac" / "control-plane"
if str(IAC_DIR) not in sys.path:
    sys.path.insert(0, str(IAC_DIR))

from app import build_app  # noqa: E402


def _orchestrator_env() -> list[dict[str, str]]:
    app = build_app()
    app.synth()
    template = assertions.Template.from_stack(app.node.find_child("RempartOrchestratorStack"))
    functions = template.find_resources("AWS::Lambda::Function")
    return [
        props["Properties"]["Environment"]["Variables"]
        for props in functions.values()
    ]


def test_les_lambdas_du_triage_portent_l_endpoint_du_modele():
    for env in _orchestrator_env():
        assert env.get("REMPART_LLM_BASE_URL", "").startswith("https://")


def test_la_cle_du_modele_vient_de_ssm_et_jamais_en_clair(monkeypatch):
    monkeypatch.setenv("REMPART_LLM_API_KEY_SSM_PARAM", "/rempart/dev/llm-key")
    app = build_app()
    app.synth()
    template = assertions.Template.from_stack(app.node.find_child("RempartOrchestratorStack"))
    functions = template.find_resources("AWS::Lambda::Function")
    env = next(iter(functions.values()))["Properties"]["Environment"]["Variables"]
    assert "REMPART_LLM_API_KEY" in env
    rendered = json.dumps(env["REMPART_LLM_API_KEY"])
    assert "resolve:ssm-secure:/rempart/dev/llm-key" in rendered
    # La valeur ne doit jamais apparaître : seulement la référence dynamique.
    assert "sk-" not in rendered.lower()


def test_sans_parametre_ssm_la_cle_est_absente_et_le_repli_reste_possible(monkeypatch):
    monkeypatch.delenv("REMPART_LLM_API_KEY_SSM_PARAM", raising=False)
    for env in _orchestrator_env():
        assert "REMPART_LLM_API_KEY" not in env
