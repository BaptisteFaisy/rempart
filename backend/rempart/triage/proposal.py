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
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "TriageProposal":
        """Build a TriageProposal from either camelCase or snake_case dictionary."""
        return cls(
            finding_id=d.get("findingId") or d.get("finding_id") or "",
            duplicate_of=d.get("duplicateOf") if "duplicateOf" in d else d.get("duplicate_of"),
            is_regression=bool(
                d.get("isRegression") if "isRegression" in d else d.get("is_regression", False)
            ),
            proposed_status=d.get("proposedStatus") or d.get("proposed_status") or "CONFIRMED",
            priority=d.get("priority") or "P4",
            plain_summary=d.get("plainSummary") or d.get("plain_summary") or "",
            technical_summary=d.get("technicalSummary") or d.get("technical_summary") or "",
            references=list(d.get("references") or []),
            justification=d.get("justification") or "",
            needs_human_validation=bool(
                d.get("needsHumanValidation")
                if "needsHumanValidation" in d
                else d.get("needs_human_validation", False)
            ),
        )
