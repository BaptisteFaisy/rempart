"""Constantes et helpers partagés par les métriques d'industrialisation.

Découpé depuis ``industrialization.py`` (642 lignes > la limite de 500).
"""

from dataclasses import dataclass
from datetime import datetime

from rempart.common.models import Decision, Finding
from rempart.common.store import Store
from rempart.common.timeutil import parse_iso
from rempart.reports.metrics import period_bounds, within_period

__all__ = [
    "AGENT_VERDICTS",
    "ALERT_FATIGUE_SCORE_THRESHOLD",
    "ALERT_RATIO_THRESHOLD",
    "ALERT_VALIDATIONS_PER_DAY_THRESHOLD",
    "ASSUMED_MINUTES_PER_FINDING_AUTOMATIC",
    "ASSUMED_MINUTES_PER_FINDING_MANUAL",
    "CORPUS_ID_SALT",
    "CORPUS_SCHEMA_VERSION",
    "HUMAN_VERDICTS",
    "MAX_ENTRY_POINT_LENGTH",
    "MAX_FETCH",
    "RELATION_DIVERGED",
    "RELATION_NOT_COMPARABLE",
    "RELATION_UNCHANGED",
    "_Review",
    "_agent_verdict",
    "_decision_key",
    "_human_verdict",
    "_month_of",
    "_parse",
    "_proposal_before",
    "_ratio",
    "_relation",
    "_review_finding",
    "_reviews",
    "_scoped_findings",
    "_sorted_decisions",
]


MAX_FETCH = 1000

# ---- Taxonomie des verdicts de tri ---------------------------------------- #
# L'agent propose un statut (TriageProposal.proposed_status), l'humain tranche
# avec une action qui peut être un verdict de tri ou un simple état de flux de
# travail (in_remediation, closed, to_retest...). Seuls les verdicts sont
# comparables entre eux : un "in_remediation" ne dit rien sur le fait que
# l'agent se soit trompé.
AGENT_VERDICTS = {
    "CONFIRMED": "CONFIRMED",
    "TO_VERIFY": "TO_VERIFY",
    "LIKELY_FALSE_POSITIVE": "FALSE_POSITIVE",
}
HUMAN_VERDICTS = {
    "confirmed": "CONFIRMED",
    "false_positive": "FALSE_POSITIVE",
    "pending_validation": "TO_VERIFY",
    "risk_accepted": "RISK_ACCEPTED",
}
RELATION_UNCHANGED = "unchanged"
RELATION_DIVERGED = "diverged"
RELATION_NOT_COMPARABLE = "not_comparable"

# ---- Seuils de fatigue d'alerte (piste #26) -------------------------------- #
# CONVENTIONS documentées, pas des mesures. Justification de chaque valeur :
#   * 40 validations par jour actif : une revue sérieuse coûte plus d'une
#     minute par cas, donc 40 cas représentent déjà une heure d'attention
#     continue ; au-delà la file est traitée par lots et le « confirmer »
#     devient un réflexe.
#   * 50 % de validations sans changement : plus d'une validation sur deux ne
#     change rien, donc la valeur ajoutée de l'analyste est sous le coût du
#     clic — soit l'agent avait raison et le clic est du temps perdu, soit les
#     propositions ne sont pas lues.
#   * 0,5 sur le score composite de fatigue.
ALERT_RATIO_THRESHOLD = 0.5
ALERT_VALIDATIONS_PER_DAY_THRESHOLD = 40
ALERT_FATIGUE_SCORE_THRESHOLD = 0.5

# ---- Hypothèses de temps analyste (piste #47) ------------------------------ #
# JAMAIS des mesures : le produit ne relève pas le temps analyste.
ASSUMED_MINUTES_PER_FINDING_MANUAL = 12.0
ASSUMED_MINUTES_PER_FINDING_AUTOMATIC = 1.0

