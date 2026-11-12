"""Le jeu figé de la démo EST le résultat du code de production.

Ces tests verrouillent la promesse « l'environnement de démonstration montre de
vraies données » : le fichier `demo/seed/demo-dataset.json` doit être
BYTE-pour-BYTE reproductible par `scripts/seed_demo.py` (qui le calcule avec
`rempart.reports.*` — le code réellement déployé). S'il dérive, c'est que
quelqu'un l'a édité à la main, ou que le code de production a changé sans
régénérer la démo.

Avant le 12/11/2026, le jeu n'avait AUCUNE collection de gouvernance : les
pages Audit / Evidence / Industrialization / Policy / Forecast du portail en
mode démo affichaient « not available in the frozen dataset ». Depuis, ces
collections sont calculées par le code de production sur le même jeu — dont un
dossier de preuves réellement scellé, dont l'empreinte se recalcule.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "scripts"))

from seed_demo import build_dataset  # noqa: E402

DATASET = ROOT / "demo" / "seed" / "demo-dataset.json"


def _canonical(dataset: dict) -> str:
    return json.dumps(dataset, indent=2, ensure_ascii=False, sort_keys=True)


def _committed() -> dict:
    return json.loads(DATASET.read_text(encoding="utf-8"))


def test_le_jeu_commite_est_reproductible_a_l_octet_pres():
    """`seed_demo.build_dataset()` doit reproduire EXACTEMENT le fichier committé."""
    rebuilt = build_dataset()
    assert _canonical(rebuilt) == _canonical(_committed()), (
        "le jeu figé a dérivé du code de production — relancez "
        "`python3 scripts/seed_demo.py --json demo/seed/demo-dataset.json`"
    )


def test_les_collections_de_gouvernance_sont_presentes():
    dataset = _committed()
    for key in ("audit", "evidence", "industrialization", "forecast", "policy", "policy_defaults"):
        assert key in dataset, f"collection manquante : {key}"
        assert len(dataset[key]) > 0, f"collection vide : {key}"


def test_le_dossier_de_preuves_porte_une_empreinte_recalculable():
    """La promesse centrale de la page « Evidence Dossier » tient en démo aussi."""
    for row in _committed()["evidence"]:
        pack = row["pack"]
        digest = pack["integrity"]["digest"]
        assert len(digest) == 64
        payload = {k: v for k, v in pack.items() if k not in ("integrity", "s3_key")}
        canonical = json.dumps(
            payload, indent=2, sort_keys=True, ensure_ascii=False, default=str
        )
        assert hashlib.sha256(canonical.encode("utf-8")).hexdigest() == digest


def test_la_prevision_est_coherente_avec_la_periode():
    """Octobre 2026 : 31 jours écoulés, projection = heures réellement consommées.

    Régressions ciblées : le bug qui comptait 43 jours écoulés (heure courante
    au lieu de la fin de période) est verrouillé par ce test.
    """
    forecast = _committed()["forecast"][0]["forecast"]
    assert forecast["period"] == "2026-10"
    assert forecast["days_elapsed"] == forecast["days_in_month"] == 31
    assert forecast["projected_hours"] == forecast["hours_used"] == 5.4
    assert forecast["projected_cost_usd"] == 270.0


def test_le_journal_d_audit_reprend_les_actions_reelles_de_la_plateforme():
    """Les mêmes chaînes d'action que le code de production tracerait."""
    actions = {event["action"] for event in _committed()["audit"]}
    assert {"tenant.create", "application.create", "run.start",
            "finding.decision", "report.create"} <= actions, actions


def test_les_identifiants_d_audit_sont_stables():
    """Pas d'uuid aléatoire : le jeu doit être reproductible à l'octet près."""
    ids = [event["audit_id"] for event in _committed()["audit"]]
    assert all(i.startswith("audit-demo-") for i in ids), ids
