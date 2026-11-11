"""Débit du tri des failles — rend ENF-PERF-01 mesurable (chapitre 10).

Exigence : « Tri de 50 failles en moins de 5 minutes ». Ce test mesure la chaîne
complète d'une livraison — ``collect_findings`` (intake : empreintes, doublons,
régressions) puis ``run_triage`` (agent de tri, chapitre 12) puis ``enforce``
(garde-fous déterministes, chapitre 12.4) — sur un lot de 50 failles réalistes.

Il vérifie aussi que le volume ne dégrade pas l'exactitude : les 50 failles sont
toutes expliquées, aucun doublon ne devient une seconde faille (donc un second
ticket), la régression est détectée, et les garde-fous tiennent sur Critical/High.

Les mesures qui justifient les seuils sont dans ``tests/performance/README.md``.
"""

from __future__ import annotations

from typing import Any

from rempart.orchestrator.tasks import create_tickets
from rempart.orchestrator.triage_dispatch import apply_proposals
from rempart.triage.guardrails import HIGH_SEVERITIES
from tests.performance.conftest import (
    APP_ID,
    PAYLOAD,
    TENANT_ID,
    TIME_FLOOR,
    ChainRun,
    PerfEnv,
    best_of,
    build_env,
    measure_triage_chain,
    run_triage_chain,
    seed_triage_env,
    triage_findings,
)
from tests.reports.conftest import make_finding

# --------------------------------------------------------------------------- #
# Seuils (mesures : README.md — machine de référence, 2026-11-11)
# --------------------------------------------------------------------------- #
# Mesuré : 3,1 ms pour la chaîne complète sur 50 failles (pire tour observé
# 8,3 ms). Un seuil à 300 s — la lettre de l'exigence — ne détecterait aucune
# régression ; un seuil à 30 ms casserait au premier runner partagé bruyant.
# 1,0 s = ~120x le pire tour observé (marge confortable en CI) et 300x sous
# l'exigence contractuelle : la CI rougit bien avant que le contrat soit menacé.
TRIAGE_BUDGET_SECONDS = 1.0
# Croissance tolérée quand le lot quadruple (50 -> 200) : mesuré entre x5,5 et
# x13 selon la charge de la machine (les durées sont de l'ordre de la
# milliseconde). Le terme quadratique est réel et documenté dans le README
# (recherche d'empreinte linéaire + garde-fous qui relisent la base par faille) :
# ce seuil ne prétend donc pas interdire le quadratique, seulement signaler une
# explosion (x100 = ~8x le pire observé). La vraie alarme est le budget absolu.
SCALE_MAX_GROWTH = 100.0
# 50 recherches d'empreintes : 0,14 ms à 50 failles connues, 0,48 ms à 200
# (x3,4 pour un volume x4 → coût linéaire par recherche). Seuil x20 = ~6x le
# ratio mesuré : les durées sont si courtes qu'un ratio serré serait aléatoire.
LOOKUP_BUDGET_SECONDS = 0.5
LOOKUP_MAX_GROWTH = 20.0


def _assert_intake_exactness(run: ChainRun) -> None:
    """Le volume ne doit rien faire perdre ni compter deux fois."""
    out, plan = run.intake, run.plan
    assert len(out["findings_created"]) == plan.expected_created
    assert out["duplicates_skipped"] == plan.expected_duplicates
    assert out["regressions"] == plan.expected_regressions
    # Les 50 failles brutes sont toutes expliquées par l'une des trois issues.
    assert len(out["findings_created"]) + out["duplicates_skipped"] + out["regressions"] == len(
        plan.raws
    )


def _assert_one_finding_per_fingerprint(run: ChainRun) -> None:
    """Une empreinte = une faille en base : un doublon ne devient pas une 2e faille."""
    stored = run.env.store.list_findings(app_id=APP_ID, limit=1000)
    fingerprints = [f.fingerprint for f in stored]
    assert len(fingerprints) == len(set(fingerprints))
    # 49 empreintes distinctes dans le lot + la sonde de régression fermée.
    assert len(stored) == run.plan.distinct_fingerprints + 1


def _assert_proposals_applied(run: ChainRun) -> None:
    """Chaque faille créée est triée, priorisée par la matrice et écrite en base."""
    apply_proposals(run.env.deps, run.proposals)
    stored = {f.finding_id: f for f in run.env.store.list_findings(app_id=APP_ID, limit=1000)}
    assert len(run.proposals) == run.plan.expected_created
    assert len({p.finding_id for p in run.proposals}) == run.plan.expected_created
    for proposal in run.proposals:
        finding = stored[proposal.finding_id]
        assert finding.priority == proposal.priority in ("P1", "P2", "P3", "P4")
        assert finding.status in ("pending_validation", "confirmed")
        assert proposal.proposed_status in ("CONFIRMED", "TO_VERIFY", "LIKELY_FALSE_POSITIVE")
        if finding.severity in HIGH_SEVERITIES:  # garde-fou EF-TRI-05 / ENF-IA-02
            assert proposal.needs_human_validation is True
            assert finding.status == "pending_validation"


def test_enf_perf_01_triage_of_50_findings_meets_budget() -> None:
    """ENF-PERF-01 : la chaîne complète de tri de 50 failles tient dans le budget."""
    run = measure_triage_chain(50)

    _assert_intake_exactness(run)
    _assert_one_finding_per_fingerprint(run)
    _assert_proposals_applied(run)

    assert run.seconds < TRIAGE_BUDGET_SECONDS, (
        f"tri de 50 failles trop lent : {run.seconds * 1000:.1f} ms "
        f"(intake {run.phases['intake'] * 1000:.1f} ms, "
        f"tri + garde-fous {run.phases['triage'] * 1000:.1f} ms)"
    )


