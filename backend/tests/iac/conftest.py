"""Contexte des tests de synthèse CDK.

Les tests synthétisent pour vérifier la STRUCTURE des stacks ; ils ne
déploient rien. Le layer des dépendances tierces n'est pas versionné (il est
reconstruit par ``scripts/build_lambda_layer.sh``), on autorise donc explicitement
son absence pendant la synthèse.

Cette échappatoire ne doit JAMAIS être posée pour un déploiement réel :
`runtime_layer()` lève alors une erreur explicite au lieu de créer des Lambdas
sans dépendances — l'incident du 11 novembre 2026 (11 Lambdas déployées,
`Runtime.ImportModuleError` à la première invocation).
"""

from __future__ import annotations

import os

os.environ.setdefault("REMPART_ALLOW_MISSING_LAYER", "1")
