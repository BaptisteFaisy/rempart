#!/usr/bin/env python3
"""Seed the frozen demo dataset (free-tier runbook, option A).

Produit le jeu de données de démonstration : deux clients, leurs applications,
des tests terminés, des failles à tous les états du cycle de vie, des décisions
d'analyste, un budget consommé et un rapport mensuel. C'est ce jeu qui permet
de montrer le portail aux juges **sans lancer un seul test réel**.

Usage :
    python3 scripts/seed_demo.py --json build/demo-seed.json   # écrire le JSON
    python3 scripts/seed_demo.py --load                        # charger dans DynamoDB
    python3 scripts/seed_demo.py --print                       # afficher le résumé

`--load` exige des credentials AWS et écrit réellement dans les tables ;
sans argument, le script n'écrit rien.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

BACKEND = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(Path(__file__).resolve().parent))

from demo_governance import governance_collections

sys.path.insert(0, str(BACKEND))

from rempart.common.models import (
    Application,
    BudgetState,
    Decision,
    Finding,
    Report,
    Run,
    Tenant,
    TestConfig,
)
from rempart.common.priority import compute_priority, due_date
from rempart.common.timeutil import iso

# Dates figées : période de démonstration d'octobre 2026.
T0 = "2026-10-05T08:00:00Z"
DEMO_TENANTS = (
    {
        "tenant_id": "demo-a",
        "name": "Northwind Retail",
        "plan": "continu",
        "budget": 40.0,
        "app": {
            "app_id": "app-shop",
            "name": "ShopLite",
            "criticality": "high",
            "exposed": True,
            "data": ["personal", "payment"],
            "repo": "demo/shoplite",
        },
    },
    {
        "tenant_id": "demo-b",
        "name": "Contoso Books",
        "plan": "essentiel",
        "budget": 20.0,
        "app": {
            "app_id": "app-book",
            "name": "BookWorm",
            "criticality": "medium",
            "exposed": True,
            "data": ["personal"],
            "repo": "demo/bookworm",
        },
    },
)

# Failles de démonstration : (app, titre, type, sévérité, confiance, statut).
DEMO_FINDINGS = (
    ("app-shop", "IDOR on order details", "IDOR", "Critical", "High", "closed"),
    ("app-shop", "Missing rate limit on login", "BruteForce", "Medium", "High", "confirmed"),
    ("app-shop", "Verbose stack trace in error page", "InfoLeak", "Low", "High", "closed"),
    ("app-book", "SQL injection in search", "SQLI", "Critical", "High", "in_remediation"),
    ("app-book", "Admin route without access control", "BrokenAuth", "High", "Medium",
     "pending_validation"),
    ("app-book", "Session cookie without Secure flag", "Misconfig", "Medium", "Low", "new"),
)


def _tenant(spec: dict[str, Any]) -> Tenant:
    return Tenant(
        tenant_id=spec["tenant_id"],
        name=spec["name"],
        aws_account_id="000000000000",
        region="eu-west-3",
        role_arn=f"arn:aws:iam::000000000000:role/rempart-ops-{spec['tenant_id']}",
        external_id=f"ext-{spec['tenant_id']}",
        plan=spec["plan"],
        contacts=[{"name": "Ops", "email": f"ops@{spec['tenant_id']}.example"}],
        monthly_budget_hours=spec["budget"],
        mandate_status="valid",
        created_at=T0,
        free_tier_confirmed=False,
    )


def _application(spec: dict[str, Any]) -> Application:
    app = spec["app"]
    return Application(
        app_id=app["app_id"],
        tenant_id=spec["tenant_id"],
        name=app["name"],
        criticality=app["criticality"],
        internet_exposed=app["exposed"],
        data_types=app["data"],
        environment="staging",
        agent_space_id=f"space-{app['app_id']}",
        domains=[f"{app['app_id']}.demo.example"],
        repositories=[app["repo"]],
        team="Core",
        ticket_channel="github",
        context={"business": "demonstration dataset"},
        created_at=T0,
    )


def _configs(app_id: str) -> list[TestConfig]:
    return [
        TestConfig(
            config_id=f"cfg-{app_id}-delivery",
            app_id=app_id,
            sa_pentest_id=f"pt-{app_id}-delivery",
            kind="delivery",
            scope={"paths": ["/"]},
            risk_types=["IDOR", "SQLI", "BrokenAuth"],
            blocking_threshold="High",
            schedule=None,
        ),
        TestConfig(
            config_id=f"cfg-{app_id}-full",
            app_id=app_id,
            sa_pentest_id=f"pt-{app_id}-full",
            kind="full",
            scope={"paths": ["/"]},
            risk_types=[],
            blocking_threshold="Critical",
            schedule="cron(0 6 1 * ? *)",
        ),
    ]


def _runs(tenant_id: str, app_id: str) -> list[Run]:
    """Trois tests : un bloqué par la porte, un complet planifié, un retest."""
    base = {
        "config_id": f"cfg-{app_id}-delivery",
        "app_id": app_id,
        "tenant_id": tenant_id,
        "scope_decision": "deployed_range",
    }
    return [
        Run(run_id=f"run-{app_id}-1", trigger="cicd", commit_from="aaa111",
            commit_to="bbb222", status="blocked", started_at="2026-10-06T09:00:00Z",
            ended_at="2026-10-06T10:12:00Z", duration_s=4320.0, task_hours=1.4,
            cost_usd=70.0, **base),
        Run(run_id=f"run-{app_id}-2", trigger="schedule", commit_from="",
            commit_to="", status="completed", started_at="2026-10-12T06:00:00Z",
            ended_at="2026-10-12T09:05:00Z", duration_s=11100.0, task_hours=3.1,
            cost_usd=155.0, config_id=f"cfg-{app_id}-full", app_id=app_id,
            tenant_id=tenant_id, scope_decision="full"),
        Run(run_id=f"run-{app_id}-3", trigger="retest", commit_from="ccc333",
            commit_to="ddd444", status="completed", started_at="2026-10-20T09:00:00Z",
            ended_at="2026-10-20T09:48:00Z", duration_s=2880.0, task_hours=0.9,
            cost_usd=45.0, **base),
    ]


def _finding(index: int, tenant_id: str, app: Application, row: tuple) -> Finding:
    app_id, title, risk, severity, confidence, status = row
    exposed_critical = app.internet_exposed and app.criticality == "high"
    sensitive = any(d in ("personal", "payment", "health") for d in app.data_types)
    result = compute_priority(
        severity, confidence, exposed_critical=exposed_critical, sensitive_data=sensitive
    )
    created = f"2026-10-{6 + index:02d}T10:00:00Z"
    # Python 3.11+ : fromisoformat accepte directement le suffixe « Z ».
    deadline = due_date(result.priority, datetime.fromisoformat(created))
    closed = status in ("closed",)
    return Finding(
        finding_id=f"f-{app_id}-{index}",
        app_id=app_id,
        tenant_id=tenant_id,
        run_id=f"run-{app_id}-1",
        fingerprint=f"fp-{app_id}-{risk.lower()}",
        title=title,
        risk_type=risk,
        severity=severity,
        confidence=confidence,
        priority=result.priority,
        status=status,
        due_at=iso(deadline) if deadline else None,
        ticket_url=f"https://github.com/demo/{app_id}/issues/{10 + index}"
        if status not in ("new",) else None,
        remediation_pr_url=f"https://github.com/demo/{app_id}/pull/{20 + index}"
        if status in ("in_remediation", "closed") else None,
        evidence={"description": f"Demonstration finding: {title}."},
        cvss={"score": 8.1 if severity == "Critical" else 5.4},
        created_at=created,
        updated_at=created,
        closed_at="2026-10-20T09:48:00Z" if closed else None,
        closed_by_run_id=f"run-{app_id}-3" if closed else None,
    )


def _reports() -> list[dict[str, Any]]:
    """Rapports mensuels figés : mêmes KPI que le rapport réel de la période."""
    return [
        Report(
            report_id=f"rep-{spec['tenant_id']}-2026-10",
            tenant_id=spec["tenant_id"], period="2026-10",
            s3_key=f"reports/{spec['tenant_id']}/2026-10/demo.pdf",
            kpis={"delivery_to_result_hours": 1.2,
                  "critical_blocked_before_prod": 1.0,
                  "mean_time_to_fix_days_by_priority": {"P1": 3.0},
                  "sla_compliance": 1.0, "coverage": 1.0, "reopen_rate": 0.0,
                  "task_hours_used": 5.4, "cost_usd": 270.0},
            created_at="2026-11-03T06:00:00Z"
        ).to_item()
        for spec in DEMO_TENANTS
    ]


def build_dataset() -> dict[str, list[dict[str, Any]]]:
    """Construit le jeu de données figé, sérialisable en JSON."""
    tenants, apps, configs, runs, findings, decisions, budgets, reports = (
        [], [], [], [], [], [], [], [])
    for spec in DEMO_TENANTS:
        tenants.append(_tenant(spec).to_item())
        app = _application(spec)
        apps.append(app.to_item())
        configs.extend(c.to_item() for c in _configs(app.app_id))
        runs.extend(r.to_item() for r in _runs(spec["tenant_id"], app.app_id))
        budgets.append(BudgetState(
            tenant_id=spec["tenant_id"], month="2026-10", hours_used=5.4,
            thresholds_hit=[], auto_stop=False).to_item())
    for index, row in enumerate(DEMO_FINDINGS):
        tenant_id = next(s["tenant_id"] for s in DEMO_TENANTS
                         if s["app"]["app_id"] == row[0])
        app = _application(next(s for s in DEMO_TENANTS
                                if s["app"]["app_id"] == row[0]))
        finding = _finding(index, tenant_id, app, row)
        findings.append(finding.to_item())
        if finding.status != "new":
            decisions.append(Decision(
                decision_id=f"dec-{finding.finding_id}",
                finding_id=finding.finding_id, author_type="agent",
                author="triage-agent", action="CONFIRMED",
                justification="Matrice déterministe : sévérité et confiance élevées.",
                created_at=finding.created_at).to_item())
            decisions.append(Decision(
                decision_id=f"dec-h-{finding.finding_id}",
                finding_id=finding.finding_id, author_type="human",
                author="analyst@msp.example", action=finding.status,
                justification="Validé en file de tri.",
                created_at=finding.created_at).to_item())
    reports.extend(_reports())
    dataset = {
        "tenants": tenants, "applications": apps, "test_configs": configs,
        "runs": runs, "findings": findings, "decisions": decisions,
        "budget": budgets, "reports": reports,
    }
    dataset.update(governance_collections(dataset, load_into_store))
    return dataset


def load_into_store(
    dataset: dict[str, list[dict[str, Any]]], store: Any = None
) -> int:
    """Charge le jeu dans un magasin (Store réel par défaut, injectable).

    ``store`` injectable sert au calcul des collections de gouvernance : on
    charge le même jeu dans un magasin en mémoire (plus de DynamoDB à démarrer)
    puis on appelle le code de production (`rempart.reports.*`).
    """
    if store is None:
        from rempart.common.store import Store

        store = Store()
    loaders = {
        "tenants": (Tenant.from_item, store.save_tenant),
        "applications": (Application.from_item, store.save_application),
        "test_configs": (TestConfig.from_item, store.save_config),
        "runs": (Run.from_item, store.save_run),
        "findings": (Finding.from_item, store.save_finding),
        "decisions": (Decision.from_item, store.save_decision),
        "budget": (BudgetState.from_item, store.save_budget),
        "reports": (Report.from_item, store.save_report),
    }
    count = 0
    for key, items in dataset.items():
        from_item, save = loaders[key]
        for item in items:
            save(from_item(item))
            count += 1
    return count


def summarise(dataset: dict[str, list[dict[str, Any]]]) -> str:
    lines = ["Jeu de données de démonstration :"]
    for key, items in dataset.items():
        lines.append(f"  {key:14} {len(items):3} item(s)")
    priorities = {}
    for f in dataset["findings"]:
        priorities[f["priority"]] = priorities.get(f["priority"], 0) + 1
    lines.append(f"  failles par priorité : {priorities}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", type=Path, help="écrire le jeu en JSON")
    parser.add_argument("--load", action="store_true",
                        help="charger dans DynamoDB (credentials AWS requis)")
    parser.add_argument("--print", action="store_true", dest="show",
                        help="afficher le résumé")
    args = parser.parse_args(argv)

    dataset = build_dataset()
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(dataset, indent=2, ensure_ascii=False))
        print(f"écrit : {args.json}")
    if args.load:
        print(f"chargé : {load_into_store(dataset)} item(s) dans DynamoDB")
    if args.show or not (args.json or args.load):
        print(summarise(dataset))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
