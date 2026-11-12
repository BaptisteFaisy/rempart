#!/usr/bin/env python3
"""PREUVE : le triage de Rempart exécuté par un VRAI modèle, sur de vraies failles.

Rejoue le triage sur le jeu de démonstration figé (les vraies failles du
projet : IDOR, prototype pollution, fuite d'information…) avec le modèle
configuré, et affiche pour chaque proposition :

- l'**origine** du verdict : ``model`` (proposé par le LLM) ou ``deterministic``
  (règleur) — le champ ``source`` de la proposition ;
- ce que le modèle a proposé (statut, résumé, justification) ;
- ce que les garde-fous déterministes ont fini par imposer (matrice de
  priorité, EF-TRI-05 : un Critical ou un High n'est jamais tranché seul).

Le secret n'est jamais affiché : la clé vient de l'environnement
(``LLM_BASE_URL`` / ``LLM_API_KEY`` ou ``REMPART_LLM_*``).

Usage :
    set -a && . ~/.config/agent-secrets/inferhub.env && set +a
    python3 scripts/proof_llm.py            # toutes les failles du jeu
    PROOF_LIMIT=3 python3 scripts/proof_llm.py

Sans clé : le script dit que le triage tomberait sur le règleur, et sort en 2.
Aucun appel AWS n'est fait : ce script ne facture rien.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from rempart.common.models import Application, Finding
from rempart.triage.agent import run_triage
from rempart.triage.llm import build_model_client, llm_configured, model_ids

DATASET = ROOT / "demo" / "seed" / "demo-dataset.json"


def load() -> tuple[Application, list[Finding]]:
    """Le client et ses failles, lus dans le jeu figé."""
    data = json.loads(DATASET.read_text(encoding="utf-8"))
    application = Application.from_item(data["applications"][0])
    findings = [Finding.from_item(row) for row in data["findings"]]
    return application, findings


def main() -> int:
    print("=" * 78)
    print("PREUVE — triage par un vrai modèle (InferHub), sur les vraies failles")
    print(f"  endpoint configuré : {llm_configured()}")
    print(f"  modèles essayés    : {', '.join(model_ids())}")
    print("=" * 78)
    if not llm_configured():
        print("\n  Aucune clé : le triage retomberait sur le règleur déterministe.")
        print("  (c'est le comportement voulu quand aucun LLM n'est configuré)")
        return 2

    client = build_model_client()
    print(f"  client Strands : {type(client).__name__ if client else 'AUCUN'}")
    if client is None:
        return 2

    application, findings = load()
    limit = int(os.environ.get("PROOF_LIMIT", str(len(findings))))
    findings = findings[:limit]
    started = time.time()
    proposals = run_triage(
        findings=findings,
        app=application,
        known_findings=[],
        past_decisions=[],
        deps=None,
        model_client=client,
    )
    elapsed = time.time() - started
    print(f"\n  {len(proposals)} proposition(s) en {elapsed:.1f} s\n")
    for proposal, finding in zip(proposals, findings):
        print(f"  ── {finding.title[:74]}")
        print(f"     sévérité / risque : {finding.severity} / {finding.priority}")
        print(f"     origine           : {proposal.source}")
        print(f"     statut proposé    : {proposal.proposed_status}")
        print(f"     résumé            : {proposal.plain_summary[:160]}")
        print(f"     justification     : {proposal.justification[:220]}")
        print(f"     validation humaine: {proposal.needs_human_validation}")
    from_model = [p for p in proposals if p.source == "model"]
    if not from_model:
        print(
            "\n  ÉCHEC : une clé est configurée mais AUCUN verdict ne vient du modèle.\n"
            "          (soit le modèle était indisponible et le règleur a pris le relais,\n"
            "          soit le cache a renvoyé de vieux verdicts marqués autrement.)"
        )
        return 1
    print(f"\n  ✓ {len(from_model)}/{len(proposals)} verdict(s) directement issus du modèle.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())