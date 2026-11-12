"""Collections de gouvernance du jeu de démonstration — calculées par le code réel.

Pourquoi ce module existe : `seed_demo.py` dépassait la limite de 500 lignes
depuis l'ajout de ces collections. Elles en sont extraites, et leur contenu est
produit par le code **réellement déployé** (`rempart.reports.*`), jamais recopié
à la main :

- `evidence` : le dossier de preuves d'audit, SCELLÉ (empreinte SHA-256
  recalculable par un tiers) ;
- `industrialization` : taux d'intervention humaine, divergence agent/humain,
  fatigue d'alerte, minutes économisées, couverture du corpus ;
- `forecast` : projection de fin de mois et date de rupture du budget ;
- `policy` : politique de correction effective (délais P1→P4, seuil de
  blocage, tarif horaire) ;
- `audit` : le journal des actions, avec les MÊMES chaînes d'action que le
  code de production tracerait (`tenant.create`, `application.create`,
  `run.start`, `finding.decision`, `report.create`).

Tout est déterministe : horodatage et identifiants d'audit stables, dossier
scellé à date fixe. Régénérer le jeu ne change donc pas un octet, et le
dossier affiché garde la même empreinte.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

BACKEND = Path(__file__).resolve().parents[1] / "backend"

#: Le dossier de preuves est scellé à une date FIXE pour que le digest soit
#: reproductible : régénérer le jeu ne change jamais l'empreinte affichée.
EVIDENCE_GENERATED_AT = "2026-11-03T06:00:00Z"
DEMO_PERIOD = "2026-10"


# Le dossier de preuves est scellé à une date FIXE pour que le digest soit
# reproductible : régénérer le jeu ne change jamais l'empreinte affichée.
EVIDENCE_GENERATED_AT = "2026-11-03T06:00:00Z"
DEMO_PERIOD = "2026-10"
#: Actions du journal, dans l'ordre chronologique du scénario. Ces chaînes
#: sont exactement celles que pose `ApiContext.audit` en production
#: (application.create, run.start, finding.decision, …) : la colonne « Action »
#: de la page Audit du portail est donc identique à un journal réel.
_AUDIT_SCENARIO = (
    ("platform_admin@msp.example", "tenant.create", "tenant", "{tid}"),
    ("platform_admin@msp.example", "application.create", "application", "{app}"),
)


def _audit_events(store: Any, dataset: dict[str, list[dict[str, Any]]]) -> None:
    """Écrit dans le store le journal d'audit que le scénario de démo implique.

    Chaque événement reprend l'action et l'objet que le code de production
    tracerait à ce moment-là, avec un **identifiant stable** : le journal et
    l'empreinte du dossier de preuves sont ainsi reproductibles à chaque
    régénération du jeu.
    """
    from rempart.common.models import AuditEvent

    events: list[AuditEvent] = []
    for tenant in dataset["tenants"]:
        events.append(AuditEvent(
            audit_id=f"audit-demo-tenant-{tenant['tenant_id']}",
            actor="platform_admin@msp.example", action="tenant.create",
            object_type="tenant", object_id=tenant["tenant_id"],
            result="ok", created_at=tenant["created_at"],
        ))
    for app in dataset["applications"]:
        events.append(AuditEvent(
            audit_id=f"audit-demo-app-{app['app_id']}",
            actor="platform_admin@msp.example", action="application.create",
            object_type="application", object_id=app["app_id"],
            result="ok", created_at=app["created_at"],
        ))
    for run in sorted(dataset["runs"], key=lambda r: r["started_at"]):
        events.append(AuditEvent(
            audit_id=f"audit-demo-run-{run['run_id']}",
            actor="orchestrator", action="run.start", object_type="run",
            object_id=run["run_id"], result="ok", created_at=run["started_at"],
        ))
    for decision in sorted(dataset["decisions"], key=lambda d: d["created_at"]):
        events.append(AuditEvent(
            audit_id=f"audit-demo-decision-{decision['decision_id']}",
            actor=str(decision["author"]), action="finding.decision",
            object_type="finding", object_id=decision["finding_id"],
            result=str(decision["action"]).lower(), created_at=decision["created_at"],
        ))
    for report in dataset["reports"]:
        events.append(AuditEvent(
            audit_id=f"audit-demo-report-{report['report_id']}",
            actor="analyst@msp.example", action="report.create", object_type="report",
            object_id=report["report_id"], result="ok", created_at=report["created_at"],
        ))
    for event in events:
        store.save_audit(event)


def _effective_policy(tenant: dict[str, Any]) -> dict[str, Any]:
    """Politique effective d'un tenant : ses surcharges fondues sur les défauts."""
    from rempart.common.priority import resolve_due_days

    stored = dict(tenant.get("policy") or {})
    return {
        "due_days": resolve_due_days(stored),
        "matrix_overrides": dict(stored.get("matrix_overrides") or {}),
        "blocking_threshold": stored.get("blocking_threshold", "High"),
        "hourly_rate": float(stored.get("hourly_rate", 50.0)),
    }


