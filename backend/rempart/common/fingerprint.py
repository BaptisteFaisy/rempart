"""Empreinte d'une faille — calculée sur des données RÉELLEMENT présentes.

INCIDENT RÉEL (12 nov. 2026, banc réel au modèle officiel `securityagent`
2025-09-06) : l'empreinte était `sha256(app_id:risk_type:entry_point:parameter)`,
or la vraie API `ListFindings` renvoie des `FindingSummary` qui n'ont **ni
`entryPoint` ni `parameter`** — les deux derniers termes de l'empreinte étaient
donc toujours vides. Résultat mesuré : 21 failles réelles distinctes → **3
créées, 18 jetées comme « doublons »** (86 % de perte silencieuse), et une
détection de régression faussée.

La cause racine est une empreinte calculée sur des champs **qui n'existent pas
dans l'API** ; la parade n'est pas de « deviner » une valeur de remplacement,
mais d'utiliser ce que l'API fournit réellement :

- `Finding.codeLocations` (`filePath`, `lineStart`, `lineEnd`) — l'emplacement
  de la faille dans le code : stable entre deux runs, distinct d'une faille à
  l'autre ;
- `Finding.name` / `FindingSummary.name` — le titre de la faille ;
- en dernier recours, `findingId`.

`finding_fingerprint()` est la **source unique** de l'empreinte : elle est
utilisée par l'intake (`findings_intake`) comme par la fermeture/réouverture
(`tasks.close_or_reopen`), sans quoi une faille détectée et sa réouverture
n'auraient pas la même empreinte.
"""

from __future__ import annotations

import hashlib
from typing import Any


def fingerprint(
    app_id: str,
    risk_type: str,
    entry_point: str,
    parameter: str | None = None,
) -> str:
    """Compute sha256 hex fingerprint truncated to 16 characters.

    Enables cross-run deduplication and regression detection.
    """
    param_clean = parameter.strip() if parameter else ""
    raw = f"{app_id.strip()}:{risk_type.strip()}:{entry_point.strip()}:{param_clean}"
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return digest[:16]


def _location_span(location: dict[str, Any]) -> str:
    """« chemin:ligne-ligne » à partir d'une `CodeLocation` officielle."""
    path = str(location.get("filePath") or "").strip()
    if not path:
        return ""
    start = location.get("lineStart")
    end = location.get("lineEnd")
    span = f":{start}" if start not in (None, "") else ""
    if end not in (None, "") and end != start:
        span += f"-{end}"
    return f"{path}{span}"


def finding_location(
    detail: dict[str, Any] | None = None,
    raw: dict[str, Any] | None = None,
) -> str:
    """Emplacement d'une faille, par ordre de fiabilité décroissante.

    1. `codeLocations` du détail (`BatchGetFindings`) — la donnée la plus stable ;
    2. `name` (titre de la faille) ;
    3. `entryPoint` (ancien format, encore produit par les jeux de démo) ;
    4. `findingId` — dernier recours : stable seulement à l'intérieur d'un job.
    """
    sources = [source for source in (detail, raw) if isinstance(source, dict)]
    for source in sources:
        for location in source.get("codeLocations") or []:
            if not isinstance(location, dict):
                continue
            span = _location_span(location)
            if span:
                return span
    for source in sources:
        name = str(source.get("name") or "").strip()
        if name:
            return name
    for source in sources:
        entry = str(source.get("entryPoint") or source.get("entry_point") or "").strip()
        if entry:
            return entry
    for source in sources:
        identifier = str(source.get("findingId") or "").strip()
        if identifier:
            return identifier
    return ""


def finding_fingerprint(
    app_id: str,
    raw: dict[str, Any],
    detail: dict[str, Any] | None = None,
) -> str:
    """Empreinte d'une faille — source unique, partagée par l'intake et la clôture."""
    risk_type = str(raw.get("riskType") or raw.get("risk_type") or "Unknown")
    parameter = raw.get("parameter")
    return fingerprint(
        app_id,
        risk_type,
        finding_location(detail, raw),
        str(parameter) if parameter else None,
    )
