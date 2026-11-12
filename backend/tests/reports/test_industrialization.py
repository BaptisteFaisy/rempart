"""Tests des métriques d'industrialisation (#68, #26, #47, #34).

Jeu de référence identique partout, résultats calculés à la main dans chaque
test : 6 failles du tenant t-1 en octobre 2026, 5 propositions d'agent et 5
décisions humaines, plus une faille hors période et une d'un autre tenant.
"""

import json
from dataclasses import replace
from datetime import datetime, timezone

import pytest

from rempart.common.models import Decision, TestConfig
from rempart.reports.industrialization import (
    alert_fatigue_indicators,
    analyst_minutes_saved,
    corpus_json,
    corpus_statistics,
    export_training_corpus,
    human_intervention_rate,
)
from tests.fakes import FakeStore
from tests.reports.conftest import make_app, make_finding, make_tenant

PERIOD = "2026-10"
NOW = datetime(2026, 11, 11, tzinfo=timezone.utc)

# Contenus identifiants,plantés pour vérifier l'anonymisation de l'export.
RAW_TITLE = "Injection SQL sur /api/orders de ShopLite (client Acme)"
RAW_HOST = "shop.acme-client.example.com"
RAW_TOKEN = "token=SECRET123"
RAW_AUTHOR = "marie.analyste@acme-client.example.com"
RAW_JUSTIFICATION = "confirmé après échange avec l'équipe Shop"
EXCLUDED_KEYS = ("title", "evidence", "cvss", "fingerprint", "justification", "author", "steps")


def make_decision(
    finding_id: str,
    *,
    author_type: str = "human",
    action: str = "confirmed",
    created_at: str = "2026-10-05T11:00:00Z",
) -> Decision:
    """Build a decision ; human decisions carry identifiable content on purpose."""
    human = author_type == "human"
    return Decision(
        decision_id=f"dec-{finding_id}-{created_at}",
        finding_id=finding_id,
        author_type=author_type,
        author=RAW_AUTHOR if human else "triage-agent",
        action=action,
        justification=RAW_JUSTIFICATION if human else "Sévérité High, confiance High.",
        created_at=created_at,
    )


def make_raw_finding(
    finding_id: str,
    *,
    risk_type: str = "injection",
    created_at: str = "2026-10-05T09:00:00Z",
    tenant_id: str = "t-1",
    app_id: str = "app-a",
):
    """Build a finding whose raw content identifies the client."""
    return replace(
        make_finding(finding_id, app_id, tenant_id=tenant_id, created_at=created_at,
                     title=RAW_TITLE),
        risk_type=risk_type,
        evidence={
            "steps": [f"POST https://{RAW_HOST}/api/orders payload ' OR 1=1--"],
            "entry_point": f"https://{RAW_HOST}/api/orders?{RAW_TOKEN}",
        },
        cvss={"score": 8.1, "vector": f"CVSS:3.1/AV:N/{RAW_HOST}"},
    )


def _seed_entities(store: FakeStore) -> None:
    """Tenants, applications, configurations et runs du jeu de référence."""
    store.save_tenant(make_tenant("t-1"))
    store.save_tenant(make_tenant("t-2"))
    store.save_application(make_app("app-a", "t-1", name="ShopLite"))
    store.save_application(make_app("app-z", "t-2", name="AutreClient"))
    store.save_config(
        TestConfig(
            config_id="cfg-a",
            app_id="app-a",
            sa_pentest_id="sa-1",
            kind="dast",
            scope={},
            risk_types=["injection", "crypto", "xss", "ssrf"],
            blocking_threshold="P2",
            schedule=None,
        )
    )


