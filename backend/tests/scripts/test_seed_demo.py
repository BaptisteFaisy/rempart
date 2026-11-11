"""Tests du jeu de données de démonstration figé (scripts/seed_demo.py).

Ce jeu est ce qui permet de montrer le portail aux juges sans lancer un seul
test réel — voir docs/free-tier-runbook.md, option A.
"""

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DATASET_PATH = ROOT / "demo" / "seed" / "demo-dataset.json"

# Le script vit hors du package `rempart` : chargement par chemin explicite.
_spec = importlib.util.spec_from_file_location(
    "seed_demo", ROOT / "scripts" / "seed_demo.py"
)
assert _spec and _spec.loader
seed_demo = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(seed_demo)
build_dataset = seed_demo.build_dataset
summarise = seed_demo.summarise


def test_dataset_has_the_two_demo_tenants():
    dataset = build_dataset()
    ids = {t["tenant_id"] for t in dataset["tenants"]}
    assert ids == {"demo-a", "demo-b"}
    # Les deux sont en mandat valide mais free tier NON confirmé : le
    # garde-fou anti-facture reste actif sur le jeu de démonstration.
    assert all(t["mandate_status"] == "valid" for t in dataset["tenants"])
    assert all(t["free_tier_confirmed"] is False for t in dataset["tenants"])


def test_dataset_covers_the_finding_lifecycle():
    dataset = build_dataset()
    statuses = {f["status"] for f in dataset["findings"]}
    # Au moins : une faille fermée avec preuve, une en correction, une en
    # attente de validation humaine, une nouvelle.
    assert {"closed", "in_remediation", "pending_validation", "new"} <= statuses


def test_closed_findings_carry_proof():
    dataset = build_dataset()
    for finding in dataset["findings"]:
        if finding["status"] == "closed":
            assert finding["closed_by_run_id"], "une fermeture sans preuve"
            assert finding["closed_at"]


def test_priorities_come_from_the_matrix():
    """La priorité du jeu est celle de la matrice déterministe (ENF-IA-01)."""
    from rempart.common.priority import compute_priority

    dataset = build_dataset()
    apps = {a["app_id"]: a for a in dataset["applications"]}
    for finding in dataset["findings"]:
        app = apps[finding["app_id"]]
        expected = compute_priority(
            finding["severity"],
            finding["confidence"],
            exposed_critical=app["internet_exposed"] and app["criticality"] == "high",
            sensitive_data=any(
                d in ("personal", "payment", "health") for d in app["data_types"]
            ),
        )
        assert finding["priority"] == expected.priority


def test_every_finding_below_high_severity_has_a_human_decision():
    dataset = build_dataset()
    decided = {d["finding_id"] for d in dataset["decisions"]
               if d["author_type"] == "human"}
    for finding in dataset["findings"]:
        if finding["status"] != "new":
            assert finding["finding_id"] in decided


def test_committed_dataset_matches_the_generator():
    """Le JSON versionné est bien produit par le générateur (pas de dérive)."""
    assert DATASET_PATH.exists(), "demo/seed/demo-dataset.json absent du dépôt"
    committed = json.loads(DATASET_PATH.read_text())
    assert committed == build_dataset()


def test_summarise_lists_every_collection():
    text = summarise(build_dataset())
    for key in ("tenants", "findings", "runs", "reports"):
        assert key in text


def test_script_runs_standalone():
    """`--print` ne doit rien écrire et sortir en 0 (utilisable en CI)."""
    proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "seed_demo.py"), "--print"],
        capture_output=True, text=True, timeout=60,
    )
    assert proc.returncode == 0, proc.stderr
    assert "tenants" in proc.stdout
