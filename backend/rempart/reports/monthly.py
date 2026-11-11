"""Monthly report orchestration: freeze KPIs, draft summary, render, persist.

The rendering lives in :mod:`rempart.reports.html_renderer` and
:mod:`rempart.reports.pdf_renderer`; the executive summary in
:mod:`rempart.reports.summary` (EF-RAP-03, annexe C).
"""

import uuid
from typing import Any

from rempart.common.models import Report
from rempart.common.store import Store
from rempart.common.timeutil import iso, utcnow
from rempart.reports.html_renderer import generate_html_report
from rempart.reports.metrics import freeze_month
from rempart.reports.pdf_renderer import generate_pdf_report
from rempart.reports.summary import ExecutiveSummary, draft_executive_summary

__all__ = [
    "ExecutiveSummary",
    "build_monthly_report",
    "draft_executive_summary",
    "generate_html_report",
    "generate_pdf_report",
]


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

