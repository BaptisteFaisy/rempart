"""Coût d'une revue : à partir des tokens **mesurés**, jamais d'une estimation.

Pourquoi un module séparé : le prix d'un fournisseur change, pas la mesure. La
mesure vient de Strands (`agent.accumulated_usage`), le prix de l'environnement.

Aucun prix par défaut : InferHub est un routeur, ses fournisseurs basculent, et
inventer un prix produirait un faux chiffre dans une page censée prouver le
contraire. Sans prix configuré, `estimate_cost` renvoie ``None`` et la réponse
API le rend comme tel.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

#: Variables de prix, en $ par million de jetons. Absentes = coût non chiffré.
PRICE_INPUT_ENV = "REMPART_LLM_USD_PER_M_INPUT"
PRICE_OUTPUT_ENV = "REMPART_LLM_USD_PER_M_OUTPUT"

_PER_MILLION = 1_000_000.0


@dataclass
class Cost:
    """Coût chiffré, ou la raison pour laquelle il ne l'est pas."""

    usd: float | None
    input_tokens: int
    output_tokens: int
    note: str

    def to_dict(self) -> dict[str, object]:
        return {
            "usd": self.usd,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "note": self.note,
        }


def _price(name: str) -> float | None:
    raw = os.environ.get(name)
    if not raw:
        return None
    try:
        value = float(raw)
    except ValueError:
        return None
    return value if value >= 0 else None


def estimate_cost(usage: dict[str, int]) -> Cost:
    """Coût de la revue, si les deux prix sont configurés ; sinon ``usd=None``."""
    in_tok = int(usage.get("inputTokens") or 0)
    out_tok = int(usage.get("outputTokens") or 0)
    price_in, price_out = _price(PRICE_INPUT_ENV), _price(PRICE_OUTPUT_ENV)
    if price_in is None or price_out is None:
        return Cost(
            usd=None,
            input_tokens=in_tok,
            output_tokens=out_tok,
            note=(
                "prix non configurés "
                f"({PRICE_INPUT_ENV}, {PRICE_OUTPUT_ENV}) : coût en jetons mesuré, "
                "coût en dollars abstenu"
            ),
        )
    usd = (in_tok / _PER_MILLION) * price_in + (out_tok / _PER_MILLION) * price_out
    return Cost(usd=usd, input_tokens=in_tok, output_tokens=out_tok, note="prix configurés")


__all__ = ["Cost", "PRICE_INPUT_ENV", "PRICE_OUTPUT_ENV", "estimate_cost"]
