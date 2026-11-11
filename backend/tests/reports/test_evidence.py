"""Tests du dossier de preuves exportable (EF-RAP-04, ISO 27001 / SOC 2).

Vérifie les trois propriétés qui rendent le dossier probant : autoportant,
déterministe, scellé — plus les deux garde-fous transverses : aucun détail
d'exploitation ne sort (ENF-SEC-05) et rien ne fuit d'un client à l'autre.
"""

from __future__ import annotations

import hashlib
import json

import pytest

from rempart.reports.evidence import (
    build_and_upload,
    build_evidence_pack,
    integrity_digest,
    render_evidence_pack_html,
    render_evidence_pack_json,
    seal_evidence_pack,
)
from rempart.reports.metrics import freeze_month
from tests.fakes import FakeS3
from tests.fakes_store import FakeStore
from tests.reports.conftest import (
    PERIOD,
    _seed_other_tenant,
    _seed_primary,
    make_finding,
)

TENANT = "t-1"
OTHER_TENANT = "t-2"
GENERATED_AT = "2026-11-03T06:00:00Z"


@pytest.fixture
def seeded() -> FakeStore:
    store = FakeStore()
    _seed_primary(store)
    _seed_other_tenant(store)
    return store


def _pack(store: FakeStore, tenant_id: str = TENANT) -> dict:
    return build_evidence_pack(
        store=store, tenant_id=tenant_id, period=PERIOD, generated_at=GENERATED_AT
    )


def test_pack_is_self_contained(seeded):
    pack = _pack(seeded)
    for section in (
        "identity",
        "scope",
        "tests",
        "decision_chains",
        "closure_proofs",
        "exceptions",
        "audit_events",
        "kpis",
        "ai_guardrails",
    ):
        assert section in pack, f"section manquante : {section}"
    assert pack["identity"]["tenant_id"] == TENANT
    assert pack["identity"]["generated_at"] == GENERATED_AT
    assert pack["identity"]["evidence_version"]


def test_scope_lists_applications_and_domains(seeded):
    pack = _pack(seeded)
    assert pack["scope"], "le périmètre ne doit pas être vide"
    assert all("domains" in app and "app_id" in app for app in pack["scope"])


def test_kpis_are_identical_to_the_monthly_report(seeded):
    """R10 : le dossier d'audit et le tableau de bord disent la même chose."""
    pack = _pack(seeded)
    frozen = freeze_month(seeded, tenant_id=TENANT, period=PERIOD)
    assert pack["kpis"] == frozen


def test_decision_chain_is_ordered_and_attributed(seeded):
    pack = _pack(seeded)
    assert pack["decision_chains"], "aucune chaîne de décision"
    for entry in pack["decision_chains"]:
        assert "finding" in entry and "decisions" in entry
        stamps = [d["created_at"] for d in entry["decisions"]]
        assert stamps == sorted(stamps), "la chaîne doit être chronologique"
        for decision in entry["decisions"]:
            assert decision["author_type"] in ("agent", "human")
            assert decision["author"]


def test_closure_proofs_reference_the_retest_run(seeded):
    pack = _pack(seeded)
    for proof in pack["closure_proofs"]:
        assert proof["proven_by_run_id"], "une fermeture sans identifiant de retest"
        assert proof["closed_at"]


def test_no_exploitation_detail_leaves_the_pack(seeded):
    """ENF-SEC-05 : ni étapes de reproduction ni script de vérification."""
    pack = _pack(seeded)
    serialized = render_evidence_pack_json(pack).lower()
    assert "evidence" not in [
        key for entry in pack["decision_chains"] for key in entry["finding"]
    ], "le champ Finding.evidence ne doit pas être exporté"
    for forbidden in ("reproduction_steps", "verification_script", "exploit_payload"):
        assert forbidden not in serialized


