"""Coût d'une revue : mesuré sur les jetons, chiffré seulement si un prix existe.

Deux pièges verrouillés ici :

- **un coût inconnu n'est pas zéro.** Rendu 0 $, il ferait croire qu'une revue
  est gratuite ; le champ `usd` est donc ``None`` tant que les prix ne sont pas
  configurés, avec une note qui explique l'abstention.
- **les jetons viennent du modèle**, pas d'une estimation sur la taille du diff :
  `estimate_cost` ne fait qu'appliquer un prix à des jetons déjà relevés.
"""

from __future__ import annotations

from rempart.review.cost import (
    PRICE_INPUT_ENV,
    PRICE_OUTPUT_ENV,
    estimate_cost,
)

USAGE = {"inputTokens": 1_000_000, "outputTokens": 500_000, "totalTokens": 1_500_000}


def test_sans_prix_le_cout_est_abstenu_pas_zero(monkeypatch):
    monkeypatch.delenv(PRICE_INPUT_ENV, raising=False)
    monkeypatch.delenv(PRICE_OUTPUT_ENV, raising=False)
    cost = estimate_cost(USAGE)
    assert cost.usd is None
    assert cost.input_tokens == 1_000_000
    assert cost.output_tokens == 500_000
    assert "abstenu" in cost.note


def test_avec_deux_prix_le_cout_est_la_somme_des_deux_moities(monkeypatch):
    monkeypatch.setenv(PRICE_INPUT_ENV, "2.0")
    monkeypatch.setenv(PRICE_OUTPUT_ENV, "8.0")
    cost = estimate_cost(USAGE)
    # 1 M jetons d'entrée à 2 $ + 0,5 M de sortie à 8 $ = 6 $.
    assert cost.usd == 6.0
    assert cost.note == "prix configurés"


def test_un_usage_vide_donne_zero_jetons_mais_pas_un_faux_cout(monkeypatch):
    monkeypatch.setenv(PRICE_INPUT_ENV, "2.0")
    monkeypatch.setenv(PRICE_OUTPUT_ENV, "8.0")
    cost = estimate_cost({})
    assert cost.usd == 0.0
    assert cost.input_tokens == 0
    # Zéro jeton ≠ revue gratuite : c'est l'absence de mesure, pas un prix.
    assert cost.to_dict()["input_tokens"] == 0


def test_un_prix_illegible_est_ignore(monkeypatch):
    monkeypatch.setenv(PRICE_INPUT_ENV, "deux")
    monkeypatch.setenv(PRICE_OUTPUT_ENV, "8.0")
    assert estimate_cost(USAGE).usd is None


def test_un_prix_negatif_est_ignore(monkeypatch):
    monkeypatch.setenv(PRICE_INPUT_ENV, "-1")
    monkeypatch.setenv(PRICE_OUTPUT_ENV, "8.0")
    assert estimate_cost(USAGE).usd is None
