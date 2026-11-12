"""Métriques d'industrialisation de Rempart (#68, #26, #47, #34).

Découpé en trois modules pour rester sous la limite de 500 lignes par fichier :
``_common`` (constantes et helpers partagés), ``metrics`` (taux d'intervention
humaine, fatigue d'alerte, minutes économisées), ``corpus`` (export du corpus
d'entraînement constitué par les décisions humaines).

Tout est calculé par du code déterministe (ENF-IA-01) ; les conventions non
mesurées (seuils de fatigue, minutes par faille) sont marquées comme telles.
"""

from .corpus import corpus_json, corpus_statistics, export_training_corpus
from .metrics import alert_fatigue_indicators, analyst_minutes_saved, human_intervention_rate

__all__ = [
    "alert_fatigue_indicators",
    "analyst_minutes_saved",
    "corpus_json",
    "corpus_statistics",
    "export_training_corpus",
    "human_intervention_rate",
]
