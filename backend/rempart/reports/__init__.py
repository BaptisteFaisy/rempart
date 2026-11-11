"""Rempart reports module: deterministic KPIs and monthly report generation."""

from .metrics import compute_kpis, freeze_month
from .monthly import build_monthly_report, generate_html_report, generate_pdf_report

__all__ = [
    "compute_kpis",
    "freeze_month",
    "build_monthly_report",
    "generate_html_report",
    "generate_pdf_report",
]
