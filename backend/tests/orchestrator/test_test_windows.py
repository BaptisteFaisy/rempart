"""Fenêtres de test par application (EF-ORC-08, chapitres 9.2 et 15.1).

Aucun test complet en production hors d'une fenêtre convenue ; la porte
CI/CD (``delivery``) et la préproduction ne sont jamais bloquées. L'instant
évalué est toujours injecté (``now`` ou ``payload["moment"]``) : aucun test
ne dépend de l'heure réelle.

Repères calendaires : le 2026-11-09 est un LUNDI, le 2026-11-10 un MARDI,
le 2026-11-11 un MERCREDI.
"""

from datetime import datetime, timezone

from rempart.common.models import Application, Tenant
from rempart.orchestrator.tasks import Deps, budget_gate
from rempart.orchestrator.windows import is_within_window
from tests.fakes import FakeSecurityAgentClient, FakeStore

NIGHT_WINDOW = {
    "days": ["mon"],
    "start": "22:00",
    "end": "06:00",
    "environment": "production",
}
DAY_WINDOW = {"days": ["mon", "tue"], "start": "09:00", "end": "17:00"}

MONDAY_22H59 = datetime(2026, 11, 9, 22, 59, tzinfo=timezone.utc)
MONDAY_21H59 = datetime(2026, 11, 9, 21, 59, tzinfo=timezone.utc)
TUESDAY_03H = datetime(2026, 11, 10, 3, 0, tzinfo=timezone.utc)
TUESDAY_07H = datetime(2026, 11, 10, 7, 0, tzinfo=timezone.utc)
WEDNESDAY_12H = datetime(2026, 11, 11, 12, 0, tzinfo=timezone.utc)


# --------------------------------------------------------------------------- #
# is_within_window — logique pure
# --------------------------------------------------------------------------- #
def test_fenetre_nuit_cote_soir():
    assert is_within_window([NIGHT_WINDOW], MONDAY_22H59) is True


def test_fenetre_nuit_cote_matin_apres_minuit():
    """22:00 → 06:00 ouverte le lundi couvre le mardi 03:00."""
    assert is_within_window([NIGHT_WINDOW], TUESDAY_03H) is True


def test_fenetre_nuit_avant_ouverture_et_apres_fin():
    assert is_within_window([NIGHT_WINDOW], MONDAY_21H59) is False
    assert is_within_window([NIGHT_WINDOW], TUESDAY_07H) is False


def test_fenetre_nuit_sans_lendemain_prevu():
    """Mardi 22:30 : la fenêtre de lundi n'est pas reconduite le mardi."""
    moment = datetime(2026, 11, 10, 22, 30, tzinfo=timezone.utc)
    assert is_within_window([NIGHT_WINDOW], moment) is False


def test_fenetre_meme_jour():
    monday_noon = datetime(2026, 11, 9, 12, 0, tzinfo=timezone.utc)
    monday_17h = datetime(2026, 11, 9, 17, 0, tzinfo=timezone.utc)
    sunday_noon = datetime(2026, 11, 8, 12, 0, tzinfo=timezone.utc)
    assert is_within_window([DAY_WINDOW], monday_noon) is True
    assert is_within_window([DAY_WINDOW], monday_17h) is False  # fin exclusive
    assert is_within_window([DAY_WINDOW], sunday_noon) is False


def test_aucune_fenetre_ne_couvre_rien():
    assert is_within_window([], WEDNESDAY_12H) is False
    assert is_within_window(None, WEDNESDAY_12H) is False


def test_jours_vides_couvrent_tous_les_jours():
    every_night = {"days": [], "start": "22:00", "end": "06:00"}
    assert is_within_window([every_night], WEDNESDAY_12H.replace(hour=23)) is True


def test_filtre_environnement():
    assert is_within_window([NIGHT_WINDOW], MONDAY_22H59, environment="production") is True
    assert is_within_window([NIGHT_WINDOW], MONDAY_22H59, environment="staging") is False
    assert is_within_window([DAY_WINDOW], WEDNESDAY_12H, environment="production") is False


def test_fenetre_mal_formee_ignorée_sans_exception():
    broken = [
        {"days": ["mon"], "start": "22h00", "end": "06:00"},
        {"days": ["mon"], "start": "22:00"},
        {"days": ["xyz"], "start": "00:00", "end": "23:59"},
        "pas-un-dict",
    ]
    assert is_within_window(broken, MONDAY_22H59) is False  # type: ignore[list-item]