def _seed_findings(store: FakeStore) -> None:
    """Failles couvrant les statuts du cycle de vie (§ 11.5)."""
    for finding_id, risk_type, created_at in (
        ("f-1", "injection", "2026-10-05T09:00:00Z"),
        ("f-2", "crypto", "2026-10-07T09:00:00Z"),
        ("f-3", "xss", "2026-10-09T09:00:00Z"),
        ("f-4", "injection", "2026-10-11T09:00:00Z"),
        ("f-5", "xss", "2026-10-15T09:00:00Z"),
        ("f-6", "crypto", "2026-10-20T09:00:00Z"),
        ("f-7", "injection", "2026-11-03T09:00:00Z"),
    ):
        store.save_finding(
            make_raw_finding(finding_id, risk_type=risk_type, created_at=created_at)
        )
    store.save_finding(
        make_raw_finding("f-z", created_at="2026-10-05T09:00:00Z", tenant_id="t-2", app_id="app-z")
    )
    # f-1 : l'agent propose CONFIRMED, l'analyste confirme -> simple validation.


def _seed_decisions(store: FakeStore) -> None:
    """Décisions agent puis humain : la divergence est ce qu'on mesure."""
    store.save_decision(make_decision("f-1", author_type="agent", action="CONFIRMED",
                                       created_at="2026-10-05T10:00:00Z"))
    store.save_decision(make_decision("f-1", action="confirmed", created_at="2026-10-05T11:00:00Z"))
    # f-2 : l'agent propose CONFIRMED, l'analyste tranche faux positif -> divergence.
    store.save_decision(make_decision("f-2", author_type="agent", action="CONFIRMED",
                                       created_at="2026-10-07T10:00:00Z"))
    store.save_decision(make_decision("f-2", action="false_positive",
                                       created_at="2026-10-07T11:00:00Z"))
    # f-3 : judgement humain seul, sans proposition d'agent -> non comparable.
    store.save_decision(make_decision("f-3", action="confirmed", created_at="2026-10-09T09:00:00Z"))
    # f-4 : proposition d'agent seule -> triée automatiquement.
    store.save_decision(make_decision("f-4", author_type="agent", action="CONFIRMED",
                                       created_at="2026-10-11T10:00:00Z"))
    # f-5 : l'agent demande vérification, l'analyste confirme la demande -> validation.
    store.save_decision(make_decision("f-5", author_type="agent", action="TO_VERIFY",
                                       created_at="2026-10-15T10:00:00Z"))
    store.save_decision(make_decision("f-5", action="pending_validation",
                                       created_at="2026-10-15T11:00:00Z"))
    # f-6 : l'agent propose un faux positif, l'analyste accepte le risque -> divergence.
    store.save_decision(make_decision("f-6", author_type="agent",
                                       action="LIKELY_FALSE_POSITIVE",
                                       created_at="2026-10-20T10:00:00Z"))
    store.save_decision(make_decision("f-6", action="risk_accepted",
                                       created_at="2026-10-20T11:00:00Z"))
    # f-7 : décision humaine de novembre (hors période d'octobre).
    store.save_decision(make_decision("f-7", action="confirmed", created_at="2026-11-03T09:00:00Z"))
    # f-z : autre tenant, ne doit jamais apparaître dans l'export de t-1.
    store.save_decision(make_decision("f-z", action="confirmed", created_at="2026-10-05T11:00:00Z"))


def seed_reference(store: FakeStore) -> None:
    """Seed the reference dataset (see the module docstring)."""
    _seed_entities(store)
    _seed_findings(store)
    _seed_decisions(store)

@pytest.fixture
def industrial_store() -> FakeStore:
    """Return the seeded reference store (two tenants)."""
    store = FakeStore()
    seed_reference(store)
    return store


def make_fatigue_store(count: int, *, unchanged: int, day: str = "2026-10-06") -> FakeStore:
    """Build a store with ``count`` validations on a single day.

    ``unchanged`` of them confirm the agent (rubber-stamp), the others correct
    it (divergence).
    """
    store = FakeStore()
    store.save_tenant(make_tenant("t-1"))
    store.save_application(make_app("app-a", "t-1", name="ShopLite"))
    for index in range(count):
        finding_id = f"g-{index}"
        store.save_finding(make_raw_finding(finding_id, created_at=f"{day}T08:00:00Z"))
        store.save_decision(make_decision(finding_id, author_type="agent", action="CONFIRMED",
                                           created_at=f"{day}T09:00:00Z"))
        action = "confirmed" if index < unchanged else "false_positive"
        store.save_decision(make_decision(finding_id, action=action, created_at=f"{day}T10:00:00Z"))
    return store


