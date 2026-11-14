"""Fermer la boucle : une PR de correction mergée déclenche un retest (idée #51).

Le parcours complet, chapitre 8.4 du cahier des charges :

    PR mergée → webhook GitHub signé → faille ``to_retest`` → machine A
    (garde-fous, ``StartPentestJob`` en revalidation, sondage) → quand le job
    est terminé, ``close_or_reopen`` compare les empreintes : disparue =
    fermée avec preuve, encore présente = réouverte en régression (EF-TRI-06).

Ce module ne tient que la portion « déclencher AWS » : nom d'exécution
idempotent, payload complet, démarrage borné. Il ne connaît ni HTTP ni
l'authorisation — la route les traite avant de l'appeler.

Idempotence : GitHub rejoue une livraison qui n'a pas rendu de 2xx. Deux
livraisons de la même PR ne doivent pas démarrer deux tests payants à 50 $/h.
Le nom d'exécution est donc dérivé de (faille, PR) et Step Functions refuse un
doublon pendant 90 jours ; ce refus devient ``DuplicateExecution``, que la route
rend par 202 avec ``started: false`` au lieu d'un 500.

Le retest passe par les mêmes gardes-fous que n'importe quel test : free tier
confirmé, quota de tests simultanés, plafond d'heures-tâches, budget du mois,
coupe-circuit. Une fusion de PR ne franchit aucune de ces portes — c'est
volontaire et c'est ce que ``budget_gate`` garantit.
"""

from __future__ import annotations

import json
import re
from typing import Any

from rempart.common.models import Application, Finding, TestConfig
from rempart.common.store import Store
from rempart.common.timeutil import iso, utcnow

#: Nom d'exécution Step Functions : lettres, chiffres, `-` et `_`, 64 caractères.
MAX_EXECUTION_NAME_LENGTH = 64
_UNSAFE_NAME = re.compile(r"[^A-Za-z0-9_-]")

#: Type de job Continuum pour un retest : REVALIDATION (documenté, optionnel).
RETEST_JOB_TYPE = "REVALIDATION"


class DuplicateExecution(Exception):
    """Une exécution porte déjà ce nom : GitHub a rejoué la livraison."""

    def __init__(self, name: str) -> None:
        super().__init__(f"execution {name} already exists")
        self.name = name


class StepFunctionsStarter:
    """Démarreur réel d'exécutions, restreint à une seule machine à états.

    La machine est fixée à la construction : une route qui pourrait choisir
    n'importe quel ARN pourrait en choisir un qui n'appartient pas à Rempart.
    """

    def __init__(self, client: Any, machine_arn: str) -> None:
        self._client = client
        self.machine_arn = machine_arn

    def start(self, name: str, payload: dict[str, Any]) -> None:
        """Démarre l'exécution ; traduit le refus de doublon en ``DuplicateExecution``."""
        try:
            self._client.start_execution(
                stateMachineArn=self.machine_arn,
                name=name,
                input=json.dumps(payload),
            )
        except Exception as exc:  # botocore sans dépendre de botocore ici
            if _is_already_exists(exc):
                raise DuplicateExecution(name) from exc
            raise


def _is_already_exists(exc: BaseException) -> bool:
    """Vrai si l'exception est le refus « ExecutionAlreadyExists » de Step Functions."""
    response = getattr(exc, "response", None)
    if not isinstance(response, dict):
        return False
    return str(response.get("Error", {}).get("Code", "")) == "ExecutionAlreadyExists"


def execution_name(finding_id: str, pr_number: Any) -> str:
    """Nom d'exécution dérivé et sûr — le même pour une même (faille, PR)."""
    raw = f"retest-{finding_id}-pr{pr_number}"
    return _UNSAFE_NAME.sub("-", raw)[:MAX_EXECUTION_NAME_LENGTH]


def config_for_finding(store: Store, finding: Finding) -> TestConfig | None:
    """La configuration qui a produit le run d'origine de la faille.

    Pas de choix arbitraire : si la configuration d'origine est introuvable, on
    rend None et le retest n'est pas démarré. Inventer une configuration
    testerait autre chose que ce qui a découvert la faille.
    """
    run = store.get_run(finding.run_id) if finding.run_id else None
    configs = store.list_configs(finding.app_id)
    if run and run.config_id:
        for config in configs:
            if config.config_id == run.config_id:
                return config
    return None


def retest_payload(
    finding: Finding, app: Application, config: TestConfig, pr: dict[str, Any]
) -> dict[str, Any]:
    """État d'entrée de la machine A pour un retest déclenché par une fusion."""
    return {
        "trigger": "retest",
        "tenant_id": finding.tenant_id,
        "app_id": app.app_id,
        "config_id": config.config_id,
        "pentest_id": config.sa_pentest_id,
        "finding_ids": [finding.finding_id],
        "job_type": RETEST_JOB_TYPE,
        "commit_to": str(pr.get("merge_commit_sha") or ""),
        "pr_url": str(pr.get("html_url") or ""),
        "requested_at": iso(utcnow()),
    }


def request_retest(
    store: Store,
    starter: Any,
    finding: Finding,
    app: Application,
    pr: dict[str, Any],
    pr_number: Any,
) -> dict[str, Any]:
    """Marque la faille ``to_retest`` puis tente de démarrer son retest.

    Renvoie le résultat brut (``started``, ``reason``) : qui appele décide du
    code HTTP et de l'événement d'audit, pour que la route reste la seule
    interface HTTP de cette logique.
    """
    name = execution_name(finding.finding_id, pr_number)
    finding.status = "to_retest"
    finding.updated_at = iso(utcnow())
    store.save_finding(finding)

    if starter is None:
        # Aucun démarreur configuré : l'état est quand même posé — une faille
        # dont la correction est mergée ne doit pas rester `in_remediation`. Le
        # retest partira dès que la machine sera joignable, ou par la main.
        return {**_outcome(finding, app, name, False), "reason": "starter_unconfigured"}

    config = config_for_finding(store, finding)
    if config is None:
        return {**_outcome(finding, app, name, False), "reason": "no_test_config"}

    payload = retest_payload(finding, app, config, pr)
    try:
        starter.start(name, payload)
    except DuplicateExecution:
        return {**_outcome(finding, app, name, False), "reason": "already_requested"}
    return {**_outcome(finding, app, name, True), "reason": ""}


def _outcome(
    finding: Finding, app: Application, name: str, started: bool
) -> dict[str, Any]:
    """Champs communs à toute issue d'un retest demandé."""
    return {
        "finding_id": finding.finding_id,
        "app_id": app.app_id,
        "tenant_id": finding.tenant_id,
        "execution_name": name,
        "started": started,
    }
