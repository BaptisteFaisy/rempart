"""Data class and serialization for triage proposals (annexe B)."""

from dataclasses import dataclass
from typing import Any


@dataclass
class TriageProposal:
    """Triage proposal format conforming to specification chapter 12 and annexe B."""

    finding_id: str
    duplicate_of: str | None
    is_regression: bool
    proposed_status: str  # "CONFIRMED" | "TO_VERIFY" | "LIKELY_FALSE_POSITIVE"
    priority: str  # "P1" | "P2" | "P3" | "P4"
    plain_summary: str
    technical_summary: str
    references: list[str]
    justification: str
    needs_human_validation: bool
    # Origine du verdict : "model" (proposé par le LLM), "deterministic"
    # (règleur) ou "memory" (reprise d'un verdict antérieur). Sans cela, on ne
    # sait pas si une décision vient d'un modèle ou d'un règleur.
    source: str = "deterministic"

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-serializable dictionary with camelCase keys matching annexe B."""
        return {
            "findingId": self.finding_id,
            "duplicateOf": self.duplicate_of,
            "isRegression": self.is_regression,
            "proposedStatus": self.proposed_status,
            "priority": self.priority,
            "plainSummary": self.plain_summary,
            "technicalSummary": self.technical_summary,
            "references": list(self.references),
            "justification": self.justification,
            "needsHumanValidation": self.needs_human_validation,
            "source": self.source,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "TriageProposal":
        """Build a TriageProposal from either camelCase or snake_case dictionary.

        Un modèle écrit les booléens en **chaîne** (« false ») et peut imbriquer
        les listes de références : mesuré le 13/11/2026 en production, la
        décision stockée portait `isRegression: true` alors que le modèle
        affirmait `false`, et `references: ["item"]` au lieu des références
        citées. Les valeurs sont donc normalisées ici, pas crues.
        """
        return cls(
            finding_id=d.get("findingId") or d.get("finding_id") or "",
            duplicate_of=_as_optional_id(
                d.get("duplicateOf") if "duplicateOf" in d else d.get("duplicate_of")
            ),
            is_regression=_as_bool(
                d.get("isRegression") if "isRegression" in d else d.get("is_regression", False)
            ),
            proposed_status=d.get("proposedStatus") or d.get("proposed_status") or "CONFIRMED",
            priority=d.get("priority") or "P4",
            plain_summary=d.get("plainSummary") or d.get("plain_summary") or "",
            technical_summary=d.get("technicalSummary") or d.get("technical_summary") or "",
            references=_as_references(d.get("references")),
            justification=d.get("justification") or "",
            needs_human_validation=_as_bool(
                d.get("needsHumanValidation")
                if "needsHumanValidation" in d
                else d.get("needs_human_validation", False)
            ),
            # Un dictionnaire ne peut venir que du modèle (l'outil de soumission).
            source=str(d.get("source") or "model"),
        )


#: Ce qu'un modèle peut écrire pour « faux » : la chaîne "false" est vraie en
#: Python (`bool("false")` → True), c'est exactement le piège mesuré le 13/11.
_FALSEY = {"false", "no", "0", "none", "null", "", "nil"}


def _as_bool(value: Any) -> bool:
    """Lit un booléen venu d'un modèle : vrai, faux, ou « false » en chaîne."""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        return value.strip().lower() not in _FALSEY
    return bool(value)


def _as_optional_id(value: Any) -> str | None:
    """Un identifiant absent : ``None``, pas la chaîne « false »."""
    if value is None or isinstance(value, bool):
        return None
    text = str(value).strip()
    if text.lower() in _FALSEY:
        return None
    return text or None


def _as_references(value: Any) -> list[str]:
    """Liste de références : chaînes, à plat, sans doublon ni vide."""
    if not value:
        return []
    if isinstance(value, str):
        value = [value]
    flat: list[str] = []
    for item in value:
        if isinstance(item, (list, tuple, set)):
            flat.extend(_as_references(item))
            continue
        text = str(item).strip()
        if text and text not in flat:
            flat.append(text)
    return flat