# --------------------------------------------------------------------------- #
# #68 — taux d'intervention humaine
# --------------------------------------------------------------------------- #
def test_human_intervention_rate_on_a_known_dataset(industrial_store):
    # 6 failles créées en octobre (f-1..f-6) ; 5 ont reçu une décision humaine
    # (f-1, f-2, f-3, f-5, f-6) -> 5/6 = 0.8333.
    rate = human_intervention_rate(industrial_store, tenant_id="t-1", period=PERIOD)
    assert rate["findings_total"] == 6
    assert rate["findings_with_human_decision"] == 5
    assert rate["human_intervention_rate"] == round(5 / 6, 4)
    assert rate["human_decisions"] == 5
    assert rate["agent_decisions"] == 5


def test_divergence_is_distinguished_from_a_plain_validation(industrial_store):
    # L'agent a proposé sur 5 failles ; l'humain a jugé 4 d'entre elles de façon
    # comparable : f-1 et f-5 ne changent rien (validations), f-2 et f-6
    # changent le verdict (divergences) -> 2/4 = 0.5 d'accord, 2/6 = 0.3333
    # de divergences sur l'ensemble des failles.
    rate = human_intervention_rate(industrial_store, tenant_id="t-1", period=PERIOD)
    assert rate["findings_with_agent_proposal"] == 5
    assert rate["findings_reviewed_by_human"] == 4
    assert rate["findings_diverged"] == 2
    assert rate["divergence_rate_among_reviewed"] == 0.5
    assert rate["agent_agreement_rate_on_reviewed"] == 0.5
    assert rate["agent_human_divergence_rate"] == round(2 / 6, 4)
    # Une simple validation n'est PAS comptée comme une divergence.
    assert rate["findings_diverged"] != rate["findings_with_human_decision"]
    # La décision humaine de f-3 (aucune proposition d'agent avant) n'est pas
    # comparable : elle ne compte ni comme validation inchangée ni comme
    # divergence, elle est signalée à part.
    assert rate["human_decisions_not_comparable"] == 1


def test_monthly_volume_gives_the_absolute_numbers(industrial_store):
    # Volume absolu par mois : 6 failles détectées, 5 interventions humaines,
    # 2 divergences.
    rate = human_intervention_rate(industrial_store, tenant_id="t-1", period=PERIOD)
    assert rate["monthly_volume"] == {
        "2026-10": {"findings": 6, "human_intervened": 5, "diverged": 2}
    }
    assert rate["monthly_human_decisions"] == {"2026-10": 5}
    assert "human_intervention_rate" in rate["formulas"]


def test_findings_outside_the_period_are_not_counted(industrial_store):
    # f-7 est créée le 3 novembre : hors période, elle n'entre pas dans le calcul.
    rate = human_intervention_rate(industrial_store, tenant_id="t-1", period=PERIOD)
    assert rate["findings_total"] == 6
    without_period = human_intervention_rate(industrial_store, tenant_id="t-1")
    assert without_period["findings_total"] == 7
    assert without_period["human_intervention_rate"] == round(6 / 7, 4)


def test_human_intervention_rate_is_tenant_scoped(industrial_store):
    # f-z (tenant t-2) n'entre pas dans le calcul de t-1.
    rate = human_intervention_rate(industrial_store, tenant_id="t-1", period=PERIOD)
    assert rate["findings_total"] == 6
    other = human_intervention_rate(industrial_store, tenant_id="t-2", period=PERIOD)
    assert other["findings_total"] == 1
    assert other["human_intervention_rate"] == 1.0


