#!/usr/bin/env python3
"""Contrôle du budget des modèles : lesquels répondent SANS dépasser le prix.

InferHub est un routeur : ses fournisseurs passent en quota/cooldown/prix, et un
modèle peut renvoyer HTTP 402 « no_provider_under_bid » quand tous ses
fournisseurs sont hors du budget de l'utilisateur. Ce script teste un appel
minimal sur chaque modèle candidat et rapporte ceux qui répondent DANS le budget.

Usage :
    set -a && . ~/.config/agent-secrets/inferhub.env && set +a
    python3 scripts/llm_budget_check.py

Le secret n'est jamais affiché. Sortie 0 si au moins un modèle répond dans le
budget, 1 sinon.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request

BASE = os.environ.get("LLM_BASE_URL", "https://api.inferhub.dev/v1").rstrip("/")
KEY = os.environ.get("LLM_API_KEY", "")
CANDIDATES = [
    "combo/cheap",
    "ali/glm-5.2",
    "ag/gemini-3.8-flash-high",
    "ali/deepseek-v4.1-flash",
    "alicn/deepseek-v4.1-flash",
    "ali/qwen3.8-flash",
]


def probe(model: str, timeout: int = 60) -> dict:
    """Un appel minimal ; rapporte succes/latence/erreur (jamais le secret)."""
    body = json.dumps(
        {
            "model": model,
            "messages": [{"role": "user", "content": "Réponds exactement : OK"}],
            "max_tokens": 16,
        }
    ).encode()
    request = urllib.request.Request(
        f"{BASE}/chat/completions",
        data=body,
        headers={"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"},
        method="POST",
    )
    started = time.time()
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
            content = (payload.get("choices") or [{}])[0].get("message", {}).get("content", "")
            return {
                "model": model,
                "ok": True,
                "seconds": round(time.time() - started, 1),
                "answer": str(content)[:40],
            }
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8")[:160]
        return {"model": model, "ok": False, "error": f"HTTP {exc.code} {detail}"}
    except Exception as exc:  # noqa: BLE001 — un modèle peut pendre
        return {"model": model, "ok": False, "error": f"{type(exc).__name__}: {exc}"}


def main() -> int:
    if not (BASE and KEY):
        print("LLM_BASE_URL / LLM_API_KEY absents — déconseillé sans clé.")
        return 2
    print(f"Sonde sur {BASE} (" "le secret n'est pas affiché) :")
    usable = []
    for model in CANDIDATES:
        result = probe(model)
        if result["ok"]:
            usable.append(model)
            print(f"  [OK] {model:30s} {result['seconds']}s  « {result['answer']} »")
        else:
            print(f"  [KO] {model:30s} {str(result.get('error', ''))[:130]}")
    print("\nmodèles répondant DANS le budget :", ", ".join(usable) or "AUCUN")
    return 0 if usable else 1


if __name__ == "__main__":
    raise SystemExit(main())