# --------------------------------------------------------------------------- #
# budget_gate — refus de tester hors fenêtre
# --------------------------------------------------------------------------- #
def _seed(environment: str = "production", test_windows: list | None = None) -> FakeStore:
    store = FakeStore()
    store.save_tenant(
        Tenant(
            tenant_id="t-1",
            name="Acme",
            aws_account_id="123456789012",
            region="eu-west-3",
            role_arn="arn:aws:iam::123456789012:role/rempart",
            external_id="ext",
            plan="continu",
            contacts=[],
            monthly_budget_hours=10.0,
            mandate_status="valid",
            free_tier_confirmed=True,
            created_at="2026-11-01T00:00:00Z",
        )
    )
    store.save_application(
        Application(
            app_id="app-1",
            tenant_id="t-1",
            name="ShopLite",
            criticality="high",
            internet_exposed=True,
            data_types=["personal"],
            environment=environment,
            agent_space_id="space-1",
            domains=["shop.acme.com"],
            repositories=["acme/shop"],
            team="Core",
            ticket_channel="github",
            context={},
            created_at="2026-11-01T00:00:00Z",
            test_windows=test_windows or [],
        )
    )
    return store


def _deps(store: FakeStore | None = None) -> Deps:
    return Deps(store=store or _seed(), sa=FakeSecurityAgentClient())


def _gate(deps: Deps, now: datetime, **payload_extra) -> dict:
    payload = {"tenant_id": "t-1", "app_id": "app-1", "kind": "full", **payload_extra}
    return budget_gate(payload, deps, now=now)


def test_test_complet_en_production_hors_fenetre_refuse():
    deps = _deps(_seed(test_windows=[NIGHT_WINDOW]))
    out = _gate(deps, WEDNESDAY_12H)
    assert out["allowed"] is False
    assert out["reason"] == "outside_test_window"


def test_test_complet_en_production_dans_fenetre_autorise():
    deps = _deps(_seed(test_windows=[NIGHT_WINDOW]))
    assert _gate(deps, MONDAY_22H59)["allowed"] is True


def test_fenetre_traversant_minuit_autorise_des_deux_cotes():
    deps = _deps(_seed(test_windows=[NIGHT_WINDOW]))
    assert _gate(deps, MONDAY_22H59)["allowed"] is True  # côté soir
    assert _gate(deps, TUESDAY_03H)["allowed"] is True  # côté matin
    assert _gate(deps, TUESDAY_07H)["allowed"] is False  # après la fin


def test_production_sans_fenetre_convenue_refuse():
    """Chapitre 15.1 : un test en production exige une fenêtre convenue."""
    deps = _deps(_seed(test_windows=[]))
    out = _gate(deps, WEDNESDAY_12H)
    assert out["allowed"] is False
    assert out["reason"] == "outside_test_window"


def test_staging_sans_fenetre_autorise():
    deps = _deps(_seed(environment="staging"))
    assert _gate(deps, WEDNESDAY_12H)["allowed"] is True


def test_delivery_en_production_hors_fenetre_autorise():
    """La porte CI/CD bloque une livraison : elle n'attend pas une fenêtre."""
    deps = _deps(_seed(test_windows=[]))
    explicit = _gate(deps, WEDNESDAY_12H, kind="delivery")
    assert explicit["allowed"] is True
    cicd = budget_gate(
        {"tenant_id": "t-1", "app_id": "app-1", "trigger": "cicd"}, deps, now=WEDNESDAY_12H
    )
    assert cicd["allowed"] is True


def test_kind_inconnu_en_production_est_traite_comme_complet():
    """Dans le doute, le test exige une fenêtre plutôt que de passer."""
    deps = _deps(_seed(test_windows=[]))
    out = budget_gate({"tenant_id": "t-1", "app_id": "app-1"}, deps, now=WEDNESDAY_12H)
    assert out["allowed"] is False
    assert out["reason"] == "outside_test_window"


def test_refus_hors_fenetre_est_audite():
    deps = _deps(_seed(test_windows=[NIGHT_WINDOW]))
    _gate(deps, WEDNESDAY_12H)
    events = [
        e
        for e in deps.store.list_audit()
        if e.action == "run.refused_outside_window"
    ]
    assert len(events) == 1
    assert events[0].result == "denied"
    assert events[0].object_type == "app"
    assert events[0].object_id == "app-1"


def test_autorisation_dans_fenetre_n_ecrit_pas_de_refus():
    deps = _deps(_seed(test_windows=[NIGHT_WINDOW]))
    _gate(deps, MONDAY_22H59)
    actions = [e.action for e in deps.store.list_audit()]
    assert "run.refused_outside_window" not in actions


def test_moment_injecte_par_le_payload():
    """Sans ``now``, ``payload["moment"]`` garde le test déterministe."""
    deps = _deps(_seed(test_windows=[NIGHT_WINDOW]))
    inside = budget_gate(
        {"tenant_id": "t-1", "app_id": "app-1", "kind": "full", "moment": "2026-11-09T23:00:00Z"},
        deps,
    )
    assert inside["allowed"] is True
    outside = budget_gate(
        {"tenant_id": "t-1", "app_id": "app-1", "kind": "full", "moment": "2026-11-11T12:00:00Z"},
        deps,
    )
    assert outside["allowed"] is False
    assert outside["reason"] == "outside_test_window"
