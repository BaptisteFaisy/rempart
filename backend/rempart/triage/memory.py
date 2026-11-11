"""Mémoire des décisions de l'analyste, par application et par empreinte (EF-TRI-09).

Chapitre 12.5 : « chaque correction de l'analyste est enregistrée et sert de cas
de test ». Une ``Decision`` ne porte ni application ni empreinte : elle est
rattachée à une faille (``Decision.finding_id``). Pour retrouver les décisions
humaines d'une empreinte, on passe donc par les failles de l'application qui
portent cette empreinte (failles connues, faille entrante, store).

Règles :
- seules les décisions humaines (``author_type == "human"``) sont réutilisées ;
- la décision la plus récente l'emporte (date ISO, puis identifiant) ;
- la mémoire influence le statut proposé et la justification, jamais la
  priorité (ENF-IA-01 : la matrice déterministe reste seule juge) ;
- l'isolement est strict : application et empreinte doivent toutes deux
  correspondre, une décision de l'app A ne fuit jamais vers l'app B ;
- le garde-fou ENF-IA-02 (chapitre 12.4) reste appliqué après coup : une
  proposition ``LIKELY_FALSE_POSITIVE`` sur Critical/High exige une validation
  humaine, mémoire ou pas.
"""

from dataclasses import dataclass
from typing import Any

from rempart.common.models import Decision, Finding

#: Actions humaines réutilisables → statut proposé correspondant.
MEMORY_ACTIONS: dict[str, str] = {
    "false_positive": "LIKELY_FALSE_POSITIVE",
    "confirmed": "CONFIRMED",
}


@dataclass(frozen=True)
class MemoryMatch:
    """Décision humaine retenue pour l'empreinte d'une faille dans son application."""

    decision: Decision
    proposed_status: str

    def justification(self) -> str:
        """Phrase citant la décision réutilisée : auteur, date et motif."""
        d = self.decision
        motif = d.justification or "(motif non renseigné)"
        return (
            "Mémoire de l'analyste (EF-TRI-09) : sur la même empreinte de cette application, "
            f"{d.author} a décidé « {d.action} » le {d.created_at} — motif : « {motif} ». "
            f"Décision réutilisée : {self.proposed_status}."
        )


def finding_ids_with_fingerprint(
    app_id: str,
    fingerprint: str,
    pools: list[Finding],
    store: Any = None,
) -> set[str]:
    """Identifiants des failles de ``app_id`` portant ``fingerprint`` (pools + store)."""
    ids: set[str] = set()
    for f in pools:
        if f.app_id == app_id and f.fingerprint == fingerprint:
            ids.add(f.finding_id)
    if store is not None and hasattr(store, "list_findings"):
        for sf in store.list_findings(app_id=app_id):
            if sf.fingerprint == fingerprint:
                ids.add(sf.finding_id)
    return ids


def _append_new(items: list[Decision], seen: set[str], candidates: list[Decision]) -> None:
    for d in candidates:
        if d.author_type == "human" and d.decision_id not in seen:
            seen.add(d.decision_id)
            items.append(d)


def human_decisions(
    finding_ids: set[str],
    past_decisions: list[Decision],
    store: Any = None,
) -> list[Decision]:
    """Décisions humaines portées par ``finding_ids`` (dédupliquées, liste + store)."""
    res: list[Decision] = []
    seen: set[str] = set()
    _append_new(res, seen, [d for d in past_decisions if d.finding_id in finding_ids])
    if store is not None and hasattr(store, "list_decisions"):
        for fid in sorted(finding_ids):
            _append_new(res, seen, list(store.list_decisions(fid)))
    return res


def latest_decision(decisions: list[Decision]) -> Decision | None:
    """Décision la plus récente (date ISO, puis identifiant en cas d'égalité)."""
    if not decisions:
        return None
    return max(decisions, key=lambda d: (d.created_at, d.decision_id))


def memory_match(
    finding: Finding,
    *,
    known_findings: list[Finding],
    past_decisions: list[Decision],
    store: Any = None,
) -> MemoryMatch | None:
    """Retrouve la dernière décision humaine réutilisable pour cette faille.

    Cherche les décisions humaines sur la même empreinte ET la même application
    (failles connues, faille entrante, store). La plus récente l'emporte ; si
    son action n'est pas réutilisable (hors ``MEMORY_ACTIONS``), aucune mémoire
    n'est proposée.
    """
    ids = finding_ids_with_fingerprint(
        finding.app_id,
        finding.fingerprint,
        [*known_findings, finding],
        store,
    )
    if not ids:
        return None
    dec = latest_decision(human_decisions(ids, past_decisions, store))
    if dec is None:
        return None
    status = MEMORY_ACTIONS.get(dec.action)
    if status is None:
        return None
    return MemoryMatch(decision=dec, proposed_status=status)
