"""Données et outillage des tests de performance (ENF-PERF-01).

Aucune valeur aléatoire : les volumes sont construits par des cycles
déterministes sur l'index, pour que deux exécutions mesurent exactement le même
travail. Les builders d'entités (``make_app``, ``make_finding``, ``make_run``,
``make_tenant``) sont réutilisés depuis ``tests/reports/conftest.py`` : ce module
n'ajoute que la génération de failles brutes « Security Agent » variées, un
chronomètre et les corpora de volume.
"""

from __future__ import annotations

import contextlib
import time
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass, field
from typing import Any

import pytest

from rempart.common.fingerprint import finding_fingerprint
from rempart.common.models import Application, Finding
from rempart.orchestrator.findings_intake import collect_findings
from rempart.orchestrator.task_types import Deps
from rempart.triage.agent import run_triage
from rempart.triage.guardrails import enforce
from tests.fakes import FakeGitHub, FakeSecurityAgentClient, FakeStore
from tests.reports.conftest import (
    make_app,
    make_finding,
    make_run,
    make_tenant,
)

TENANT_ID = "t-perf"
APP_ID = "app-perf"
JOB_ID = "job-perf"
PERIOD = "2026-10"
PAYLOAD = {"app_id": APP_ID, "tenant_id": TENANT_ID, "run_id": JOB_ID}

# Nombre de répétitions d'une mesure : on retient le minimum, ce qui filtre le
# bruit d'un runner partagé (GC, cache froid, voisins bruyants).
REPEATS = 5
# Plancher anti-bruit (0,1 ms) pour les rapports de croissance entre mesures.
TIME_FLOOR = 1e-4

# Volumes du corpus KPI : un mois réaliste pour un client en formule « continu ».
APPS = 5
RUNS = 50
FINDINGS = 200

SEVERITIES = ("Critical", "High", "Medium", "Low", "Informational")
CONFIDENCES = ("High", "Medium", "Low")
RISK_TYPES = (
    "IDOR",
    "SQLi",
    "XSS",
    "SSRF",
    "AuthBypass",
    "PathTraversal",
    "CSRF",
    "OpenRedirect",
)

# Triplets (risk_type, entry_point, parameter) déjà connus du Store.
KNOWN_OPEN = ("SSRF", "/legacy/export", "url")  # doublon d'une faille ouverte
KNOWN_CLOSED = ("IDOR", "/billing/{invoice}", "invoice_id")  # régression
KNOWN_CLOSED_PROBE = ("XSS", "/comments/preview", "body")  # sonde pour `enforce`

_OPEN_STATUSES = (
    "new",
    "pending_validation",
    "confirmed",
    "in_remediation",
    "to_retest",
    "reopened",
)


# --------------------------------------------------------------------------- #
# Chronomètre
# --------------------------------------------------------------------------- #
@contextlib.contextmanager
def chrono() -> Iterator[dict[str, float]]:
    """Chronomètre à ``time.perf_counter()`` : ``with chrono() as t: ...; t["seconds"]``."""
    box = {"seconds": 0.0}
    started = time.perf_counter()
    try:
        yield box
    finally:
        box["seconds"] = time.perf_counter() - started


def best_of(run: Callable[[], Any], repeats: int = REPEATS) -> float:
    """Meilleure durée (secondes) de ``run`` sur ``repeats`` exécutions."""
    samples: list[float] = []
    for _ in range(repeats):
        with chrono() as spent:
            run()
        samples.append(spent["seconds"])
    return min(samples)


