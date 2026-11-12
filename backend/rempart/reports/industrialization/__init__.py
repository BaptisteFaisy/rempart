"""Métriques d'industrialisation de Rempart (#68, #26, #47, #34).

Découpé en trois modules pour rester sous la limite de 500 lignes par fichier :
``_common`` (constantes et helpers partagés), ``metrics`` (taux d'intervention
humaine, fatigue d'alerte, minutes économisées), ``corpus`` (export du corpus
d'entraînement constitué par les décisions humaines).

Tout est calculé par du code déterministe (ENF-IA-01) ; les hypothèses non
mesurées sont explicitement marquées ``ASSUMED``.
"""

from ._common import *  # noqa: F401,F403
from .corpus import *  # noqa: F401,F403
from .metrics import *  # noqa: F401,F403
