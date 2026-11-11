"""Tests EF-TRI-09 : mémoire des décisions de l'analyste par application (chapitre 12.5).

Couvre : réutilisation d'un faux positif / d'une confirmation, la décision la
plus récente l'emporte, garde-fou ENF-IA-02 (Critical/High jamais écartées
automatiquement), priorité inchangée (ENF-IA-01), isolement par application,
décisions humaines uniquement, lecture depuis le store, et le filtre par
empreinte de ``get_past_decisions``.
"""

from typing import Any

import pytest

from rempart.common.models import Application, Decision, Finding
from rempart.triage.agent import run_triage
from rempart.triage.guardrails import compute_finding_priority
from rempart.triage.memory import memory_match
from rempart.triage.tools import TriageContext, get_past_decisions
from tests.fakes import FakeStore


class _FakeDeps:
    def __init__(self, store: FakeStore) -> None:
        self.store = store


def _app(app_id: str = "app-1") -> Application:
    return Application(
        app_id=app_id,
        tenant_id="tenant-a",
        name="ShopLite",
        criticality="high",
        internet_exposed=True,
        data_types=["none"],
        environment="staging",
        agent_space_id="space-1",
        domains=["shop.example.com"],
        repositories=["org/shoplite"],
        team="checkout",
        ticket_channel="github",
        context={},
        created_at="2026-11-10T10:00:00Z",
    )


def _finding(
    fid: str,
    *,
    app_id: str = "app-1",
    severity: str = "Medium",
    confidence: str = "High",
    fingerprint: str = "fp-1",
    status: str = "new",
) -> Finding:
    return Finding(
        finding_id=fid,
        app_id=app_id,
        tenant_id="tenant-a",
        run_id="run-1",
        fingerprint=fingerprint,
        title=f"Issue {fid}",
        risk_type="IDOR",
        severity=severity,
        confidence=confidence,
        priority="P4",
        status=status,
        due_at=None,
        ticket_url=None,
        remediation_pr_url=None,
        evidence={"entry_point": "/orders/{id}"},
        cvss={},
        created_at="2026-11-10T10:00:00Z",
        updated_at="2026-11-10T10:00:00Z",
        closed_at=None,
        closed_by_run_id=None,
    )


def _decision(
    did: str,
    fid: str,
    action: str,
    *,
    author: str = "alice@msp",
    author_type: str = "human",
    justification: str = "Vu en réunion de tri",
    created_at: str = "2026-10-01T09:00:00Z",
) -> Decision:
    return Decision(
        decision_id=did,
        finding_id=fid,
        author_type=author_type,
        author=author,
        action=action,
        justification=justification,
        created_at=created_at,
    )


def _triage_one(
    finding: Finding,
    app: Application,
    known: list[Finding],
    decisions: list[Decision],
    store: Any = None,
) -> Any:
    deps = _FakeDeps(store) if store is not None else None
    return run_triage(
        findings=[finding],
        app=app,
        known_findings=known,
        past_decisions=decisions,
        deps=deps,
    )[0]


def test_memory_reuses_false_positive_decision() -> None:
    """Une faille déjà jugée faux positif par un humain → LIKELY_FALSE_POSITIVE justifié."""
    app = _app()
    known = _finding("f-old", status="false_positive")
    dec = _decision(
        "d-1",
        "f-old",
        "false_positive",
        author="alice@msp",
        justification="Endpoint interne derrière WAF",
        created_at="2026-10-01T09:00:00Z",
    )
    prop = _triage_one(_finding("f-new"), app, [known], [dec])

    assert prop.proposed_status == "LIKELY_FALSE_POSITIVE"
    assert prop.needs_human_validation is False
    assert "EF-TRI-09" in prop.justification
    assert "alice@msp" in prop.justification
    assert "2026-10-01T09:00:00Z" in prop.justification
    assert "Endpoint interne derrière WAF" in prop.justification


def test_memory_reuses_confirmed_decision() -> None:
    """Une faille déjà confirmée par un humain → CONFIRMED avec citation de la décision."""
    app = _app()
    known = _finding("f-old", status="confirmed")
    dec = _decision(
        "d-1",
        "f-old",
        "confirmed",
        author="bob@msp",
        justification="Exploit reproduit en staging",
        created_at="2026-10-02T14:30:00Z",
    )
    prop = _triage_one(_finding("f-new"), app, [known], [dec])

    assert prop.proposed_status == "CONFIRMED"
    assert "EF-TRI-09" in prop.justification
    assert "bob@msp" in prop.justification
    assert "2026-10-02T14:30:00Z" in prop.justification
    assert "Exploit reproduit en staging" in prop.justification


@pytest.mark.parametrize(
    ("old_action", "new_action", "expected"),
    [
        ("false_positive", "confirmed", "CONFIRMED"),
        ("confirmed", "false_positive", "LIKELY_FALSE_POSITIVE"),
    ],
)
@pytest.mark.parametrize("reversed_list", [False, True])
def test_latest_human_decision_wins(
    old_action: str, new_action: str, expected: str, reversed_list: bool
) -> None:
    """La décision la plus récente l'emporte, quel que soit l'ordre de la liste."""
    app = _app()
    known = _finding("f-old", status="false_positive")
    old = _decision("d-old", "f-old", old_action, author="old@msp",
                    created_at="2026-09-01T09:00:00Z")
    new = _decision("d-new", "f-old", new_action, author="new@msp",
                    created_at="2026-11-01T09:00:00Z")
    decisions = [new, old] if reversed_list else [old, new]

    prop = _triage_one(_finding("f-new"), app, [known], decisions)

    assert prop.proposed_status == expected
    assert "new@msp" in prop.justification
    assert "old@msp" not in prop.justification


