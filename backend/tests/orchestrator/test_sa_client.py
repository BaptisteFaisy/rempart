"""Tests du client AWS Continuum / Security Agent (doc officielle 2025-09-06).

Chaque action doit envoyer EXACTEMENT les paramètres requis documentés et lire
les champs de réponse documentés. Un paramètre requis manquant doit lever une
erreur explicite plutôt que de partir en 400 côté AWS.
"""

from typing import Any

import pytest

from rempart.orchestrator.sa_client import (
    SecurityAgentClient,
    job_source,
    require_params,
)


class _RecordingClient:
    """Double boto3 minimaliste qui enregistre les appels du wrapper."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.responses: dict[str, dict[str, Any]] = {
            "batch_get_pentest_jobs": {"pentestJobs": [{"pentestJobId": "job-1"}]},
            "list_findings": {"findingsSummaries": [{"findingId": "f-1"}]},
            "list_pentests": {"pentestSummaries": [{"pentestId": "pt-1"}]},
            "list_pentest_jobs_for_pentest": {
                "pentestJobSummaries": [{"pentestJobId": "job-9"}]
            },
            "list_pentest_job_tasks": {
                "taskSummaries": [
                    {"taskId": "task-1", "pentestJobId": "job-1", "taskHours": 0.75},
                    {"taskId": "task-2", "pentestJobId": "job-1", "taskHours": 0.25},
                ]
            },
        }

    def __getattr__(self, name: str):
        def _call(**kwargs: Any) -> dict[str, Any]:
            self.calls.append((name, kwargs))
            return self.responses.get(name, {"ok": True})

        return _call


def _client() -> tuple[SecurityAgentClient, _RecordingClient]:
    boto = _RecordingClient()
    return SecurityAgentClient(boto_client=boto), boto


def test_create_agent_space_envoie_name():
    client, boto = _client()
    client.create_agent_space("space-name")
    assert boto.calls[-1] == ("create_agent_space", {"name": "space-name"})


def test_create_target_domain_exige_le_domaine_et_la_methode():
    client, boto = _client()
    client.create_target_domain("shop.acme.com", "DNS_TXT")
    assert boto.calls[-1] == (
        "create_target_domain",
        {"targetDomainName": "shop.acme.com", "verificationMethod": "DNS_TXT"},
    )
    with pytest.raises(ValueError, match="targetDomainName"):
        client.create_target_domain("")


def test_verify_target_domain_exige_target_domain_id():
    client, boto = _client()
    client.verify_target_domain("dom-1")
    assert boto.calls[-1] == ("verify_target_domain", {"targetDomainId": "dom-1"})
    with pytest.raises(ValueError, match="targetDomainId"):
        client.verify_target_domain("")


def test_create_pentest_exige_espace_et_titre():
    client, boto = _client()
    client.create_pentest("space-1", "Livraison ShopLite")
    assert boto.calls[-1] == (
        "create_pentest",
        {"agentSpaceId": "space-1", "title": "Livraison ShopLite"},
    )
    with pytest.raises(ValueError, match="title"):
        client.create_pentest("space-1", "")


def test_start_pentest_job_exige_espace_et_pentest():
    client, boto = _client()
    client.start_pentest_job("space-1", "pt-1")
    assert boto.calls[-1] == (
        "start_pentest_job",
        {"agentSpaceId": "space-1", "pentestId": "pt-1"},
    )
    with pytest.raises(ValueError, match="pentestId"):
        client.start_pentest_job("space-1", "")


def test_stop_pentest_job_exige_espace_et_job():
    client, boto = _client()
    client.stop_pentest_job("space-1", "job-1")
    assert boto.calls[-1] == (
        "stop_pentest_job",
        {"agentSpaceId": "space-1", "pentestJobId": "job-1"},
    )
    with pytest.raises(ValueError, match="pentestJobId"):
        client.stop_pentest_job("space-1", "")


def test_batch_get_pentest_jobs_lit_pentest_jobs():
    client, boto = _client()
    assert client.batch_get_pentest_jobs("space-1", ["job-1"]) == [
        {"pentestJobId": "job-1"}
    ]
    assert boto.calls[-1] == (
        "batch_get_pentest_jobs",
        {"agentSpaceId": "space-1", "pentestJobIds": ["job-1"]},
    )
    with pytest.raises(ValueError, match="pentestJobIds"):
        client.batch_get_pentest_jobs("space-1", [])


def test_list_pentests_lit_pentest_summaries():
    client, _ = _client()
    assert client.list_pentests("space-1") == [{"pentestId": "pt-1"}]
    with pytest.raises(ValueError, match="agentSpaceId"):
        client.list_pentests("")


def test_list_pentest_jobs_for_pentest_lit_les_summaries():
    client, boto = _client()
    assert client.list_pentest_jobs_for_pentest("space-1", "pt-1") == [
        {"pentestJobId": "job-9"}
    ]
    assert boto.calls[-1] == (
        "list_pentest_jobs_for_pentest",
        {"agentSpaceId": "space-1", "pentestId": "pt-1"},
    )


def test_list_findings_lit_findings_summaries():
    client, boto = _client()
    assert client.list_findings("space-1", pentest_job_id="job-1") == [
        {"findingId": "f-1"}
    ]
    assert boto.calls[-1] == (
        "list_findings",
        {"agentSpaceId": "space-1", "pentestJobId": "job-1"},
    )
    with pytest.raises(ValueError, match="agentSpaceId"):
        client.list_findings("")


def test_update_finding_exige_espace_et_finding():
    client, boto = _client()
    client.update_finding("space-1", "f-1", status="CLOSED")
    assert boto.calls[-1] == (
        "update_finding",
        {"agentSpaceId": "space-1", "findingId": "f-1", "status": "CLOSED"},
    )
    with pytest.raises(ValueError, match="findingId"):
        client.update_finding("space-1", "")


def test_start_code_remediation_prend_un_tableau_de_findings():
    client, boto = _client()
    client.start_code_remediation("space-1", ["f-1", "f-2"], pentest_job_id="job-1")
    assert boto.calls[-1] == (
        "start_code_remediation",
        {
            "agentSpaceId": "space-1",
            "findingIds": ["f-1", "f-2"],
            "pentestJobId": "job-1",
        },
    )
    with pytest.raises(ValueError, match="findingIds"):
        client.start_code_remediation("space-1", [])


def test_job_source_refuse_les_deux_jobs_a_la_fois():
    assert job_source(pentest_job_id="job-1") == {"pentestJobId": "job-1"}
    assert job_source(code_review_job_id="cr-1") == {"codeReviewJobId": "cr-1"}
    assert job_source() == {}
    with pytest.raises(ValueError, match="exclusifs"):
        job_source(pentest_job_id="job-1", code_review_job_id="cr-1")


def test_require_params_liste_tous_les_manquants():
    require_params("X", {"a": 1, "b": 2}, ("a", "b"))
    with pytest.raises(ValueError, match="b"):
        require_params("X", {"a": 1}, ("a", "b"))


def test_client_is_lazy_when_no_boto_client_injected():
    """Aucun client boto3 n'est créé à l'import (les tests n'ont pas AWS)."""
    client = SecurityAgentClient()
    assert client._client is None


def test_list_pentest_job_tasks_lit_task_summaries():
    """SEULE source réelle des heures-tâches (D1) : `TaskSummary.taskHours`."""
    client, boto = _client()
    tasks = client.list_pentest_job_tasks("space-1", pentest_job_id="job-1")
    assert [t["taskHours"] for t in tasks] == [0.75, 0.25]
    assert boto.calls[-1] == (
        "list_pentest_job_tasks",
        {"agentSpaceId": "space-1", "pentestJobId": "job-1"},
    )


def test_list_pentest_job_tasks_exige_l_espace_d_agent():
    client, _ = _client()
    with pytest.raises(ValueError, match="agentSpaceId"):
        client.list_pentest_job_tasks("")


def test_list_pentest_job_tasks_sans_job_renvoie_toutes_les_taches():
    client, boto = _client()
    client.list_pentest_job_tasks("space-1")
    assert boto.calls[-1] == ("list_pentest_job_tasks", {"agentSpaceId": "space-1"})


def test_sans_role_le_client_parle_avec_les_identifiants_courants():
    """Déploiement dans un compte unique : pas d'assomption de rôle."""
    client = SecurityAgentClient(region="eu-north-1")
    assert client._credentials() == {}


def test_avec_un_role_le_client_assume_le_role_d_operateur(monkeypatch):
    """INCIDENT RÉEL (13 nov 2026) : le rôle n'était JAMAIS assumé.

    Le rôle `rempart-ops-role` du compte client porte les droits
    `securityagent:*` ; sans assomption, l'appel partait avec les identifiants
    de la Lambda du plan de contrôle et se faisait refuser
    (« not authorized to perform: securityagent:StartPentestJob »).
    """
    assumed: dict[str, Any] = {}

    class _FakeSts:
        def assume_role(self, **kwargs: Any) -> dict[str, Any]:
            assumed.update(kwargs)
            return {
                "Credentials": {
                    "AccessKeyId": "AKIA",
                    "SecretAccessKey": "secret",
                    "SessionToken": "token",
                }
            }

    import rempart.orchestrator.sa_client as module

    monkeypatch.setattr(module.boto3, "client", lambda *a, **k: _FakeSts())
    client = SecurityAgentClient(
        region="eu-north-1",
        role_arn="arn:aws:iam::710332178565:role/rempart-ops-role",
        external_id="shared-external-id",
    )
    creds = client._credentials()

    assert assumed["RoleArn"] == "arn:aws:iam::710332178565:role/rempart-ops-role"
    assert assumed["ExternalId"] == "shared-external-id"
    assert creds["aws_access_key_id"] == "AKIA"
    assert creds["aws_session_token"] == "token"