# --------------------------------------------------------------------------- #
# #26 — fatigue d'alerte
# --------------------------------------------------------------------------- #
def test_alert_fatigue_indicators_on_a_known_dataset(industrial_store):
    # 5 validations humaines en octobre, sur 5 jours distincts -> 1,0 par jour
    # actif et 5/31 = 0,161 par jour calendaire. 4 validations comparables :
    # 2 inchangées (f-1, f-5) et 2 divergentes (f-2, f-6) -> ratio 0,5.
    fatigue = alert_fatigue_indicators(industrial_store, tenant_id="t-1", period=PERIOD)
    assert fatigue["human_validations"] == 5
    assert fatigue["active_days"] == 5
    assert fatigue["validations_per_active_day"] == 1.0
    assert fatigue["validations_per_calendar_day"] == round(5 / 31, 3)
    assert fatigue["comparable_validations"] == 4
    assert fatigue["unchanged_validations"] == 2
    assert fatigue["diverged_validations"] == 2
    assert fatigue["no_change_validation_ratio"] == 0.5
    # 0,5 x min(1 ; 1,0/40) = 0,0125
    assert fatigue["fatigue_score"] == 0.0125


def test_fatigue_indicators_are_bounded(industrial_store):
    fatigue = alert_fatigue_indicators(industrial_store, tenant_id="t-1", period=PERIOD)
    assert 0.0 <= fatigue["fatigue_score"] <= 1.0
    assert 0.0 <= fatigue["no_change_validation_ratio"] <= 1.0


def test_no_alert_on_a_healthy_dataset(industrial_store):
    # Ratio 0,5 = seuil (non dépassé), 1 validation/jour << 40 -> pas d'alerte.
    fatigue = alert_fatigue_indicators(industrial_store, tenant_id="t-1", period=PERIOD)
    assert fatigue["alert_triggered"] is False
    assert fatigue["alert_reasons"] == []


def test_alert_triggered_when_almost_every_validation_changes_nothing():
    # 10 validations, toutes inchangées -> ratio 1,0 > 0,5 -> alerte.
    store = make_fatigue_store(10, unchanged=10)
    fatigue = alert_fatigue_indicators(store, tenant_id="t-1", period=PERIOD)
    assert fatigue["no_change_validation_ratio"] == 1.0
    assert fatigue["alert_triggered"] is True
    assert any("rien changé" in reason for reason in fatigue["alert_reasons"])


def test_alert_triggered_when_the_queue_is_too_long():
    # 41 validations dans la journée -> 41 > 40 -> alerte de volume, alors que
    # le ratio de validations inchangées reste faible (1/41).
    store = make_fatigue_store(41, unchanged=1)
    fatigue = alert_fatigue_indicators(store, tenant_id="t-1", period=PERIOD)
    assert fatigue["validations_per_active_day"] == 41.0
    assert fatigue["no_change_validation_ratio"] == round(1 / 41, 4)
    assert fatigue["alert_triggered"] is True
    assert any("file" in reason for reason in fatigue["alert_reasons"])


def test_no_alert_exactly_at_the_volume_threshold():
    # 40 validations dans la journée : le seuil est dépassé strictement, donc
    # pas d'alerte de volume ; le ratio est nul, donc pas d'alerte non plus.
    store = make_fatigue_store(40, unchanged=0)
    fatigue = alert_fatigue_indicators(store, tenant_id="t-1", period=PERIOD)
    assert fatigue["validations_per_active_day"] == 40.0
    assert fatigue["alert_triggered"] is False


def test_fatigue_window_follows_the_injected_clock(industrial_store):
    # Sans période, la fenêtre est les 30 jours précédant `now` :
    # 2026-10-12 -> 2026-11-11, soit f-5, f-6 et f-7 (3 validations).
    fatigue = alert_fatigue_indicators(industrial_store, tenant_id="t-1", now=NOW)
    assert fatigue["human_validations"] == 3
    assert fatigue["comparable_validations"] == 2
    # Une fenêtre sans aucune validation n'est pas mesurable : ratio absent.
    empty = alert_fatigue_indicators(industrial_store, tenant_id="t-1",
                                     now=datetime(2026, 1, 1, tzinfo=timezone.utc))
    assert empty["human_validations"] == 0
    assert empty["no_change_validation_ratio"] is None


