"""E-mail templates for Rempart notifications — English bodies (EF-POR-04).

EF-NOT-01 / EF-NOT-02 : une fonction par kind, paramètres explicites, rendant
``(subject, body_html, body_text)``. L'en-tête, le tableau de faits et le pied
de page proviennent d'**un seul** gabarit commun (``_layout``) : zéro
duplication entre les kinds.

ENF-SEC-05 : aucun e-mail ne contient de détail d'exploitation (étapes de
reproduction, script de vérification, preuve brute). Ces fonctions n'acceptent
aucun paramètre ``evidence`` : les détails techniques restent dans le portail,
visibles des seuls rôles habilités. L'e-mail cite le client, l'application, la
faille ou le seuil, la priorité, l'échéance et le lien portail — rien de plus.
"""

from __future__ import annotations

import os
from collections.abc import Sequence
from html import escape

DEFAULT_PORTAL_URL = "https://portal.rempart.example.com"

_SUBJECT_PREFIX = "[Rempart]"
_HEADER = "Rempart — continuous penetration testing"
_FOOTER = (
    "For security reasons, this notification contains no attack details. "
    "Technical evidence is available in the Rempart portal to authorized "
    "roles only."
)

Row = tuple[str, str]
Email = tuple[str, str, str]


def portal_url() -> str:
    """Lien portail cité dans chaque corps (variable ``REMPART_PORTAL_URL``)."""
    return os.environ.get("REMPART_PORTAL_URL") or DEFAULT_PORTAL_URL


def _layout(
    *,
    subject: str,
    headline: str,
    intro: str,
    facts: Sequence[Row],
    portal: str,
) -> Email:
    """Gabarit commun : rend sujet, corps HTML et corps texte depuis les faits."""
    html_rows = "".join(
        f"<tr><th align='left'>{escape(label)}</th><td>{escape(value)}</td></tr>"
        for label, value in facts
    )
    body_html = (
        f"<html><body style='font-family:sans-serif;color:#1a202c'>"
        f"<h2>{escape(headline)}</h2>"
        f"<p>{escape(intro)}</p>"
        f"<table cellpadding='4' style='border-collapse:collapse'>{html_rows}</table>"
        f"<p><a href='{escape(portal)}'>Open the Rempart portal</a></p>"
        f"<hr><p style='font-size:12px;color:#4a5568'>{escape(_FOOTER)}</p>"
        f"<p style='font-size:12px;color:#4a5568'>{escape(_HEADER)}</p>"
        f"</body></html>"
    )
    text_lines = [headline, "", intro, ""]
    text_lines += [f"{label}: {value}" for label, value in facts]
    text_lines += ["", f"Portal: {portal}", "", _FOOTER, _HEADER]
    return f"{_SUBJECT_PREFIX} {subject}", body_html, "\n".join(text_lines)


def _common_facts(
    *,
    client: str,
    application: str,
    priority: str,
    due_at: str,
    extra: Sequence[Row] = (),
) -> list[Row]:
    """Faits obligatoires de tout corps : client, application, priorité, échéance."""
    return [
        ("Client", client),
        ("Application", application),
        *extra,
        ("Priority", priority),
        ("Due date", due_at),
    ]


def critical_finding_confirmed(
    *,
    client: str,
    application: str,
    finding_title: str,
    finding_id: str,
    priority: str,
    due_at: str,
    portal: str | None = None,
) -> Email:
    """EF-NOT-01 — a P1/P2 finding has been confirmed by triage."""
    return _layout(
        subject=f"{priority} finding confirmed — {application}",
        headline=f"{priority} finding confirmed: {finding_title}",
        intro=(
            f"A {priority} finding was confirmed on {application} for {client}. "
            "Remediation should start now; technical details are in the portal."
        ),
        facts=_common_facts(
            client=client,
            application=application,
            priority=priority,
            due_at=due_at,
            extra=[("Finding", f"{finding_title} ({finding_id})")],
        ),
        portal=portal or portal_url(),
    )


def delivery_blocked(
    *,
    client: str,
    application: str,
    blocking_threshold: str,
    finding_title: str,
    priority: str,
    due_at: str,
    portal: str | None = None,
) -> Email:
    """EF-NOT-01 — a delivery is blocked by the blocking threshold."""
    return _layout(
        subject=f"Delivery blocked — {application}",
        headline=f"Delivery blocked on {application}",
        intro=(
            f"Delivery of {application} for {client} is blocked: the finding "
            f"'{finding_title}' meets the blocking threshold "
            f"({blocking_threshold}). Review it in the portal to unblock."
        ),
        facts=_common_facts(
            client=client,
            application=application,
            priority=priority,
            due_at=due_at,
            extra=[
                ("Blocked by", finding_title),
                ("Blocking threshold", blocking_threshold),
            ],
        ),
        portal=portal or portal_url(),
    )


def deadline_overdue(
    *,
    client: str,
    application: str,
    finding_title: str,
    priority: str,
    due_at: str,
    days_overdue: int,
    portal: str | None = None,
) -> Email:
    """EF-NOT-01 — a remediation deadline has passed."""
    return _layout(
        subject=f"Remediation deadline overdue — {application}",
        headline=f"Remediation overdue by {days_overdue} day(s): {finding_title}",
        intro=(
            f"The remediation deadline for '{finding_title}' on {application} "
            f"({client}) passed on {due_at}. Please update the status in the "
            "portal or request a risk acceptance review."
        ),
        facts=_common_facts(
            client=client,
            application=application,
            priority=priority,
            due_at=due_at,
            extra=[
                ("Finding", finding_title),
                ("Days overdue", str(days_overdue)),
            ],
        ),
        portal=portal or portal_url(),
    )


def budget_threshold(
    *,
    client: str,
    threshold_percent: int,
    hours_used: float,
    monthly_budget_hours: float,
    month: str,
    portal: str | None = None,
) -> Email:
    """EF-NOT-01 — the monthly task-hour budget crossed a threshold (50/80/100 %)."""
    return _layout(
        subject=f"Budget threshold {threshold_percent}% reached",
        headline=f"Monthly budget at {threshold_percent}% for {client}",
        intro=(
            f"The task-hour budget of {client} for {month} reached "
            f"{threshold_percent}% ({hours_used:g} of {monthly_budget_hours:g} hours). "
            "Testing stops automatically at 100% unless adjusted in the portal."
        ),
        facts=[
            ("Client", client),
            ("Application", "All applications"),
            ("Threshold", f"{threshold_percent}%"),
            ("Hours used", f"{hours_used:g} / {monthly_budget_hours:g}"),
            ("Period", month),
        ],
        portal=portal or portal_url(),
    )


def weekly_digest(
    *,
    client: str,
    period: str,
    tests_run: int,
    findings_opened: int,
    findings_closed: int,
    overdue: int,
    hours_used: float,
    portal: str | None = None,
) -> Email:
    """EF-NOT-02 (S) — weekly summary. Rendered on demand; not scheduled yet."""
    return _layout(
        subject=f"Weekly security digest — {period}",
        headline=f"Weekly digest for {client} ({period})",
        intro=(
            f"Summary of continuous testing activity for {client} over {period}. "
            "Open the portal for the full dashboard and every finding."
        ),
        facts=[
            ("Client", client),
            ("Period", period),
            ("Tests run", str(tests_run)),
            ("Findings opened", str(findings_opened)),
            ("Findings closed", str(findings_closed)),
            ("Overdue findings", str(overdue)),
            ("Task hours used", f"{hours_used:g}"),
        ],
        portal=portal or portal_url(),
    )
