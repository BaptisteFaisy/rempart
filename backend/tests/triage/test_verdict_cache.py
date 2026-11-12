"""Cache des verdicts du triage (par lot) : économie d'appels au modèle.

Le modèle coûte du temps et de l'argent : un lot déjà trié dans le même
processus (rejeu d'une tâche Step Functions, `dispatch_triage` exécuté deux
fois sur le même run) doit être réutilisé sans rappeler le LLM. Ces tests
n'appellent JAMAIS un vrai modèle.
"""

from __future__ import annotations

from rempart.common.models import Application, Finding
from rempart.triage import verdict_cache
from rempart.triage.agent import run_triage
from rempart.triage.proposal import TriageProposal


def _finding(fingerprint: str, severity: str = "High") -> Finding:
    return Finding(
        finding_id=f"f-{fingerprint}", app_id="app-1", tenant_id="t-1",
        run_id="run-1", fingerprint=fingerprint, title=f"Faille {fingerprint}",
        risk_type="IDOR", severity=severity, confidence="High", priority="P1",
        status="new", due_at=None, ticket_url=None, remediation_pr_url=None,
        evidence={"description": "d"}, cvss={},
        created_at="2026-11-12T10:00:00Z", updated_at="2026-11-12T10:00:00Z",
        closed_at=None, closed_by_run_id=None,
    )


def _app() -> Application:
    return Application(
        app_id="app-1", tenant_id="t-1", name="App", criticality="high",
        internet_exposed=True, data_types=["personal"], environment="production",
        agent_space_id="space-1", domains=[], repositories=[], team="",
        ticket_channel="github", context={}, created_at="2026-11-01T00:00:00Z",
    )


def test_le_cache_est_vide_puis_rempli():
    verdict_cache.reset()
    assert verdict_cache.get_batch(["fp-1"]) is None
    proposal = TriageProposal(
        finding_id="f-fp-1", duplicate_of=None, is_regression=False,
        proposed_status="CONFIRMED", priority="P1", plain_summary="s",
        technical_summary="t", references=[], justification="j",
        needs_human_validation=True, source="model",
    )
    verdict_cache.put_batch(["fp-1"], [proposal])
    cached = verdict_cache.get_batch(["fp-1"])
    assert cached is not None and cached[0].source == "model"


def test_une_copie_est_renvoyee_et_non_la_reference_interne():
    """Le cache ne peut pas être corrompu par l'appelant."""
    verdict_cache.reset()
    proposal = TriageProposal(
        finding_id="f-x", duplicate_of=None, is_regression=False,
        proposed_status="CONFIRMED", priority="P1", plain_summary="s",
        technical_summary="t", references=[], justification="j",
        needs_human_validation=True,
    )
    verdict_cache.put_batch(["fp-a"], [proposal])
    first = verdict_cache.get_batch(["fp-a"])[0]
    first.proposed_status = "TO_VERIFY"
    second = verdict_cache.get_batch(["fp-a"])[0]
    assert second.proposed_status == "CONFIRMED"


def test_le_trie_deterministe_n_utilise_pas_le_cache():
    """Le règleur est instantané et déterministe : pas de cache nécessaire.

    On vérifie seulement que le cache ne fausse pas le résultat : deux appels
    successifs sans modèle renvoient des verdicts identiques (traçabilité
    déterministe).
    """
    verdict_cache.reset()
    findings = [_finding("fp-1")]
    first = run_triage(
        findings=findings, app=_app(), known_findings=[], past_decisions=[],
        deps=None, model_client=None,
    )
    second = run_triage(
        findings=findings, app=_app(), known_findings=[], past_decisions=[],
        deps=None, model_client=None,
    )
    assert first[0].to_dict() == second[0].to_dict()