# --------------------------------------------------------------------------- #
# Failles brutes variées (format ListFindings / FakeSecurityAgentClient)
# --------------------------------------------------------------------------- #
def make_raw_finding(index: int) -> dict[str, Any]:
    """Faille brute « Security Agent » variée et déterministe pour un index donné.

    Sévérité, confiance, type de risque et point d'entrée varient indépendamment ;
    ``entry_point`` porte l'index, ce qui garantit 50 empreintes distinctes.
    """
    return {
        "severity": SEVERITIES[index % len(SEVERITIES)],
        "confidence": CONFIDENCES[(index // 2) % len(CONFIDENCES)],
        "risk_type": RISK_TYPES[index % len(RISK_TYPES)],
        "entry_point": f"/api/v{index % 4}/resource-{index}",
        "parameter": f"param-{index}" if index % 3 == 0 else None,
        "title": f"{RISK_TYPES[index % len(RISK_TYPES)]} sur /api/v{index % 4}",
        "description": f"Étapes de reproduction de la faille {index}.",
    }


@dataclass(frozen=True)
class BatchPlan:
    """Lot de failles brutes et ce que l'intake doit en faire, par construction."""

    raws: list[dict[str, Any]]
    expected_created: int
    expected_duplicates: int
    expected_regressions: int
    distinct_fingerprints: int = field(default=0)


def build_batch(count: int = 50) -> BatchPlan:
    """Lot de ``count`` failles brutes, dont des doublons et une régression.

    Injections volontaires (volumes fixés par construction, donc exacts) :
    - index 5 : doublon interne du lot (même triplet que l'index 4) ;
    - index 10 : doublon d'une faille déjà ouverte en base (``KNOWN_OPEN``) ;
    - index 11 : réapparition d'une faille fermée (``KNOWN_CLOSED``) → régression.
    """
    raws = [make_raw_finding(i) for i in range(count)]
    _clone_triple(raws, source=4, target=5)
    _clone_triple(raws, target=10, triple=KNOWN_OPEN)
    _clone_triple(raws, target=11, triple=KNOWN_CLOSED)
    return BatchPlan(
        raws=raws,
        expected_created=count - 3,
        expected_duplicates=2,
        expected_regressions=1,
        distinct_fingerprints=count - 1,
    )


def _clone_triple(
    raws: list[dict[str, Any]],
    *,
    target: int,
    source: int | None = None,
    triple: tuple[str, str, str | None] | None = None,
) -> None:
    """Donne à ``raws[target]`` le triplet d'identification d'une autre faille."""
    if triple is None:
        assert source is not None
        triple = (
            raws[source]["risk_type"],
            raws[source]["entry_point"],
            raws[source]["parameter"],
        )
    risk_type, entry_point, parameter = triple
    raws[target].update(
        risk_type=risk_type,
        entry_point=entry_point,
        parameter=parameter,
        title=f"{risk_type} sur {entry_point}",
    )


# --------------------------------------------------------------------------- #
# Environnements seedés
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class PerfEnv:
    """Dépôt, client Security Agent et dépendances partagés par un scénario."""

    store: FakeStore
    sa: FakeSecurityAgentClient
    deps: Deps


def build_env() -> PerfEnv:
    """Store vide + client Security Agent fake + ``Deps`` prêtes pour une tâche."""
    store = FakeStore()
    store.save_tenant(make_tenant(TENANT_ID, budget_hours=120.0))
    store.save_application(make_app(APP_ID, TENANT_ID, name="PerfShop", environment="staging"))
    sa = FakeSecurityAgentClient()
    deps = Deps(store=store, sa=sa, github=FakeGitHub())
    deps.settings.github_owner = "acme"
    return PerfEnv(store=store, sa=sa, deps=deps)


def seed_known_finding(
    store: FakeStore,
    triple: tuple[str, str, str | None],
    *,
    finding_id: str,
    status: str,
) -> Finding:
    """Enregistre une faille déjà connue dont l'empreinte est celle de ``triple``."""
    risk_type, entry_point, parameter = triple
    finding = make_finding(
        finding_id,
        APP_ID,
        tenant_id=TENANT_ID,
        status=status,
        created_at="2026-09-01T09:00:00Z",
        closed_at="2026-09-20T09:00:00Z" if status == "closed" else None,
    )
    # make_finding ne connaît que la faille « injection » : on aligne l'identité
    # sur le triplet voulu pour que l'empreinte soit identique à celle de
    # l'intake. L'empreinte est calculée comme en production : sur l'emplacement
    # réel du code (filePath:lignes), pas sur un `entryPoint`/`parameter` que la
    # vraie API ne renvoie pas.
    finding.fingerprint = finding_fingerprint(
        APP_ID,
        {"riskType": risk_type},
        {"codeLocations": [{"filePath": entry_point, "lineStart": 1, "lineEnd": 1}]},
    )
    finding.risk_type = risk_type
    finding.evidence = {"entry_point": entry_point, "parameter": parameter}
    return store.save_finding(finding)


def seed_job(
    sa: FakeSecurityAgentClient, raws: Iterable[dict[str, Any]], job_id: str = JOB_ID
) -> None:
    """Publie les failles brutes dans le job du fake Security Agent."""
    for raw in raws:
        sa.seed_finding(job_id=job_id, **raw)


def seed_triage_env(count: int = 50) -> tuple[PerfEnv, BatchPlan]:
    """Environnement complet : failles connues en base + lot brut dans le job."""
    env = build_env()
    seed_known_finding(env.store, KNOWN_OPEN, finding_id="f-known-open", status="confirmed")
    seed_known_finding(env.store, KNOWN_CLOSED, finding_id="f-known-closed", status="closed")
    seed_known_finding(env.store, KNOWN_CLOSED_PROBE, finding_id="f-probe-closed", status="closed")
    plan = build_batch(count)
    seed_job(env.sa, plan.raws)
    return env, plan


# --------------------------------------------------------------------------- #
# Harnais de mesure de la chaîne de tri (ENF-PERF-01)
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class ChainRun:
    """Une mesure de la chaîne de tri et les objets produits, pour assertions."""

    seconds: float
    phases: dict[str, float]
    env: PerfEnv
    plan: BatchPlan
    intake: dict[str, Any]
    proposals: list[Any]


def triage_findings(
    env: PerfEnv, findings: list[Finding], app: Application, known: list[Finding]
) -> list[Any]:
    """``run_triage`` puis ``enforce`` sur des failles déjà présentes en base."""
    raw = run_triage(
        findings=findings, app=app, known_findings=known, past_decisions=[], deps=env.deps
    )
    return [
        enforce(p, f, app, known_findings=known, store=env.store) for p, f in zip(raw, findings)
    ]


def run_triage_chain(env: PerfEnv) -> tuple[dict[str, Any], list[Any], dict[str, float]]:
    """Chaîne mesurée : ``collect_findings`` → ``run_triage`` → ``enforce``.

    L'environnement est muté (les failles sont écrites en base) : il ne sert
    qu'une fois. Renvoie la sortie d'intake, les propositions durcies et la
    durée de chaque phase.
    """
    with chrono() as intake_phase:
        intake = collect_findings(PAYLOAD, env.deps)
    created = intake["findings_created"]
    findings = [f for f in (env.store.get_finding(fid) for fid in created) if f is not None]
    app = env.store.get_application(APP_ID)
    triaged = {f.finding_id for f in findings}
    known = [
        f
        for f in env.store.list_findings(app_id=APP_ID, limit=1000)
        if f.finding_id not in triaged
    ]
    with chrono() as triage_phase:
        proposals = triage_findings(env, findings, app, known)
    phases = {"intake": intake_phase["seconds"], "triage": triage_phase["seconds"]}
    return intake, proposals, phases


def measure_triage_chain(count: int, repeats: int = REPEATS) -> ChainRun:
    """Mesure la chaîne sur un lot de ``count`` failles, ``repeats`` fois.

    Le seed est refait à chaque tour mais reste hors de la fenêtre de mesure ;
    le meilleur tour est retenu, le dernier tour fournit les objets à vérifier.
    """
    best_seconds = float("inf")
    best_phases: dict[str, float] = {}
    last: ChainRun | None = None
    for _ in range(repeats):
        env, plan = seed_triage_env(count)
        started = time.perf_counter()
        intake, proposals, phases = run_triage_chain(env)
        seconds = time.perf_counter() - started
        last = ChainRun(seconds, phases, env, plan, intake, proposals)
        if seconds < best_seconds:
            best_seconds, best_phases = seconds, phases
    assert last is not None
    return ChainRun(best_seconds, best_phases, last.env, last.plan, last.intake, last.proposals)


# --------------------------------------------------------------------------- #
# Corpus de volume pour les KPI
# --------------------------------------------------------------------------- #
def seed_kpi_corpus(
    store: FakeStore, *, findings: int = FINDINGS, runs: int = RUNS, apps: int = APPS
) -> None:
    """Corpus réaliste : ``apps`` applications, ``runs`` tests, ``findings`` failles."""
    store.save_tenant(make_tenant(TENANT_ID, budget_hours=120.0))
    for i in range(apps):
        store.save_application(
            make_app(
                f"{APP_ID}-{i}",
                TENANT_ID,
                name=f"App {i}",
                environment="staging" if i % 2 == 0 else "production",
            )
        )
    for i in range(runs):
        store.save_run(
            make_run(
                f"run-{i}",
                f"{APP_ID}-{i % apps}",
                tenant_id=TENANT_ID,
                trigger=("cicd", "schedule", "manual", "retest")[i % 4],
                status=("completed", "completed", "blocked", "completed")[i % 4],
                started_at=f"2026-10-{1 + i % 28:02d}T08:00:00Z",
                ended_at=f"2026-10-{1 + i % 28:02d}T09:{i % 60:02d}:00Z",
                duration_s=3600.0 + 60.0 * i,
                task_hours=1.0 + (i % 5) * 0.25,
                cost_usd=50.0 + 25.0 * (i % 4),
            )
        )
    for i in range(findings):
        store.save_finding(_kpi_finding(i, apps))


def _kpi_finding(index: int, apps: int) -> Finding:
    """Faille du corpus : statut, priorité et dates variés mais exactement connus."""
    status = ("closed", "confirmed", "new", "reopened")[index % 4]
    created = f"2026-10-{1 + index % 28:02d}T09:00:00Z"
    closed = None
    if status == "closed":
        closed = f"2026-10-{10 + index % 15:02d}T12:00:00Z"
    finding = make_finding(
        f"f-{index:03d}",
        f"{APP_ID}-{index % apps}",
        tenant_id=TENANT_ID,
        run_id=f"run-{index % 50}",
        priority=("P1", "P2", "P3", "P4")[index % 4],
        status=status,
        created_at=created,
        closed_at=closed,
        due_at=f"2026-10-{15 + index % 12:02d}T09:00:00Z",
        closed_by_run_id=f"run-{index % 50}" if status == "closed" else None,
    )
    return finding


def count_open_by_priority(findings: Iterable[Finding]) -> dict[str, int]:
    """Calcul indépendant (boucle simple) des failles ouvertes par priorité."""
    counts = {"P1": 0, "P2": 0, "P3": 0, "P4": 0}
    for finding in findings:
        if finding.status in _OPEN_STATUSES:
            counts[finding.priority] += 1
    return counts


@pytest.fixture(scope="session", autouse=True)
def warm_optional_imports() -> None:
    """Paye l'import lazy de ``strands`` hors de toute fenêtre de mesure.

    ``run_triage`` teste la présence de Strands à chaque appel
    (``_strands_available``) : le premier appel importe le paquet, ce qui coûte
    plusieurs secondes et n'a rien à voir avec le tri de 50 failles. Sans ce
    préchauffage, la mesure inclurait un coût d'import unique (chiffre relevé
    dans le README).
    """
    with contextlib.suppress(ImportError):
        import strands  # noqa: F401


@pytest.fixture
def kpi_store() -> FakeStore:
    """Dépôt chargé du corpus de volume : 5 applications, 50 runs, 200 failles."""
    store = FakeStore()
    seed_kpi_corpus(store)
    return store
