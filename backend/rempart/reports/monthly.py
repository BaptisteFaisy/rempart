"""Monthly report generator (HTML + PDF via fpdf2) for Rempart (EF-RAP-03, Annexe C).

The executive summary is produced either by a model client (if supplied) or
by a deterministic fallback template, always strictly grounded in the frozen
numbers.
"""

import html
import re
import uuid
from dataclasses import dataclass
from typing import Any

from fpdf import FPDF

from rempart.common.models import Report
from rempart.common.store import Store
from rempart.common.timeutil import iso, utcnow
from rempart.reports.metrics import freeze_month

_BULLET_RE = re.compile(r"^\s*(?:[-*]|\d+[.)])\s*")


# --------------------------------------------------------------------------- #
# Executive summary (model or fallback)
# --------------------------------------------------------------------------- #
@dataclass
class ExecutiveSummary:
    """The 3 pieces required by Annexe C item 1."""

    risk_level: str
    highlights: list[str]
    expected_decision: str


def _risk_level_label(level: str) -> str:
    """Translate risk level code to French presentation string."""
    mapping = {
        "critical": "Critique",
        "moderate": "Modere",
        "low": "Faible",
    }
    return mapping.get(level.lower(), level.capitalize())


def _badge_class(label: str) -> str:
    """Map a risk level label onto its CSS badge class."""
    normalized = label.strip().lower()
    if normalized in ("critique", "critical"):
        return "crit"
    if normalized in ("modere", "modéré", "moderate"):
        return "mod"
    return "low"


def _fallback_summary(frozen: dict[str, Any]) -> ExecutiveSummary:
    """Deterministic summary complying with Annexe C item 1."""
    level = _risk_level_label(str(frozen.get("risk_level", "low")))
    p1 = frozen.get("findings_open_by_priority", {}).get("P1", 0)
    p2 = frozen.get("findings_open_by_priority", {}).get("P2", 0)
    blocked_pct = round(frozen.get("critical_blocked_before_prod", 0.0) * 100, 1)
    sla_pct = round(frozen.get("sla_compliance", 1.0) * 100, 1)
    coverage_pct = round(frozen.get("coverage", 0.0) * 100, 1)

    highlights = [
        (
            f"{frozen.get('tests_total', 0)} tests d'intrusion realises : "
            f"{blocked_pct} % des failles P1/P2 arretees avant mise en production "
            f"({frozen.get('tests_blocked', 0)} livraisons bloquees par la porte CI/CD)."
        ),
        (
            f"{frozen.get('findings_closed', 0)} failles fermees avec preuve de correction, "
            f"avec un respect des echeances contractuelles de {sla_pct} %."
        ),
        (
            f"Couverture du parc a {coverage_pct} % des applications du contrat, "
            f"pour {frozen.get('task_hours_used', 0.0)} heures-taches consommees."
        ),
    ]

    if p1 > 0:
        decision = (
            f"Arbitrer et allouer les ressources de developpement pour resoudre les "
            f"{p1} faille(s) critique(s) P1 avant l'echeance des 7 jours."
        )
    elif p2 > 0:
        decision = (
            f"Valider le calendrier de correction sous 30 jours pour les {p2} faille(s) P2 "
            "identifiees ce mois-ci."
        )
    else:
        decision = (
            "Renouveler le mandat de test continu et maintenir la politique de blocage "
            "en preproduction sans modification."
        )

    return ExecutiveSummary(
        risk_level=level,
        highlights=highlights,
        expected_decision=decision,
    )


def _parse_model_summary(raw: str, fallback: ExecutiveSummary) -> ExecutiveSummary:
    """Best-effort parser for the model output, falling back to deterministic lines."""
    lines = [line.strip() for line in raw.splitlines() if line.strip()]
    if not lines:
        return fallback

    level = fallback.risk_level
    highlights: list[str] = []
    decision = fallback.expected_decision

    for line in lines:
        lower = line.lower()
        if "niveau de risque" in lower:
            for candidate in ("critique", "modere", "modéré", "faible", "critical", "low"):
                if candidate in lower:
                    level = _risk_level_label(candidate.replace("é", "e"))
                    break
        elif _BULLET_RE.match(line) and len(highlights) < 3:
            highlights.append(_BULLET_RE.sub("", line))
        elif "decision" in lower or "décision" in lower:
            parts = line.split(":", 1)
            decision = parts[1].strip() if len(parts) > 1 else line

    while len(highlights) < 3:
        highlights.append(fallback.highlights[len(highlights)])

    return ExecutiveSummary(
        risk_level=level,
        highlights=highlights[:3],
        expected_decision=decision,
    )


