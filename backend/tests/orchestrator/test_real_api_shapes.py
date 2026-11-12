"""Conformité des doubles au modèle officiel de l'API `securityagent`.

Garde-fou anti-récidive de l'incident du 2026-11-12 : `FakeSecurityAgentClient`
renvoyait `taskHours` sur la vue d'un job, un champ que le modèle officiel ne
déclare **pas** sur `PentestJob`. Le code de production lisait donc un champ que
la vraie API n'envoie jamais, et tous les tests passaient.

La référence est la fixture `tests/fixtures/securityagent_shapes.json`, extrait
figé du modèle botocore officiel (AWS CLI v2, service `securityagent`, version
2025-09-06) : la CI n'a pas l'AWS CLI, mais le contrat doit rester opposable.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.fakes_sa import FakeSecurityAgentClient

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "securityagent_shapes.json"
SHAPES = json.loads(FIXTURE.read_text(encoding="utf-8"))["shapes"]


def allowed_fields(shape_name: str) -> set[str]:
    """Champs déclarés par le modèle officiel pour une forme donnée."""
    return set(SHAPES[shape_name])


@pytest.mark.parametrize(
    "shape_name,produce",
    [
        ("PentestJob", lambda sa: sa.batch_get_pentest_jobs("space-1", ["job-1"])),
        ("TaskSummary", lambda sa: sa.list_pentest_job_tasks("space-1", "job-1")),
        ("StartPentestJobOutput", lambda sa: sa.start_pentest_job("space-1", "pt-1")),
    ],
)
def test_le_double_ne_renvoie_que_des_champs_officiels(shape_name, produce):
    """Aucun champ inventé : sinon le code lit des données qui n'existent pas."""
    sa = FakeSecurityAgentClient()
    sa.jobs["job-1"] = {"pentestJobId": "job-1", "pentestId": "pt-1", "status": "COMPLETED"}
    result = produce(sa)
    rows = result if isinstance(result, list) else [result]
    assert rows, "le double doit renvoyer au moins une ligne pour ce test"
    for row in rows:
        invented = set(row) - allowed_fields(shape_name)
        assert not invented, f"{shape_name} : champs absents du modèle officiel {sorted(invented)}"


def test_pentest_job_ne_porte_pas_les_heures_consommees():
    """Rappel du contrat : `PentestJob` n'a que `maxTaskHours`, jamais `taskHours`."""
    assert "taskHours" not in allowed_fields("PentestJob")
    assert "maxTaskHours" in allowed_fields("PentestJob")
    assert "taskHours" in allowed_fields("TaskSummary")


@pytest.mark.xfail(
    reason="D3 ouvert : la vraie API ListFindings renvoie des FindingSummary sans "
    "entryPoint/parameter/description, que le double invente encore (empreinte "
    "dégénérée : 18 failles réelles sur 21 avalées comme doublons).",
    strict=False,
)
def test_list_findings_ne_renvoie_que_des_champs_officiels():
    sa = FakeSecurityAgentClient()
    sa.add_finding(
        "job-1",
        severity="High",
        confidence="High",
        risk_type="SQL_INJECTION",
        entry_point="/orders/{id}",
    )
    rows = sa.list_findings("space-1", pentest_job_id="job-1")
    assert rows
    for row in rows:
        assert not set(row) - allowed_fields("FindingSummary")