# --------------------------------------------------------------------------- #
# #47 — temps analyste économisé
# --------------------------------------------------------------------------- #
def test_analyst_minutes_saved_marks_its_hypotheses_as_assumptions(industrial_store):
    # 6 failles triées sur la période ; 5 vues par un humain (5 x 12 min) et
    # 1 triée par l'agent seul (1 x 1 min) -> 72 - 61 = 11 minutes économisées.
    saved = analyst_minutes_saved(industrial_store, tenant_id="t-1", period=PERIOD)
    assert saved["findings_triaged"] == 6
    assert saved["findings_automatically_triaged"] == 1
    assert saved["findings_reviewed_by_human"] == 5
    assert saved["manual_minutes_if_all_human"] == 72.0
    assert saved["estimated_minutes_spent"] == 61.0
    assert saved["minutes_saved"] == 11.0
    assert saved["hours_saved"] == round(11 / 60, 2)
    # Une hypothèse n'est jamais présentée comme une mesure.
    assert saved["assumptions"]["measured"] is False
    assert saved["assumptions"]["is_estimate"] is True
    assert saved["assumptions"]["minutes_per_finding_manual"] == 12.0


# --------------------------------------------------------------------------- #
# #34 — corpus de décisions
# --------------------------------------------------------------------------- #
def test_corpus_export_holds_one_case_per_human_judgement(industrial_store):
    # 7 failles de t-1, dont 6 avec décision humaine (f-4 n'a qu'une
    # proposition d'agent) -> 6 cas, du plus ancien au plus récent.
    cases = export_training_corpus(industrial_store, tenant_id="t-1")
    assert len(cases) == 6
    assert [case["label"]["decided_at"] for case in cases] == sorted(
        case["label"]["decided_at"] for case in cases
    )
    assert [case["label"]["human_action"] for case in cases] == [
        "confirmed",
        "false_positive",
        "confirmed",
        "pending_validation",
        "risk_accepted",
        "confirmed",
    ]


def test_corpus_export_schema_is_stable(industrial_store):
    cases = export_training_corpus(industrial_store, tenant_id="t-1")
    for case in cases:
        assert set(case) == {"schema_version", "case_id", "features", "agent_proposal", "label"}
        assert case["schema_version"] == "1.0"
        assert set(case["features"]) == {
            "risk_type",
            "severity",
            "confidence",
            "entry_point",
            "app_criticality",
            "app_internet_exposed",
            "app_sensitive_data",
            "app_environment",
        }
        assert set(case["agent_proposal"]) == {"proposed_status", "proposed_at"}
        assert set(case["label"]) == {
            "human_action",
            "final_verdict",
            "decided_at",
            "decided_month",
            "agent_human_relation",
        }


def test_corpus_export_carries_no_raw_finding_content(industrial_store):
    # Aucun champ écarté ne doit se retrouver dans le JSON : ni les noms de
    # champs (titre, preuve, cvss, empreinte, justification, auteur), ni les
    # contenus bruts correspondants.
    cases = export_training_corpus(industrial_store, tenant_id="t-1")
    payload = corpus_json(cases)
    for key in EXCLUDED_KEYS:
        assert f'"{key}"' not in payload
    for leaked in (RAW_TITLE, RAW_HOST, RAW_TOKEN, RAW_AUTHOR, RAW_JUSTIFICATION, "ShopLite"):
        assert leaked not in payload
    # L'identifiant de la faille, du tenant et de l'application non plus.
    for leaked in ("f-1", "f-z", "t-1", "t-2", "app-a"):
        assert leaked not in payload


def test_corpus_export_is_anonymised(industrial_store):
    # Le case_id est un identifiant salé : il ne dit rien de la faille, il est
    # stable pour une même faille et différent d'un tenant à l'autre.
    cases = export_training_corpus(industrial_store, tenant_id="t-1")
    ids = [case["case_id"] for case in cases]
    assert len(set(ids)) == len(ids)
    assert all(case_id.startswith("case-") and len(case_id) == 21 for case_id in ids)
    other = export_training_corpus(industrial_store, tenant_id="t-2")
    assert not set(ids) & {case["case_id"] for case in other}


def test_corpus_export_keeps_only_the_fields_needed_for_triage(industrial_store):
    cases = export_training_corpus(industrial_store, tenant_id="t-1")
    features = cases[0]["features"]
    assert features["risk_type"] == "injection"
    assert features["severity"] == "High"
    assert features["confidence"] == "High"
    # Le point d'entrée garde le chemin mais perd l'hôte et la requête.
    assert features["entry_point"] == "/api/orders"
    assert features["app_criticality"] == "high"
    assert features["app_internet_exposed"] is True
    assert features["app_sensitive_data"] is True
    assert features["app_environment"] == "staging"


