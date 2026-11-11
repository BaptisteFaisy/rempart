"""HTML rendering of the monthly report (EF-RAP-03, annexe C)."""

import html
from typing import Any

from rempart.reports.summary import ExecutiveSummary, badge_class


# --------------------------------------------------------------------------- #
# HTML rendering
# --------------------------------------------------------------------------- #
def _render_highlights_html(highlights: list[str]) -> str:
    items = "".join(f"<li>{html.escape(h)}</li>" for h in highlights)
    return f"<ul>{items}</ul>"


def _render_closed_table_html(items: list[dict[str, Any]]) -> str:
    if not items:
        return "<p><em>Aucune faille fermée sur la période.</em></p>"
    rows = []
    for it in items:
        rows.append(
            f"<tr><td>{html.escape(it.get('priority', ''))}</td>"
            f"<td>{html.escape(it.get('title', ''))}</td>"
            f"<td>{html.escape(it.get('application', ''))}</td>"
            f"<td><code>{html.escape(str(it.get('proof', '')))}</code></td></tr>"
        )
    body = "".join(rows)
    return (
        "<table><thead><tr><th>Priorité</th><th>Titre</th><th>Application</th>"
        f"<th>Preuve de fermeture</th></tr></thead><tbody>{body}</tbody></table>"
    )


def _render_overdue_table_html(items: list[dict[str, Any]]) -> str:
    if not items:
        return "<p><em>Aucune faille en retard d'échéance.</em></p>"
    rows = []
    for it in items:
        rows.append(
            f"<tr><td>{html.escape(it.get('priority', ''))}</td>"
            f"<td>{html.escape(it.get('title', ''))}</td>"
            f"<td>{html.escape(it.get('application', ''))}</td>"
            f"<td>{html.escape(it.get('owner', ''))}</td>"
            f"<td>{html.escape(str(it.get('due_at', '')))}</td></tr>"
        )
    body = "".join(rows)
    return (
        "<table><thead><tr><th>Priorité</th><th>Titre</th><th>Application</th>"
        f"<th>Responsable</th><th>Échéance</th></tr></thead><tbody>{body}</tbody></table>"
    )


def _render_apps_table_html(items: list[dict[str, Any]]) -> str:
    if not items:
        return "<p><em>Aucune application rattachée.</em></p>"
    rows = []
    for it in items:
        counts = it.get("open_by_priority", {})
        open_str = f"P1:{counts.get('P1', 0)} P2:{counts.get('P2', 0)} P3:{counts.get('P3', 0)} P4:{counts.get('P4', 0)}"
        rows.append(
            f"<tr><td>{html.escape(it.get('name', ''))}</td>"
            f"<td>{html.escape(it.get('criticality', ''))}</td>"
            f"<td>{html.escape(it.get('environment', ''))}</td>"
            f"<td>{it.get('tests', 0)}</td>"
            f"<td>{open_str}</td></tr>"
        )
    body = "".join(rows)
    return (
        "<table><thead><tr><th>Application</th><th>Criticité</th><th>Environnement</th>"
        f"<th>Tests</th><th>Failles ouvertes</th></tr></thead><tbody>{body}</tbody></table>"
    )



def _html_head(period: str, doc_kind: str = "Rapport mensuel") -> str:
    """Return the document head with the inline stylesheet (print-friendly).

    ``doc_kind`` lets other exports (e.g. the evidence pack, EF-RAP-04) reuse
    the exact same stylesheet without duplicating it.
    """
    return f"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="utf-8"/>
