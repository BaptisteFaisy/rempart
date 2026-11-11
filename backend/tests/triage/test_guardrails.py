"""Tests for deterministic triage guardrails (R5, R7, chapter 12.4)."""

import logging

import pytest

from rempart.common.models import Application, Finding
from rempart.triage.guardrails import enforce
from rempart.triage.proposal import TriageProposal
from tests.fakes import FakeStore


def _app(
    *,
    criticality: str = "high",
    internet_exposed: bool = True,
    data_types: list[str] | None = None,
) -> Application:
    return Application(
        app_id="app-1",
        tenant_id="tenant-a",
        name="ShopLite",
        criticality=criticality,
        internet_exposed=internet_exposed,
        data_types=data_types if data_types is not None else ["none"],
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
    fid: str = "f-1",
    *,
    severity: str = "High",
    confidence: str = "High",
    fingerprint: str = "fp-1234",
    status: str = "new",
) -> Finding:
    return Finding(
        finding_id=fid,
        app_id="app-1",
        tenant_id="tenant-a",
        run_id="run-1",
        fingerprint=fingerprint,
        title="IDOR on orders",
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


def _proposal(
    fid: str = "f-1",
    *,
    priority: str = "P1",
    status: str = "CONFIRMED",
    needs_human: bool = False,
    is_regression: bool = False,
) -> TriageProposal:
    return TriageProposal(
        finding_id=fid,
        duplicate_of=None,
        is_regression=is_regression,
        proposed_status=status,
        priority=priority,
        plain_summary="Plain summary.",
        technical_summary="Tech summary.",
        references=["CWE-639"],
        justification="Reasoning.",
        needs_human_validation=needs_human,
    )


def test_priority_matrix_overrides_divergent_model_priority(
    caplog: pytest.LogCaptureFixture,
) -> None:
    app = _app(criticality="high", internet_exposed=True, data_types=["personal"])
    finding = _finding(severity="Critical", confidence="High")
    # Model wrongly proposed P4
    prop = _proposal(priority="P4", status="CONFIRMED")

    with caplog.at_level(logging.WARNING):
        res = enforce(prop, finding, app)

    assert res.priority == "P1"
    assert any("P4" in rec.message and "P1" in rec.message for rec in caplog.records)


@pytest.mark.parametrize("severity", ["Critical", "High"])
def test_high_severity_false_positive_requires_human(severity: str) -> None:
    """R5 / EF-TRI-05 / ENF-IA-02: Critical/High cannot be auto-dismissed as false positive."""
    app = _app(criticality="low", internet_exposed=False, data_types=["none"])
    finding = _finding(severity=severity, confidence="High")
    prop = _proposal(priority="P2", status="LIKELY_FALSE_POSITIVE", needs_human=False)

    res = enforce(prop, finding, app)

    assert res.proposed_status == "TO_VERIFY"
    assert res.needs_human_validation is True


def test_low_severity_false_positive_is_preserved() -> None:
    app = _app(criticality="low", internet_exposed=False, data_types=["none"])
    finding = _finding(severity="Low", confidence="Low")
    prop = _proposal(priority="P4", status="LIKELY_FALSE_POSITIVE", needs_human=False)

    res = enforce(prop, finding, app)

    assert res.proposed_status == "LIKELY_FALSE_POSITIVE"
    assert res.needs_human_validation is False
    assert res.priority == "P4"


def test_detect_regression_on_closed_fingerprint() -> None:
    """R7: Matching a closed finding's fingerprint sets is_regression=True."""
    app = _app()
    closed_prev = _finding("f-prev", fingerprint="fp-abc", status="closed")
    new_finding = _finding("f-new", fingerprint="fp-abc", status="new")
    prop = _proposal("f-new", priority="P1", is_regression=False)

    res = enforce(prop, new_finding, app, known_findings=[closed_prev])
    assert res.is_regression is True


def test_detect_regression_via_store() -> None:
    app = _app()
    store = FakeStore()
    closed_prev = _finding("f-prev", fingerprint="fp-xyz", status="closed")
    store.save_finding(closed_prev)

    new_finding = _finding("f-new", fingerprint="fp-xyz", status="new")
    prop = _proposal("f-new", priority="P1", is_regression=False)

    res = enforce(prop, new_finding, app, store=store)
    assert res.is_regression is True