def test_corpus_export_records_the_agent_human_relation(industrial_store):
    cases = {case["label"]["decided_at"]: case for case in export_training_corpus(
        industrial_store, tenant_id="t-1"
    )}
    assert cases["2026-10-05T11:00:00Z"]["label"]["agent_human_relation"] == "unchanged"
    assert cases["2026-10-05T11:00:00Z"]["agent_proposal"]["proposed_status"] == "CONFIRMED"
    assert cases["2026-10-07T11:00:00Z"]["label"]["agent_human_relation"] == "diverged"
    assert cases["2026-10-09T09:00:00Z"]["label"]["agent_human_relation"] == "not_comparable"
    assert cases["2026-10-09T09:00:00Z"]["agent_proposal"]["proposed_status"] == ""


def test_corpus_export_is_deterministic_byte_for_byte(industrial_store):
    first = corpus_json(export_training_corpus(industrial_store, tenant_id="t-1"))
    second = corpus_json(export_training_corpus(industrial_store, tenant_id="t-1"))
    assert first == second
    assert first.encode("utf-8") == second.encode("utf-8")
    # Les clés sont triées : le format est diffable.
    assert first == json.dumps(
        json.loads(first), sort_keys=True, indent=2, ensure_ascii=False
    ) + "\n"


def test_corpus_export_is_tenant_scoped(industrial_store):
    cases = export_training_corpus(industrial_store, tenant_id="t-1")
    other = export_training_corpus(industrial_store, tenant_id="t-2")
    assert len(cases) == 6
    assert len(other) == 1
    payload = corpus_json(cases)
    assert "f-z" not in payload
    assert "AutreClient" not in payload
    assert not {case["case_id"] for case in cases} & {case["case_id"] for case in other}


def test_corpus_export_filters_on_the_since_date(industrial_store):
    # since = 10/10 : f-1, f-2 et f-3 (décidées avant) sortent du corpus.
    cases = export_training_corpus(industrial_store, tenant_id="t-1", since="2026-10-10T00:00:00Z")
    assert len(cases) == 3
    assert [case["label"]["decided_at"] for case in cases] == [
        "2026-10-15T11:00:00Z",
        "2026-10-20T11:00:00Z",
        "2026-11-03T09:00:00Z",
    ]


def test_corpus_statistics_report_the_gaps(industrial_store):
    # 6 cas ; types de risque vus : crypto, injection, xss ; catalogue de la
    # configuration : + ssrf, jamais détecté et jamais jugé -> trou du corpus.
    stats = corpus_statistics(industrial_store, tenant_id="t-1")
    assert stats["size"] == 6
    assert stats["by_status"] == {
        "confirmed": 3,
        "false_positive": 1,
        "pending_validation": 1,
        "risk_accepted": 1,
    }
    assert stats["by_risk_type"] == {"crypto": 2, "injection": 2, "xss": 2}
    assert stats["by_agent_human_relation"] == {"diverged": 2, "not_comparable": 2, "unchanged": 2}
    assert stats["observed_risk_types"] == ["crypto", "injection", "xss"]
    assert stats["configured_risk_types"] == ["crypto", "injection", "ssrf", "xss"]
    assert stats["covered_risk_types"] == ["crypto", "injection", "xss"]
    assert stats["gaps"] == ["ssrf"]
    assert stats["coverage_ratio"] == 0.75


def test_corpus_statistics_of_an_empty_corpus_are_safe(industrial_store):
    # Un corpus vide ne doit pas faire division par zéro ni annoncer une
    # couverture flatteuse.
    stats = corpus_statistics(industrial_store, tenant_id="t-1", since="2027-01-01T00:00:00Z")
    assert stats["size"] == 0
    assert stats["by_status"] == {}
    assert stats["gaps"] == ["crypto", "injection", "ssrf", "xss"]
    assert stats["coverage_ratio"] == 0.0