def _industrialization_metrics(store: Any, tenant_id: str) -> dict[str, Any]:
    """Les quatre familles de métriques d'industrialisation, calculées."""
    from rempart.reports.industrialization import (
        alert_fatigue_indicators,
        analyst_minutes_saved,
        corpus_statistics,
        human_intervention_rate,
    )

    return {
        "tenant_id": tenant_id,
        "period": DEMO_PERIOD,
        "intervention": human_intervention_rate(
            store, tenant_id=tenant_id, period=DEMO_PERIOD
        ),
        "alert_fatigue": alert_fatigue_indicators(
            store, tenant_id=tenant_id, period=DEMO_PERIOD
        ),
        "minutes_saved": analyst_minutes_saved(
            store, tenant_id=tenant_id, period=DEMO_PERIOD
        ),
        "corpus": corpus_statistics(store, tenant_id=tenant_id),
    }


def _tenant_governance(
    store: Any, tenant: dict[str, Any]
) -> dict[str, dict[str, Any]]:
    """Dossier de preuves, industrialisation, prévision et politique d'un client.

    Tout est produit par le code de production (`rempart.reports.*`) — à la
    réserve sorti du dossier : l'empreinte est scellée à date fixe pour être
    reproductible.
    """
    from rempart.reports.evidence import build_evidence_pack, seal_evidence_pack
    from rempart.reports.forecast import forecast_month

    tenant_id = tenant["tenant_id"]
    sealed = seal_evidence_pack(
        build_evidence_pack(
            store=store, tenant_id=tenant_id, period=DEMO_PERIOD,
            generated_at=EVIDENCE_GENERATED_AT,
        )
    )
    metrics = _industrialization_metrics(store, tenant_id)
    projected = forecast_month(
        store, tenant_id=tenant_id, period=DEMO_PERIOD, hourly_rate=50.0
    ).to_dict()
    return {
        "evidence": {
            "tenant_id": tenant_id, "period": DEMO_PERIOD, "pack": sealed,
        },
        "industrialization": {"tenant_id": tenant_id, "metrics": metrics},
        "forecast": {"tenant_id": tenant_id, "forecast": projected},
        "policy": {
            "tenant_id": tenant_id,
            "policy": dict(tenant.get("policy") or {}),
            "effective": _effective_policy(tenant),
        },
    }


def governance_collections(
    dataset: dict[str, list[dict[str, Any]]],
    loader: Any,
) -> dict[str, list[dict[str, Any]]]:
    """Collections de gouvernance, calculées par le code de production.

    Le même jeu, chargé dans un magasin en mémoire, passe dans les fonctions
    réellement déployées : de la sorte, les chiffres de la démo (audit, dossier
    de preuves, industrialisation, prévision, politique) sont ceux que la
    production calculerait sur ces données — pas des valeurs recopiées à la main.
    """
    sys.path.insert(0, str(BACKEND))
    from tests.fakes_store import FakeStore

    store = FakeStore()
    loader(dataset, store=store)
    _audit_events(store, dataset)

    evidence, industrialization, forecast, policy = [], [], [], []
    for tenant in dataset["tenants"]:
        pieces = _tenant_governance(store, tenant)
        evidence.append(pieces["evidence"])
        industrialization.append(pieces["industrialization"])
        forecast.append(pieces["forecast"])
        policy.append(pieces["policy"])

    audit = sorted(
        [event.to_item() for event in store.list_audit()],
        key=lambda item: item["created_at"],
        reverse=True,
    )
    defaults = {
        "due_days": {"P1": 7, "P2": 30, "P3": 90, "P4": None},
        "matrix_overrides": {},
        "blocking_threshold": "High",
        "hourly_rate": 50.0,
    }
    return {
        "audit": audit,
        "evidence": evidence,
        "industrialization": industrialization,
        "forecast": forecast,
        "policy": policy,
        "policy_defaults": [defaults],
    }



