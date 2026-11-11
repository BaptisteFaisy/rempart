"""PDF rendering of the monthly report via fpdf2 (EF-RAP-03, annexe C)."""

from typing import Any

from fpdf import FPDF

from rempart.reports.summary import ExecutiveSummary


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


