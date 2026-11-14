"""`POST /v1/events/github` : la pull request de correction mergée ferme la boucle.

Jus'ici, rien ne démarrait la machine `RempartRetestClose` : une faille confirmée
recevait sa PR (`request_remediation`), la PR était mergée par le client, et Rempart
ne s'en apercevait jamais. La boucle « test d'intrusion **en continu** » restait
ouverte — la faille demeurait `in_remediation` jusqu'à ce qu'un humain y pense.

Cette route est le second point d'entrée sans jeton du produit, donc elle applique
les mêmes protections que le webhook CI/CD, dans le même ordre : secret partagé,
signature HMAC, puis limite de débit. Seule la signature change de forme : GitHub
hache les octets bruts du corps (`X-Hub-Signature-256`), pas un JSON ré-écrit —
c'est `webhook_auth.raw_signature_of`, et le corps brut est porté par le contexte.

Ce qu'un refus ne dit pas : quelle protection a manqué. Ce qu'il dit à l'audit :
la cause exacte.
"""

from __future__ import annotations

from typing import Any

from rempart.api import webhook_auth as wh
from rempart.api.context import ApiContext
from rempart.api.helpers import (
    Response,
    application_for_repository,
    error_response,
    get_store,
)
from rempart.api.router import Router
from rempart.common import ratelimit
from rempart.common.models import Finding
from rempart.orchestrator.retest import request_retest

SECRET_ATTR = "github_webhook_secret"
SECRET_ENV = "REMPART_GITHUB_WEBHOOK_SECRET"
SIGNATURE_HEADER = "X-Hub-Signature-256"
EVENT_HEADER = "X-GitHub-Event"
#: Seul événement traité : une PR qui se ferme (mergée ou non — voir `not_merged`).
SUPPORTED_EVENT = "pull_request"
MERGED_ACTION = "closed"
#: Message de refus unique : on ne distingue pas « secret absent », « signature
#: absente » et « signature fausse » pour un appelant non authentifié.
DENIED_MESSAGE = "Événement GitHub non authentifié"
#: Statuts pour lesquels une fusion a un sens. Une faille déjà fermée, ou écartée
#: comme faux positif, ne se rouvre pas toute seule sur un événement externe :
#: ce serait laisser un dépôt tiers décider de notre journal.
RETESTABLE_STATUSES = (
    "in_remediation",
    "confirmed",
    "pending_validation",
    "reopened",
    "to_retest",
)


def _check_auth(ctx: ApiContext) -> Response | None:
    """Secret partagé puis HMAC sur les octets bruts ; None si l'appel est autorisé."""
    secret = wh.resolve_secret(ctx.settings, SECRET_ATTR, SECRET_ENV)
    if not secret:
        return wh.deny(ctx, "github_event.rejected", "unconfigured", DENIED_MESSAGE)
    expected = wh.raw_signature_of(ctx.raw_body or "", secret)
    if not wh.signature_matches(wh.header_get(ctx.headers, SIGNATURE_HEADER), expected):
        return wh.deny(ctx, "github_event.rejected", "bad_signature", DENIED_MESSAGE)
    return None


def _event_of(ctx: ApiContext) -> tuple[dict[str, Any] | None, Response | None]:
    """Enveloppe GitHub validée strictement : (événement normalisé, None) ou (None, 400).

    Validation avant toute écriture : un corps trompeur ne doit atteindre ni le
    rate-limit (clé injectable) ni le magasin.
    """
    body = ctx.body
    if not isinstance(body, dict) or not body:
        return None, error_response("Corps JSON attendu : un objet non vide", 400)
    action = body.get("action")
    if not isinstance(action, str) or not action.strip():
        return None, error_response("`action` doit être une chaîne non vide", 400)
    envelope = body.get("repository")
    full_name = envelope.get("full_name") if isinstance(envelope, dict) else None
    repository = wh.repository_of(full_name)
    if repository is None:
        return None, error_response("`repository.full_name` est requis (owner/repo)", 400)
    pr = body.get("pull_request")
    if not isinstance(pr, dict):
        return None, error_response("`pull_request` doit être un objet", 400)
    url = pr.get("html_url")
    if not isinstance(url, str) or not url.strip():
        return None, error_response("`pull_request.html_url` est requis", 400)
    return {
        "action": action.strip().lower(),
        "repository": repository,
        "pr": pr,
        "url": url.strip(),
        "number": body.get("number") or pr.get("number") or 0,
    }, None


def _finding_for_pull_request(store: Any, app_id: str, url: str) -> Finding | None:
    """La faille dont c'est LA PR de correction, bornée à l'application du dépôt.

    La borne d'application EST le contrôle d'isolation (ENF-SEC-01) : sans elle,
    une PR d'un autre locataire dont l'URL ressemblerait à la nôtre muterait une
    faille d'autrui.
    """
    for finding in store.list_findings(app_id=app_id):
        if finding.remediation_pr_url == url:
            return finding
    return None


def _ignored(ctx: ApiContext, reason: str, object_id: str) -> Response:
    """202 + raison : GitHub ne doit PAS rejouer une livraison juste ignorée."""
    ctx.audit("github_event.ignored", "pull_request", object_id, result="ignored")
    return 202, {"received": True, "ignored": reason}


def _unsupported(ctx: ApiContext) -> Response | None:
    """Acquitte une livraison d'un autre type : GitHub ne doit PAS la rejouer.

    Un 4xx sur un événement `push`, `issues` ou `deployment` ferait échouer le
    hook côté GitHub, qui le désactive après assez d'échecs — et la boucle de
    retest ne se fermerait plus jamais, pour une raison invisible.
    """
    delivered = (wh.header_get(ctx.headers, EVENT_HEADER) or "").strip().lower()
    if delivered == SUPPORTED_EVENT:
        return None
    return _ignored(ctx, f"unsupported_event:{delivered or 'none'}", delivered or "none")


def post_github_event(ctx: ApiContext) -> Response:
    """Traite une livraison GitHub : PR mergée → faille `to_retest` → retest."""
    denied = _check_auth(ctx)
    if denied:
        return denied
    unsupported = _unsupported(ctx)
    if unsupported:
        return unsupported
    event, invalid = _event_of(ctx)
    if invalid:
        return invalid
    assert event is not None  # Narrowed by `invalid`; keeps mypy honest.

    if not ratelimit.allow(f"gh:{event['repository']}"):
        ctx.audit(
            "github_event.rate_limited", "repository", event["repository"], result="denied"
        )
        return error_response("Trop d'événements pour ce dépôt, réessayez plus tard", 429)

    if event["action"] != MERGED_ACTION or not event["pr"].get("merged"):
        return _ignored(ctx, "not_merged", event["url"])

    store = get_store(ctx)
    app = application_for_repository(store, event["repository"])
    if app is None:
        return _ignored(ctx, "unknown_repository", event["repository"])

    finding = _finding_for_pull_request(store, app.app_id, event["url"])
    if finding is None:
        return _ignored(ctx, "no_matching_finding", event["url"])
    if finding.status not in RETESTABLE_STATUSES:
        return _ignored(ctx, f"status_{finding.status}", finding.finding_id)

    result = request_retest(store, ctx.retest, finding, app, event["pr"], event["number"])
    ctx.audit(
        "retest.requested",
        "finding",
        result["finding_id"],
        result="ok" if result["started"] else "ignored",
    )
    return 202, {"received": True, **result}


def register(router: Router) -> None:
    router.add("POST", "/v1/events/github", post_github_event)
