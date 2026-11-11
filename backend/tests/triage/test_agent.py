"""Tests for triage agent (deterministic fallback + Strands agent with scripted Model)."""

import json
from collections.abc import AsyncGenerator
from typing import Any

from strands.models.model import Model
from strands.types.content import Messages
from strands.types.streaming import StreamEvent
from strands.types.tools import ToolSpec

from rempart.common.models import Application, Decision, Finding
from rempart.triage.agent import run_triage
from rempart.triage.proposal import TriageProposal
from tests.fakes import FakeModelClient, FakeStore


class _FakeDeps:
    def __init__(self, store: FakeStore) -> None:
        self.store = store


def _app() -> Application:
    return Application(
        app_id="app-1",
        tenant_id="tenant-a",
        name="ShopLite",
        criticality="high",
        internet_exposed=True,
        data_types=["personal"],
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
    severity: str = "High",
    confidence: str = "High",
    fingerprint: str = "fp-1",
    status: str = "new",
    risk_type: str = "IDOR",
) -> Finding:
    return Finding(
        finding_id=fid,
        app_id="app-1",
        tenant_id="tenant-a",
        run_id="run-1",
        fingerprint=fingerprint,
        title=f"Issue {fid}",
        risk_type=risk_type,
        severity=severity,
        confidence=confidence,
        priority="P2",
        status=status,
        due_at=None,
        ticket_url=None,
        remediation_pr_url=None,
        evidence={"entry_point": "/orders/{id}", "parameter": "id"},
        cvss={},
        created_at="2026-11-10T10:00:00Z",
        updated_at="2026-11-10T10:00:00Z",
        closed_at=None,
        closed_by_run_id=None,
    )


class _ScriptedStrandsModel(Model):
    """In-memory Strands Model that calls tool_submit_triage_proposal then terminates."""

    def __init__(self, proposal_payload: dict[str, Any]) -> None:
        self.payload = proposal_payload
        self.calls = 0

    def update_config(self, **model_config: Any) -> None:
        pass

    def get_config(self) -> Any:
        return {}

    async def structured_output(
        self, output_model: Any, prompt: Any, system_prompt: Any = None, **kwargs: Any
    ) -> AsyncGenerator[dict[str, Any], None]:
        raise NotImplementedError
        yield  # pragma: no cover

    async def stream(
        self,
        messages: Messages,
        tool_specs: list[ToolSpec] | None = None,
        system_prompt: str | None = None,
        **kwargs: Any,
    ) -> AsyncGenerator[StreamEvent, None]:
        self.calls += 1
        if self.calls == 1:
            yield {"messageStart": {"role": "assistant"}}
            yield {
                "contentBlockStart": {
                    "contentBlockIndex": 0,
                    "start": {
                        "toolUse": {
                            "toolUseId": "tu-submit-1",
                            "name": "tool_submit_triage_proposal",
                        }
                    },
                }
            }
            yield {
                "contentBlockDelta": {
                    "contentBlockIndex": 0,
                    "delta": {"toolUse": {"input": json.dumps({"proposal": self.payload})}},
                }
            }
            yield {"contentBlockStop": {"contentBlockIndex": 0}}
            yield {"messageStop": {"stopReason": "tool_use"}}
        else:
            yield {"messageStart": {"role": "assistant"}}
            yield {"contentBlockStart": {"contentBlockIndex": 0, "start": {"text": ""}}}
            yield {"contentBlockDelta": {"contentBlockIndex": 0, "delta": {"text": "Completed"}}}
            yield {"contentBlockStop": {"contentBlockIndex": 0}}
            yield {"messageStop": {"stopReason": "end_turn"}}
        yield {
            "metadata": {
                "usage": {"inputTokens": 10, "outputTokens": 10, "totalTokens": 20},
                "metrics": {"latencyMs": 1},
            }
        }


