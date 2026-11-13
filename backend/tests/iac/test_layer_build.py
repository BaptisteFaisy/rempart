"""Le layer Lambda doit être importable en isolement, comme dans la Lambda.

Défaut trouvé le 13/11/2026 : `scripts/build_lambda_layer.sh` supprimait les
répertoires `*.dist-info` après l'installation. Les paquets sont alors présents
mais **sans métadonnées**, et ceux qui lisent leur version à l'import échouent :
la Lambda levait « No package metadata was found for httpx2 » en chargeant
`strands.models.openai`. Conséquence : le triage retombait sur le règleur
déterministe, en silence, et le « vrai modèle » n'a jamais tourné en
production.

Ces deux tests verrouillent le correctif : le script ne doit plus supprimer les
métadonnées, et le layer construit doit s'importer dans un interpréteur **sans
site-packages** (le contexte réel de la Lambda).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
BUILD_SCRIPT = REPO_ROOT / "scripts" / "build_lambda_layer.sh"
VERIFY_SCRIPT = REPO_ROOT / "scripts" / "verify_layer.py"
LAYER_DIR = REPO_ROOT / "iac" / "control-plane" / "lambda-layer"


def test_le_script_de_construction_garde_les_metadonnees():
    """Les `*.dist-info` sont la version du paquet : sans eux, l'import casse."""
    source = BUILD_SCRIPT.read_text(encoding="utf-8")
    destructive = [
        line.strip()
        for line in source.splitlines()
        if "dist-info" in line and ("rm -rf" in line or "unlink" in line)
    ]
    assert not destructive, (
        f"le script supprime les métadonnées des paquets : {destructive} — "
        f"les paquets lisent leur version à l'import"
    )


def test_le_layer_construit_est_importable_en_isolement():
    """Le layer, seul sur le sys.path, doit s'importer (comme dans la Lambda)."""
    if not (LAYER_DIR / "python").is_dir():
        pytest.skip("layer non construit (construit par scripts/build_lambda_layer.sh)")
    result = subprocess.run(
        [sys.executable, str(VERIFY_SCRIPT), "--layer-dir", str(LAYER_DIR)],
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert result.returncode == 0, (
        f"le layer n'est pas importable en isolement :\n{result.stdout}\n{result.stderr}"
    )