def draft_executive_summary(frozen: dict[str, Any], model_client: Any | None = None) -> ExecutiveSummary:
    """Produce the Annexe C item 1 executive summary."""
    fallback = _fallback_summary(frozen)
    if model_client is None:
        return fallback

    prompt = (
        "Redige la synthese executive du rapport mensuel de securite Rempart pour le dirigeant.\n"
        "Contraintes absolues :\n"
        "- Utilise UNIQUEMENT les chiffres figes fournis, n'en invente AUCUN.\n"
        "- Exactement 3 faits marquants courts et percutants.\n"
        "- Exactement 1 decision attendue pour le dirigeant.\n"
        "- Un niveau de risque : Faible, Modere ou Critique.\n\n"
        f"Chiffres figes :\n{frozen}\n"
    )
    try:
        raw = model_client.invoke(prompt)
        if isinstance(raw, str) and raw.strip():
            return _parse_model_summary(raw, fallback)
    except Exception:
        pass
    return fallback


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


def generate_html_report(
    tenant_id: str,
    period: str,
    frozen: dict[str, Any],
    summary: ExecutiveSummary,
) -> str:
    """Generate the full HTML report matching the 9 items of Annexe C."""
    open_by_p = frozen.get("findings_open_by_priority", {})
    mttf = frozen.get("mean_time_to_fix_days_by_priority", {})
    tests = frozen.get("tests_detail", {})
    budget = frozen.get("budget_detail", {})
    closed_html = _render_closed_table_html(frozen.get("closed_findings", []))
    overdue_html = _render_overdue_table_html(frozen.get("overdue_findings", []))
    apps_html = _render_apps_table_html(frozen.get("applications_detail", []))
    recs = "".join(f"<li>{html.escape(r)}</li>" for r in frozen.get("recommendations", []))
    badge = _badge_class(summary.risk_level)

    return f"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="utf-8"/>
<title>Rempart - Rapport mensuel {html.escape(period)}</title>
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
<body>
<header>
  <h1>Rempart — Rapport Mensuel de Sécurité Continue</h1>
  <div class="meta">Client : <strong>{html.escape(tenant_id)}</strong> | Période : <strong>{html.escape(period)}</strong> | Figé le {html.escape(str(frozen.get('frozen_at', '')))}</div>
</header>

<section>
  <h2>1. Synthèse pour le dirigeant</h2>
  <div class="card">
    <p><strong>Niveau de risque du mois :</strong> <span class="badge badge-{badge}">{html.escape(summary.risk_level)}</span></p>
    <p><strong>Trois faits marquants :</strong></p>
    {_render_highlights_html(summary.highlights)}
    <p><strong>Décision attendue :</strong> {html.escape(summary.expected_decision)}</p>
  </div>
</section>

<section>
  <h2>2. Indicateurs clés (KPIs déterministes)</h2>
  <div class="kpis">
    <div class="kpi"><div class="kpi-val">{frozen.get('delivery_to_result_hours', 0.0)} h</div><div class="kpi-lbl">Délai livraison → résultat</div></div>
    <div class="kpi"><div class="kpi-val">{round(frozen.get('critical_blocked_before_prod', 0.0) * 100, 1)} %</div><div class="kpi-lbl">P1/P2 bloquées avant prod</div></div>
    <div class="kpi"><div class="kpi-val">{round(frozen.get('sla_compliance', 1.0) * 100, 1)} %</div><div class="kpi-lbl">Respect des échéances</div></div>
    <div class="kpi"><div class="kpi-val">{round(frozen.get('coverage', 0.0) * 100, 1)} %</div><div class="kpi-lbl">Couverture des applications</div></div>
  </div>
