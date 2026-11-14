"""`POST /v1/events/github` : la PR de correction mergée ferme la boucle (idée #51).

Trois propriétés non négociables, chacune testée :

1. **Authentification** — le webhook est le second point d'entrée sans jeton du
   produit. Signature HMAC sur les **octets bruts** du corps (le schéma GitHub),
   refus neutre : un appelant non authentifié n'apprend pas quelle protection a
   manqué, ni si un secret est configuré.
2. **Isolation (ENF-SEC-01)** — la jointure se fait par le dépôt, puis par
   l'application de ce dépôt. Un événement venant d'un autre locataire ne peut
   muter aucune faille chez le voisin, même avec une URL de PR identique.
3. **Aucun 500** — toute entrée invalide est refusée explicitement (400) ou
   acquittée comme ignorée (202). Un 5xx ferait rejouer la livraison par GitHub,
   puis désactiver le hook : la boucle se rouvrirait silencieusement.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from typing import Any

import pytest

from rempart.api.app import lambda_handler
from rempart.common import ratelimit
from rempart.common.config import Settings
from rempart.common.models import TestConfig
from rempart.orchestrator.retest import DuplicateExecution
from tests.api.conftest import make_event, seed_two_tenants
from tests.fakes import FakeRetestStarter

SECRET = "secret-webhook-github"
REPO = "t-a/shop"
PR_URL = "https://github.com/t-a/shop/pull/7"
OTHER_PR_URL = "https://github.com/t-b/shop/pull/9"


@pytest.fixture(autouse=True)
def _fresh_rate_limit():
    """Le limiteur est global par instance : sans reset, un test en pollue un autre."""
    ratelimit.reset()
    yield
    ratelimit.reset()


def _store(*, pr_url: str | None = PR_URL, status: str = "in_remediation"):
    """Deux locataires ; la faille de `t-a` attend sa correction sur `pr_url`."""
    store = seed_two_tenants()
    finding = store.get_finding("f-t-a")
    assert finding is not None
    finding.remediation_pr_url = pr_url
    finding.status = status
    store.save_finding(finding)
    other = store.get_finding("f-t-b")
    assert other is not None
    other.remediation_pr_url = OTHER_PR_URL
    other.status = "in_remediation"
    store.save_finding(other)
    # La configuration d'origine du run : sans elle, le retest n'a pas de
    # `pentestId` et ne part pas (testé plus bas).
    store.save_config(
        TestConfig(
            config_id="cfg-1",
            app_id="app-t-a",
            sa_pentest_id="pt-1",
            kind="full",
            scope={},
            risk_types=[],
            blocking_threshold="high",
            schedule=None,
        )
    )
    return store


def _payload(
    *,
    url: str = PR_URL,
    merged: bool = True,
    action: str = "closed",
    repo: str = REPO,
    number: Any = 7,
) -> dict[str, Any]:
    """Corps d'une livraison `pull_request`, dans la forme réelle de GitHub."""
    return {
        "action": action,
        "number": number,
        "pull_request": {
            "html_url": url,
            "number": number,
            "merged": merged,
            "state": "closed",
            "merge_commit_sha": "deadbee",
        },
        "repository": {"full_name": repo, "id": 42},
    }


def _post(
    store: Any,
    body: Any,
    *,
    secret: str | None = SECRET,
    signature: str | None = "AUTO",
    event: str | None = "pull_request",
    retest: Any = None,
    headers: dict[str, str] | None = None,
):
    """Appel réel de la Lambda API : même chemin que la production."""
    raw = json.dumps(body)
    headers = dict(headers or {})
    if event is not None:
        headers["X-GitHub-Event"] = event
    if signature == "AUTO":
        digest = hmac.new(SECRET.encode("utf-8"), raw.encode("utf-8"), hashlib.sha256)
        headers["X-Hub-Signature-256"] = f"sha256={digest.hexdigest()}"
    elif signature is not None:
        headers["X-Hub-Signature-256"] = signature
    request = make_event("POST", "/v1/events/github", body=body, headers=headers)
    request["body"] = raw  # le corps brut, tel que GitHub l'a transmis
    response = lambda_handler(
        request,
        None,
        store=store,
        sa=None,
        retest=retest,
        settings=Settings(github_webhook_secret=secret),
    )
    return response["statusCode"], json.loads(response["body"])


