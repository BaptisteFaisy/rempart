"""Route de revue de code : `POST /v1/applications/:id/reviews` (EF-ONB-04).

Ce qu'elle rend visible : la revue du changement livré, par l'agent InferHub
déjà branché au triage. Rempart n'appelle **pas** la fonction « code review »
de Continuum : elle coûte 200 $/M lignes protégées/mois plus 10 $/unité
d'inférence et n'est pas couverte par l'essai gratuit (`docs/free-tier-runbook.md`).

Trois façons de donner le diff, par ordre de préférence :

1. ``pull_request`` : le diff exact d'une PR, lu côté GitHub (le dépôt vient du
   corps ou du premier dépôt déclaré de l'application) ;
2. ``commit_sha`` : le diff d'un commit (poussée récente, pipeline CI/CD) ;
3. ``diff`` : le texte du diff, fourni par l'appelant (banc, test, CI locale).

Garde-fous appliqués **avant** tout appel au modèle : le coupe-circuit global,
un plafond d'appels par fenêtre (chaque revue coûte une inférence réelle), et
l'autorisation d'écrire sur le tenant. Si aucun modèle n'est branché, la route
répond **503** avec le statut ``model_unavailable`` : renvoyer 200 avec zéro
commentaire ferait croire à une revue propre.
"""

from __future__ import annotations

import os
from typing import Any

from rempart.api.context import ApiContext
from rempart.api.helpers import (
    Response,
    authorize,
    error_response,
    get_store,
    kill_switch_active,
    load_or_404,
    require_principal,
)
from rempart.api.router import Router
from rempart.common import ratelimit
from rempart.orchestrator.github_client import GitHubClient, github_token_from_env
from rempart.review import (
    STATUS_MODEL_UNAVAILABLE,
    DiffSource,
    from_commit,
    from_pull,
    from_text,
    run_review,
    split_repository,
)
from rempart.triage import llm

#: Plafond d'appels de revue par fenêtre et par application : une revue = une
#: inférence payante, un pipeline mal configuré ne doit pas pouvoir en ouvrir 500.
REVIEW_LIMIT = int(os.environ.get("REMPART_REVIEW_LIMIT", "5"))
REVIEW_WINDOW = float(os.environ.get("REMPART_REVIEW_WINDOW", "60"))

MAX_BODY_DIFF = 2_000_000


def _load_app(ctx: ApiContext) -> tuple[Any, Response | None]:
    return load_or_404(get_store(ctx).get_application, ctx.path_params.get("id", ""), "Application")


def _resolve_repository(ctx: ApiContext, app: Any) -> str | None:
    """Dépôt à revoir : celui demandé, sinon le premier déclaré par l'application."""
    wanted = str(ctx.body.get("repository") or "").strip()
    declared = [r for r in (getattr(app, "repositories", None) or []) if r]
    if wanted:
        return wanted
    return declared[0] if declared else None


def _diff_source(
    ctx: ApiContext, repository: str | None
) -> tuple[DiffSource | None, Response | None]:
    """Construit la source du diff depuis le corps de la requête.

    Ordre important : le sélecteur (`diff`, `pull_request`, `commit_sha`) est
    validé **avant** de réclamer un jeton GitHub. Sinon une requête mal formée
    répond 501 « jeton manquant », ce qui fait porter la faute au serveur.
    """
    raw_diff = ctx.body.get("diff")
    if isinstance(raw_diff, str) and raw_diff.strip():
        if len(raw_diff.encode("utf-8")) > MAX_BODY_DIFF:
            return None, error_response("`diff` trop volumineux", 413)
        return from_text(raw_diff, origin="diff fourni par l'appelant"), None

    if not repository:
        return None, error_response("aucun dépôt : précise `repository` ou fournis `diff`", 400)
    try:
        owner, repo = split_repository(repository)
    except ValueError as exc:
        return None, error_response(str(exc), 400)

    number = ctx.body.get("pull_request")
    sha = str(ctx.body.get("commit_sha") or "").strip()
    if number is None and not sha:
        return None, error_response("précise `pull_request`, `commit_sha` ou `diff`", 400)

    client, err = _github_client(ctx)
    if err or client is None:
        return None, err
    if number is not None:
        try:
            return from_pull(client, owner, repo, int(number)), None
        except (TypeError, ValueError) as exc:
            return None, error_response(f"`pull_request` invalide : {exc}", 400)
    try:
        return from_commit(client, owner, repo, sha), None
    except ValueError as exc:
        return None, error_response(str(exc), 400)


def _github_client(ctx: ApiContext) -> tuple[GitHubClient | None, Response | None]:
    token = github_token_from_env()
    if not token:
        return None, error_response(
            "aucun jeton GitHub configuré (REMPART_GITHUB_TOKEN) : "
            "impossible de lire le diff d'une PR ou d'un commit",
            501,
        )
    api = ctx.settings.github_api if ctx.settings else "https://api.github.com"
    return GitHubClient(token=token, api=api), None


def post_review(ctx: ApiContext) -> Response:
    """Relit un diff et rend les commentaires ancrés dans ce diff."""
    principal, err = require_principal(ctx)
    if err:
        return err
    app_id = ctx.path_params.get("id", "")
    app, err = _load_app(ctx)
    if err or app is None:
        return err  # type: ignore[return-value]
    err = authorize(principal, app.tenant_id, write=True)
    if err:
        return err
    if kill_switch_active(ctx):
        return error_response("coupe-circuit levé : aucune inférence de revue ne démarre", 503)
    if not ratelimit.allow(f"review:{app_id}", limit=REVIEW_LIMIT, window_s=REVIEW_WINDOW):
        return error_response(
            f"trop de revues pour cette application ({REVIEW_LIMIT}/{int(REVIEW_WINDOW)}s)", 429
        )

    repository = _resolve_repository(ctx, app)
    source, err = _diff_source(ctx, repository)
    if err or source is None:
        ctx.audit("review.refused", "application", app_id, result="refused")
        return err  # type: ignore[return-value]

    client = ctx.model_client if ctx.model_client is not None else llm.build_model_client()
    result = run_review(source, model_client=client)
    status = 503 if result.status == STATUS_MODEL_UNAVAILABLE else 200
    ctx.audit(
        "review.created", "application", app_id, result="ok" if status == 200 else "unavailable"
    )
    payload = result.to_dict()
    payload["application_id"] = app_id
    payload["repository"] = repository
    return status, payload


def register(router: Router) -> None:
    """Une seule route : la revue est déclenchée, pas stockée (aucune nouvelle table)."""
    router.add("POST", "/v1/applications/:id/reviews", post_review)


__all__ = ["post_review", "register"]
