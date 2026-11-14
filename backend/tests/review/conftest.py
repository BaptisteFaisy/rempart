"""Fixtures de la revue de code : un diff réal, court et ancrable."""

from __future__ import annotations

import pytest

from rempart.triage import verdict_cache

#: Diff d'une PR volontairement défectueuse : identifiant pris du corps de la
#: requête (IDOR), secret en dur, SQL concaténé. L'en-tête de hunk pose le côté
#: nouveau sur les lignes 9 à 12 — c'est ce que les tests utilisent pour ancrer
#: un commentaire, et c'est la seule vérité que `rules.index_diff` retient.
SAMPLE_DIFF = """diff --git a/api/orders.py b/api/orders.py
index 1111111..2222222 100644
--- a/api/orders.py
+++ b/api/orders.py
@@ -9,1 +9,4 @@
-    order_id = request.GET["id"]
+    order_id = request.GET["id"]
+    api_key = "sk-live-abcdef1234567890"
+    query = "SELECT * FROM orders WHERE id = " + order_id
+    return db.raw(query)
"""

#: Chemin et lignes réellement présents dans `SAMPLE_DIFF` (côté nouveau).
SAMPLE_FILE = "api/orders.py"
SAMPLE_LINES = (9, 10, 11, 12)

#: Extraits citables (mot pour mot dans le diff, marqueurs et blancs hors compte).
SECRET_EVIDENCE = 'api_key = "sk-live-abcdef1234567890"'
SQL_EVIDENCE = 'query = "SELECT * FROM orders WHERE id = " + order_id'


def comment_payload(**overrides):
    """Payload d'un commentaire valide, avec les champs voulus en surcharge."""
    base = {
        "file": SAMPLE_FILE,
        "line": 10,
        "category": "secrets",
        "severity": "Critical",
        "confidence": "High",
        "title": "Clé API en dur dans le source",
        "recommendation": "Déplacer la clé dans un gestionnaire de secrets.",
        "evidence": SECRET_EVIDENCE,
        "references": ["CWE-798"],
        "blocking": True,
    }
    base.update(overrides)
    return base


@pytest.fixture(autouse=True)
def _vide_le_cache_des_revues():
    """Le cache de revues est keyed par empreinte du diff : il faut le vider.

    Sans cela, deux tests portant sur le même diff se marchent dessus : le
    second recevrait le verdict du premier (source « cache ») au lieu d'appeler
    son propre modèle scripté. Ce fixture rend chaque test indépendant.
    """
    verdict_cache.reset()
    yield
    verdict_cache.reset()
