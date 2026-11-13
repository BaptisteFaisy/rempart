"""Le layer Lambda et les dépendances CI doivent dire la même chose.

Défaut trouvé le 13/11/2026 : `scripts/build_lambda_layer.sh` empaquetait
`openai==3.50.0` (client du modèle de triage), mais `requirements-ci.txt` ne
l'avait pas. Conséquence silencieuse : un environnement installé depuis la CI
ne pouvait pas construire le client Strands, `build_model_client()` rendait
`None`, et **le triage retombait sur le règleur sans que rien ne le dise** —
un poste sur deux n'avait donc pas de « vrai LLM », selon la façon dont il
avait été installé.

Ces tests lisent les deux fichiers réels : une divergence de version ou un
paquet manquant échoue ici, pas en production.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
LAYER_SCRIPT = REPO_ROOT / "scripts" / "build_lambda_layer.sh"
CI_REQUIREMENTS = REPO_ROOT / "backend" / "requirements-ci.txt"

_PACKAGES_BLOCK = re.compile(r"^PACKAGES=\((.*?)^\)", re.DOTALL | re.MULTILINE)
_QUOTED_ENTRY = re.compile(r'^\s*"([^"]+)"\s*$', re.MULTILINE)


def _pin(entry: str) -> tuple[str, str]:
    name, _, version = entry.partition("==")
    return name.strip().lower(), version.strip()


def layer_packages() -> dict[str, str]:
    """Paquets épinglés empaquetés dans le layer Lambda (`nom -> version`)."""
    text = LAYER_SCRIPT.read_text(encoding="utf-8")
    block = _PACKAGES_BLOCK.search(text)
    assert block, f"bloc PACKAGES introuvable dans {LAYER_SCRIPT.name}"
    return dict(_pin(entry) for entry in _QUOTED_ENTRY.findall(block.group(1)))


def ci_packages() -> dict[str, str]:
    """Paquets épinglés de l'environnement de CI (`nom -> version`)."""
    pins: dict[str, str] = {}
    for line in CI_REQUIREMENTS.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "==" not in line:
            continue
        name, version = _pin(line)
        pins[name] = version
    return pins


def test_le_layer_n_est_pas_vide():
    """Sans paquet, ce test ne prouverait rien (un parseur cassé passerait)."""
    packages = layer_packages()
    assert packages, "aucun paquet lu dans build_lambda_layer.sh"
    assert "strands-agents" in packages


def test_tout_paquet_du_layer_est_dans_les_dependances_ci():
    """Ce que la Lambda embarque doit pouvoir être importé (et testé) en CI."""
    layer = layer_packages()
    ci = ci_packages()
    missing = sorted(name for name in layer if name not in ci)
    assert not missing, (
        f"paquets du layer absents de requirements-ci.txt : {missing} — "
        f"un poste installé depuis la CI n'aurait pas ces modules"
    )


def test_les_versions_du_layer_et_de_la_ci_sont_identiques():
    """Deux versions du même paquet = deux comportements, selon l'endroit."""
    layer = layer_packages()
    ci = ci_packages()
    diverging = {
        name: (version, ci[name])
        for name, version in layer.items()
        if name in ci and ci[name] != version
    }
    assert not diverging, f"versions divergentes (layer, ci) : {diverging}"