CORPUS_SCHEMA_VERSION = "1.0"
CORPUS_ID_SALT = "rempart-corpus-v1"
MAX_ENTRY_POINT_LENGTH = 120


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _parse(value: str | None) -> datetime | None:
    """Parse an ISO timestamp, returning None when missing or malformed."""
    if not value:
        return None
    try:
        return parse_iso(value)
    except ValueError:
        return None


def _decision_key(decision: Decision) -> tuple[str, str]:
    """Total order on decisions: chronological, ties broken by id."""
    return (decision.created_at or "", decision.decision_id or "")


def _sorted_decisions(store: Store, finding_id: str) -> list[Decision]:
    """Decisions of a finding, chronological (the store scan order is arbitrary)."""
    return sorted(store.list_decisions(finding_id), key=_decision_key)


def _agent_verdict(action: str) -> str | None:
    """Canonical verdict of an agent proposal, None when it is not a verdict."""
    return AGENT_VERDICTS.get((action or "").strip().upper())


def _human_verdict(action: str) -> str | None:
    """Canonical verdict of a human decision, None when it is not a verdict."""
    return HUMAN_VERDICTS.get((action or "").strip().lower())


def _proposal_before(decisions: list[Decision], decision: Decision) -> Decision | None:
    """Most recent agent proposal that precedes the given decision."""
    key = _decision_key(decision)
    candidates = [d for d in decisions if d.author_type == "agent" and _decision_key(d) < key]
    return candidates[-1] if candidates else None


def _relation(decision: Decision, decisions: list[Decision]) -> str:
    """Compare a human decision with the agent proposal that precedes it."""
    proposal = _proposal_before(decisions, decision)
    if proposal is None:
        return RELATION_NOT_COMPARABLE
    agent = _agent_verdict(proposal.action)
    human = _human_verdict(decision.action)
    if agent is None or human is None:
        return RELATION_NOT_COMPARABLE
    return RELATION_UNCHANGED if agent == human else RELATION_DIVERGED


def _ratio(numerator: int, denominator: int) -> float:
    """Ratio rounded to 4 decimals, 0.0 when the denominator is empty."""
    if denominator <= 0:
        return 0.0
    return round(numerator / denominator, 4)


def _month_of(value: str | None) -> str:
    """Month key ('YYYY-MM') of an ISO timestamp."""
    return (value or "")[:7]


def _scoped_findings(store: Store, tenant_id: str | None, period: str | None) -> list[Finding]:
    """Findings of the tenant, restricted to the period, in a stable order."""
    findings = store.list_findings(tenant_id=tenant_id, limit=MAX_FETCH)
    if period:
        start, end = period_bounds(period)
        findings = [f for f in findings if within_period(f.created_at, start, end)]
    return sorted(findings, key=lambda f: (f.created_at or "", f.finding_id or ""))


@dataclass
class _Review:
    """Everything the metrics need to know about one finding's decision chain."""

    finding: Finding
    decisions: list[Decision]
    human_decisions: int
    agent_decisions: int
    unchanged: int
    diverged: int
    not_comparable: int

    @property
    def reviewed(self) -> bool:
        """True when the agent proposed and a human judged the same finding."""
        return self.unchanged + self.diverged > 0


def _review_finding(finding: Finding, decisions: list[Decision]) -> _Review:
    """Compare every human decision of a finding with the agent's proposals."""
    humans = [d for d in decisions if d.author_type == "human"]
    agents = [d for d in decisions if d.author_type == "agent"]
    unchanged = diverged = not_comparable = 0
    for human in humans:
        relation = _relation(human, decisions)
        if relation == RELATION_UNCHANGED:
            unchanged += 1
        elif relation == RELATION_DIVERGED:
            diverged += 1
        else:
            not_comparable += 1
    return _Review(
        finding=finding,
        decisions=decisions,
        human_decisions=len(humans),
        agent_decisions=len(agents),
        unchanged=unchanged,
        diverged=diverged,
        not_comparable=not_comparable,
    )


def _reviews(store: Store, findings: list[Finding]) -> list[_Review]:
    """Review every finding of the scope."""
    return [_review_finding(f, _sorted_decisions(store, f.finding_id)) for f in findings]