def test_enf_perf_01_triage_cost_stays_bounded_when_volume_quadruples() -> None:
    """Coût marginal du volume : 200 failles restent dans le budget de 50."""
    small = measure_triage_chain(50, repeats=3)
    large = measure_triage_chain(200, repeats=3)

    assert len(large.proposals) == large.plan.expected_created
    # Alarme principale, insensible au bruit : un budget absolu pour 4x le volume.
    assert large.seconds < TRIAGE_BUDGET_SECONDS, (
        f"tri de 200 failles trop lent : {large.seconds * 1000:.1f} ms"
    )
    growth = large.seconds / max(small.seconds, TIME_FLOOR)
    assert growth <= SCALE_MAX_GROWTH, (
        f"coût du tri en explosion : {small.seconds * 1000:.1f} ms pour 50 failles, "
        f"{large.seconds * 1000:.1f} ms pour 200 (x{growth:.1f})"
    )


def _known_others(env: PerfEnv, excluded_id: str) -> tuple[Any, list[Any]]:
    """Application et failles connues, hors celle qu'on trie."""
    app = env.store.get_application(APP_ID)
    known = [
        f
        for f in env.store.list_findings(app_id=APP_ID, limit=1000)
        if f.finding_id != excluded_id
    ]
    return app, known


def test_enf_perf_01_same_run_marks_regression() -> None:
    """La faille fermée réapparue est rouverte et le garde-fou marque la régression."""
    env, plan = seed_triage_env(50)
    intake, proposals, _ = run_triage_chain(env)

    reopened = env.store.get_finding("f-known-closed")
    assert reopened is not None and reopened.status == "reopened"
    assert intake["regressions"] == 1
    assert len(proposals) == plan.expected_created

    # Sonde : ``enforce`` doit détecter la régression sur une empreinte fermée.
    probe = make_finding("f-probe-new", APP_ID, tenant_id=TENANT_ID, status="new")
    probe.fingerprint = env.store.get_finding("f-probe-closed").fingerprint
    env.store.save_finding(probe)
    app, known = _known_others(env, probe.finding_id)
    hardened = triage_findings(env, [probe], app, known)[0]
    assert hardened.is_regression is True
    assert hardened.duplicate_of is None


def _ticketed_finding_ids(env: PerfEnv) -> list[str]:
    """Identifiants de failles cités dans les tickets ouverts (corps de l'issue)."""
    ids: list[str] = []
    marker = "Finding id: `"
    for issue in env.deps.github.issues:
        body = issue["body"]
        start = body.index(marker) + len(marker)
        ids.append(body[start : body.index("`", start)])
    return ids


def test_enf_perf_01_duplicates_do_not_create_duplicate_tickets() -> None:
    """Un doublon écarté à l'intake ne produit pas de second ticket."""
    env, plan = seed_triage_env(50)
    intake, _, _ = run_triage_chain(env)
    created_ids = intake["findings_created"]
    for finding_id in created_ids:
        env.store.get_finding(finding_id).status = "confirmed"

    tickets = create_tickets({**PAYLOAD, "confirmed": created_ids}, env.deps)

    assert len(tickets["tickets"]) == plan.expected_created
    # Un ticket par faille créée, et pour aucune autre : le doublon interne au
    # lot et le doublon d'une faille déjà ouverte n'ont rien produit de plus.
    assert sorted(_ticketed_finding_ids(env)) == sorted(created_ids)


def _measure_lookup_cost(known: int, lookups: int = 50) -> float:
    """Coût de ``lookups`` recherches d'empreintes sur ``known`` failles connues."""
    env = build_env()
    for i in range(known):
        finding = make_finding(f"f-known-{i}", APP_ID, tenant_id=TENANT_ID, run_id=f"run-{i % 50}")
        finding.fingerprint = f"fp-known-{i:04d}"
        env.store.save_finding(finding)

    def look() -> None:
        for i in range(lookups):
            env.store.find_by_fingerprint(APP_ID, f"fp-absent-{i:04d}")

    return best_of(look)


def test_fingerprint_lookup_cost_stays_bounded_when_volume_grows() -> None:
    """Coût marginal de ``find_by_fingerprint``, mesuré à 50 et à 200 failles connues.

    ``find_by_fingerprint`` balaie toutes les failles (``FakeStore`` comme
    ``Store`` DynamoDB, qui fait un ``scan``) : le coût unitaire croît avec le
    volume connu, et l'intake d'un lot de n failles est en O(n x base). On mesure
    les deux chiffres et on borne la croissance — sans corriger le code
    applicatif, hors de la zone de ce test (pistes dans le README).
    """
    cost_50 = _measure_lookup_cost(50)
    cost_200 = _measure_lookup_cost(200)
    growth = cost_200 / max(cost_50, TIME_FLOOR)

    assert cost_50 < LOOKUP_BUDGET_SECONDS
    assert cost_200 < LOOKUP_BUDGET_SECONDS
    assert growth <= LOOKUP_MAX_GROWTH, (
        f"coût de recherche d'empreinte anormalement super-linéaire : "
        f"{cost_50 * 1000:.2f} ms à 50 failles connues, {cost_200 * 1000:.2f} ms à 200 "
        f"(x{growth:.1f} pour un volume x4)"
    )