@pytest.mark.parametrize("severity", ["Critical", "High"])
def test_memory_cannot_dismiss_critical_or_high_finding(severity: str) -> None:
    """ENF-IA-02 : la mémoire n'écarte jamais automatiquement une faille critique/élevée."""
    app = _app()
    known = _finding("f-old", severity=severity, status="false_positive")
    dec = _decision("d-1", "f-old", "false_positive", justification="Faux positif historique")
    prop = _triage_one(_finding("f-new", severity=severity), app, [known], [dec])

    assert prop.needs_human_validation is True
    assert prop.proposed_status != "LIKELY_FALSE_POSITIVE"
    assert prop.proposed_status == "TO_VERIFY"  # garde-fou chapitre 12.4


def test_memory_never_changes_priority() -> None:
    """ENF-IA-01 : la priorité vient toujours de la matrice, mémoire ou pas."""
    app = _app()
    finding = _finding("f-new", severity="High", confidence="High")
    expected = compute_finding_priority(finding, app).priority

    without = _triage_one(finding, app, [], [])
    known = _finding("f-old", severity="High", status="false_positive")
    dec = _decision("d-1", "f-old", "false_positive")
    with_memory = _triage_one(finding, app, [known], [dec])

    assert expected == "P1"
    assert without.priority == expected
    assert with_memory.priority == expected


def test_memory_isolated_per_application() -> None:
    """Une décision de l'app A sur la même empreinte ne fuit pas vers l'app B."""
    app_b = _app("app-2")
    known_a = _finding("f-old-a", app_id="app-1", status="false_positive")
    dec_a = _decision("d-1", "f-old-a", "false_positive", author="alice@msp")

    prop = _triage_one(_finding("f-new-b", app_id="app-2"), app_b, [known_a], [dec_a])

    assert prop.proposed_status == "CONFIRMED"
    assert "EF-TRI-09" not in prop.justification
    assert "alice@msp" not in prop.justification


def test_memory_isolated_per_application_via_store() -> None:
    """Même isolement quand les failles et décisions viennent du store."""
    store = FakeStore()
    store.save_finding(_finding("f-old-a", app_id="app-1", status="false_positive"))
    store.save_decision(_decision("d-1", "f-old-a", "false_positive"))

    prop = _triage_one(_finding("f-new-b", app_id="app-2"), _app("app-2"), [], [], store=store)

    assert prop.proposed_status == "CONFIRMED"
    assert "EF-TRI-09" not in prop.justification


def test_only_human_decisions_are_reused() -> None:
    """Une décision de l'agent (author_type != human) n'alimente pas la mémoire."""
    app = _app()
    known = _finding("f-old", status="confirmed")
    dec = _decision("d-1", "f-old", "false_positive", author_type="agent", author="triage-agent")

    prop = _triage_one(_finding("f-new"), app, [known], [dec])

    assert prop.proposed_status == "CONFIRMED"
    assert "EF-TRI-09" not in prop.justification
    assert "triage-agent" not in prop.justification
    match = memory_match(_finding("f-new"), known_findings=[known], past_decisions=[dec])
    assert match is None


def test_latest_unmapped_action_disables_memory() -> None:
    """Si la dernière décision humaine n'est pas réutilisable, aucune mémoire n'est proposée."""
    app = _app()
    known = _finding("f-old", status="risk_accepted")
    old = _decision("d-old", "f-old", "false_positive", created_at="2026-09-01T09:00:00Z")
    new = _decision("d-new", "f-old", "risk_accepted", created_at="2026-11-01T09:00:00Z")

    match = memory_match(_finding("f-new"), known_findings=[known], past_decisions=[old, new])
    assert match is None

    prop = _triage_one(_finding("f-new"), app, [known], [old, new])
    assert prop.proposed_status == "CONFIRMED"
    assert "EF-TRI-09" not in prop.justification


def test_memory_reads_decisions_from_store() -> None:
    """La mémoire retrouve une décision humaine stockée, sans past_decisions en mémoire vive."""
    store = FakeStore()
    store.save_finding(_finding("f-old", status="false_positive"))
    store.save_decision(_decision("d-1", "f-old", "false_positive", author="carol@msp"))

    prop = _triage_one(_finding("f-new"), _app(), [], [], store=store)

    assert prop.proposed_status == "LIKELY_FALSE_POSITIVE"
    assert "carol@msp" in prop.justification


def test_get_past_decisions_fingerprint_filter() -> None:
    """get_past_decisions(fingerprint=...) ne renvoie que les décisions de cette empreinte."""
    store = FakeStore()
    known_same = _finding("f-same", fingerprint="fp-1", status="false_positive")
    known_other = _finding("f-other", fingerprint="fp-2", status="confirmed")
    dec_same_list = _decision("d-1", "f-same", "false_positive")
    dec_other_list = _decision("d-2", "f-other", "confirmed")
    dec_same_store = _decision("d-3", "f-same", "confirmed", created_at="2026-11-02T09:00:00Z")
    store.save_decision(dec_same_store)

    ctx = TriageContext(
        store=store,
        app=_app(),
        findings=[_finding("f-new")],
        known_findings=[known_same, known_other],
        past_decisions=[dec_same_list, dec_other_list],
    )

    all_ids = {d["decision_id"] for d in get_past_decisions(ctx, "app-1")}
    assert all_ids == {"d-1", "d-2", "d-3"}

    fp1 = get_past_decisions(ctx, "app-1", fingerprint="fp-1")
    assert {d["decision_id"] for d in fp1} == {"d-1", "d-3"}

    assert get_past_decisions(ctx, "app-1", fingerprint="fp-unknown") == []
