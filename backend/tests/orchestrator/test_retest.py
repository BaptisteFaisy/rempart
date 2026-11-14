"""Fermer la boucle de retest (idée #51) : nom d'exécution, payload, démarrage.

Le défaut que ces tests empêchent de revenir n'est pas théorique : la machine
`RempartRetestClose` existait, `close_or_reopen` était testé, et **rien ne la
démarrait jamais**. Une PR de correction mergée laissait la faille en
`in_remediation` jusqu'à ce qu'un humain y pense — le « en continu » du produit
était une promesse dans le cahier des charges, pas un comportement.

Deux dangers propres à un webhook GitHub, tous deux payants ici à 50 $
par heure-tâche :

1. GitHub **rejoue** une livraison non acquittée → sans nom d'exécution dérivé
   de (faille, PR), chaque rejouement démarre un test réel ;
2. un retest sans `selectedFindingIds` reteste **toute** l'application alors
   qu'une seule correction a été mergée : plus cher, et la preuve de fermeture
   (EF-COR-04) ne dit plus quelle faille ce run a éteinte.
"""

from __future__ import annotations

from typing import Any

import pytest

from rempart.common.models import Application, Finding, Run, Tenant, TestConfig
from rempart.common.store import Store
from rempart.orchestrator.retest import (
    DuplicateExecution,
    StepFunctionsStarter,
    config_for_finding,
    execution_name,
    request_retest,
    retest_payload,
)
from rempart.orchestrator.tasks import Deps, start_run
from tests.fakes import FakeSecurityAgentClient, FakeStore

APP_ID = "app-t-a"
FINDING_ID = "f-t-a"
PR_URL = "https://github.com/t-a/shop/pull/7"


class RecordingStarter:
    """Démarreur de test : note chaque appel, peut simuler le refus de doublon.

    `fail_after` borne le nombre d'appels qui réussissent avant que l'erreur ne
    soit levée — c'est le comportement réel de Step Functions : le premier
    démarrage passe, le rejouement du même nom est refusé.
    """

    def __init__(self, error: Exception | None = None, fail_after: int = 0) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.error = error
        self.fail_after = fail_after

    def start(self, name: str, payload: dict[str, Any]) -> None:
        self.calls.append((name, payload))
        if self.error is not None and len(self.calls) > self.fail_after:
            raise self.error


class AlreadyExists(Exception):
    """L'erreur `ExecutionAlreadyExists` de Step Functions, dans sa forme réelle."""

    def __init__(self, name: str) -> None:
        super().__init__("Execution already exists")
        self.response = {"Error": {"Code": "ExecutionAlreadyExists"}}
        self.name = name


def _tenant() -> Tenant:
    """Un locataire éligible au free tier, avec un budget mensuel large."""
    return Tenant(
        tenant_id="t-a",
        name="Acme",
        aws_account_id="123456789012",
        region="eu-west-3",
        role_arn="arn:aws:iam::123456789012:role/rempart",
        external_id="ext",
        plan="continu",
        contacts=[],
        monthly_budget_hours=40.0,
        mandate_status="valid",
        free_tier_confirmed=True,
        created_at="2026-11-01T00:00:00Z",
    )


def _application() -> Application:
    """Une application sur le dépôt `t-a/shop` : la jointure du webhook passe par là."""
    return Application(
        app_id=APP_ID,
        tenant_id="t-a",
        name="Acme Shop",
        criticality="high",
        internet_exposed=True,
        data_types=["personal"],
        environment="staging",
        agent_space_id="space-a",
        domains=["t-a.example.com"],
        repositories=["t-a/shop"],
        team="Core",
        ticket_channel="github",
        context={},
        created_at="2026-11-01T00:00:00Z",
    )


def _config() -> TestConfig:
    """La configuration d'origine : elle porte le `pentestId` du retest."""
    return TestConfig(
        config_id="cfg-1",
        app_id=APP_ID,
        sa_pentest_id="pt-1",
        kind="full",
        scope={},
        risk_types=[],
        blocking_threshold="high",
        schedule=None,
    )


def _run() -> Run:
    """Le run qui a découvert la faille (terminé, 2 heures-tâches)."""
    return Run(
        run_id="run-1",
        config_id="cfg-1",
        app_id=APP_ID,
        tenant_id="t-a",
        trigger="manual",
        commit_from="aaa",
        commit_to="bbb",
        scope_decision="full",
        status="completed",
        started_at="2026-11-01T10:00:00Z",
        ended_at="2026-11-01T11:00:00Z",
        duration_s=3600.0,
        task_hours=2.0,
        cost_usd=100.0,
    )


def _finding_record() -> Finding:
    """Une faille en correction, dont la PR de correction est `PR_URL`."""
    return Finding(
        finding_id=FINDING_ID,
        app_id=APP_ID,
        tenant_id="t-a",
        run_id="run-1",
        fingerprint="fp-1",
        title="IDOR on orders",
        risk_type="IDOR",
        severity="Critical",
        confidence="High",
        priority="P1",
        status="in_remediation",
        due_at=None,
        ticket_url=None,
        remediation_pr_url=PR_URL,
        evidence={},
        cvss={},
        created_at="2026-11-01T11:00:00Z",
        updated_at="2026-11-01T11:00:00Z",
        closed_at=None,
        closed_by_run_id=None,
    )


def _store() -> FakeStore:
    """Le jeu complet d'une faille en attente de sa correction mergée."""
    store = FakeStore()
    store.save_tenant(_tenant())
    store.save_application(_application())
    store.save_config(_config())
    store.save_run(_run())
    store.save_finding(_finding_record())
    return store


def _finding(store: Store) -> Finding:
    finding = store.get_finding(FINDING_ID)
    assert finding is not None
    return finding


