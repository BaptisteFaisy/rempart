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
import hashlib
from collections import Counter
from typing import Any

from rempart.common.models import Application, Decision, Finding
from rempart.common.store import Store

# La définition des « données sensibles » est celle des garde-fous (chapitre 12) :
# on la partage au lieu de la dupliquer.
from rempart.triage.guardrails import _has_sensitive_data

from ._common import (
    CORPUS_ID_SALT,
    CORPUS_SCHEMA_VERSION,
    MAX_ENTRY_POINT_LENGTH,
    _agent_verdict,
    _human_verdict,
    _month_of,
    _parse,
    _proposal_before,
    _relation,
    _scoped_findings,
    _sorted_decisions,
)


def _case_id(finding: Finding) -> str:
    """Stable anonymised identifier: neither the finding nor the tenant is readable."""
    raw = f"{CORPUS_ID_SALT}|{finding.tenant_id}|{finding.finding_id}"
    return "case-" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _sanitize_entry_point(finding: Finding) -> str:
    """Keep the path of the entry point, drop the host and the query string.

    Hosts identify the client (subdomains, pre-production names) and query
    strings carry tokens or identifiers: neither may leave the perimeter.
    """
    evidence = finding.evidence if isinstance(finding.evidence, dict) else {}
    value = str(evidence.get("entry_point", "") or "")
    value = value.split("#", 1)[0].split("?", 1)[0].strip()
    if "://" in value:
        value = value.split("://", 1)[1]
        slash = value.find("/")
        value = value[slash:] if slash >= 0 else "/"
    return value[:MAX_ENTRY_POINT_LENGTH]


def _features(finding: Finding, app: Application | None) -> dict[str, Any]:
    """The only fields the triage agent needs, anonymised."""
    return {
        "risk_type": finding.risk_type,
        "severity": finding.severity,
        "confidence": finding.confidence,
        "entry_point": _sanitize_entry_point(finding),
        "app_criticality": app.criticality if app else "",
        "app_internet_exposed": bool(app.internet_exposed) if app else False,
        "app_sensitive_data": bool(app is not None and _has_sensitive_data(app)),
        "app_environment": app.environment if app else "",
    }


def _case(
    finding: Finding, decisions: list[Decision], final: Decision, app: Application | None
) -> dict[str, Any]:
    """One labelled case of the reference set."""
    proposal = _proposal_before(decisions, final)
    return {
        "schema_version": CORPUS_SCHEMA_VERSION,
        "case_id": _case_id(finding),
        "features": _features(finding, app),
        "agent_proposal": {
            "proposed_status": _agent_verdict(proposal.action) if proposal else "",
            "proposed_at": proposal.created_at if proposal else "",
        },
        "label": {
            "human_action": final.action,
            "final_verdict": _human_verdict(final.action) or "",
            "decided_at": final.created_at,
            "decided_month": _month_of(final.created_at),
            "agent_human_relation": _relation(final, decisions),
        },
    }


