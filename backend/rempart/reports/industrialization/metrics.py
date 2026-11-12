"""Industrialisation metrics for Rempart (pistes #34 and #68, ENF-IA-01).

Two questions, answered with plain Python — no language model ever takes part
in a number:

* **#68 — taux d'intervention humaine** : how many findings still need a
  human? A finding nobody touched was triaged by the agent alone; a finding a
  human decided on is an agency in disguise. The useful sub-metric is the
  *divergence* : a human who confirms the agent without changing anything
  pays the click for nothing (see :func:`alert_fatigue_indicators`).
* **#34 — corpus de décisions** : every analyst correction must feed a
  reusable reference set for the triage agent, otherwise the asset does not
  appreciate with usage. The export is anonymised : no raw finding content
  ever leaves the function (see :func:`export_training_corpus`).

Determinism: same store + same parameters = same bytes. The only clock used
is ``now``, and it is injectable wherever it defines a window.

Découpé depuis ``industrialization.py`` (642 lignes > la limite de 500).
"""
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any

from rempart.common.models import Decision
from rempart.common.store import Store
from rempart.common.timeutil import utcnow
from rempart.reports.metrics import period_bounds

# La définition des « données sensibles » est celle des garde-fous (chapitre 12) :
# on la partage au lieu de la dupliquer.
from ._common import (
    ALERT_FATIGUE_SCORE_THRESHOLD,
    ALERT_RATIO_THRESHOLD,
    ALERT_VALIDATIONS_PER_DAY_THRESHOLD,
    ASSUMED_MINUTES_PER_FINDING_AUTOMATIC,
    ASSUMED_MINUTES_PER_FINDING_MANUAL,
    RELATION_DIVERGED,
    RELATION_NOT_COMPARABLE,
    RELATION_UNCHANGED,
    _month_of,
    _parse,
    _ratio,
    _relation,
    _Review,
    _reviews,
    _scoped_findings,
)


def _monthly_volume(reviews: list[_Review]) -> dict[str, dict[str, int]]:
    """Absolute volume per month of detection (finding creation)."""
    volume: dict[str, dict[str, int]] = {}
    for review in reviews:
        entry = volume.setdefault(
            _month_of(review.finding.created_at),
            {"findings": 0, "human_intervened": 0, "diverged": 0},
        )
        entry["findings"] += 1
        if review.human_decisions:
            entry["human_intervened"] += 1
        if review.diverged:
            entry["diverged"] += 1
    return {month: volume[month] for month in sorted(volume)}


def _monthly_human_decisions(reviews: list[_Review]) -> dict[str, int]:
    """Number of human decisions per month of decision."""
    counts: Counter[str] = Counter()
    for review in reviews:
        for decision in review.decisions:
            if decision.author_type == "human":
                counts[_month_of(decision.created_at)] += 1
    return {month: counts[month] for month in sorted(counts)}


def human_intervention_rate(
    store: Store,
    *,
    tenant_id: str | None = None,
    period: str | None = None,
) -> dict[str, Any]:
    """Share of the findings that needed a human, and where the agent was corrected.

    Scope: the findings of the tenant created during the period ('YYYY-MM');
    with no period, every finding of the tenant.

    Formulas (deterministic, ENF-IA-01):

    * ``human_intervention_rate``
      = findings_with_human_decision / findings_total
    * ``agent_human_divergence_rate`` = findings_diverged / findings_total
      (a finding is *diverged* when a human verdict differs from the agent
      proposal that preceded it: the analyst had to correct the agent)
    * ``divergence_rate_among_reviewed``
      = findings_diverged / findings_reviewed_by_human
      (the agent's error rate on the findings a human actually looked at)
    """
    findings = _scoped_findings(store, tenant_id, period)
    reviews = _reviews(store, findings)
    total = len(reviews)
    with_human = sum(1 for r in reviews if r.human_decisions)
    with_agent = sum(1 for r in reviews if r.agent_decisions)
    reviewed = [r for r in reviews if r.reviewed]
    diverged = sum(1 for r in reviewed if r.diverged)
    divergence_rate = _ratio(diverged, len(reviewed)) if reviewed else None
    return {
        "period": period,
        "tenant_id": tenant_id,
        "findings_total": total,
        "findings_with_human_decision": with_human,
        "human_intervention_rate": _ratio(with_human, total),
        "findings_with_agent_proposal": with_agent,
        "findings_reviewed_by_human": len(reviewed),
        "findings_diverged": diverged,
        "agent_human_divergence_rate": _ratio(diverged, total),
        "divergence_rate_among_reviewed": divergence_rate,
        "agent_agreement_rate_on_reviewed": (
            round(1.0 - divergence_rate, 4) if divergence_rate is not None else None
        ),
        "human_decisions": sum(r.human_decisions for r in reviews),
        "agent_decisions": sum(r.agent_decisions for r in reviews),
        "monthly_volume": _monthly_volume(reviews),
        "monthly_human_decisions": _monthly_human_decisions(reviews),
        "formulas": {
            "human_intervention_rate": "findings_with_human_decision / findings_total",
            "agent_human_divergence_rate": "findings_diverged / findings_total",
            "divergence_rate_among_reviewed": "findings_diverged / findings_reviewed_by_human",
            "agent_agreement_rate_on_reviewed": "1 - divergence_rate_among_reviewed",
        },
    }


