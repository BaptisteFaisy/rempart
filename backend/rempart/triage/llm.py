"""Client LLM du triage — Strands branché sur un endpoint OpenAI-compatible.

Pourquoi ce module existe : le triage de Rempart savait déjà utiliser un
vrai modèle Strands (`triage/agent.py::_run_strands_agent`), mais rien ne le
construisait : en production, l'agent tombait donc toujours sur le repli
déterministe. C'est ce qui rendait la démonstration « pas assez réelle » : les
propositions venaient d'un règleur, pas d'un modèle.

Ici, on construit le client Strands à partir de l'environnement :

- ``REMPART_LLM_BASE_URL`` (ou ``LLM_BASE_URL``) — endpoint compatible
  OpenAI (par défaut celui d'InferHub : ``https://api.inferhub.dev/v1``) ;
- ``REMPART_LLM_API_KEY`` (ou ``LLM_API_KEY``) — secret, jamais écrit dans un
  template : en production il vient d'un paramètre SSM SecureString, en local
  de ``~/.config/agent-secrets/inferhub.env`` ;
- ``REMPART_LLM_MODEL`` — identifiant du modèle (``combo/cheap`` par défaut).

Sans configuration, on renvoie ``None`` : le triage déterministe reste le
repli, et la démo hors ligne ne coûte donc **rien** (aucun appel LLM, aucune
facturation).

Les garde-fous déterministes (`triage/guardrails.py`) s'appliquent TOUJOURS
après le modèle : priorité recalculée par la matrice, EF-TRI-05 (un Critical ou
un High ne peut pas être écarté seul comme faux positif), détection de doublon
et de régression. Un modèle qui propose n'importe quoi ne peut donc pas faire
passer une faute critique en P4.
"""

from __future__ import annotations

import os
from typing import Any

from strands.models import Model

DEFAULT_BASE_URL = "https://api.inferhub.dev/v1"
#: Modèles essayés dans l'ordre. Le routeur d'InferHub bascule ses fournisseurs
#: (quota, cooldown, prix) : un seul modèle rend le triage instable, une chaîne
#: de modèles le rend robuste. Mesuré le 12/11/2026 : `combo/cheap` répond en
#: ~2 s, mais peut être saturé ; `ali/glm-5.2` répond en ~2 s ; au-delà, les
#: fournisseurs sont hors budget de l'utilisateur (HTTP 402 « no_provider_under_bid »).
DEFAULT_MODELS = ("combo/cheap", "ali/glm-5.2")


class _FallbackModel(Model):
    """Modèle Strands qui essaie plusieurs modèles OpenAI-compatibles.

    L'agent de triage ne doit jamais tomber en panne parce qu'un fournisseur est
    saturé : on essaie le suivant. Si TOUS échouent, l'appel remonte et le
    triage déterministe prend le relais (voir `triage/agent.py`).
    """

    def __init__(self, models: list[Any]) -> None:
        super().__init__()
        self._models = list(models)

    def update_config(self, **model_config: Any) -> None:
        """Applique la configuration à tous les modèles de la chaîne."""
        for model in self._models:
            try:
                model.update_config(**model_config)
            except Exception:  # pragma: no cover - un modèle peut refuser
                continue

    def get_config(self) -> Any:
        """Configuration du premier modèle de la chaîne."""
        return self._models[0].get_config()

    async def structured_output(self, *args: Any, **kwargs: Any) -> Any:
        """Sortie structurée : déléguée au premier modèle de la chaîne."""
        return await self._models[0].structured_output(*args, **kwargs)

    async def stream(
        self,
        messages: Any,
        tool_specs: Any = None,
        system_prompt: Any = None,
        **kwargs: Any,
    ) -> Any:
        """Diffuse les événements du premier modèle qui répond."""
        last_error: Exception | None = None
        for model in self._models:
            try:
                async for event in model.stream(
                    messages, tool_specs=tool_specs, system_prompt=system_prompt, **kwargs
                ):
                    yield event
                return
            except Exception as exc:  # noqa: BLE001 — on essaie le suivant
                last_error = exc
        raise last_error if last_error else RuntimeError("aucun modèle disponible")


def llm_configured() -> bool:
    """Vrai si un endpoint et une clé sont disponibles."""
    return bool(
        (os.environ.get("REMPART_LLM_BASE_URL") or os.environ.get("LLM_BASE_URL"))
        and (os.environ.get("REMPART_LLM_API_KEY") or os.environ.get("LLM_API_KEY"))
    )


def model_ids() -> tuple[str, ...]:
    """Modèles à essayer, dans l'ordre (``REMPART_LLM_MODELS``, séparés par des virgules)."""
    raw = os.environ.get("REMPART_LLM_MODELS")
    if raw:
        return tuple(part.strip() for part in raw.split(",") if part.strip())
    single = os.environ.get("REMPART_LLM_MODEL")
    if single:
        return (single.strip(),)
    return DEFAULT_MODELS


def build_model_client(model_client: Any = None) -> Any:
    """Construit le client Strands du triage, ou ``None`` si non configuré.

    ``model_client`` permet d'injecter un client (tests) sans toucher à
    l'environnement. Sinon, une chaîne de modèles est construite : le premier
    qui répond est utilisé, les suivants servent de repli si un fournisseur est
    saturé.
    """
    if model_client is not None:
        return model_client
    if not llm_configured():
        return None
    base_url = os.environ.get("REMPART_LLM_BASE_URL") or os.environ.get("LLM_BASE_URL")
    api_key = os.environ.get("REMPART_LLM_API_KEY") or os.environ.get("LLM_API_KEY")
    try:
        from strands.models.openai import OpenAIModel
    except ImportError:  # pragma: no cover - dépendance optionnelle
        return None
    models = []
    for model_id in model_ids():
        try:
            models.append(
                OpenAIModel(
                    client_args={"base_url": base_url, "api_key": api_key},
                    model_id=model_id,
                )
            )
        except Exception:  # pragma: no cover - configuration invalide
            continue
    if not models:
        return None
    if len(models) == 1:
        return models[0]
    return _FallbackModel(models)


__all__ = [
    "DEFAULT_BASE_URL",
    "DEFAULT_MODELS",
    "build_model_client",
    "llm_configured",
    "model_ids",
]
