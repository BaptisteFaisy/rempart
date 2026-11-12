"""Normalisation des énumérations officielles de l'API Security Agent.

La fixture `tests/fixtures/securityagent_shapes.json` (extrait du modèle
botocore officiel) fait foi : les tables de correspondance doivent couvrir
TOUTES les valeurs officielles, sinon une nouvelle valeur de l'API retomberait
sur le défaut sans que personne ne le voie.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from rempart.common.api_enums import (
    CONFIDENCE_TO_INTERNAL,
    DEFAULT_CONFIDENCE,
    DEFAULT_SEVERITY,
    RISK_LEVEL_TO_SEVERITY,
    normalize_confidence,
    normalize_severity,
)
from rempart.common.models import CONFIDENCES, SEVERITIES

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "securityagent_shapes.json"
ENUMS = json.loads(FIXTURE.read_text(encoding="utf-8"))["enums"]
RISK_LEVELS = ENUMS["RiskLevel"]["values"]
CONFIDENCE_LEVELS = ENUMS["ConfidenceLevel"]["values"]


def test_la_table_couvre_toutes_les_valeurs_officielles_de_risk_level():
    assert set(RISK_LEVEL_TO_SEVERITY) == set(RISK_LEVELS)


def test_la_table_couvre_toutes_les_valeurs_officielles_de_confidence():
    assert set(CONFIDENCE_TO_INTERNAL) == set(CONFIDENCE_LEVELS)


@pytest.mark.parametrize("value", RISK_LEVELS)
def test_chaque_risk_level_officiel_donne_une_severite_interne(value):
    assert normalize_severity(value) in SEVERITIES


@pytest.mark.parametrize("value", CONFIDENCE_LEVELS)
def test_chaque_confidence_officielle_donne_une_confiance_interne(value):
    assert normalize_confidence(value) in CONFIDENCES


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("CRITICAL", "Critical"),
        ("HIGH", "High"),
        ("MEDIUM", "Medium"),
        ("LOW", "Low"),
        ("INFORMATIONAL", "Informational"),
        ("UNKNOWN", "Informational"),
        ("critical", "Critical"),
        (" Critical ", "Critical"),
    ],
)
def test_normalisation_de_severite(raw, expected):
    assert normalize_severity(raw) == expected


def test_la_normalisation_est_idempotente_pour_les_jeux_de_demonstration():
    """Une valeur déjà interne ressort inchangée (le jeu figé utilise « Critical »)."""
    for value in SEVERITIES:
        assert normalize_severity(value) == value
    for value in CONFIDENCES:
        assert normalize_confidence(value) == value


@pytest.mark.parametrize("raw", [None, "", "   ", 42, ["HIGH"], {"a": 1}, "INVENTE"])
def test_une_valeur_inconnue_retombe_sur_le_defaut_sans_inventer(raw):
    assert normalize_severity(raw) == DEFAULT_SEVERITY
    assert normalize_confidence(raw) == DEFAULT_CONFIDENCE


def test_les_confiances_douteuses_ne_sont_jamais_survaluees():
    """`UNCONFIRMED`/`FALSE_POSITIVE` → Low : la matrice exigera un humain."""
    assert normalize_confidence("UNCONFIRMED") == "Low"
    assert normalize_confidence("FALSE_POSITIVE") == "Low"