# --------------------------------------------------------------------------- #
# #26 — fatigue d'alerte
# --------------------------------------------------------------------------- #
def _window(period: str | None, now: datetime) -> tuple[datetime, datetime]:
    """Analysis window: the period, or the 30 days ending at ``now``."""
    if period:
        return period_bounds(period)
    return now - timedelta(days=30), now


def _validations_in_window(
    reviews: list[_Review], start: datetime, end: datetime
) -> list[tuple[Decision, str]]:
    """Human decisions dated inside the window, with their agent/human relation."""
    out: list[tuple[Decision, str]] = []
    for review in reviews:
        for decision in review.decisions:
            if decision.author_type != "human":
                continue
            moment = _parse(decision.created_at)
            if moment is None or not (start <= moment < end):
                continue
            out.append((decision, _relation(decision, review.decisions)))
    return out


def _alert_reasons(ratio: float | None, per_active_day: float, score: float) -> list[str]:
    """Human readable reasons why the fatigue alert is raised."""
    reasons: list[str] = []
    if ratio is not None and ratio > ALERT_RATIO_THRESHOLD:
        reasons.append(
            f"{ratio:.0%} des validations n'ont rien changé à la proposition de l'agent "
            f"(seuil {ALERT_RATIO_THRESHOLD:.0%}) : l'analyste valide en série."
        )
    if per_active_day > ALERT_VALIDATIONS_PER_DAY_THRESHOLD:
        reasons.append(
            f"{per_active_day} validations par jour actif (seuil "
            f"{ALERT_VALIDATIONS_PER_DAY_THRESHOLD}) : la file est trop longue pour être lue."
        )
    if score > ALERT_FATIGUE_SCORE_THRESHOLD:
        reasons.append(f"score de fatigue {score} (seuil {ALERT_FATIGUE_SCORE_THRESHOLD}).")
    return reasons


