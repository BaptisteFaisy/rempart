"""Socle commun des preuves : journal, requêtes HTTP, dataclass de preuve.

Isolé pour que chaque fichier de preuve reste sous la limite de 500 lignes.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any

TOKEN = os.environ.get("REMPART_TOKEN", "")

#: Preuves qui exigent un jeton : sans jeton elles sont SAUTEES (annoncées),
#: jamais comptées comme des échecs — une preuve non jouée n'est pas une
#: preuve fausse.
AUTHENTICATED_PREFIXES = ("P2", "P4", "P5", "P6", "P7")

PROOFS: list[Proof] = []


@dataclass
class Proof:
    """Une preuve : identifiant, attendu, observé, source, verdict."""

    pid: str
    label: str
    expected: str
    observed: str
    source: str
    ok: bool = True
    note: str = ""
    extra: dict[str, Any] = field(default_factory=dict)




def needs_token(pid: str) -> bool:
    """Vrai si cette preuve exige un jeton Cognito."""
    return not TOKEN and pid.startswith(AUTHENTICATED_PREFIXES)


def record(pid: str, label: str, expected: Any, observed: Any, source: str, note: str = "") -> bool:
    """Enregistre une preuve et l'affiche immédiatement."""
    if needs_token(pid):
        proof = Proof(pid, label, str(expected), "non joué (jeton absent)", source, True, note)
        PROOFS.append(proof)
        print(f"[PREUVE NON JOUÉE] {pid} — {label}")
        print("          raison   : jeton Cognito absent (REMPART_TOKEN non posé)")
        return True
    ok = expected == observed
    proof = Proof(pid, label, str(expected), str(observed), source, ok, note)
    PROOFS.append(proof)
    mark = "PREUVE OK " if ok else "PREUVE ÉCHEC"
    print(f"[{mark}] {pid} — {label}")
    print(f"          attendu : {expected!r}")
    print(f"          observé : {observed!r}")
    print(f"          source  : {source}")
    if note:
        print(f"          note    : {note}")
    return ok


def record_bool(pid: str, label: str, ok: bool, observed: Any, source: str, note: str = "") -> bool:
    """Enregistre une preuve dont le verdict est un booléen calculé."""
    if needs_token(pid):
        proof = Proof(pid, label, "vrai", "non joué (jeton absent)", source, True, note)
        PROOFS.append(proof)
        print(f"[PREUVE NON JOUÉE] {pid} — {label}")
        return True
    proof = Proof(pid, label, "vrai", str(observed), source, ok, note)
    PROOFS.append(proof)
    mark = "PREUVE OK " if ok else "PREUVE ÉCHEC"
    print(f"[{mark}] {pid} — {label}")
    print(f"          observé : {observed!r}")
    print(f"          source  : {source}")
    if note:
        print(f"          note    : {note}")
    return ok


def request(
    method: str,
    url: str,
    body: dict | None = None,
    token: str | None = TOKEN,
    headers: dict | None = None,
) -> dict[str, Any]:
    """Requête HTTP réelle ; renvoie status, corps JSON, en-têtes."""
    sent = {"Content-Type": "application/json", "Accept": "application/json"}
    sent.update(headers or {})
    if token:
        sent["Authorization"] = f"Bearer {token}"
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, headers=sent, method=method)
    try:
        with urllib.request.urlopen(req, timeout=60) as response:
            raw = response.read().decode("utf-8")
            return {
                "status": response.status,
                "headers": dict(response.headers),
                "body": _parse_body(raw),
                "text": raw,
            }
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8")
        try:
            parsed = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            parsed = {"raw": raw[:200]}
        return {
            "status": exc.code,
            "headers": dict(exc.headers or {}),
            "body": parsed,
            "text": raw,
        }
    except urllib.error.URLError as exc:
        return {"status": 0, "headers": {}, "body": {"error": str(exc.reason)}, "text": ""}


def _parse_body(raw: str) -> Any:
    """Corps JSON si possible, sinon le texte brut (le portail renvoie du HTML)."""
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"raw": raw}


