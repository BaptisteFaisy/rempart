"""Hygiène des assets et de la synthèse : rien de local ne part, rien ne fuit.

Deux incidents mesurés le 13/11/2026 sur le poste de développement :

1. un environnement virtuel posé dans `backend/` était **empaqueté** dans
   l'asset des Lambdas : 655 Mo par synthèse ;
2. `cdk.App()` sans `outdir` laisse son assemblage dans un dossier temporaire
   que rien ne supprime : 111 dossiers `cdk.out*`, **59 Go**, disque à 100 %,
   suite de tests en ENOSPC.

Ces tests portent sur l'asset RÉEL et sur une synthèse RÉELLE : vérifier une
constante d'exclusion ne prouverait pas que l'exclusion est appliquée.
"""

from __future__ import annotations

import sys
from pathlib import Path

import aws_cdk as cdk

IAC_DIR = Path(__file__).resolve().parents[3] / "iac" / "control-plane"
if str(IAC_DIR) not in sys.path:
    sys.path.insert(0, str(IAC_DIR))

from stacks._helpers import BACKEND_DIR, LAMBDA_ASSET_EXCLUDES  # noqa: E402

VOLATILE = (".venv", "__pycache__", ".pytest_cache", ".ruff_cache", ".mypy_cache")


def _staged_files(source: Path, stack: cdk.Stack) -> list[str]:
    """Chemins relatifs des fichiers réellement empaquetés dans l'asset."""
    staging = cdk.AssetStaging(
        stack, "StagedAsset", source_path=str(source), exclude=LAMBDA_ASSET_EXCLUDES
    )
    root = Path(staging.absolute_staged_path)
    return [p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()]


def _fake_backend(root: Path) -> None:
    """Un backend minimal avec tout ce qui doit rester dehors."""
    (root / "rempart").mkdir(parents=True)
    (root / "rempart" / "__init__.py").write_text("x = 1\n", encoding="utf-8")
    (root / "tests").mkdir()
    (root / "tests" / "test_x.py").write_text("def test_x(): pass\n", encoding="utf-8")
    for volatile in (".venv/lib/heavy.bin", "__pycache__/a.pyc", ".pytest_cache/v"):
        target = root / volatile
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"0" * 64)


def test_a_virtualenv_inside_the_backend_is_never_packaged(tmp_path):
    """Un venv et des caches posés dans backend/ ne partent pas dans l'asset."""
    _fake_backend(tmp_path)
    stack = cdk.Stack(cdk.App(), "Hygiene")
    staged = _staged_files(tmp_path, stack)

    assert "rempart/__init__.py" in staged, "le code réel doit être empaqueté"
    for path in staged:
        parts = path.split("/")
        assert not set(parts) & set(VOLATILE), f"fichier volatil empaqueté : {path}"
        assert parts[0] != "tests", f"test empaqueté : {path}"


def test_the_real_backend_asset_excludes_environments_and_caches():
    """Garde sur l'asset réel : un venv sur le poste ne peut plus le gonfler."""
    stack = cdk.Stack(cdk.App(), "HygieneReel")
    staged = _staged_files(BACKEND_DIR, stack)

    assert "rempart/__init__.py" in staged
    offenders = [p for p in staged if set(p.split("/")) & set(VOLATILE)]
    assert not offenders, f"volatils dans l'asset réel : {offenders[:5]}"


def test_synthesis_writes_only_into_the_session_directory(synth_root):
    """La synthèse n'ajoute aucun dossier temporaire dans /tmp."""
    before = set(Path("/tmp").glob("cdk.out*"))
    app = cdk.App()
    app.synth()
    after = set(Path("/tmp").glob("cdk.out*"))

    assert not (after - before), f"assemblages laissés dans /tmp : {after - before}"
    assert Path(app.outdir).is_relative_to(synth_root), (
        f"{app.outdir} hors du dossier de session {synth_root}"
    )
