"""Point d'entrée unique des fakes de test Rempart.

Les implémentations vivent dans trois modules (limite de 500 lignes par
fichier) ; ce fichier les ré-exporte pour que les tests continuent d'écrire
``from tests.fakes import FakeStore``.
"""

from tests.fakes_io import FakeGitHub, FakeS3, FakeS3Object
from tests.fakes_sa import FakeModelClient, FakeSecurityAgentClient
from tests.fakes_store import FakeDdbResource, FakeDdbTable, FakeStore

__all__ = [
    "FakeDdbResource",
    "FakeDdbTable",
    "FakeGitHub",
    "FakeModelClient",
    "FakeS3",
    "FakeS3Object",
    "FakeSecurityAgentClient",
    "FakeStore",
]