def _app(store: Store) -> Application:
    app = store.get_application(APP_ID)
    assert app is not None
    return app


def _pr(number: Any = 7, merged: bool = True) -> dict[str, Any]:
    return {
        "html_url": PR_URL,
        "merged": merged,
        "merge_commit_sha": "deadbee",
        "number": number,
    }


def test_le_nom_dexecution_est_derive_et_stable() -> None:
    """Le même (faille, PR) donne le même nom : c'est ce qui rend le rejouement inoffensif."""
    assert execution_name(FINDING_ID, 7) == execution_name(FINDING_ID, "7")
    assert execution_name(FINDING_ID, 7) != execution_name(FINDING_ID, 8)


def test_le_nom_nettoie_les_caracteres_interdits_et_teste() -> None:
    """Step Functions n'accepte que `[A-Za-z0-9_-]` sur 64 caractères."""
    name = execution_name("f./:x" + "y" * 90, "7#1")
    assert len(name) <= 64
    assert name.replace("-", "").replace("_", "").isalnum()


def test_deux_livraisons_rejouees_demarrent_un_seul_test() -> None:
    """Rejouement → `already_requested`, pas un second test payant."""
    store = _store()
    starter = RecordingStarter(
        error=DuplicateExecution("retest-f-t-a-pr7"), fail_after=1
    )
    first = request_retest(store, starter, _finding(store), _app(store), _pr(), 7)
    second = request_retest(store, starter, _finding(store), _app(store), _pr(), 7)
    assert first["started"] is True
    assert second["started"] is False
    assert second["reason"] == "already_requested"
    assert len(starter.calls) == 2  # deux tentatives, un seul démarrage réel côté AWS


def test_le_payload_vise_la_seule_faille_corrigee() -> None:
    """`jobType` REVALIDATION + `selectedFindingIds` : le retest porte sur la correction."""
    store = _store()
    payload = retest_payload(
        _finding(store), _app(store), store.list_configs(APP_ID)[0], _pr()
    )
    assert payload["trigger"] == "retest"
    assert payload["job_type"] == "REVALIDATION"
    assert payload["finding_ids"] == [FINDING_ID]
    assert payload["pentest_id"] == "pt-1"
    assert payload["app_id"] == APP_ID


def test_start_run_transmet_le_type_de_job_et_les_failles() -> None:
    """Le payload est traduit dans la forme réelle de `StartPentestJob`."""
    store = _store()
    sa = FakeSecurityAgentClient()
    deps = Deps(store=store, sa=sa)
    payload = retest_payload(
        _finding(store), _app(store), store.list_configs(APP_ID)[0], _pr()
    )
    start_run(payload, deps)
    calls = [body for name, body in sa.calls if name == "start_pentest_job"]
    assert calls, "StartPentestJob n'a pas été appelé"
    assert calls[0]["jobType"] == "REVALIDATION"
    assert calls[0]["selectedFindingIds"] == [FINDING_ID]


def test_un_test_ordinaire_ne_porte_aucune_option() -> None:
    """Pas de régression : un payload sans `job_type`/`finding_ids` appelle comme avant."""
    store = _store()
    sa = FakeSecurityAgentClient()
    start_run(
        {"app_id": APP_ID, "tenant_id": "t-a", "pentest_id": "pt-1"},
        Deps(store=store, sa=sa),
    )
    body = [b for n, b in sa.calls if n == "start_pentest_job"][0]
    assert "jobType" not in body and "selectedFindingIds" not in body


def test_san_configuration_dorigine_aucun_retest_invente() -> None:
    """Choisir une configuration au hasard retesterait autre chose que la faille."""
    store = _store()
    finding = _finding(store)
    finding.run_id = "run-introuvable"
    store.save_finding(finding)
    assert config_for_finding(store, finding) is None

    starter = RecordingStarter()
    result = request_retest(store, starter, finding, _app(store), _pr(), 7)
    assert starter.calls == []
    assert result["started"] is False
    assert result["reason"] == "no_test_config"
    # L'état est posé quand même : la correction est mergée, c'est un fait.
    assert store.get_finding(FINDING_ID).status == "to_retest"


def test_sans_machine_configurable_lest_est_pose_sans_promesse() -> None:
    """Aucun ARN de machine : la route dit `starter_unconfigured`, elle n'invente pas un run."""
    store = _store()
    result = request_retest(store, None, _finding(store), _app(store), _pr(), 7)
    assert result["started"] is False
    assert result["reason"] == "starter_unconfigured"
    assert store.get_finding(FINDING_ID).status == "to_retest"


def test_le_demarreur_reel_traduit_le_refus_de_doublon() -> None:
    """`StepFunctionsStarter` ne remonte pas une erreur boto3 brute à la route HTTP."""
    arn = "arn:aws:states:eu-north-1:123456789012:stateMachine:RempartPentestLifecycle"

    class Client:
        def start_execution(self, **kwargs: Any) -> dict[str, str]:
            raise AlreadyExists(kwargs["name"])

    starter = StepFunctionsStarter(Client(), arn)
    with pytest.raises(DuplicateExecution):
        starter.start("retest-f-t-a-pr7", {"trigger": "retest"})


def test_le_demarreur_ne_reste_pas_sur_une_autre_erreur() -> None:
    """Une panne AWS réelle doit remonter (et rendre 500), pas passer pour un doublon."""

    class Client:
        def start_execution(self, **kwargs: Any) -> dict[str, str]:
            raise RuntimeError("throttled")

    starter = StepFunctionsStarter(Client(), "arn:aws:states::stateMachine:M")
    with pytest.raises(RuntimeError):
        starter.start("retest-x-pr1", {})