</section>

<section>
  <h2>3. Nouvelles failles détectées</h2>
  <table>
    <thead><tr><th>Priorité</th><th>Nouvelles failles</th><th>Ouvertes fin de mois</th><th>Délai moyen correction (jours)</th></tr></thead>
    <tbody>
      <tr><td>P1 (Critique)</td><td>{frozen.get('findings_new_by_priority', {}).get('P1', 0)}</td><td>{open_by_p.get('P1', 0)}</td><td>{mttf.get('P1', 0.0)}</td></tr>
      <tr><td>P2 (Élevée)</td><td>{frozen.get('findings_new_by_priority', {}).get('P2', 0)}</td><td>{open_by_p.get('P2', 0)}</td><td>{mttf.get('P2', 0.0)}</td></tr>
      <tr><td>P3 (Moyenne)</td><td>{frozen.get('findings_new_by_priority', {}).get('P3', 0)}</td><td>{open_by_p.get('P3', 0)}</td><td>{mttf.get('P3', 0.0)}</td></tr>
      <tr><td>P4 (Faible)</td><td>{frozen.get('findings_new_by_priority', {}).get('P4', 0)}</td><td>{open_by_p.get('P4', 0)}</td><td>{mttf.get('P4', 0.0)}</td></tr>
    </tbody>
  </table>
</section>

<section>
  <h2>4. Failles corrigées avec preuve</h2>
  {closed_html}
</section>

<section>
  <h2>5. Failles en retard d'échéance</h2>
  {overdue_html}
</section>

<section>
  <h2>6. Tests réalisés</h2>
  <p>Total tests : <strong>{tests.get('tests_total', 0)}</strong> | Livraisons bloquées par la porte CI/CD : <strong>{tests.get('tests_blocked', 0)}</strong></p>
</section>

<section>
  <h2>7. Budget d'heures-tâches</h2>
  <p>Consommées : <strong>{budget.get('task_hours_used', 0.0)} h</strong> / Allouées : <strong>{budget.get('monthly_budget_hours', 0.0)} h</strong> (Restant : <strong>{budget.get('remaining_task_hours', 0.0)} h</strong>, soit {budget.get('budget_used_pct', 0.0)} % utilisé). Coût estimé : <strong>{budget.get('cost_usd', 0.0)} $</strong>.</p>
</section>

<section>
  <h2>8. Recommandations du mois</h2>
  <ul>{recs}</ul>
</section>

<section>
  <h2>9. Annexe technique par application</h2>
  {apps_html}
</section>

