"""Acquisition du diff à revoir, et son empreinte.

Le diff vient de GitHub (PR ou commit) ou est fourni directement. Dans les deux
cas il est borné : un modèle paye par jeton, et un diff de 3 Mo coûterait plus
cher qu'il n'éclaire. La troncature est **annoncée** dans le résultat — une
revue partielle présentée comme complète serait une fausse preuve.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from rempart.orchestrator.github_client import GitHubClient

#: Plafond de taille du diff envoyé au modèle (octets). Environ 50 000 jetons
#: pour un code moyen : largement assez pour une PR, et borné en coût.
MAX_DIFF_BYTES = 200_000

_SHA = re.compile(r"^[0-9a-f]{7,40}$")


@dataclass
class DiffSource:
    """D'où vient le diff, et s'il a dû être tronqué."""

    text: str
    origin: str
    truncated: bool = False

    @property
    def fingerprint(self) -> str:
        """Empreinte SHA-256 du diff : clé du cache et trace d'audit."""
        return hashlib.sha256(self.text.encode("utf-8")).hexdigest()

    @property
    def size_bytes(self) -> int:
        return len(self.text.encode("utf-8"))


def _truncate(diff: str, limit: int = MAX_DIFF_BYTES) -> tuple[str, bool]:
    """Coupe à la limite, sur une frontière de ligne, et le signale.

    Sans frontière de ligne dans la partie gardée (diff d'un seul tenant), le
    texte est coupé tel quel : rendre une chaîne vide ferait passer un diff
    volumineux pour un diff absent, ce qui est le contraire de l'intention.
    """
    encoded = diff.encode("utf-8")
    if len(encoded) <= limit:
        return diff, False
    text = encoded[:limit].decode("utf-8", errors="ignore")
    cut = text.rfind("\n")
    return (text[: cut + 1] if cut >= 0 else text), True


def from_text(text: str, *, origin: str = "diff fourni") -> DiffSource:
    """Diff fourni par l'appelant (banc, test, API sans accès au dépôt)."""
    body, truncated = _truncate(text)
    return DiffSource(text=body, origin=origin, truncated=truncated)


def from_pull(client: GitHubClient, owner: str, repo: str, number: int) -> DiffSource:
    """Diff exact d'une pull request, côté GitHub."""
    body, truncated = _truncate(client.fetch_diff(f"repos/{owner}/{repo}/pulls/{number}"))
    return DiffSource(text=body, origin=f"github:pull:{owner}/{repo}#{number}", truncated=truncated)


def from_commit(client: GitHubClient, owner: str, repo: str, sha: str) -> DiffSource:
    """Diff d'un commit (poussée récente, webhook CI/CD sans PR ouverte)."""
    if not _SHA.match(sha):
        raise ValueError(f"identifiant de commit invalide : {sha!r}")
    body, truncated = _truncate(client.fetch_diff(f"repos/{owner}/{repo}/commits/{sha}"))
    return DiffSource(text=body, origin=f"github:commit:{owner}/{repo}@{sha}", truncated=truncated)


def split_repository(value: str) -> tuple[str, str]:
    """Sépare `owner/repo` — le format des dépôts GitHub et de `Application.repositories`."""
    parts = [p for p in str(value or "").strip().split("/") if p]
    if len(parts) != 2:
        raise ValueError(f"dépôt attendu au format 'owner/repo', reçu {value!r}")
    return parts[0], parts[1]


__all__ = [
    "MAX_DIFF_BYTES",
    "DiffSource",
    "from_commit",
    "from_pull",
    "from_text",
    "split_repository",
]
