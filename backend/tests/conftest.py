import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Le cache jsii refuse un repertoire lisible par d'autres comptes : on le
# place dans un dossier temporaire propre a la session de tests.
os.environ.setdefault(
    "JSII_RUNTIME_PACKAGE_CACHE_ROOT",
    os.path.join(tempfile.gettempdir(), "rempart-jsii-cache"),
)
os.environ.setdefault("JSII_SILENCE_WARNING_UNTESTED_NODE_VERSION", "1")
