#!/usr/bin/env python3
"""Auto-contrôle : Rempart s'analyse lui-même.

Lance de VRAIS scanners sur le VRAI code du dépôt (npm audit sur le portail,
pip-audit et bandit si installés), normalise leurs résultats en failles, les
fait ingérer par le vrai `collect_findings`, et vérifie qu'aucune faille
distincte n'est perdue (le défaut D3, qui a valu 18 failles perdues sur 21, a
motivé ce contrôle).

Usage :
    python3 scripts/selftest.py
Sortie 0 si la conservation est exacte et qu'au moins un scanner a produit des
failles ; 1 sinon. Aucun appel AWS, aucun coût.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from rempart.orchestrator.findings_intake import collect_findings
from rempart.orchestrator.task_types import Deps
from tests.fakes_sa import FakeSecurityAgentClient
from tests.orchestrator.test_tasks import _seed

JOB_ID = "selftest-job"


def run_npm_audit() -> list[dict]:
    """Vrais avis GHSA du portail (package-lock, sans npm install)."""
    lock = ROOT / "portal" / "package-lock.json"
    if not lock.is_file():
        return []
    result = subprocess.run(
        ["npm", "audit", "--package-lock-only", "--json"],
        check=False, cwd=ROOT / "portal", capture_output=True, text=True, timeout=300,
    )
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        return []
    findings = []
    for name, info in (payload.get("vulnerabilities") or {}).items():
        advisories = [a for a in (info.get("via") or []) if isinstance(a, dict)]
        for advisory in advisories:
            advisory_id = advisory.get("url", "").rsplit("/", 1)[-1] or f"npm-{name}"
            findings.append({
                "title": f"{name}: {advisory.get('title', 'advisory')}"[:120],
                "id": advisory_id,
                "severity": str(advisory.get("severity") or info.get("severity") or "moderate"),
                "type": "Vulnerable Dependency",
                "location": f"portal/package-lock.json:{name}#{advisory_id}",
            })
    return findings


def run_pip_audit() -> list[dict]:
    """Vrais CVE PyPI, si l'outil est installé (sinon : rien, proprement)."""
    import shutil

    if shutil.which("pip-audit") is None:
        return []
    result = subprocess.run(
        ["pip-audit", "-r", str(ROOT / "backend" / "requirements-ci.txt"), "--format", "json"],
        check=False, capture_output=True, text=True, timeout=300,
    )
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        return []
    findings = []
    for dep in payload.get("dependencies") or []:
        for vuln in dep.get("vulns") or []:
            findings.append({
                "title": f"{dep.get('name')}=={dep.get('version')} {vuln.get('id')}"[:120],
                "id": vuln.get("id") or f"pip-{dep.get('name')}",
                "severity": "high",
                "type": "Vulnerable Dependency",
                "location": f"backend/requirements-ci.txt:{dep.get('name')}#{vuln.get('id')}",
            })
    return findings


def run_bandit() -> list[dict]:
    """Vraies failles de code Python (seuil medium+), si bandit est installé."""
    import shutil

    if shutil.which("bandit") is None:
        return []
    result = subprocess.run(
        ["bandit", "-r", str(ROOT / "backend" / "rempart"), "-f", "json", "-ll", "-q"],
        check=False, capture_output=True, text=True, timeout=300,
    )
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        return []
    findings = []
    for issue in payload.get("results") or []:
        findings.append({
            "title": f"{issue.get('test_id')}: {issue.get('issue_text', '').splitlines()[0] if issue.get('issue_text') else ''}"[:120],
            "id": issue.get("test_id") or f"bandit-{issue.get('filename')}",
            "severity": str(issue.get("issue_severity") or "low"),
            "type": "Insecure Code Pattern",
            "location": f"{issue.get('filename')}:{issue.get('line_number')}",
        })
    return findings


def severity_rank(value: str) -> str:
    lowered = value.lower()
    for rank in ("critical", "high", "medium", "moderate", "low"):
        if rank in lowered:
            return rank
    return "medium"


def seed_fake_sa(sa: FakeSecurityAgentClient, findings: list[dict]) -> None:
    """Charge les vraies failles dans le double officiel (résumé + détail)."""
    for index, finding in enumerate(findings):
        sa.seed_finding(
            JOB_ID,
            severity=severity_rank(finding["severity"]).title(),
            confidence="High",
            risk_type="Vulnerable Dependency"
            if finding["type"] == "Vulnerable Dependency"
            else "INFORMATION_DISCLOSURE",
            entry_point=finding["location"],
            parameter=finding["id"],
            title=finding["title"],
            description=finding.get("description", finding["title"]),
        )


def main() -> int:
    print("=" * 72)
    print("SELF-TEST — Rempart s'analyse lui-même (vrais scanners, vrai intake)")
    print("=" * 72)

    npm = run_npm_audit()
    pip = run_pip_audit()
    bandit = run_bandit()
    print(f"  failles brutes : npm={len(npm)} pip-audit={len(pip)} bandit={len(bandit)}")

    raw = npm + pip + bandit
    if not raw:
        print("  Aucun scanner n'a produit de faille — impossible de prouver la conservation.")
        return 1

    sa = FakeSecurityAgentClient()
    seed_fake_sa(sa, raw)
    store = _seed()
    deps = Deps(store=store, sa=sa)
    outcome = collect_findings(
        {"app_id": "app-1", "tenant_id": "t-1", "run_id": JOB_ID}, deps
    )

    created = len(outcome.get("findings_created", []))
    duplicates = outcome.get("duplicates_skipped", 0)
    expected = len({f["location"] for f in raw})
    print(f"  intake réel : {created} créée(s), {duplicates} doublon(s), "
          f"{len(raw)} failles brutes, {expected} emplacements distincts")

    ok = created == expected and duplicates == 0
    print(f"  verdict : {'CONSERVATION EXACTE ✓' if ok else 'PERTE DÉTECTÉE ✗'}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())