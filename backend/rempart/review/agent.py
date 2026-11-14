"""Agent de revue de code : un vrai modèle InferHub relit le diff, des règles le bornent.

Ce que ce module ajoute au produit (EF-ONB-04, « activer la revue de code ») :
la revue du changement livré, sans appeler la fonction payante de Continuum
(200 $/M lignes protégées/mois + 10 $/unité d'inférence, hors essai gratuit —
voir `docs/free-tier-runbook.md`). Elle utilise le même agent InferHub que le
triage, déjà branché et prouvé en production.

Honnêteté sur le résultat — c'est le point sensible d'une revue automatique :

- sans modèle disponible, le statut est ``model_unavailable`` et la liste est
  **vide** : la revue ne dit jamais « aucun problème trouvé », parce qu'elle ne
  l'a pas cherché. Le triage, lui, a un repli déterministe ; la revue de code
  n'en a aucun — un règleur ne peut pas lire un diff.
- chaque commentaire passe par `rules.enforce` : fichier, ligne et extrait
  doivent exister dans le diff réel, sinon le commentaire est écarté et la
  raison est rendue à l'appelant.

Le client du modèle est réutilisé tel quel (`triage.llm.build_model_client`) :
même endpoint, même clé lue depuis SSM, même chaîne de repli entre fournisseurs.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from rempart.triage import llm, verdict_cache

from .comments import ReviewComment
from .cost import Cost, estimate_cost
from .diff import DiffSource
from .prompts import format_diff_for_prompt, review_instruction, system_prompt
from .rules import MAX_COMMENTS, Enforcement, enforce

LOGGER = logging.getLogger("rempart.review.agent")

#: Statuts possibles d'une revue.
STATUS_REVIEWED = "reviewed"
STATUS_PARTIAL = "partial"
STATUS_MODEL_UNAVAILABLE = "model_unavailable"


@dataclass
class ReviewContext:
    """Ce que les outils de l'agent peuvent lire et écrire pendant la revue."""

    diff: DiffSource
    comments: list[ReviewComment] = field(default_factory=list)
    #: Tokens réellement consommés, relevés sur le manager de conversation de
    #: Strands. Mesurés, pas estimés : c'est ce qui permet de dire combien coûte
    #: une revue.
    usage: dict[str, int] = field(default_factory=dict)


@dataclass
class ReviewResult:
    """Résultat d'une revue : commentaires retenus, écartés, et d'où ça vient."""

    status: str
    source: str
    origin: str
    fingerprint: str
    truncated: bool
    comments: list[ReviewComment] = field(default_factory=list)
    dropped: list[dict[str, str]] = field(default_factory=list)
    needs_human: list[str] = field(default_factory=list)
    model_id: str | None = None
    note: str = ""
    #: Tokens mesurés par Strands, et coût chiffré seulement si un prix l'est.
    usage: dict[str, int] = field(default_factory=dict)
    cost: Cost = field(default_factory=lambda: estimate_cost({}))

    def to_dict(self) -> dict[str, Any]:
        """Payload de la réponse API, sérialisable tel quel."""
        return {
            "status": self.status,
            "source": self.source,
            "origin": self.origin,
            "diff_fingerprint": self.fingerprint,
            "diff_truncated": self.truncated,
            "model": self.model_id,
            "note": self.note,
            "comments": [c.to_dict() for c in self.comments],
            "dropped": list(self.dropped),
            "needs_human": list(self.needs_human),
            "usage": dict(self.usage),
            "cost": self.cost.to_dict(),
            "counts": {
                "comments": len(self.comments),
                "dropped": len(self.dropped),
                "blocking": sum(1 for c in self.comments if c.blocking),
                "needs_human": len(self.needs_human),
            },
        }


@dataclass
class RawReview:
    """Ce qu'une revue consomme : le filtrage des règles, l'usage, le modèle.

    C'est l'unité mise en cache : garder seulement les commentaires ferait perdre
    le coût mesuré au rejeu.
    """

    enforced: Enforcement
    usage: dict[str, int] = field(default_factory=dict)
    model_id: str | None = None


def _unavailable(diff: DiffSource, reason: str) -> ReviewResult:
    """Revue non faite : vide, et dit pourquoi — jamais « propre »."""
    return ReviewResult(
        status=STATUS_MODEL_UNAVAILABLE,
        source="none",
        origin=diff.origin,
        fingerprint=diff.fingerprint,
        truncated=diff.truncated,
        note=reason,
    )


def _build_tools(ctx: ReviewContext) -> list[Any]:
    """Outils de l'agent : soumettre un commentaire, relire le diff.

    Nommage `tool_*`, comme dans le triage (`triage/agent.py`) : les deux agents
    exposent le même préfixe à Strands, donc le même comportement côté garde-fous.
    """
    from strands import tool

    @tool
    def tool_submit_review_comment(comment: dict[str, Any]) -> dict[str, Any]:
        """Submit one anchored review comment.

        Champs attendus : file, line, category, severity, confidence, title,
        recommendation, evidence (extrait du diff, mot pour mot), references,
        blocking.
        """
        parsed = ReviewComment.from_dict(comment)
        ctx.comments.append(parsed)
        return {"accepted": True, "location": parsed.location()}

    @tool
    def tool_get_diff() -> str:
        """Return the exact diff under review, to quote evidence verbatim."""
        return ctx.diff.text

    return [tool_submit_review_comment, tool_get_diff]


