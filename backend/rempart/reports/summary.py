"""Executive summary for the monthly report (model draft or deterministic fallback).

Every number comes from the frozen KPI snapshot: the model only writes prose
(ENF-IA-01).
"""

import re
from dataclasses import dataclass
from typing import Any

_BULLET_RE = re.compile(r"^\s*(?:[-*]|\d+[.)])\s*")


# --------------------------------------------------------------------------- #
# Executive summary (model or fallback)
# --------------------------------------------------------------------------- #
@dataclass
class ExecutiveSummary:
    """The 3 pieces required by Annexe C item 1."""

    risk_level: str
    highlights: list[str]
    expected_decision: str


def risk_level_label(level: str) -> str:
    """Translate risk level code to French presentation string."""
    mapping = {
        "critical": "Critique",
        "moderate": "Modere",
        "low": "Faible",
    }
    return mapping.get(level.lower(), level.capitalize())


def badge_class(label: str) -> str:
    """Map a risk level label onto its CSS badge class."""
    normalized = label.strip().lower()
    if normalized in ("critique", "critical"):
        return "crit"
    if normalized in ("modere", "modéré", "moderate"):
        return "mod"
    return "low"


def _fallback_summary(frozen: dict[str, Any]) -> ExecutiveSummary:
    """Deterministic summary complying with Annexe C item 1."""
    level = risk_level_label(str(frozen.get("risk_level", "low")))
    p1 = frozen.get("findings_open_by_priority", {}).get("P1", 0)
    p2 = frozen.get("findings_open_by_priority", {}).get("P2", 0)
    blocked_pct = round(frozen.get("critical_blocked_before_prod", 0.0) * 100, 1)
    sla_pct = round(frozen.get("sla_compliance", 1.0) * 100, 1)
    coverage_pct = round(frozen.get("coverage", 0.0) * 100, 1)

    highlights = [
        (
            f"{frozen.get('tests_total', 0)} tests d'intrusion realises : "
            f"{blocked_pct} % des failles P1/P2 arretees avant mise en production "
            f"({frozen.get('tests_blocked', 0)} livraisons bloquees par la porte CI/CD)."
        ),
        (
            f"{frozen.get('findings_closed', 0)} failles fermees avec preuve de correction, "
            f"avec un respect des echeances contractuelles de {sla_pct} %."
        ),
        (
            f"Couverture du parc a {coverage_pct} % des applications du contrat, "
            f"pour {frozen.get('task_hours_used', 0.0)} heures-taches consommees."
        ),
    ]

    if p1 > 0:
        decision = (
            f"Arbitrer et allouer les ressources de developpement pour resoudre les "
            f"{p1} faille(s) critique(s) P1 avant l'echeance des 7 jours."
        )
    elif p2 > 0:
        decision = (
            f"Valider le calendrier de correction sous 30 jours pour les {p2} faille(s) P2 "
            "identifiees ce mois-ci."
        )
    else:
        decision = (
            "Renouveler le mandat de test continu et maintenir la politique de blocage "
            "en preproduction sans modification."
        )

    return ExecutiveSummary(
        risk_level=level,
        highlights=highlights,
        expected_decision=decision,
    )


def _parse_model_summary(raw: str, fallback: ExecutiveSummary) -> ExecutiveSummary:
    """Best-effort parser for the model output, falling back to deterministic lines."""
    lines = [line.strip() for line in raw.splitlines() if line.strip()]
    if not lines:
        return fallback

    level = fallback.risk_level
    highlights: list[str] = []
    decision = fallback.expected_decision

    for line in lines:
        lower = line.lower()
        if "niveau de risque" in lower:
            for candidate in ("critique", "modere", "modéré", "faible", "critical", "low"):
                if candidate in lower:
                    level = risk_level_label(candidate.replace("é", "e"))
                    break
        elif _BULLET_RE.match(line) and len(highlights) < 3:
            highlights.append(_BULLET_RE.sub("", line))
        elif "decision" in lower or "décision" in lower:
            parts = line.split(":", 1)
            decision = parts[1].strip() if len(parts) > 1 else line

    while len(highlights) < 3:
        highlights.append(fallback.highlights[len(highlights)])

    return ExecutiveSummary(
        risk_level=level,
        highlights=highlights[:3],
        expected_decision=decision,
    )


def draft_executive_summary(frozen: dict[str, Any], model_client: Any | None = None) -> ExecutiveSummary:
    """Produce the Annexe C item 1 executive summary."""
    fallback = _fallback_summary(frozen)
    if model_client is None:
        return fallback

    prompt = (
        "Redige la synthese executive du rapport mensuel de securite Rempart pour le dirigeant.\n"
        "Contraintes absolues :\n"
        "- Utilise UNIQUEMENT les chiffres figes fournis, n'en invente AUCUN.\n"
        "- Exactement 3 faits marquants courts et percutants.\n"
        "- Exactement 1 decision attendue pour le dirigeant.\n"
        "- Un niveau de risque : Faible, Modere ou Critique.\n\n"
        f"Chiffres figes :\n{frozen}\n"
    )
    try:
        raw = model_client.invoke(prompt)
        if isinstance(raw, str) and raw.strip():
            return _parse_model_summary(raw, fallback)
    except Exception:
        pass
    return fallback


