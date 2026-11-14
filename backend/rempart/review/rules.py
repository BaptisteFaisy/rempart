"""Garde-fous déterministes de la revue de code.

Un modèle de langage peut inventer un fichier, une ligne et même un extrait de
code. Rien de ce qui sort de l'agent n'est donc cru : chaque commentaire doit
être ancré dans le diff **réel** qui a été soumis.

Règles (toutes vérifiables, donc testables) :

1. le fichier doit apparaître dans le diff ;
2. la ligne, si elle est donnée, doit être une ligne du côté « nouveau » d'un
   hunk de ce fichier ;
3. l'extrait cité (`evidence`) doit se retrouver mot pour mot dans le diff,
   blancs compressés — c'est ce qui interdit un commentaire « inventé » ;
4. les doublons (même fichier, même ligne, même catégorie) sont fusionnés ;
5. au plus `MAX_COMMENTS` commentaires, les plus sévères gardés ;
6. un commentaire Critical/High exige une validation humaine (mêmes sévérités
   que le garde-fou EF-TRI-05 du triage).

Sans ces règles, la revue de code serait une opinion décorée : le produit
annoncerait « 12 commentaires de sécurité » alors que 9 portent sur du code
absent du dépôt.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from rempart.common.models import SEVERITIES

from .comments import ReviewComment

#: Plafond : au-delà, un revue noie le développeur. Mesuré sur ce dépôt, une
#: revue d'un gros diff produit 8 à 15 commentaires utiles.
MAX_COMMENTS = 20

#: Sévérités qui exigent un humain (réutilise le sens de EF-TRI-05).
HIGH_SEVERITIES = ("Critical", "High")

_HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")
_NEW_FILE = re.compile(r"^\+\+\+ (?:b/)?(\S+)")


@dataclass
class DiffIndex:
    """Ce que le diff contient réellement : fichiers et lignes du côté neuf."""

    files: dict[str, set[int]] = field(default_factory=dict)
    #: Texte du diff, blancs compressés, marqueurs retirés — pour citer un extrait.
    normalized: str = ""

    def has_file(self, path: str) -> bool:
        return path in self.files

    def has_line(self, path: str, line: int) -> bool:
        return line in self.files.get(path, set())


def index_diff(diff: str) -> DiffIndex:
    """Parcourt le diff une fois : fichiers, plages de lignes, texte normalisé."""
    index = DiffIndex()
    current: str | None = None
    kept: list[str] = []
    for raw in diff.splitlines():
        kept.extend(_normalize_lines(raw))
        header = _NEW_FILE.match(raw)
        if header:
            current = header.group(1)
            index.files.setdefault(current, set())
            continue
        hunk = _HUNK.match(raw)
        if hunk and current is not None:
            _add_hunk_range(index.files[current], hunk)
    index.normalized = " ".join(kept)
    return index


def _add_hunk_range(lines: set[int], hunk: re.Match[str]) -> None:
    """Ajoute les lignes du côté « nouveau » d'un hunk (`,0` = suppression seule)."""
    start = int(hunk.group(1))
    count = int(hunk.group(2) or 1)
    lines.update(range(start, start + max(count, 1)))


def _normalize_lines(raw: str) -> list[str]:
    """Retire les marqueurs de diff et les blancs superflus, pour une citation fiable."""
    body = raw[1:] if raw[:1] in "+- " else raw
    parts = [p for p in body.split() if p]
    return parts


def quote(text: str) -> str:
    """Clé de comparaison d'une citation : les mots, sans marqueur ni blanc superflu.

    Partagée par les garde-fous et par la preuve (`scripts/proof_review.py`) :
    si la preuve normalisait autrement que la règle, elle validerait autre chose.
    """
    return " ".join(word for line in text.splitlines() for word in _normalize_lines(line))


@dataclass
class Enforcement:
    """Résultat des garde-fous : ce qui reste, et ce qui est écarté avec la raison."""

    comments: list[ReviewComment] = field(default_factory=list)
    dropped: list[dict[str, str]] = field(default_factory=list)
    needs_human: list[str] = field(default_factory=list)


def _reject_reason(comment: ReviewComment, index: DiffIndex) -> str | None:
    """Première règle violée, ou ``None`` si le commentaire est ancré dans le diff."""
    if not comment.file:
        return "aucun fichier indiqué"
    if not index.has_file(comment.file):
        return f"fichier absent du diff ({comment.file})"
    if comment.line is not None and not index.has_line(comment.file, comment.line):
        return f"ligne {comment.line} absente du diff pour {comment.file}"
    if not comment.title:
        return "aucun titre"
    if not comment.evidence:
        return "aucun extrait du diff cité"
    cited = quote(comment.evidence)
    if cited and cited not in index.normalized:
        return "extrait introuvable dans le diff (citation inventée)"
    return None


def enforce(comments: list[ReviewComment], diff: str, *, limit: int = MAX_COMMENTS) -> Enforcement:
    """Applique les règles, fusionne les doublons et tronque au plafond.

    L'ordre compte : les commentaires sont triés par sévérité décroissante avant
    troncature, pour que le plafond écarte le moins important et jamais un
    Critical.
    """
    index = index_diff(diff)
    out = Enforcement()
    seen: set[tuple[str, int | None, str]] = set()
    for comment in comments:
        reason = _reject_reason(comment, index)
        if reason:
            out.dropped.append({"location": comment.location(), "reason": reason})
            continue
        key = comment.dedupe_key()
        if key in seen:
            out.dropped.append({"location": comment.location(), "reason": "doublon"})
            continue
        seen.add(key)
        out.comments.append(comment)
    out.comments.sort(key=lambda c: (-_severity_rank(c.severity), c.location()))
    if len(out.comments) > limit:
        for extra in out.comments[limit:]:
            out.dropped.append(
                {"location": extra.location(), "reason": f"plafond de {limit} commentaires"}
            )
        out.comments = out.comments[:limit]
    out.needs_human = [c.location() for c in out.comments if c.severity in HIGH_SEVERITIES]
    return out


#: Rang par sévérité, dérivé de `SEVERITIES` (une seule table, celle du modèle
#: interne). Une sévérité inconnue est traitée comme la plus basse : elle ne peut
#: jamais passer devant un Critical quand le plafond de commentaires tranque.
_RANK = {name: index for index, name in enumerate(reversed(SEVERITIES))}


def _severity_rank(severity: str) -> int:
    return _RANK.get(severity, -1)


__all__ = ["Enforcement", "HIGH_SEVERITIES", "MAX_COMMENTS", "enforce", "index_diff", "quote"]
