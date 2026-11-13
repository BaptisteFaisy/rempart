#!/usr/bin/env python3
"""Vérifie que le layer Lambda est importable **en isolement**, comme la Lambda.

Pourquoi un script à part : la Lambda n'installe que le layer (plus le runtime
AWS). Un poste de développement, lui, a ses paquets dans son environnement :
une faulty import y passe alors qu'elle casse en production. Le 13/11/2026, le
layer était construit sans les métadonnées `*.dist-info`, et la Lambda levait
« No package metadata was found for httpx2 » à l'import de `strands.models.openai`
→ le triage retombait sur le règleur, silencieusement.

Ce script lance un interpréteur **sans site-packages** (`-S -I`) avec le seul
chemin du layer : c'est exactement le contexte d'exécution de la Lambda.

Usage :
    python3 scripts/verify_layer.py            # vérifie le layer construit
    python3 scripts/verify_layer.py --quiet    # sans le détail des modules
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
LAYER_DIR = REPO_ROOT / "iac" / "control-plane" / "lambda-layer"

#: Ce que la Lambda doit pouvoir importer, et ce que le produit en dépend.
REQUIRED_MODULES = ("fpdf", "requests", "strands", "openai", "httpx2")

#: Ce qui doit être lisible : les paquets lisent leur version à l'import.
REQUIRED_METADATA = ("openai", "strands-agents", "httpx2")


def isolation_script(layer_python: Path) -> str:
    """Code exécuté dans l'interpréteur isolé (sans site-packages)."""
    return (
        "import sys\n"
        f"sys.path.insert(0, {str(layer_python)!r})\n"
        "import importlib\n"
        "from importlib.metadata import version, PackageNotFoundError\n"
        "missing = []\n"
        f"for name in {REQUIRED_METADATA!r}:\n"
        "    try:\n"
        "        version(name)\n"
        "    except PackageNotFoundError:\n"
        "        missing.append(name)\n"
        "if missing:\n"
        "    print('METADATA MANQUANTE: ' + ','.join(missing))\n"
        "    sys.exit(2)\n"
        f"for name in {REQUIRED_MODULES!r}:\n"
        "    try:\n"
        "        importlib.import_module(name)\n"
        "    except Exception as exc:\n"
        "        print(f'IMPORT ÉCHEC {name}: {type(exc).__name__}: {exc}')\n"
        "        sys.exit(1)\n"
        "print('OK')\n"
    )


def verify(layer_dir: Path = LAYER_DIR) -> tuple[bool, str]:
    """Vérifie le layer ; renvoie (ok, sortie)."""
    layer_python = layer_dir / "python"
    if not layer_python.is_dir():
        return False, f"layer absent : {layer_python} (construits par build_lambda_layer.sh)"
    result = subprocess.run(
        [sys.executable, "-S", "-I", "-c", isolation_script(layer_python)],
        capture_output=True,
        text=True,
        timeout=180,
    )
    return result.returncode == 0, (result.stdout + result.stderr).strip()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--quiet", action="store_true", help="n'affiche que le verdict")
    parser.add_argument("--layer-dir", default=str(LAYER_DIR), help="dossier du layer")
    args = parser.parse_args()

    ok, output = verify(Path(args.layer_dir))
    if not args.quiet or not ok:
        print(output)
    if not ok:
        return 1
    if not args.quiet:
        print("layer importable en isolement : métadonnées et modules présents")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
