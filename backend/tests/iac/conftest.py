"""Contexte des tests de synthèse CDK.

Les tests synthétisent pour vérifier la STRUCTURE des stacks ; ils ne
déploient rien. Le layer des dépendances tierces n'est pas versionné (il est
reconstruit par ``scripts/build_lambda_layer.sh``), on autorise donc explicitement
son absence pendant la synthèse.

Cette échappatoire ne doit JAMAIS être posée pour un déploiement réel :
`runtime_layer()` lève alors une erreur explicite au lieu de créer des Lambdas
sans dépendances — l'incident du 11 novembre 2026 (11 Lambdas déployées,
`Runtime.ImportModuleError` à la première invocation).

Mesure du 13/11/2026 : `cdk.App()` sans `outdir` écrit son assemblage dans un
dossier temporaire que **rien** ne supprime. La suite complète en crée ~110
(111 mesurés), et un venv présent dans `backend/` les portait à 655 Mo chacun :
**59 Go** dans /tmp, disque à 100 %, tests en ENOSPC. On isole donc toute la
synthèse dans un seul dossier de session, supprimé à la sortie ; l'isolement
lui-même est gardé par `test_synthesis_writes_only_into_the_session_directory`.
"""

from __future__ import annotations

import atexit
import os
import shutil
import tempfile
from pathlib import Path

import aws_cdk as cdk
import pytest

os.environ.setdefault("REMPART_ALLOW_MISSING_LAYER", "1")
# jsii n'est pas testé sur node 26 (poste de dev) : son avertissement ne dit
# rien de la validité des tests, et il pollue les échecs.
os.environ.setdefault("JSII_SILENCE_WARNING_UNTESTED_NODE_VERSION", "1")

#: Dossier unique de la session : tout ce que la synthèse écrit va là.
SYNTH_ROOT = Path(tempfile.mkdtemp(prefix="rempart-cdk-synth-"))
atexit.register(shutil.rmtree, SYNTH_ROOT, True)

_ORIGINAL_APP_INIT = cdk.App.__init__


def _app_init_into_session_dir(self, *args, **kwargs):
    """`cdk.App()` inchangé, sauf qu'il écrit dans le dossier de session.

    Un sous-dossier par instance : deux assemblages ne se marchent pas dessus,
    et le nettoyage est un seul `rmtree` à la sortie du processus.
    """
    if "outdir" not in kwargs and len(args) < 2:
        kwargs["outdir"] = tempfile.mkdtemp(dir=SYNTH_ROOT)
    return _ORIGINAL_APP_INIT(self, *args, **kwargs)


cdk.App.__init__ = _app_init_into_session_dir

@pytest.fixture(scope="session")
def synth_root() -> Path:
    """Dossier où cette session écrit ses assemblages CDK (supprimé à la fin)."""
    return SYNTH_ROOT
