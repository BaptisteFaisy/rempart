"""Fakes AWS Continuum / Security Agent et modèle de langage."""

import uuid
from typing import Any


def _verification_details(method: str) -> dict[str, Any]:
    """Forme documentée de `verificationDetails` selon la méthode choisie.

    `HTTP_ROUTE` renvoie `{routePath, token}` (aucun accès DNS nécessaire) ;
    les autres renvoient `{dnsRecordName, dnsRecordType, token}`.
    """
    if method == "HTTP_ROUTE":
        return {
            "method": method,
            "httpRoute": {
                "routePath": "/.well-known/continuum-verification",
                "token": "tok-http-demo",
            },
        }
    return {
        "method": method,
        "dnsTxt": {
            "dnsRecordName": "_continuum-verify",
            "dnsRecordType": "TXT",
            "token": "tok-dns-demo",
        },
    }


class FakeSecurityAgentClient:
    """Scriptable fake for the AWS Continuum / Security Agent API.

    Mêmes signatures et mêmes noms de champs que
    :class:`rempart.orchestrator.sa_client.SecurityAgentClient` (doc officielle
    ``securityagent`` 2025-09-06) : ``agentSpaceId``, ``pentestId``,
    ``pentestJobId``, ``pentestSummaries``, ``pentestJobSummaries``,
    ``findingsSummaries``. Les paramètres requis sont VALIDÉS : un appel qui en
    oublie un lève ``ValueError``, ce qui protège contre les régressions.
    """

    def __init__(
        self,
        boto_client: Any = None,
        endpoint_url: str | None = None,
        region: str = "eu-west-3",
    ) -> None:
        self.spaces: dict[str, dict[str, Any]] = {}
        self.domains: dict[str, dict[str, Any]] = {}
        self.pentests: dict[str, dict[str, Any]] = {}
        self.jobs: dict[str, dict[str, Any]] = {}
        self.findings_by_job: dict[str, list[dict[str, Any]]] = {}
        self.job_outcomes: dict[str, str] = {}  # pentestJobId -> COMPLETED | FAILED
        self.default_outcome = "COMPLETED"
        # Réglage de scénario : les heures consommées d'UNE tâche du job.
        # Exposées uniquement par `list_pentest_job_tasks` (forme réelle).
        self.task_hours = 1.5
        self.max_task_hours = 5.0
        self.calls: list[tuple[str, dict[str, Any]]] = []

    @staticmethod
    def _require(action: str, values: dict[str, Any], required: tuple[str, ...]) -> None:
        missing = [k for k in required if not values.get(k)]
        if missing:
            raise ValueError(f"{action}: paramètre(s) requis manquant(s): {', '.join(missing)}")

    def set_job_outcome(self, job_id: str, status: str) -> None:
        """Script the final status of a job ('COMPLETED' or 'FAILED')."""
        self.job_outcomes[job_id] = status

    def create_agent_space(self, name: str, **kw: Any) -> dict[str, Any]:
        self._require("CreateAgentSpace", {"name": name}, ("name",))
        space_id = f"space-{uuid.uuid4().hex[:8]}"
        obj = {"agentSpaceId": space_id, "name": name, **kw}
        self.spaces[space_id] = obj
        self.calls.append(("create_agent_space", obj))
        return obj

    def create_target_domain(
        self,
        target_domain_name: str,
        verification_method: str = "DNS_TXT",
        **kw: Any,
    ) -> dict[str, Any]:
        self._require(
            "CreateTargetDomain",
            {"targetDomainName": target_domain_name,
             "verificationMethod": verification_method},
            ("targetDomainName", "verificationMethod"),
        )
        domain_id = f"dom-{uuid.uuid4().hex[:8]}"
        obj = {
            "targetDomainId": domain_id,
            "domainName": target_domain_name,
            "verificationMethod": verification_method,
            "verificationStatus": "PENDING",
            # Forme documentée de `verificationDetails` : dnsTxt OU httpRoute.
            "verificationDetails": _verification_details(verification_method),
            **kw,
        }
        self.domains[domain_id] = obj
        self.calls.append(("create_target_domain", obj))
        return obj

    def verify_target_domain(self, target_domain_id: str) -> dict[str, Any]:
        self._require(
            "VerifyTargetDomain",
            {"targetDomainId": target_domain_id},
            ("targetDomainId",),
        )
        self.calls.append(("verify_target_domain", {"targetDomainId": target_domain_id}))
        return {"targetDomainId": target_domain_id, "status": "VERIFIED"}

    def create_pentest(self, space_id: str, title: str, **kw: Any) -> dict[str, Any]:
        self._require(
            "CreatePentest",
            {"agentSpaceId": space_id, "title": title},
            ("agentSpaceId", "title"),
        )
        pentest_id = f"pt-{uuid.uuid4().hex[:8]}"
        obj = {"pentestId": pentest_id, "agentSpaceId": space_id, "title": title, **kw}
        self.pentests[pentest_id] = obj
        self.calls.append(("create_pentest", obj))
        return obj

    def start_pentest_job(self, space_id: str, pentest_id: str, **kw: Any) -> dict[str, Any]:
        self._require(
            "StartPentestJob",
            {"agentSpaceId": space_id, "pentestId": pentest_id},
            ("agentSpaceId", "pentestId"),
        )
        job_id = kw.get("pentestJobId") or f"job-{uuid.uuid4().hex[:8]}"
        self.jobs[job_id] = {
            "pentestJobId": job_id,
            "pentestId": pentest_id,
            "agentSpaceId": space_id,
            "status": "RUNNING",
        }
        self.calls.append(("start_pentest_job", {"agentSpaceId": space_id,
                                                "pentestId": pentest_id, **kw}))
        return {"pentestJobId": job_id, "status": "RUNNING"}

    def list_pentest_job_tasks(
        self,
        space_id: str,
        pentest_job_id: str | None = None,
        **kw: Any,
    ) -> list[dict[str, Any]]:
        """ListPentestJobTasks — SEULE source réelle des heures-tâches.

        Renvoie des ``TaskSummary`` conformes au modèle officiel : `taskId`,
        `pentestJobId`, `agentSpaceId`, `executionStatus`, `taskHours`.
        """
        self._require(
            "ListPentestJobTasks", {"agentSpaceId": space_id}, ("agentSpaceId",)
        )
        job_ids = (
            [pentest_job_id] if pentest_job_id else sorted(self.jobs)
        )
        summaries = []
        for job_id in job_ids:
            summaries.append(
                {
                    "taskId": f"task-{job_id}",
                    "pentestJobId": job_id,
                    "agentSpaceId": space_id,
                    "executionStatus": "COMPLETED",
                    "taskHours": self.task_hours,
                }
            )
        self.calls.append(
            ("list_pentest_job_tasks", {"agentSpaceId": space_id, "pentestJobId": pentest_job_id})
        )
        return summaries

    def stop_pentest_job(self, space_id: str, pentest_job_id: str) -> dict[str, Any]:
        self._require(
            "StopPentestJob",
            {"agentSpaceId": space_id, "pentestJobId": pentest_job_id},
            ("agentSpaceId", "pentestJobId"),
        )
        if pentest_job_id in self.jobs:
            self.jobs[pentest_job_id]["status"] = "STOPPED"
        self.calls.append(("stop_pentest_job", {"agentSpaceId": space_id,
                                                "pentestJobId": pentest_job_id}))
        return {}

    def _job_view(self, job_id: str) -> dict[str, Any]:
        job = self.jobs.get(job_id, {})
        status = job.get("status", "RUNNING")
        if status == "RUNNING":
            # scénario scripté : bascule dans l'état final au premier poll
            status = self.job_outcomes.get(job_id, self.default_outcome)
            if job_id in self.jobs:
                self.jobs[job_id]["status"] = status
        # Forme fidèle au modèle officiel : `PentestJob` n'a NI `taskHours`
        # (seulement `maxTaskHours`, un plafond) NI `durationSeconds`. Les heures
        # consommées vivent sur `TaskSummary.taskHours`, rendu par
        # `list_pentest_job_tasks` ci-dessous. Un double qui invente un champ
        # masque le défaut en production : c'est exactement ce qui s'est passé.
        view = {
            "pentestJobId": job_id,
            "status": status,
            "maxTaskHours": self.max_task_hours,
        }
        # Les horodatages posés par le scénario doivent survivre : la découverte
        # des tests CI/CD filtre sur `startedAt`.
        for key in ("startedAt", "startTime", "createdAt", "pentestId", "agentSpaceId"):
            if job.get(key):
                view[key] = job[key]
        return view

    def batch_get_pentest_jobs(
        self, space_id: str, pentest_job_ids: list[str]
    ) -> list[dict[str, Any]]:
        self._require(
            "BatchGetPentestJobs",
            {"agentSpaceId": space_id, "pentestJobIds": pentest_job_ids},
            ("agentSpaceId", "pentestJobIds"),
        )
        self.calls.append(("batch_get_pentest_jobs",
                           {"agentSpaceId": space_id,
                            "pentestJobIds": list(pentest_job_ids)}))
        return [self._job_view(jid) for jid in pentest_job_ids]

    def list_pentests(self, space_id: str, **kw: Any) -> list[dict[str, Any]]:
        self._require("ListPentests", {"agentSpaceId": space_id}, ("agentSpaceId",))
        return [p for p in self.pentests.values() if p.get("agentSpaceId") == space_id]

    def list_pentest_jobs_for_pentest(
        self, space_id: str, pentest_id: str, **kw: Any
    ) -> list[dict[str, Any]]:
        self._require(
            "ListPentestJobsForPentest",
            {"agentSpaceId": space_id, "pentestId": pentest_id},
            ("agentSpaceId", "pentestId"),
        )
        return [
            self._job_view(jid)
            for jid, job in self.jobs.items()
            if job.get("pentestId") == pentest_id
        ]

    def list_findings(
        self,
        space_id: str,
        *,
        pentest_job_id: str | None = None,
        code_review_job_id: str | None = None,
        **filters: Any,
    ) -> list[dict[str, Any]]:
        self._require("ListFindings", {"agentSpaceId": space_id}, ("agentSpaceId",))
        if pentest_job_id and code_review_job_id:
            raise ValueError("pentestJobId et codeReviewJobId sont mutuellement exclusifs")
        job_id = pentest_job_id or ""
        return list(self.findings_by_job.get(job_id, []))

    def seed_finding(
        self,
        job_id: str,
        *,
        severity: str,
        confidence: str,
        risk_type: str,
        entry_point: str,
        parameter: str | None = None,
        title: str = "Test Finding",
        description: str = "Detailed description",
    ) -> dict[str, Any]:
        """Ajoute une faille au scénario d'un job (aide de test, hors API réelle)."""
        f = {
            "findingId": f"sa-f-{uuid.uuid4().hex[:8]}",
            "title": title,
            "severity": severity,
            "confidence": confidence,
            "riskType": risk_type,
            "entryPoint": entry_point,
            "parameter": parameter,
            "description": description,
            "cvss": {"score": 7.5},
        }
        self.findings_by_job.setdefault(job_id, []).append(f)
        return f

    def update_finding(self, space_id: str, finding_id: str, **kw: Any) -> dict[str, Any]:
        self._require(
            "UpdateFinding",
            {"agentSpaceId": space_id, "findingId": finding_id},
            ("agentSpaceId", "findingId"),
        )
        self.calls.append(("update_finding", {"agentSpaceId": space_id,
                                              "findingId": finding_id, **kw}))
        return {}

    def start_code_remediation(
        self,
        space_id: str,
        finding_ids: list[str],
        *,
        pentest_job_id: str | None = None,
        code_review_job_id: str | None = None,
    ) -> dict[str, Any]:
        self._require(
            "StartCodeRemediation",
            {"agentSpaceId": space_id, "findingIds": finding_ids},
            ("agentSpaceId", "findingIds"),
        )
        if pentest_job_id and code_review_job_id:
            raise ValueError("pentestJobId et codeReviewJobId sont mutuellement exclusifs")
        self.calls.append(("start_code_remediation",
                           {"agentSpaceId": space_id, "findingIds": list(finding_ids)}))
        return {
            "pullRequestUrl": f"https://github.com/rempart/demo/pull/{uuid.uuid4().hex[:4]}",
            "remediationPrUrl": f"https://github.com/rempart/demo/pull/{uuid.uuid4().hex[:4]}",
        }



class FakeModelClient:
    """Fake Bedrock / LLM client returning canned responses."""

    def __init__(self, canned_response: str = '{"status": "ok"}') -> None:
        self.canned_response = canned_response
        self.calls: list[dict[str, Any]] = []

    def invoke(self, prompt: str, **kwargs: Any) -> str:
        self.calls.append({"prompt": prompt, "kwargs": kwargs})
        return self.canned_response
