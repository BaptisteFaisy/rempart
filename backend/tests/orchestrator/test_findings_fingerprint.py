"""D3 — l'empreinte des failles ne doit plus dégénérer (constat du 2026-11-12).

La vraie API `ListFindings` renvoie des `FindingSummary` : ni `entryPoint`, ni
`parameter`, ni `description`. L'empreinte `sha256(app_id:risk_type:entry_point:
:parameter)` tombait donc sur une constante par type de risque : sur 21 failles
réelles distinctes, **3 étaient créées et 18 jetées comme « doublons »** (86 %
de perte silencieuse), et la détection de régression était faussée.

Ces tests rejouent le scénario avec la forme réelle de l'API : un résumé
(`FindingSummary`) et un détail (`Finding`, avec `codeLocations`).
"""

from __future__ import annotations

from rempart.common.fingerprint import finding_fingerprint, finding_location
from rempart.orchestrator.findings_intake import collect_findings
from rempart.orchestrator.task_types import Deps
from tests.fakes_store import FakeStore
from tests.orchestrator.test_tasks import _seed

FINDING_TYPES = ("IDOR", "SQL_INJECTION", "CRYPTOGRAPHIC_VULNERABILITIES")


def _deps(store: FakeStore | None = None) -> Deps:
    """Dépendances d'un test d'intake : tenant + application realistes.

    Le jeu (client + application exposés, données personnelles) est celui des
    autres tests de l'orchestrateur — réutilisé plutôt que recopié.
    """
    from tests.fakes_sa import FakeSecurityAgentClient

    return Deps(store=store or _seed(), sa=FakeSecurityAgentClient())


def _seed_realistic_batch(sa, job_id: str, count: int = 21) -> None:
    """21 failles distinctes, aux formes officielles, réparties sur 3 types."""
    for index in range(count):
        sa.seed_finding(
            job_id,
            severity=("Critical", "High", "Medium")[index % 3],
            confidence=("High", "Medium", "Low")[index % 3],
            risk_type=FINDING_TYPES[index % 3],
            entry_point=f"src/api/handler_{index % 7}.py",
            parameter=f"param_{index}",
            title=f"Vulnérabilité {index} — {FINDING_TYPES[index % 3]}",
            description=f"Détail de la vulnérabilité {index}",
            line_start=10 + index,
            line_end=10 + index,
        )


def test_vingt_et_une_failles_reelles_sont_toutes_conservees():
    """21 failles distinctes → 21 créées, 0 doublon (avant : 3 créées, 18 perdues)."""
    deps = _deps()
    deps.sa.jobs["job-1"] = {"pentestJobId": "job-1", "status": "COMPLETED"}
    _seed_realistic_batch(deps.sa, "job-1")

    out = collect_findings({"app_id": "app-1", "tenant_id": "t-1", "run_id": "job-1"}, deps)

    assert len(out["findings_created"]) == 21
    assert out["duplicates_skipped"] == 0
    stored = deps.store.list_findings(app_id="app-1")
    assert len(stored) == 21
    assert len({f.fingerprint for f in stored}) == 21, "les empreintes doivent être distinctes"


def test_le_rejeu_du_meme_lot_ne_duplique_pas():
    """Même lot rejoué sur un autre run → 0 créée, 21 doublons (déduplication)."""
    deps = _deps()
    deps.sa.jobs["job-1"] = {"pentestJobId": "job-1", "status": "COMPLETED"}
    deps.sa.jobs["job-2"] = {"pentestJobId": "job-2", "status": "COMPLETED"}
    _seed_realistic_batch(deps.sa, "job-1")
    _seed_realistic_batch(deps.sa, "job-2")

    first = collect_findings({"app_id": "app-1", "tenant_id": "t-1", "run_id": "job-1"}, deps)
    second = collect_findings({"app_id": "app-1", "tenant_id": "t-1", "run_id": "job-2"}, deps)

    assert len(first["findings_created"]) == 21
    assert second["findings_created"] == []
    assert second["duplicates_skipped"] == 21


def test_une_faille_fermee_qui_reapparait_est_rouverte_sans_preuve_perimee():
    """La régression garde son comportement : `reopened`, et la preuve effacée."""
    deps = _deps()
    deps.sa.jobs["job-1"] = {"pentestJobId": "job-1", "status": "COMPLETED"}
    _seed_realistic_batch(deps.sa, "job-1")
    first = collect_findings({"app_id": "app-1", "tenant_id": "t-1", "run_id": "job-1"}, deps)

    finding_id = first["findings_created"][0]
    finding = deps.store.get_finding(finding_id)
    finding.status = "closed"
    finding.closed_at = "2026-11-12T10:00:00Z"
    finding.closed_by_run_id = "job-0"
    deps.store.save_finding(finding)

    out = collect_findings({"app_id": "app-1", "tenant_id": "t-1", "run_id": "job-1"}, deps)
    assert out["regressions"] == 1
    reopened = deps.store.get_finding(finding_id)
    assert reopened.status == "reopened"
    assert reopened.closed_by_run_id is None


def test_les_preuves_de_la_faille_sont_conservees_sans_script_d_exploitation():
    """La description et l'emplacement sont gardés ; le script d'attaque, non."""
    deps = _deps()
    deps.sa.jobs["job-1"] = {"pentestJobId": "job-1", "status": "COMPLETED"}
    deps.sa.seed_finding(
        "job-1",
        severity="Critical",
        confidence="High",
        risk_type="IDOR",
        entry_point="src/api/orders.py",
        parameter="id",
        title="IDOR sur les commandes",
        description="Un utilisateur lit les commandes d'un autre.",
    )
    out = collect_findings({"app_id": "app-1", "tenant_id": "t-1", "run_id": "job-1"}, deps)
    finding = deps.store.get_finding(out["findings_created"][0])
    assert finding.evidence["description"].startswith("Un utilisateur")
    assert finding.evidence["code_locations"][0]["file_path"] == "src/api/orders.py"
    assert "attackScript" not in finding.evidence
    assert "verificationScript" not in finding.evidence


def test_lemplacement_privilegie_le_code_puis_le_nom():
    """L'emplacement retenu est le fichier:ligne du détail, sinon le nom."""
    detail = {
        "name": "Titre de la faille",
        "codeLocations": [{"filePath": "src/a.py", "lineStart": 12, "lineEnd": 14}],
    }
    assert finding_location(detail, {"name": "Autre"}) == "src/a.py:12-14"
    assert finding_location({}, {"name": "Titre de la faille"}) == "Titre de la faille"
    assert finding_location({}, {}) == ""


def test_deux_failles_de_meme_type_ont_des_empreintes_differentes():
    """Même type de risque, emplacements différents → empreintes différentes."""
    raw = {"riskType": "IDOR", "name": "Bypass"}
    first = finding_fingerprint(
        "app-1", raw, {"codeLocations": [{"filePath": "a.py", "lineStart": 1}]}
    )
    second = finding_fingerprint(
        "app-1", raw, {"codeLocations": [{"filePath": "b.py", "lineStart": 1}]}
    )
    assert first != second
    # …et stable si l'emplacement ne bouge pas.
    again = finding_fingerprint(
        "app-1", raw, {"codeLocations": [{"filePath": "a.py", "lineStart": 1}]}
    )
    assert first == again