def _run_strands_agent(ctx: ReviewContext, model_client: Any) -> None:
    from strands import Agent

    # `callback_handler=None` : Strands imprime par défaut le texte ET le
    # raisonnement du modèle sur stdout. Dans une Lambda, cela verse la chaîne
    # de pensée du modèle dans CloudWatch — du bruit, un coût, et une fuite.
    agent = Agent(
        model=model_client,
        tools=_build_tools(ctx),
        system_prompt=system_prompt(),
        callback_handler=None,
    )
    prompt = review_instruction(ctx.diff.origin, ctx.diff.size_bytes, ctx.diff.truncated)
    agent(f"{prompt}{format_diff_for_prompt(ctx.diff.text)}")
    # L'usage est relevé sur Strands, pas estimé : ce que le modèle a réellement
    # consommé pour cette revue, et rien d'autre.
    ctx.usage = accumulated_usage(agent)


def accumulated_usage(agent: Any) -> dict[str, int]:
    """Tokens cumulés d'une invocation, tels que Strands les a comptabilisés.

    ``{}`` quand l'agent n'expose pas de métriques : un coût inconnu est rendu
    comme absent, jamais comme zéro (zéro voudrait dire « gratuit », ce qui
    serait faux).

    `accumulated_usage` est un `TypedDict` chez Strands : on le lit donc comme
    un dictionnaire, et non par attributs — un ``getattr`` sur un dict renvoie
    systématiquement ``None``, ce qui faisait disparaître silencieusement les
    tokens mesurés.
    """
    metrics = getattr(agent, "event_loop_metrics", None)
    usage = getattr(metrics, "accumulated_usage", None)
    if not isinstance(usage, dict):
        return {}
    return {
        key: value
        for key in (
            "inputTokens",
            "outputTokens",
            "totalTokens",
            "cacheReadInputTokens",
            "cacheWriteInputTokens",
        )
        if isinstance((value := usage.get(key)), int)
    }


def _cache_key(diff: DiffSource) -> list[str]:
    return [diff.fingerprint]


def run_review(
    diff: DiffSource,
    *,
    model_client: Any = None,
    limit: int = MAX_COMMENTS,
) -> ReviewResult:
    """Relit un diff avec l'agent InferHub, puis applique les garde-fous.

    ``model_client`` permet d'injecter un modèle (tests, banc). Sans lui, le
    client est construit depuis l'environnement — le même chemin que le triage,
    donc la même clé SSM et le même routeur de fournisseurs.
    """
    if not diff.text.strip():
        return _unavailable(diff, "diff vide : rien à revoir")
    if not llm.strands_available() or not llm.is_real_model(model_client):
        return _unavailable(
            diff,
            "aucun modèle réel disponible : la revue n'a pas été faite "
            "(repli déterministe impossible pour du code)",
        )

    cached = verdict_cache.get_batch(_cache_key(diff))
    if cached is not None:
        LOGGER.info("revue : diff déjà revu dans ce processus, cache réutilisé")
        return _from_raw(diff, cached[0], cached=True)

    ctx = ReviewContext(diff=diff)
    try:
        _run_strands_agent(ctx, model_client)
    except Exception as exc:  # noqa: BLE001 — un fournisseur saturé ne produit pas de fausse revue
        LOGGER.warning("revue : modèle indisponible (%s: %s)", type(exc).__name__, exc)
        return _unavailable(diff, f"modèle indisponible ({type(exc).__name__})")

    outcome = enforce(ctx.comments, diff.text, limit=limit)
    raw = RawReview(
        enforced=outcome,
        usage=dict(ctx.usage),
        model_id=llm.model_label(model_client),
    )
    verdict_cache.put_batch(_cache_key(diff), [raw])
    return _from_raw(diff, raw)


def _from_raw(diff: DiffSource, raw: RawReview, *, cached: bool = False) -> ReviewResult:
    """Résultat construit depuis la revue brute, en cache ou non.

    L'usage et le coût sont conservés dans les deux cas : un rejeu qui réutilise
    le verdict doit pouvoir dire « cette revue a consommé tant de jetons », pas
    faire croire qu'elle est gratuite parce qu'aucun appel n'a eu lieu.
    """
    result = _result(diff, raw.enforced, raw.model_id)
    result.usage = dict(raw.usage)
    result.cost = estimate_cost(raw.usage)
    if cached:
        result.note = "cache : ce diff a déjà été revu dans ce processus"
        result.source = "cache"
    return result


def _result(diff: DiffSource, enforced: Enforcement, model_id: str | None) -> ReviewResult:
    status = STATUS_PARTIAL if diff.truncated else STATUS_REVIEWED
    note = (
        "diff tronqué : revue partielle, seulement la partie visible a été lue"
        if diff.truncated
        else ""
    )
    return ReviewResult(
        status=status,
        source="model",
        origin=diff.origin,
        fingerprint=diff.fingerprint,
        truncated=diff.truncated,
        comments=enforced.comments,
        dropped=enforced.dropped,
        needs_human=enforced.needs_human,
        model_id=model_id,
        note=note,
    )


__all__ = [
    "ReviewContext",
    "ReviewResult",
    "STATUS_MODEL_UNAVAILABLE",
    "STATUS_PARTIAL",
    "STATUS_REVIEWED",
    "run_review",
]
