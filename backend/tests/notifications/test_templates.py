"""Tests des gabarits d'e-mail — mentions obligatoires et ENF-SEC-05."""

from __future__ import annotations

import pytest

from rempart.notifications import templates

PORTAL = "https://portal.rempart.test"

# Chaînes qui trahiraient un détail d'exploitation (ENF-SEC-05). Le pied de
# page commun et les corps ne doivent jamais les contenir.
FORBIDDEN = (
    "reproduce",
    "reproduction",
    "verification script",
    "curl ",
    "sqlmap",
    "nmap",
    "Step 1",
    "OR 1=1",
    "<script",
)

CASES: dict[str, dict[str, object]] = {
    "critical_finding_confirmed": {
        "client": "Acme",
        "application": "ShopLite",
        "finding_title": "SQL injection on /login",
        "finding_id": "f-1",
        "priority": "P1",
        "due_at": "2026-11-20T00:00:00Z",
        "portal": PORTAL,
    },
    "delivery_blocked": {
        "client": "Acme",
        "application": "ShopLite",
        "blocking_threshold": "P2",
        "finding_title": "Stored XSS on reviews",
        "priority": "P2",
        "due_at": "2026-11-25T00:00:00Z",
        "portal": PORTAL,
    },
    "deadline_overdue": {
        "client": "Acme",
        "application": "ShopLite",
        "finding_title": "Open S3 bucket",
        "priority": "P2",
        "due_at": "2026-11-01T00:00:00Z",
        "days_overdue": 9,
        "portal": PORTAL,
    },
    "budget_threshold": {
        "client": "Acme",
        "threshold_percent": 80,
        "hours_used": 16.0,
        "monthly_budget_hours": 20.0,
        "month": "2026-11",
        "portal": PORTAL,
    },
    "weekly_digest": {
        "client": "Acme",
        "period": "2026-W45",
        "tests_run": 4,
        "findings_opened": 2,
        "findings_closed": 1,
        "overdue": 1,
        "hours_used": 7.5,
        "portal": PORTAL,
    },
}


def _render(kind: str) -> tuple[str, str, str]:
    return getattr(templates, kind)(**CASES[kind])  # type: ignore[arg-type]


@pytest.mark.parametrize("kind", sorted(CASES))
def test_renders_subject_html_and_text_in_english(kind: str) -> None:
    subject, body_html, body_text = _render(kind)
    assert subject.startswith("[Rempart]")
    assert body_html.startswith("<html>")
    assert "Acme" in body_html and "Acme" in body_text
    assert PORTAL in body_html and PORTAL in body_text


@pytest.mark.parametrize("kind", sorted(CASES))
def test_html_and_text_share_the_same_facts(kind: str) -> None:
    _, body_html, body_text = _render(kind)
    # Le gabarit commun : chaque fait du texte apparaît aussi dans le HTML.
    # (La ligne « Portal: » du texte est un lien <a> côté HTML, déjà vérifié.)
    for line in body_text.splitlines():
        if ": " in line and line != body_text.splitlines()[0]:
            label, value = line.split(": ", 1)
            if label in {"Client", "Application", "Priority", "Due date"}:
                assert label in body_html
                assert value in body_html


@pytest.mark.parametrize(
    ("kind", "expected"),
    [
        ("critical_finding_confirmed", ("ShopLite", "SQL injection on /login", "P1", "2026-11-20")),
        ("delivery_blocked", ("ShopLite", "Stored XSS on reviews", "P2", "2026-11-25")),
        ("deadline_overdue", ("ShopLite", "Open S3 bucket", "P2", "2026-11-01", "9")),
        ("budget_threshold", ("80%", "16 / 20", "2026-11", "All applications")),
        ("weekly_digest", ("2026-W45", "4", "2", "1", "7.5")),
    ],
)
def test_mandatory_mentions(kind: str, expected: tuple[str, ...]) -> None:
    subject, body_html, body_text = _render(kind)
    combined = f"{subject}\n{body_html}\n{body_text}"
    for mention in expected:
        assert mention in combined, f"{kind}: mention obligatoire {mention!r} absente"


@pytest.mark.parametrize("kind", sorted(CASES))
def test_no_exploitation_details(kind: str) -> None:
    """ENF-SEC-05 : aucune étape, aucun script, aucune preuve dans l'e-mail."""
    subject, body_html, body_text = _render(kind)
    combined = f"{subject}\n{body_html}\n{body_text}".lower()
    for token in FORBIDDEN:
        assert token.lower() not in combined, f"{kind}: détail d'exploitation {token!r}"


def test_html_escapes_untrusted_values() -> None:
    """Un titre de faille hostile ne peut pas injecter de HTML."""
    params = dict(CASES["critical_finding_confirmed"])
    params["finding_title"] = "<script>alert('xss')</script>"
    subject, body_html, body_text = templates.critical_finding_confirmed(**params)  # type: ignore[arg-type]
    assert "<script>" not in body_html
    assert "&lt;script&gt;" in body_html
    assert "<script>" in body_text  # le corps texte est inoffensif
    assert "<script>" not in subject


def test_portal_url_defaults_to_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("REMPART_PORTAL_URL", "https://custom.example.org")
    assert templates.portal_url() == "https://custom.example.org"
    monkeypatch.delenv("REMPART_PORTAL_URL")
    assert templates.portal_url() == templates.DEFAULT_PORTAL_URL


def test_common_footer_in_every_kind() -> None:
    """Le pied de page commun (facteur unique) est présent partout."""
    for kind in CASES:
        _, body_html, body_text = _render(kind)
        assert "no attack details" in body_html
        assert "no attack details" in body_text