<title>Rempart - {html.escape(doc_kind)} {html.escape(period)}</title>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
         margin: 24px auto; max-width: 960px; color: #0f172a; line-height: 1.5; }}
  header {{ border-bottom: 2px solid #0f172a; padding-bottom: 12px; margin-bottom: 24px; }}
  h1 {{ margin: 0 0 4px 0; font-size: 24px; }}
  .meta {{ color: #475569; font-size: 14px; }}
  .card {{ background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 6px; padding: 16px; margin: 16px 0; }}
  .badge {{ display: inline-block; padding: 2px 8px; border-radius: 4px; font-weight: bold; font-size: 12px; }}
  .badge-crit {{ background: #fee2e2; color: #991b1b; }}
  .badge-mod {{ background: #fef3c7; color: #92400e; }}
  .badge-low {{ background: #dcfce7; color: #166534; }}
  .kpis {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin: 16px 0; }}
  .kpi {{ background: #ffffff; border: 1px solid #cbd5e1; border-radius: 6px; padding: 12px; text-align: center; }}
  .kpi-val {{ font-size: 22px; font-weight: bold; color: #0f172a; }}
  .kpi-lbl {{ font-size: 12px; color: #64748b; text-transform: uppercase; }}
  table {{ width: 100%; border-collapse: collapse; margin: 12px 0 20px 0; font-size: 13px; }}
  th, td {{ border: 1px solid #cbd5e1; padding: 8px 10px; text-align: left; }}
  th {{ background: #f1f5f9; }}
  footer {{ margin-top: 32px; border-top: 1px solid #e2e8f0; padding-top: 12px; color: #94a3b8; font-size: 11px; }}
</style>
</head>
<body>"""


def _html_header(tenant_id: str, period: str, frozen: dict[str, Any]) -> str:
    """Return the report header (client, period, freeze timestamp)."""
    frozen_at = html.escape(str(frozen.get("frozen_at", "")))
    return f"""<header>
  <h1>Rempart — Rapport Mensuel de Sécurité Continue</h1>
  <div class="meta">Client : <strong>{html.escape(tenant_id)}</strong> | Période : <strong>{html.escape(period)}</strong> | Figé le {frozen_at}</div>
</header>"""


def _html_summary_section(summary: ExecutiveSummary) -> str:
    """Return Annexe C item 1: the executive summary card."""
    badge = badge_class(summary.risk_level)
    return f"""<section>
  <h2>1. Synthèse pour le dirigeant</h2>
  <div class="card">
    <p><strong>Niveau de risque du mois :</strong> <span class="badge badge-{badge}">{html.escape(summary.risk_level)}</span></p>
    <p><strong>Trois faits marquants :</strong></p>
    {_render_highlights_html(summary.highlights)}
    <p><strong>Décision attendue :</strong> {html.escape(summary.expected_decision)}</p>
  </div>
</section>"""


def _html_kpis_section(frozen: dict[str, Any]) -> str:
    """Return Annexe C item 2: the four headline deterministic KPIs."""
    blocked = round(frozen.get("critical_blocked_before_prod", 0.0) * 100, 1)
    sla = round(frozen.get("sla_compliance", 1.0) * 100, 1)
    coverage = round(frozen.get("coverage", 0.0) * 100, 1)
    return f"""<section>
  <h2>2. Indicateurs clés (KPIs déterministes)</h2>
  <div class="kpis">
    <div class="kpi"><div class="kpi-val">{frozen.get('delivery_to_result_hours', 0.0)} h</div><div class="kpi-lbl">Délai livraison → résultat</div></div>
    <div class="kpi"><div class="kpi-val">{blocked} %</div><div class="kpi-lbl">P1/P2 bloquées avant prod</div></div>
    <div class="kpi"><div class="kpi-val">{sla} %</div><div class="kpi-lbl">Respect des échéances</div></div>
    <div class="kpi"><div class="kpi-val">{coverage} %</div><div class="kpi-lbl">Couverture des applications</div></div>
  </div>
</section>"""


def _html_findings_section(frozen: dict[str, Any]) -> str:
    """Return Annexe C item 3: new findings by priority."""
    open_by_p = frozen.get("findings_open_by_priority", {})
    mttf = frozen.get("mean_time_to_fix_days_by_priority", {})
    new_by_p = frozen.get("findings_new_by_priority", {})
    rows = []
    for priority, label in (
        ("P1", "P1 (Critique)"),
        ("P2", "P2 (Élevée)"),
        ("P3", "P3 (Moyenne)"),
        ("P4", "P4 (Faible)"),
    ):
        rows.append(
            f"<tr><td>{label}</td><td>{new_by_p.get(priority, 0)}</td>"
            f"<td>{open_by_p.get(priority, 0)}</td><td>{mttf.get(priority, 0.0)}</td></tr>"
        )
    return f"""<section>
  <h2>3. Nouvelles failles détectées</h2>
  <table>
    <thead><tr><th>Priorité</th><th>Nouvelles failles</th><th>Ouvertes fin de mois</th><th>Délai moyen correction (jours)</th></tr></thead>
    <tbody>
      {"".join(rows)}
    </tbody>
  </table>
</section>"""


def _html_tests_section(tests: dict[str, Any]) -> str:
    """Return Annexe C item 6: tests run and deliveries blocked."""
    return f"""<section>
  <h2>6. Tests réalisés</h2>
  <p>Total tests : <strong>{tests.get('tests_total', 0)}</strong> | Livraisons bloquées par la porte CI/CD : <strong>{tests.get('tests_blocked', 0)}</strong></p>
</section>"""


def _html_budget_section(budget: dict[str, Any]) -> str:
    """Return Annexe C item 7: task-hour budget consumption."""
    return f"""<section>
  <h2>7. Budget d'heures-tâches</h2>
  <p>Consommées : <strong>{budget.get('task_hours_used', 0.0)} h</strong> / Allouées : <strong>{budget.get('monthly_budget_hours', 0.0)} h</strong> (Restant : <strong>{budget.get('remaining_task_hours', 0.0)} h</strong>, soit {budget.get('budget_used_pct', 0.0)} % utilisé). Coût estimé : <strong>{budget.get('cost_usd', 0.0)} $</strong>.</p>
</section>"""


def _html_list_section(title: str, items_html: str, number: int) -> str:
    """Return a generic annexe C section wrapping already-rendered HTML."""
    return f"""<section>
  <h2>{number}. {title}</h2>
  {items_html}
</section>"""


def generate_html_report(
    tenant_id: str,
    period: str,
    frozen: dict[str, Any],
    summary: ExecutiveSummary,
) -> str:
    """Generate the full HTML report matching the 9 items of Annexe C."""
    recs = "".join(f"<li>{html.escape(r)}</li>" for r in frozen.get("recommendations", []))
    sections = [
        _html_head(period),
        _html_header(tenant_id, period, frozen),
        _html_summary_section(summary),
        _html_kpis_section(frozen),
        _html_findings_section(frozen),
        _html_list_section(
            "Failles corrigées avec preuve",
            _render_closed_table_html(frozen.get("closed_findings", [])),
            4,
        ),
        _html_list_section(
            "Failles en retard d'échéance",
            _render_overdue_table_html(frozen.get("overdue_findings", [])),
            5,
        ),
        _html_tests_section(frozen.get("tests_detail", {})),
        _html_budget_section(frozen.get("budget_detail", {})),
        _html_list_section("Recommandations du mois", f"<ul>{recs}</ul>", 8),
        _html_list_section(
            "Annexe technique par application",
            _render_apps_table_html(frozen.get("applications_detail", [])),
            9,
        ),
        "<footer>Plateforme Rempart — Tests d'intrusion en continu par abonnement — "
        "Tous chiffres calculés de manière déterministe (ENF-IA-01).</footer>",
        "</body>",
        "</html>",
    ]
    return "\n".join(sections)
