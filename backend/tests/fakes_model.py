"""Modèle Strands scripté, partagé par les tests d'agents (triage et revue).

Un agent Strands se teste sans réseau et sans argent : on lui donne un modèle en
mémoire qui émet les mêmes événements de flux qu'un vrai, et qui appelle l'outil
attendu avec le payload voulu. Deux agents (triage, revue de code) ont ce même
besoin, donc une seule implémentation paramétrée par (nom de l'outil, nom de
l'argument, liste de payloads) — pas deux copies à désynchroniser.

Le scénario est le même qu'avec un vrai modèle : un tour par outil appelé, puis
un tour de texte qui termine la conversation.
"""

from __future__ import annotations

import json
from collections.abc import AsyncGenerator, Iterable
from typing import Any

from strands.models.model import Model


class ScriptedToolModel(Model):
    """Modèle en mémoire qui soumet ``payloads`` un par un via ``tool_name``."""

    def __init__(
        self,
        tool_name: str,
        arg_name: str,
        payloads: Iterable[dict[str, Any]],
        *,
        final_text: str = "Completed",
        model_id: str = "scripted/test",
    ) -> None:
        super().__init__()
        self.tool_name = tool_name
        self.arg_name = arg_name
        self.payloads = list(payloads)
        self.final_text = final_text
        self.model_id = model_id
        self.calls = 0

    def update_config(self, **model_config: Any) -> None:
        pass

    def get_config(self) -> Any:
        return {"model": self.model_id}

    async def structured_output(
        self, output_model: Any, prompt: Any, system_prompt: Any = None, **kwargs: Any
    ) -> AsyncGenerator[dict[str, Any], None]:
        raise NotImplementedError
        yield  # pragma: no cover

    async def stream(
        self,
        messages: Any,
        tool_specs: Any = None,
        system_prompt: Any = None,
        **kwargs: Any,
    ) -> AsyncGenerator[dict[str, Any], None]:
        index = self.calls
        self.calls += 1
        events = self._tool_events(index) if index < len(self.payloads) else self._text_events()
        for event in events:
            yield event
        yield {
            "metadata": {
                "usage": {"inputTokens": 10, "outputTokens": 10, "totalTokens": 20},
                "metrics": {"latencyMs": 1},
            }
        }

    def _tool_events(self, index: int) -> list[dict[str, Any]]:
        payload = self.payloads[index]
        return [
            {"messageStart": {"role": "assistant"}},
            {
                "contentBlockStart": {
                    "contentBlockIndex": 0,
                    "start": {
                        "toolUse": {
                            "toolUseId": f"tu-{index}",
                            "name": self.tool_name,
                        }
                    },
                }
            },
            {
                "contentBlockDelta": {
                    "contentBlockIndex": 0,
                    "delta": {"toolUse": {"input": json.dumps({self.arg_name: payload})}},
                }
            },
            {"contentBlockStop": {"contentBlockIndex": 0}},
            {"messageStop": {"stopReason": "tool_use"}},
        ]

    def _text_events(self) -> list[dict[str, Any]]:
        return [
            {"messageStart": {"role": "assistant"}},
            {"contentBlockStart": {"contentBlockIndex": 0, "start": {"text": ""}}},
            {
                "contentBlockDelta": {
                    "contentBlockIndex": 0,
                    "delta": {"text": self.final_text},
                }
            },
            {"contentBlockStop": {"contentBlockIndex": 0}},
            {"messageStop": {"stopReason": "end_turn"}},
        ]


class BrokenModel(Model):
    """Modèle qui échoue à chaque tour : teste le repli quand un fournisseur est saturé."""

    def __init__(self, error: Exception | None = None) -> None:
        super().__init__()
        self.error = error or RuntimeError("no_provider_under_bid")
        self.calls = 0

    def update_config(self, **model_config: Any) -> None:
        pass

    def get_config(self) -> Any:
        return {"model": "broken/test"}

    async def structured_output(
        self, output_model: Any, prompt: Any, system_prompt: Any = None, **kwargs: Any
    ) -> AsyncGenerator[dict[str, Any], None]:
        raise self.error
        yield  # pragma: no cover

    async def stream(
        self,
        messages: Any,
        tool_specs: Any = None,
        system_prompt: Any = None,
        **kwargs: Any,
    ) -> AsyncGenerator[dict[str, Any], None]:
        self.calls += 1
        raise self.error
        yield  # pragma: no cover


__all__ = ["BrokenModel", "ScriptedToolModel"]