def export_training_corpus(
    store: Store,
    *,
    tenant_id: str | None = None,
    since: str | None = None,
) -> list[dict[str, Any]]:
    """Export the (finding, final human decision) pairs as triage test cases (#34).

    Schema (stable, versioned, ``schema_version`` = "1.0") :

    * ``case_id`` — anonymised, stable identifier (sha256 of the finding id
      salted with the tenant id) ; the raw identifiers never appear.
    * ``features`` — what the agent has to learn from : ``risk_type``,
      ``severity``, ``confidence``, ``entry_point`` (path only : host and query
      string removed), ``app_criticality``, ``app_internet_exposed``,
      ``app_sensitive_data``, ``app_environment``.
    * ``agent_proposal`` — the verdict proposed by the agent before the
      analyst, empty when the analyst judged without any proposal.
    * ``label`` — the human's final verdict : ``human_action``,
      ``final_verdict``, ``decided_at``, ``decided_month``,
      ``agent_human_relation`` (unchanged / diverged / not_comparable).

    Fields deliberately left out, and why :

    * ``finding.title`` — free text written from the raw scan : payloads,
      identifiers and sometimes client data.
    * ``finding.evidence`` — the exploitation proof (steps, requests,
      responses) : the highest re-identification risk of the whole record.
    * ``finding.cvss`` — derived from the exploit, useless for triage (the
      severity is exported) and it may embed the vulnerable URL.
    * ``finding.fingerprint`` — hash of the raw content : it would let anyone
      holding the same finding link two tenants together.
    * ``finding.finding_id`` / ``run_id`` / ``app_id`` / ``tenant_id`` — direct
      identifiers, replaced by the salted ``case_id``.
    * ``application.name`` / ``team`` / ``domains`` / ``repositories`` /
      ``context`` — they identify the client and its organisation.
    * ``decision.author`` — identity of the analyst (personal data).
    * ``decision.justification`` — free text by the analyst, same
      re-identification risk as the evidence ; if it is ever needed it must
      be redacted upstream (piste #38 : anonymisation à la source).

    ``since`` filters on the date of the final human decision. The export is
    sorted by ``(decided_at, case_id)`` and holds no clock-derived value :
    two successive exports are byte-for-byte identical.
    """
    findings = _scoped_findings(store, tenant_id, None)
    apps = {a.app_id: a for a in store.list_applications(tenant_id=tenant_id)}
    since_at = _parse(since)
    cases: list[dict[str, Any]] = []
    for finding in findings:
        decisions = _sorted_decisions(store, finding.finding_id)
        humans = [d for d in decisions if d.author_type == "human"]
        if not humans:
            continue
        final = humans[-1]
        moment = _parse(final.created_at)
        if since_at is not None and (moment is None or moment < since_at):
            continue
        cases.append(_case(finding, decisions, final, apps.get(finding.app_id)))
    return sorted(cases, key=lambda c: (c["label"]["decided_at"], c["case_id"]))


# --------------------------------------------------------------------------- #
# Statistiques du corpus (et ses trous)
# --------------------------------------------------------------------------- #
def _configured_risk_types(store: Store, tenant_id: str | None) -> list[str]:
    """Risk types the product is configured to look for (the catalogue)."""
    types: set[str] = set()
    for app in store.list_applications(tenant_id=tenant_id):
        for config in store.list_configs(app.app_id):
            for risk_type in config.risk_types or []:
                if risk_type:
                    types.add(risk_type)
    return sorted(types)


def _sorted_counter(counter: Counter[str]) -> dict[str, int]:
    """Counter as a dict with sorted keys (stable, diffable output)."""
    return {key: counter[key] for key in sorted(counter)}


def corpus_statistics(
    store: Store,
    *,
    tenant_id: str | None = None,
    since: str | None = None,
) -> dict[str, Any]:
    """Size, coverage and — above all — the holes of the training corpus.

    A corpus whose holes are unknown gives a false confidence: the agent is
    only tested on the risk types the analysts happened to judge. ``gaps``
    lists the risk types the product looks for (catalogue of the test
    configurations) or detects (findings), but that no human ever judged.
    """
    cases = export_training_corpus(store, tenant_id=tenant_id, since=since)
    findings = _scoped_findings(store, tenant_id, None)
    by_status = Counter(c["label"]["human_action"] for c in cases)
    by_verdict = Counter(c["label"]["final_verdict"] for c in cases if c["label"]["final_verdict"])
    by_risk_type = Counter(c["features"]["risk_type"] for c in cases if c["features"]["risk_type"])
    by_severity = Counter(c["features"]["severity"] for c in cases if c["features"]["severity"])
    by_relation = Counter(c["label"]["agent_human_relation"] for c in cases)
    observed = sorted({f.risk_type for f in findings if f.risk_type})
    configured = _configured_risk_types(store, tenant_id)
    covered = sorted(by_risk_type)
    universe = sorted(set(observed) | set(configured))
    gaps = sorted(set(universe) - set(covered))
    return {
        "tenant_id": tenant_id,
        "since": since,
        "size": len(cases),
        "by_status": _sorted_counter(by_status),
        "by_final_verdict": _sorted_counter(by_verdict),
        "by_risk_type": _sorted_counter(by_risk_type),
        "by_severity": _sorted_counter(by_severity),
        "by_agent_human_relation": _sorted_counter(by_relation),
        "observed_risk_types": observed,
        "configured_risk_types": configured,
        "covered_risk_types": covered,
        "gaps": gaps,
        "coverage_ratio": round(len(covered) / len(universe), 4) if universe else 0.0,
    }