def alert_fatigue_indicators(
    store: Store,
    *,
    tenant_id: str | None = None,
    period: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Alert-fatigue indicators (piste #26) of the triage loop.

    The analyst clicks "confirm" without reading when the queue is too long or
    when the proposals are too easy to rubber-stamp. Both are measured here:

    * ``validations_per_active_day`` : human validations per day that had at
      least one validation (the queue seen by the analyst);
    * ``no_change_validation_ratio`` : share of validations that changed
      *nothing* compared to the agent proposal (rubber-stamp clicks), computed
      on the comparable validations only — a decision whose action is not a
      triage verdict is not comparable and is excluded;
    * ``fatigue_score`` = ``no_change_validation_ratio`` x min(1,
      ``validations_per_active_day`` / 40) — bounded to [0, 1].

    The thresholds are the documented conventions explained in the module
    constants; the alert is raised when one of them is exceeded (strictly).
    ``now`` is injectable so the rolling window (30 days without a period) is
    reproducible.
    """
    reference = (now or utcnow()).astimezone(timezone.utc)
    start, end = _window(period, reference)
    days = max(1, (end - start).days)
    reviews = _reviews(store, _scoped_findings(store, tenant_id, None))
    validations = _validations_in_window(reviews, start, end)
    active_days = {(d.created_at or "")[:10] for d, _ in validations}
    comparable = [rel for _, rel in validations if rel != RELATION_NOT_COMPARABLE]
    unchanged = sum(1 for rel in comparable if rel == RELATION_UNCHANGED)
    diverged = sum(1 for rel in comparable if rel == RELATION_DIVERGED)
    ratio = round(unchanged / len(comparable), 4) if comparable else None
    per_active_day = round(len(validations) / len(active_days), 2) if active_days else 0.0
    per_calendar_day = round(len(validations) / days, 3) if days else 0.0
    score = round(
        (ratio or 0.0) * min(1.0, per_active_day / ALERT_VALIDATIONS_PER_DAY_THRESHOLD), 4
    )
    reasons = _alert_reasons(ratio, per_active_day, score)
    return {
        "period": period,
        "tenant_id": tenant_id,
        "window_start": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "window_end": end.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "window_days": days,
        "human_validations": len(validations),
        "active_days": len(active_days),
        "validations_per_active_day": per_active_day,
        "validations_per_calendar_day": per_calendar_day,
        "comparable_validations": len(comparable),
        "unchanged_validations": unchanged,
        "diverged_validations": diverged,
        "no_change_validation_ratio": ratio,
        "fatigue_score": score,
        "alert_triggered": bool(reasons),
        "alert_reasons": reasons,
        "thresholds": {
            "no_change_validation_ratio": ALERT_RATIO_THRESHOLD,
            "validations_per_active_day": ALERT_VALIDATIONS_PER_DAY_THRESHOLD,
            "fatigue_score": ALERT_FATIGUE_SCORE_THRESHOLD,
        },
    }


# --------------------------------------------------------------------------- #
# #47 — temps analyste économisé (ESTIMATION, hypothèses explicites)
# --------------------------------------------------------------------------- #
def analyst_minutes_saved(
    store: Store,
    *,
    tenant_id: str | None = None,
    period: str | None = None,
    minutes_per_finding_manual: float = ASSUMED_MINUTES_PER_FINDING_MANUAL,
    minutes_per_finding_automatic: float = ASSUMED_MINUTES_PER_FINDING_AUTOMATIC,
) -> dict[str, Any]:
    """Estimated analyst minutes saved by the automated triage (piste #47).

    The two durations are HYPOTHESES, never measurements: the product does not
    track the time an analyst spends on a finding, so the output carries them
    under ``assumptions`` with ``measured: False``.

    Only the findings the agent handled end-to-end are credited: a finding a
    human judged is counted at the full manual cost, because the time saved
    by reading a proposal instead of triaging from scratch is not measured.
    """
    findings = _scoped_findings(store, tenant_id, period)
    reviews = _reviews(store, findings)
    triaged = [r for r in reviews if r.human_decisions or r.agent_decisions]
    automatic = [r for r in triaged if r.agent_decisions and not r.human_decisions]
    human = [r for r in triaged if r.human_decisions]
    manual_total = len(triaged) * minutes_per_finding_manual
    spent = len(automatic) * minutes_per_finding_automatic + len(human) * minutes_per_finding_manual
    saved = max(0.0, manual_total - spent)
    return {
        "period": period,
        "tenant_id": tenant_id,
        "findings_total": len(reviews),
        "findings_triaged": len(triaged),
        "findings_not_triaged": len(reviews) - len(triaged),
        "findings_automatically_triaged": len(automatic),
        "findings_reviewed_by_human": len(human),
        "manual_minutes_if_all_human": round(manual_total, 2),
        "estimated_minutes_spent": round(spent, 2),
        "minutes_saved": round(saved, 2),
        "hours_saved": round(saved / 60.0, 2),
        "assumptions": {
            "minutes_per_finding_manual": minutes_per_finding_manual,
            "minutes_per_finding_automatic": minutes_per_finding_automatic,
            "measured": False,
            "is_estimate": True,
            "basis": (
                "hypothèse documentée, pas une mesure : le produit ne relève pas le temps "
                "analyste ; seul le temps des failles triées sans intervention humaine est crédité"
            ),
        },
    }


# --------------------------------------------------------------------------- #
# #34 — corpus de décisions (export anonymisé)
# --------------------------------------------------------------------------- #