def test_ai_guardrails_are_asserted_not_claimed(seeded):
    pack = _pack(seeded)
    guardrails = pack["ai_guardrails"]
    assert guardrails["model_can_dismiss_critical"] is False
    assert guardrails["priority_source"]
    # Aucune faille critique écartée sans décision humaine dans le jeu de référence.
    assert guardrails["critical_dismissed_without_human"] == []


def test_json_rendering_is_deterministic(seeded):
    pack = _pack(seeded)
    first = render_evidence_pack_json(pack)
    second = render_evidence_pack_json(pack)
    assert first == second
    assert json.loads(first) == pack


def test_integrity_digest_is_stable_and_content_sensitive(seeded):
    pack = _pack(seeded)
    digest = integrity_digest(pack)
    assert len(digest) == 64
    assert digest == integrity_digest(_pack(seeded))  # mêmes données → même empreinte

    tampered = json.loads(render_evidence_pack_json(pack))
    tampered["identity"]["tenant_name"] = "Another Company"
    assert integrity_digest(tampered) != digest


def test_digest_can_be_recomputed_by_an_auditor(seeded):
    """La méthode de recalcul documentée doit réellement fonctionner."""
    sealed = seal_evidence_pack(_pack(seeded))
    payload = {k: v for k, v in sealed.items() if k != "integrity"}
    recomputed = hashlib.sha256(
        render_evidence_pack_json(payload).encode("utf-8")
    ).hexdigest()
    assert recomputed == sealed["integrity"]["digest"]
    assert sealed["integrity"]["algorithm"] == "sha256"


def test_sealed_pack_keeps_every_section(seeded):
    sealed = seal_evidence_pack(_pack(seeded))
    assert sealed["identity"]["tenant_id"] == TENANT
    assert sealed["decision_chains"]
    assert "integrity" in sealed


def test_html_renders_the_sections_without_external_asset(seeded):
    sealed = seal_evidence_pack(_pack(seeded))
    html = render_evidence_pack_html(sealed)
    assert html.startswith("<!DOCTYPE html>")
    # Aucune ressource externe chargée : le dossier doit rester lisible hors
    # ligne, des années plus tard, sans dépendre d'un CDN.
    for tag in ("<script", "<link", "<img", "<iframe"):
        assert tag not in html, f"{tag} rendrait le dossier dépendant du réseau"
    assert sealed["integrity"]["digest"] in html
    for title in ("Identity", "Scope", "Closure proofs", "Audit events"):
        assert title in html


def test_pack_of_one_tenant_contains_nothing_from_the_other(seeded):
    pack = _pack(seeded)
    serialized = render_evidence_pack_json(pack)
    assert OTHER_TENANT not in serialized
    for entry in pack["decision_chains"]:
        assert entry["finding"]["tenant_id"] == TENANT
    for run in pack["tests"]:
        assert run["tenant_id"] == TENANT


def test_exceptions_are_listed_with_their_author(seeded):
    seeded.save_finding(
        make_finding(
            "f-risk",
            "app-a",
            run_id="run-2",
            priority="P3",
            status="risk_accepted",
            created_at="2026-10-11T10:00:00Z",
            title="Accepted risk",
        )
    )
    pack = _pack(seeded)
    accepted = pack["exceptions"]["risk_accepted"]
    assert any(item["finding_id"] == "f-risk" for item in accepted)


def test_upload_writes_json_and_html(seeded):
    s3 = FakeS3()
    sealed = build_and_upload(
        store=seeded, tenant_id=TENANT, period=PERIOD, s3=s3, generated_at=GENERATED_AT
    )
    assert sealed["s3_key"].startswith(f"evidence/{TENANT}/{PERIOD}/")
    keys = list(s3.objects)
    assert any(k.endswith(".json") for k in keys)
    assert any(k.endswith(".html") for k in keys)
    assert sealed["integrity"]["digest"]


def test_build_without_s3_still_seals_the_pack(seeded):
    sealed = build_and_upload(
        store=seeded, tenant_id=TENANT, period=PERIOD, generated_at=GENERATED_AT
    )
    assert sealed["integrity"]["digest"]
    assert sealed["s3_key"]
