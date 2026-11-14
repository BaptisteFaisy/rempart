"""Commentaire de revue de code : format, sérialisation, normalisation.

Pourquoi un type dédié, et pas `Finding` : une faille issue d'un test
d'intrusion Continuum a un `run_id`, une empreinte et un cycle de vie (triage →
ticket → re-test). Un commentaire de revue naît d'un diff, n'a pas d'empreinte
sttable et ne se « re-teste » pas. Mélanger les deux ferait apparaître des
commentaires de revue dans les compteurs de failles et dans le dossier de
preuves — ce qui fausserait les chiffres montrés à un juge.

La normalisation est la même que celle du triage (`common.normalize`) : un
modèle écrit `blocking: "false"` (chaîne), imbrique ses listes, et propose des
sévérités en majuscules. Rien de ce qu'il écrit n'est cru tel quel.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from rempart.common.api_enums import normalize_confidence, normalize_severity
from rempart.common.normalize import as_bool, as_flat_strings

#: Catégories fermées : un modèle qui invente une catégorie retombe sur `other`,
#: ce qui garde les compteurs exploitables (page « industrialisation », corpus).
CATEGORIES = (
    "injection",
    "authz",
    "secrets",
    "crypto",
    "input_validation",
    "dependency",
    "logic",
    "other",
)

DEFAULT_CATEGORY = "other"


def normalize_category(raw: object) -> str:
    """Catégorie parmi `CATEGORIES` — jamais une catégorie inventée."""
    if not isinstance(raw, str):
        return DEFAULT_CATEGORY
    text = raw.strip().lower().replace(" ", "_").replace("-", "_")
    return text if text in CATEGORIES else DEFAULT_CATEGORY


@dataclass
class ReviewComment:
    """Un commentaire de revue, ancré sur un fichier et une ligne du diff."""

    file: str
    line: int | None
    category: str
    severity: str
    confidence: str
    title: str
    recommendation: str
    evidence: str = ""
    references: list[str] = field(default_factory=list)
    blocking: bool = False
    # "model" (proposé par l'agent InferHub) ou "deterministic". Sans ce champ,
    # on ne peut pas prouver qu'un vrai modèle a participé à la revue.
    source: str = "model"

    def to_dict(self) -> dict[str, Any]:
        """Dictionnaire sérialisable (clés snake_case, comme le reste de l'API)."""
        return {
            "file": self.file,
            "line": self.line,
            "category": self.category,
            "severity": self.severity,
            "confidence": self.confidence,
            "title": self.title,
            "recommendation": self.recommendation,
            "evidence": self.evidence,
            "references": list(self.references),
            "blocking": self.blocking,
            "source": self.source,
        }

    def location(self) -> str:
        """Emplacement lisible : `chemin:ligne`, ou le chemin seul."""
        return f"{self.file}:{self.line}" if self.line is not None else self.file

    def dedupe_key(self) -> tuple[str, int | None, str]:
        """Clé de doublon : même fichier, même ligne, même catégorie."""
        return (self.file, self.line, self.category)

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "ReviewComment":
        """Commentaire normalisé depuis ce que le modèle a écrit.

        Les sévérités passent par `normalize_severity` (idem intake Continuum) :
        `HIGH`, `high` et `High` donnent la même valeur interne, et une valeur
        inconnue retombe sur le défaut — jamais sur une surévaluation.
        """
        return cls(
            file=str(raw.get("file") or raw.get("path") or "").strip(),
            line=as_line(raw.get("line")),
            category=normalize_category(raw.get("category")),
            severity=normalize_severity(raw.get("severity")),
            confidence=normalize_confidence(raw.get("confidence")),
            title=str(raw.get("title") or "").strip(),
            recommendation=str(raw.get("recommendation") or raw.get("suggestion") or "").strip(),
            evidence=str(raw.get("evidence") or raw.get("snippet") or "").strip(),
            references=as_flat_strings(raw.get("references")),
            blocking=as_bool(raw.get("blocking")),
            # Un dictionnaire ne peut venir que de l'outil de soumission du modèle.
            source=str(raw.get("source") or "model"),
        )


def as_line(value: Any) -> int | None:
    """Une ligne : un entier positif, sinon ``None`` (commentaire sur le fichier)."""
    if isinstance(value, bool) or value is None:
        return None
    try:
        line = int(str(value).strip())
    except (TypeError, ValueError):
        return None
    return line if line > 0 else None


__all__ = ["CATEGORIES", "DEFAULT_CATEGORY", "ReviewComment", "as_line", "normalize_category"]