# --------------------------------------------------------------------------- #
# Authentification
# --------------------------------------------------------------------------- #
def test_une_livraison_signeest_acceptee_et_le_retest_demarre():
    starter = FakeRetestStarter()
    status, payload = _post(_store(), _payload(), retest=starter)
    assert status == 202
    assert payload["received"] is True
    assert payload["started"] is True
    assert payload["finding_id"] == "f-t-a"
    assert payload["app_id"] == "app-t-a"
    assert len(starter.calls) == 1
    name, state = starter.calls[0]
    assert name == "retest-f-t-a-pr7"
    assert state["trigger"] == "retest"
    assert state["job_type"] == "REVALIDATION"
    assert state["finding_ids"] == ["f-t-a"]


def test_letat_de_la_faille_est_pos_dans_le_magasin():
    """La preuve visible par un auditeur : `to_retest`, tracé au journal d'audit."""
    store = _store()
    _post(store, _payload(), retest=FakeRetestStarter())
    finding = store.get_finding("f-t-a")
    assert finding is not None and finding.status == "to_retest"
    actions = {(e.action, e.object_id) for e in store.list_audit()}
    assert ("retest.requested", "f-t-a") in actions


def test_la_signature_porte_sur_les_octets_bruts_pas_sur_le_json_reecrit():
    """Un HMAC du corps ré-encodé ne peut PAS passer : c'est le schéma GitHub."""
    body = _payload()
    forged = hmac.new(
        SECRET.encode("utf-8"),
        json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    status, payload = _post(_store(), body, signature=forged)
    assert status == 403
    assert "started" not in payload


def test_sans_signature_le_refus_est_neutre():
    """Même message pour signature absente, fausse et secret non configuré."""
    body = _payload()
    absent, refused_absent = _post(_store(), body, signature=None)
    false_, refused_false = _post(_store(), body, signature="0" * 64)
    no_secret, refused_unconfigured = _post(_store(), body, secret=None)
    messages = {refused_absent["error"], refused_false["error"], refused_unconfigured["error"]}
    assert absent == false_ == no_secret == 403
    assert len(messages) == 1, messages
    assert "configur" not in messages.pop().lower()


def test_une_signature_de_forme_invalide_refuse_sans_500():
    """`sha256=` absent, hors ASCII, trop court : refus, jamais une exception."""
    body = _payload()
    for provided in ("", "  ", "not-hex", "sha256=", "sha256:" + "0" * 64, "é" * 64):
        status, _ = _post(_store(), body, signature=provided)
        assert status == 403, provided


# --------------------------------------------------------------------------- #
# Enveloppe et décisions
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("event_type", ["push", "issues", "deployment", None, ""])
def test_un_evenement_dun_autre_type_est_acquitte_sans_traitement(event_type):
    """202, pas 400 : un 4xx ferait rejouer puis désactiver le hook par GitHub."""
    status, payload = _post(_store(), {"ref": "refs/heads/main"}, event=event_type)
    assert status == 202
    assert payload["received"] is True
    assert str(payload["ignored"]).startswith("unsupported_event")


def test_une_pr_non_mergee_ne_declenche_rien():
    """`closed` sans `merged` : la correction n'existe pas encore en production."""
    store = _store()
    starter = FakeRetestStarter()
    status, payload = _post(store, _payload(merged=False), retest=starter)
    assert status == 202 and payload["ignored"] == "not_merged"
    assert starter.calls == []
    assert store.get_finding("f-t-a").status == "in_remediation"


def test_une_pr_ouverte_qui_se_ferme_sans_fusion_ne_declenche_rien():
    store = _store()
    starter = FakeRetestStarter()
    status, payload = _post(store, _payload(action="closed", merged=False), retest=starter)
    assert status == 202 and payload["ignored"] == "not_merged"
    assert starter.calls == []


@pytest.mark.parametrize(
    "body",
    [
        ["pas", "un", "objet"],
        {},
        {"action": "closed"},
        {"action": "closed", "pull_request": {"html_url": PR_URL}},
        {"action": "", "pull_request": {}, "repository": {"full_name": REPO}},
        {"action": "closed", "pull_request": "chaîne", "repository": {"full_name": REPO}},
        {"action": "closed", "pull_request": {}, "repository": {"full_name": ""}},
        {"action": "closed", "pull_request": {}, "repository": {"full_name": "a/b/c"}},
        {"action": "closed", "pull_request": {}, "repository": "t-a/shop"},
        {"action": "closed", "pull_request": {"html_url": ""}, "repository": {"full_name": REPO}},
        {"action": "closed", "pull_request": {"html_url": 42}, "repository": {"full_name": REPO}},
        {"action": "closed", "pull_request": {}, "repository": {"full_name": "a" * 300}},
    ],
)
def test_toute_entree_invalide_est_refusee_sans_500(body):
    """Validation stricte avant toute écriture : ni 500, ni mutation partielle."""
    status, _ = _post(_store(), body)
    assert status in (400, 403, 429), status


def test_un_corps_non_decode_est_refuse_par_analyse_avant_route():
    """Le corps illisible est refusé à l'entrée de la Lambda, jamais par une 500."""
    request = make_event("POST", "/v1/events/github", headers={"X-GitHub-Event": "pull_request"})
    request["body"] = "{corps tronqué"
    response = lambda_handler(
        request, None, store=_store(), sa=None, settings=Settings(github_webhook_secret=SECRET)
    )
    assert response["statusCode"] == 400


# --------------------------------------------------------------------------- #
# Isolation (ENF-SEC-01)
# --------------------------------------------------------------------------- #
def test_une_pr_d_un_autre_locataire_ne_mut_rien_chez_voisin():
    """Le contrôle d'isolation : la jointure passe par le dépôt, pas par l'URL seule."""
    store = _store()
    starter = FakeRetestStarter()
    status, payload = _post(
        store, _payload(url=PR_URL, repo="t-b/shop"), retest=starter
    )
    assert status == 202
    assert payload["ignored"] == "no_matching_finding"
    assert starter.calls == []
    assert store.get_finding("f-t-a").status == "in_remediation"
    assert store.get_finding("f-t-b").status == "in_remediation"


def test_un_depot_inconnu_est_ignore():
    store = _store()
    starter = FakeRetestStarter()
    status, payload = _post(store, _payload(repo="inconnu/shop"), retest=starter)
    assert status == 202 and payload["ignored"] == "unknown_repository"
    assert starter.calls == []


def test_une_faille_deja_fermee_ne_se_rouvre_pas_toute_seule():
    """Un événement externe ne réouvre pas un dossier clos : ce serait du télécommandage."""
    store = _store(status="closed")
    starter = FakeRetestStarter()
    status, payload = _post(store, _payload(), retest=starter)
    assert status == 202
    assert payload["ignored"] == "status_closed"
    assert starter.calls == []
    assert store.get_finding("f-t-a").status == "closed"


def test_une_faille_sans_pr_de_correction_est_ignoree():
    store = _store(pr_url=None)
    starter = FakeRetestStarter()
    status, payload = _post(store, _payload(), retest=starter)
    assert status == 202 and payload["ignored"] == "no_matching_finding"
    assert starter.calls == []


# --------------------------------------------------------------------------- #
# Rejouements, débit, configuration
# --------------------------------------------------------------------------- #
def test_un_rejouement_de_github_ne_debute_pas_deux_tests():
    """Deux livraisons identiques, un seul démarrage : le nom d'exécution est dérivé."""
    store = _store()
    starter = FakeRetestStarter(
        error=DuplicateExecution("retest-f-t-a-pr7"), fail_after=1
    )
    first, first_body = _post(store, _payload(), retest=starter)
    second, second_body = _post(store, _payload(), retest=starter)
    assert first == 202 and first_body["started"] is True
    assert second == 202 and second_body["started"] is False
    assert second_body["reason"] == "already_requested"


def test_le_debit_est_limite_par_depot(monkeypatch):
    monkeypatch.setattr(ratelimit, "MAX_PER_WINDOW", 3)
    store, starter = _store(), FakeRetestStarter()
    statuses = [_post(store, _payload(), retest=starter)[0] for _ in range(5)]
    assert statuses[:3] == [202, 202, 202]
    assert statuses[3:] == [429, 429]
    assert len(starter.calls) == 3


def test_sans_machine_configlee_letat_est_pose_et_le_declare():
    """Aucun ARN de machine : pas de faux départ promis, mais l'état est réel."""
    store = _store()
    status, payload = _post(store, _payload(), retest=None)
    assert status == 202
    assert payload["started"] is False
    assert payload["reason"] == "starter_unconfigured"
    assert store.get_finding("f-t-a").status == "to_retest"


def test_sans_configuration_dorigine_le_retest_ne_part_pas():
    """Pas de `pentestId` connu : inventer une configuration retesterait autre chose."""
    store = _store()
    store.configs.clear()
    starter = FakeRetestStarter()
    status, payload = _post(store, _payload(), retest=starter)
    assert status == 202
    assert payload["started"] is False and payload["reason"] == "no_test_config"
    assert starter.calls == []
    assert store.get_finding("f-t-a").status == "to_retest"


def test_une_panne_aws_remonte_en_500_et_non_en_doublon():
    """Une vraie panne de démarrage doit être visible, pas masquée par un 202."""
    class Broken:
        def start(self, name: str, payload: dict[str, Any]) -> None:
            raise RuntimeError("stepfunctions unavailable")

    status, body = _post(_store(), _payload(), retest=Broken())
    assert status == 500
    assert "stepfunctions unavailable" in body["error"]
