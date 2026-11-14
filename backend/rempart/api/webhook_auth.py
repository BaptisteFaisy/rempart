"""Primitives d'authentification des webhooks entrants (le seul point d'entrée sans jeton).

Deux schémas de signature coexistent, et la différence est réelle, pas de style :

- le pipeline CI/CD du client (`POST /v1/events/deployment`) signe le corps
  **canonicalisé** : l'expéditeur est notre propre script, on impose donc la
  forme du message (JSON à clés triées, séparateurs compacts, ASCII) ;
- GitHub (`POST /v1/events/github`) signe les **octets bruts** tels qu'ils
  partent : le destinataire doit hacher ce qu'il a reçu, pas une ré-écriture du
  JSON. `X-Hub-Signature-256` vaut `sha256=<hexadécimal>`.

Regrouper les deux ici fait qu'une seule implémentation de la comparaison
constante-temps existe dans le produit, et que les deux routes refusent de la
même manière : un refus neutre, identique quelle que soit la protection manquante
(clé absente, clé fausse, signature absente ou fausse). Révéler laquelle dirait à
un appelant non authentifié comment le serveur est configuré — constat fait le
2026-11-12 sur l'API eu-north-1, où aucune clé n'était posée et où le message le
disait à tout venant. La cause exacte reste écrite dans le journal d'audit,
lisible uniquement par les rôles habilités.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
from typing import Any

from rempart.api.helpers import Response, error_response

#: Préfixe de la signature GitHub : `X-Hub-Signature-256: sha256=<hex>`.
GITHUB_SIGNATURE_PREFIX = "sha256="
#: Longueur maximale d'un identifiant de dépôt (« owner/repo »).
MAX_REPOSITORY_LENGTH = 256


def header_get(headers: dict[str, Any] | None, name: str) -> str | None:
    """En-tête insensible à la casse : API Gateway v2 conserve la casse d'origine."""
    for key, value in (headers or {}).items():
        if str(key).lower() == name.lower():
            return str(value)
    return None


def canonical_body(body: dict[str, Any]) -> bytes:
    """Forme canonique signée : JSON trié, séparateurs compacts, ASCII.

    Le client et le serveur canonicalisent de la même façon, donc la signature
    ne dépend ni de l'ordre des clés ni des espaces du JSON transmis.
    """
    return json.dumps(
        body, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")


def signature_of(body: dict[str, Any], key: str) -> str:
    """HMAC-SHA256 hexadécimal du corps canonicalisé, avec la clé partagée."""
    return hmac.new(
        key.encode("utf-8"), canonical_body(body), hashlib.sha256
    ).hexdigest()


def raw_signature_of(raw: str | bytes, key: str) -> str:
    """HMAC-SHA256 des octets **bruts** du corps (schéma GitHub).

    `raw` est ce que la requête a réellement transporté : le re-sérialiser
    changerait la signature, même avec des clés triées.
    """
    payload = raw.encode("utf-8") if isinstance(raw, str) else bytes(raw)
    return hmac.new(key.encode("utf-8"), payload, hashlib.sha256).hexdigest()


def strip_scheme(provided: str | None) -> str:
    """Signature sans préfixe de schéma, normalisée (espaces, casse)."""
    if provided is None:
        return ""
    value = str(provided).strip().lower()
    return value[len(GITHUB_SIGNATURE_PREFIX):] if value.startswith(
        GITHUB_SIGNATURE_PREFIX
    ) else value


def signature_matches(provided: str | None, expected: str) -> bool:
    """Comparaison constante-temps, sûre hors ASCII.

    `hmac.compare_digest` exige de l'ASCII pour deux chaînes : on compare donc
    des octets. Un corps non décodable refuse au lieu de lever.
    """
    candidate = strip_scheme(provided)
    if not candidate:
        return False
    try:
        return hmac.compare_digest(
            candidate.encode("utf-8"), expected.encode("utf-8")
        )
    except (AttributeError, TypeError, UnicodeEncodeError):
        return False


def resolve_secret(settings: Any, attribute: str, env_var: str) -> str | None:
    """Secret partagé : d'abord l'attribut de configuration, puis l'environnement.

    En Lambda, l'IaC injecte la valeur depuis un paramètre SSM SecureString :
    elle n'apparaît jamais en clair dans le template CloudFormation.
    """
    if settings is not None:
        value = getattr(settings, attribute, None)
        if value:
            return str(value)
    return os.environ.get(env_var) or None


def deny(ctx: Any, action: str, object_id: str, message: str) -> Response:
    """Refus 403 neutre, tracé au journal d'audit avec sa cause exacte."""
    ctx.audit(action, "webhook", object_id, result="denied")
    return error_response(message, 403)


def repository_of(value: Any) -> str | None:
    """Identifiant de dépôt validé, ou None si absent/trop long/non conforme.

    « owner/repo » : deux segments, aucun caractère de contrôle. Le dépôt sert à
    la fois de clé de rate-limit et de jointure vers l'application cliente — une
    valeur librement longue permettrait de gonfler le journal d'audit.
    """
    if not isinstance(value, str):
        return None
    repo = value.strip()
    if not repo or len(repo) > MAX_REPOSITORY_LENGTH:
        return None
    if repo.count("/") != 1 or any(char in repo for char in "\r\n\t "):
        return None
    return repo