<footer>Plateforme Rempart — Tests d'intrusion en continu par abonnement — Tous chiffres calculés de manière déterministe (ENF-IA-01).</footer>
</body>
</html>"""


# --------------------------------------------------------------------------- #
# PDF rendering via fpdf2
# --------------------------------------------------------------------------- #
def _latin(text: str) -> str:
    """Normalize unicode into latin-1 for FPDF core Helvetica font."""
    rep = {
        "—": "-",
        "–": "-",
        "’": "'",
        "‘": "'",
        "“": '"',
        "”": '"',
        "…": "...",
        "\xa0": " ",
        "\u202f": " ",
        "•": "-",
        "→": "->",
        "€": "EUR",
        "é": "e",
        "è": "e",
        "ê": "e",
        "ë": "e",
        "à": "a",
        "â": "a",
        "ô": "o",
        "î": "i",
        "ï": "i",
        "ù": "u",
        "û": "u",
        "ç": "c",
        "É": "E",
        "È": "E",
        "À": "A",
        "Ç": "C",
    }
    for k, v in rep.items():
        text = text.replace(k, v)
    return text.encode("latin-1", "replace").decode("latin-1")


class _ReportPdf(FPDF):
    """Custom FPDF subclass with page headers and footers."""

    def header(self) -> None:
        self.set_font("Helvetica", "B", 8)
        self.set_text_color(100, 116, 139)
        self.cell(0, 5, _latin("REMPART - RAPPORT MENSUEL DE SECURITE CONTINUE"), align="L")
        self.ln(6)

    def footer(self) -> None:
        self.set_y(-12)
        self.set_font("Helvetica", "", 8)
        self.set_text_color(148, 163, 184)
        page_str = _latin(f"Page {self.page_no()}/{{nb}} - Deterministe (ENF-IA-01)")
        self.cell(0, 6, page_str, align="C")


def _pdf_section_title(pdf: FPDF, title: str) -> None:
    pdf.set_font("Helvetica", "B", 11)
    pdf.set_text_color(15, 23, 42)
    pdf.cell(0, 7, _latin(title), new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(30, 41, 59)


def _render_pdf_summary(pdf: FPDF, summary: ExecutiveSummary) -> None:
    _pdf_section_title(pdf, "1. Synthese pour le dirigeant")
    pdf.set_font("Helvetica", "B", 9)
    pdf.cell(0, 5, _latin(f"Niveau de risque : {summary.risk_level}"), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 8)
    for h in summary.highlights:
        pdf.multi_cell(pdf.epw, 4, _latin(f"- {h}"))
    pdf.set_font("Helvetica", "I", 8)
    pdf.multi_cell(pdf.epw, 4, _latin(f"Decision attendue : {summary.expected_decision}"))
    pdf.ln(3)


def _render_pdf_kpis(pdf: FPDF, frozen: dict[str, Any]) -> None:
    _pdf_section_title(pdf, "2. Indicateurs cles (KPIs)")
    pdf.set_font("Helvetica", "", 8)
    rows = [
        ("Delai livraison -> resultat", f"{frozen.get('delivery_to_result_hours', 0.0)} h"),
        ("Failles P1/P2 bloquees avant prod", f"{round(frozen.get('critical_blocked_before_prod', 0.0) * 100, 1)} %"),
        ("Respect des echeances (SLA)", f"{round(frozen.get('sla_compliance', 1.0) * 100, 1)} %"),
        ("Couverture des applications", f"{round(frozen.get('coverage', 0.0) * 100, 1)} %"),
        ("Failles fermees ce mois", f"{frozen.get('findings_closed', 0)}"),
        ("Taux de reouverture", f"{round(frozen.get('reopen_rate', 0.0) * 100, 1)} %"),
        ("Tests realises (bloques)", f"{frozen.get('tests_total', 0)} ({frozen.get('tests_blocked', 0)})"),
        ("Heures-taches / Cout USD", f"{frozen.get('task_hours_used', 0.0)} h / {frozen.get('cost_usd', 0.0)} $"),
    ]
    for lbl, val in rows:
        pdf.set_font("Helvetica", "", 8)
        pdf.cell(120, 5, _latin(lbl), border=1)
        pdf.set_font("Helvetica", "B", 8)
        pdf.cell(60, 5, _latin(val), border=1, new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)


def _render_pdf_findings_table(pdf: FPDF, frozen: dict[str, Any]) -> None:
    _pdf_section_title(pdf, "3. Nouvelles failles et delais de correction")
    open_by_p = frozen.get("findings_open_by_priority", {})
    new_by_p = frozen.get("findings_new_by_priority", {})
    mttf = frozen.get("mean_time_to_fix_days_by_priority", {})
    pdf.set_font("Helvetica", "B", 8)
    pdf.cell(40, 5, _latin("Priorite"), border=1)
    pdf.cell(40, 5, _latin("Nouvelles"), border=1)
    pdf.cell(40, 5, _latin("Ouvertes"), border=1)
    pdf.cell(60, 5, _latin("MTTF moyen (jours)"), border=1, new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 8)
    for p in ("P1", "P2", "P3", "P4"):
        pdf.cell(40, 5, p, border=1)
        pdf.cell(40, 5, str(new_by_p.get(p, 0)), border=1)
        pdf.cell(40, 5, str(open_by_p.get(p, 0)), border=1)
        pdf.cell(60, 5, str(mttf.get(p, 0.0)), border=1, new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)


def _render_pdf_closed_table(pdf: FPDF, closed_items: list[dict[str, Any]]) -> None:
    _pdf_section_title(pdf, "4. Failles corrigees (avec preuve)")
    pdf.set_font("Helvetica", "", 8)
    if not closed_items:
        pdf.cell(0, 5, _latin("Aucune faille fermee sur la periode."), new_x="LMARGIN", new_y="NEXT")
        pdf.ln(2)
        return
    for item in closed_items[:8]:
        proof = str(item.get("proof", ""))[:40]
        line = f"[{item.get('priority')}] {item.get('title')} ({item.get('application')}) -> {proof}"
        pdf.cell(0, 5, _latin(line), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)


def _render_pdf_budget_recs(pdf: FPDF, frozen: dict[str, Any]) -> None:
    _pdf_section_title(pdf, "7 & 8. Budget et Recommandations")
    budget = frozen.get("budget_detail", {})
    pdf.set_font("Helvetica", "", 8)
    b_line = (
        f"Consomme : {budget.get('task_hours_used', 0.0)} h / {budget.get('monthly_budget_hours', 0.0)} h "
        f"(Restant : {budget.get('remaining_task_hours', 0.0)} h). Cout : {budget.get('cost_usd', 0.0)} $."
    )
    pdf.multi_cell(pdf.epw, 4, _latin(b_line))
    for rec in frozen.get("recommendations", []):
        pdf.multi_cell(pdf.epw, 4, _latin(f"- {rec}"))
    pdf.ln(2)


def generate_pdf_report(
    tenant_id: str,
    period: str,
    frozen: dict[str, Any],
    summary: ExecutiveSummary,
) -> bytes:
    """Generate the PDF report matching the Annexe C structure."""
    pdf = _ReportPdf(orientation="P", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=14)
    pdf.add_page()

    pdf.set_font("Helvetica", "B", 14)
    title = f"Rapport Mensuel de Securite - {period}"
    pdf.cell(0, 8, _latin(title), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 9)
    meta = f"Client: {tenant_id}  |  Fige le: {frozen.get('frozen_at', '')}"
    pdf.cell(0, 5, _latin(meta), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)

    _render_pdf_summary(pdf, summary)
    _render_pdf_kpis(pdf, frozen)
    _render_pdf_findings_table(pdf, frozen)
    _render_pdf_closed_table(pdf, frozen.get("closed_findings", []))
    _render_pdf_budget_recs(pdf, frozen)

    return bytes(pdf.output())


# --------------------------------------------------------------------------- #
# Storage & Orchestration
# --------------------------------------------------------------------------- #
def _persist_reports(
    s3: Any | None,
    tenant_id: str,
    report_id: str,
    period: str,
    html_content: str,
    pdf_bytes: bytes,
) -> str:
    """Save the HTML and PDF to S3/FakeS3, returning the canonical S3 key."""
    pdf_key = f"reports/{tenant_id}/{period}/{report_id}.pdf"
    html_key = f"reports/{tenant_id}/{period}/{report_id}.html"
    if s3 is not None:
        bucket = getattr(s3, "bucket_name", "rempart-reports")
        s3.put_object(
            Bucket=bucket,
            Key=pdf_key,
            Body=pdf_bytes,
            ContentType="application/pdf",
        )
        s3.put_object(
            Bucket=bucket,
            Key=html_key,
            Body=html_content.encode("utf-8"),
            ContentType="text/html; charset=utf-8",
        )
    return pdf_key


def build_monthly_report(
    store: Store,
    tenant_id: str,
    period: str,
    model_client: Any | None = None,
    s3: Any | None = None,
) -> Report:
    """Build, generate (HTML+PDF), store and return a monthly Report for tenant."""
    frozen = freeze_month(store, tenant_id=tenant_id, period=period)
    summary = draft_executive_summary(frozen, model_client)

    html_content = generate_html_report(tenant_id, period, frozen, summary)
    pdf_bytes = generate_pdf_report(tenant_id, period, frozen, summary)

    report_id = f"rep-{uuid.uuid4().hex[:12]}"
    s3_key = _persist_reports(s3, tenant_id, report_id, period, html_content, pdf_bytes)

    report = Report(
        report_id=report_id,
        tenant_id=tenant_id,
        period=period,
        s3_key=s3_key,
        kpis=frozen,
        created_at=iso(utcnow()),
    )
    store.save_report(report)
    return report
