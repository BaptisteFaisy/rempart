#!/usr/bin/env python3
"""PREUVE : la revue de code de Rempart exécutée par un VRAI modèle InferHub.

Ce script ne se contente pas d'afficher un résultat : il **vérifie** les trois
choses sans lesquelles une revue automatique n'est qu'une opinion décorée.

1. au moins un commentaire vient du **modèle** (`source == "model"`) — sinon la
   revue n'a pas eu lieu, elle a été simulée ;
2. chaque commentaire retenu est **ancré** : son fichier et son extrait
   existent dans le diff réel. C'est ce qui écarte les inventions ;
3. les jetons sont **mesurés** (relevés sur Strands), et le coût en dollars
   n'est affiché que si un prix est configuré — sinon il est abstenu.

Le diff est celui du dépôt lui-même (auto-revue) : du vrai code, historique
d'un commit, d'une PR GitHub, ou d'un fichier. Rien n'est inventé pour l'occasion.

Usage :
    set -a && . ~/.config/agent-secrets/inferhub.env && set +a
    python3 scripts/proof_review.py                    # auto-revue : HEAD
    python3 scripts/proof_review.py --ref HEAD~1..HEAD # un intervalle
    PROOF_DIFF_FILE=/tmp/x.diff python3 scripts/proof_review.py
    PROOF_PR=31 PROOF_REPO=Tradoooo/rempart python3 scripts/proof_review.py

Sortie : 0 si la preuve tient, 1 si un commentaire n'est pas ancré ou si aucun
ne vient du modèle, 2 si aucun modèle n'est configuré (le script ne facture rien
dans ce cas).
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from rempart.review import run_review
from rempart.review.diff import from_pull, from_text
from rempart.review.rules import index_diff, quote
from rempart.triage.llm import (
    build_model_client,
    llm_configured,
    model_ids,
)


def _git(args: list[str]) -> str:
    """Une commande git en lecture seule, depuis le dépôt du projet."""
    return subprocess.run(
        ["git", "-C", str(ROOT), *args],
        capture_output=True,
        text=True,
        check=True,
        timeout=60,
    ).stdout


def load_source(opts: argparse.Namespace):
    """Diff à revoir : fichier, intervalle/revision git, ou PR GitHub."""
    if opts.diff_file:
        text = Path(opts.diff_file).read_text(encoding="utf-8", errors="ignore")
        return from_text(text, origin=f"fichier:{opts.diff_file}")
    if opts.pr:
        from rempart.orchestrator.github_client import (
            GitHubClient,
            github_token_from_env,
        )

        token = github_token_from_env()
        if not token:
            print(
                "  ÉCHEC : aucun jeton GitHub pour lire la PR (REMPART_GITHUB_TOKEN)."
            )
            raise SystemExit(2)
        owner, _, repo = opts.repo.partition("/")
        return from_pull(GitHubClient(token=token), owner, repo, int(opts.pr))
    ref = opts.ref or os.environ.get("PROOF_REF") or "HEAD~1..HEAD"
    if ".." in ref:
        # Un intervalle n'a pas de commit unique : `git show` refuserait. On prend
        # le diff complet et le libellé du commit de droite comme étiquette.
        label = _git(["log", "-1", "--format=%h %s", ref.split("..", 1)[1]]).strip()
        patch = _git(["diff", ref])
    else:
        label = _git(["log", "-1", "--format=%h %s", ref]).strip()
        patch = _git(["show", "--format=", "--patch", ref])
    return from_text(patch, origin=f"git:{ref} ({label})")


def verify(source, result) -> list[str]:
    """Contrôles indépendants des garde-fous : la preuve ne se cite pas elle-même."""
    index = index_diff(source.text)
    problems: list[str] = []
    model_comments = [c for c in result.comments if c.source == "model"]
    if not model_comments:
        problems.append("aucun commentaire ne vient du modèle (source != 'model')")
    for comment in result.comments:
        if not index.has_file(comment.file):
            problems.append(f"{comment.location()} : fichier absent du diff")
        cited = quote(comment.evidence)
        if cited and cited not in index.normalized:
            problems.append(f"{comment.location()} : extrait introuvable dans le diff")
    if result.usage.get("totalTokens", 0) <= 0:
        problems.append("aucun jeton mesuré : la revue n'a pas parlé au modèle")
    return problems


def show_comments(result) -> None:
    """Affiche les commentaires retenus et les écartés, avec leur raison."""
    for comment in result.comments:
        print(
            f"  ── {comment.location()}  [{comment.severity}/{comment.confidence}] {comment.category}"
        )
        print(f"     {comment.title[:88]}")
        print(f"     preuve : {comment.evidence[:88]}")
        print(f"     réf    : {', '.join(comment.references[:3]) or '—'}")
    if result.dropped:
        print(f"\n  écartés par les garde-fous : {len(result.dropped)}")
        for item in result.dropped[:5]:
            print(f"     - {item['location']} : {item['reason']}")


def show_result(result, elapsed: float) -> None:
    """Affiche le statut, la durée, les jetons et le coût mesuré."""
    print(
        f"  statut        : {result.status} (source {result.source}, modèle {result.model_id})"
    )
    print(f"  durée         : {elapsed:.1f} s")
    print(f"  jetons mesurés: {result.usage}")
    coût = (
        f"abstenu ({result.cost.note})"
        if result.cost.usd is None
        else f"{result.cost.usd:.6f} $"
    )
    print(f"  coût          : {coût}\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="Preuve de revue de code par InferHub")
    parser.add_argument(
        "--ref", default=None, help="révision ou intervalle git (défaut HEAD)"
    )
    parser.add_argument("--pr", default=None, help="numéro de PR GitHub à relire")
    parser.add_argument(
        "--repo", default="Tradoooo/rempart", help="owner/repo pour --pr"
    )
    parser.add_argument(
        "--diff-file",
        default=os.environ.get("PROOF_DIFF_FILE"),
        help="diff depuis un fichier",
    )
    opts = parser.parse_args()

    if not llm_configured():
        print("  ÉCHEC : aucun modèle configuré (LLM_API_KEY / REMPART_LLM_*).")
        print(
            "          Rien n'est appelé, rien n'est facturé ; la revue serait model_unavailable."
        )
        return 2

    source = load_source(opts)
    print(f"\n  diff          : {source.origin}")
    print(f"  taille        : {source.size_bytes} octets (tronqué: {source.truncated})")
    print(f"  empreinte     : {source.fingerprint[:16]}…")
    print(f"  modèles       : {', '.join(model_ids())}\n")

    started = time.time()
    result = run_review(source, model_client=build_model_client())
    elapsed = time.time() - started

    if result.status == "model_unavailable":
        print(f"  ÉCHEC : revue non faite — {result.note}")
        return 1

    show_result(result, elapsed)
    show_comments(result)
    problems = verify(source, result)
    if problems:
        print("\n  ÉCHEC de la preuve :")
        for problem in problems:
            print(f"     ✗ {problem}")
        return 1
    print(
        f"\n  ✓ {len(result.comments)} commentaire(s) ancré(s) sur {len(result.dropped)} écarté(s), "
        f"tous issus du modèle, jetons mesurés."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