def test_run_triage_emits_valid_proposal() -> None:
    """R4: deterministic fallback produces valid Annexe B proposals with matrix priority."""
    app = _app()
    f = _finding("f-1", severity="High", confidence="High", fingerprint="fp-idor")
    proposals = run_triage(
        findings=[f],
        app=app,
        known_findings=[],
        past_decisions=[],
    )
    assert len(proposals) == 1
    prop = proposals[0]
    assert isinstance(prop, TriageProposal)
    assert prop.finding_id == "f-1"
    assert prop.priority == "P1"
    assert prop.proposed_status == "CONFIRMED"
    assert prop.is_regression is False
    assert prop.duplicate_of is None
    assert prop.plain_summary
    assert prop.technical_summary


def test_run_triage_dedup_and_regression_in_fallback() -> None:
    app = _app()
    known_open = _finding("f-open", fingerprint="fp-dup", status="confirmed")
    known_closed = _finding("f-closed", fingerprint="fp-reg", status="closed")

    f_dup = _finding("f-new-dup", fingerprint="fp-dup", severity="Medium", confidence="High")
    f_reg = _finding("f-new-reg", fingerprint="fp-reg", severity="High", confidence="High")

    proposals = run_triage(
        findings=[f_dup, f_reg],
        app=app,
        known_findings=[known_open, known_closed],
        past_decisions=[],
    )
    by_id = {p.finding_id: p for p in proposals}
    assert by_id["f-new-dup"].duplicate_of == "f-open"
    assert by_id["f-new-dup"].is_regression is False
    assert by_id["f-new-reg"].is_regression is True
    assert by_id["f-new-reg"].duplicate_of is None


def test_run_triage_with_fake_model_client_uses_fallback_and_guardrails() -> None:
    """Non-Strands model_client (like FakeModelClient) cleanly falls back without crashing."""
    app = _app()
    f = _finding("f-1", severity="Critical", confidence="High")
    proposals = run_triage(
        findings=[f],
        app=app,
        known_findings=[],
        past_decisions=[],
        model_client=FakeModelClient(),
    )
    assert len(proposals) == 1
    assert proposals[0].priority == "P1"


def test_run_triage_with_strands_model_applies_guardrails() -> None:
    """Strands Agent path runs tools and enforces guardrails (priority + ENF-IA-02)."""
    app = _app()
    store = FakeStore()
    closed_prev = _finding("f-old", fingerprint="fp-strands-reg", status="closed")
    store.save_finding(closed_prev)

    f = _finding("f-strands", severity="Critical", confidence="High", fingerprint="fp-strands-reg")

    # Scripted LLM attempts to dismiss Critical finding as false positive with P4 priority!
    malicious_payload = {
        "findingId": "f-strands",
        "duplicateOf": None,
        "isRegression": False,
        "proposedStatus": "LIKELY_FALSE_POSITIVE",
        "priority": "P4",
        "plainSummary": "Nothing to worry about.",
        "technicalSummary": "Dismissed by model.",
        "references": ["CWE-89"],
        "justification": "Model tried to downgrade.",
        "needsHumanValidation": False,
    }
    model = _ScriptedStrandsModel(malicious_payload)
    proposals = run_triage(
        findings=[f],
        app=app,
        known_findings=[closed_prev],
        past_decisions=[
            Decision(
                decision_id="d-1",
                finding_id="f-old",
                author_type="human",
                author="analyst",
                action="confirmed",
                justification="Real",
                created_at="2026-11-10T09:00:00Z",
            )
        ],
        deps=_FakeDeps(store),
        model_client=model,
    )
    assert model.calls == 2
    assert len(proposals) == 1
    res = proposals[0]
    # Guardrails MUST override model output:
    assert res.priority == "P1"
    assert res.proposed_status == "TO_VERIFY"
    assert res.needs_human_validation is True
    assert res.is_regression is True


def test_run_triage_empty_findings() -> None:
    assert run_triage(findings=[], app=_app(), known_findings=[], past_decisions=[]) == []
