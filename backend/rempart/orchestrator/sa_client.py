"""AWS Security Agent client — conforme à l'API Reference officielle.

Référence : https://docs.aws.amazon.com/securityagent/latest/APIReference/API_Operations.html
(service ``securityagent``, version 2025-09-06). Chaque méthode envoie
exactement les paramètres requis documentés (corps JSON, aucun paramètre URI)
et retourne les champs documentés : ``agentSpaceId``, ``pentestJobId``,
``pentestSummaries``, ``pentestJobSummaries``, ``findingsSummaries``, etc.
"""

from collections.abc import Sequence
from typing import Any


def require_params(action: str, body: dict[str, Any], required: tuple[str, ...]) -> None:
    """Lever une ``ValueError`` explicite si un paramètre requis manque au corps."""
    missing = [key for key in required if not body.get(key)]
    if missing:
        raise ValueError(f"{action}: paramètre(s) requis manquant(s): {', '.join(missing)}")


def job_source(
    pentest_job_id: str | None = None,
    code_review_job_id: str | None = None,
) -> dict[str, str]:
    """Construire le sélecteur de job documenté (pentestJobId XOR codeReviewJobId)."""
    if pentest_job_id and code_review_job_id:
        raise ValueError("pentestJobId et codeReviewJobId sont mutuellement exclusifs")
    if pentest_job_id:
        return {"pentestJobId": pentest_job_id}
    if code_review_job_id:
        return {"codeReviewJobId": code_review_job_id}
    return {}


class SecurityAgentClient:
    """Thin wrapper over the boto3 ``securityagent`` client.

    The boto3 client is created lazily on first use so importing this module
    never requires AWS credentials (tests inject ``boto_client`` or a fake).
    """

    def __init__(
        self,
        boto_client: Any = None,
        endpoint_url: str | None = None,
        region: str = "eu-west-3",
    ) -> None:
        self._client = boto_client
        self._endpoint_url = endpoint_url
        self._region = region

    @property
    def client(self) -> Any:
        """Return the underlying boto3 client, creating it on first access."""
        if self._client is None:
            import boto3

            self._client = boto3.client(
                "securityagent",
                endpoint_url=self._endpoint_url,
                region_name=self._region,
            )
        return self._client

    def create_agent_space(self, name: str, **kw: Any) -> dict[str, Any]:
        """CreateAgentSpace — requis : ``name``. Réponse : ``agentSpaceId``."""
        body = {"name": name, **kw}
        require_params("CreateAgentSpace", body, ("name",))
        return self.client.create_agent_space(**body)

    def create_target_domain(
        self,
        target_domain_name: str,
        verification_method: str = "DNS_TXT",
        **kw: Any,
    ) -> dict[str, Any]:
        """CreateTargetDomain — requis : ``targetDomainName``, ``verificationMethod``.

        ``verificationMethod`` : DNS_TXT | HTTP_ROUTE | PRIVATE_VPC.
        Réponse : ``targetDomainId``, ``domainName``, ``verificationStatus``.
        """
        body = {
            "targetDomainName": target_domain_name,
            "verificationMethod": verification_method,
            **kw,
        }
        require_params("CreateTargetDomain", body, ("targetDomainName", "verificationMethod"))
        return self.client.create_target_domain(**body)

    def verify_target_domain(self, target_domain_id: str) -> dict[str, Any]:
        """VerifyTargetDomain — requis : ``targetDomainId``. Réponse : ``status``."""
        body = {"targetDomainId": target_domain_id}
        require_params("VerifyTargetDomain", body, ("targetDomainId",))
        return self.client.verify_target_domain(**body)

    def create_pentest(self, space_id: str, title: str, **kw: Any) -> dict[str, Any]:
        """CreatePentest — requis : ``agentSpaceId``, ``title``. Réponse : ``pentestId``."""
        body = {"agentSpaceId": space_id, "title": title, **kw}
        require_params("CreatePentest", body, ("agentSpaceId", "title"))
        return self.client.create_pentest(**body)

    def start_pentest_job(self, space_id: str, pentest_id: str, **kw: Any) -> dict[str, Any]:
        """StartPentestJob — requis : ``agentSpaceId``, ``pentestId``.

        Optionnels : ``jobType`` (FULL|REVALIDATION|CICD), ``scopeChanges``,
        ``selectedFindingIds``. Réponse : ``pentestJobId``, ``status``.
        """
        body = {"agentSpaceId": space_id, "pentestId": pentest_id, **kw}
        require_params("StartPentestJob", body, ("agentSpaceId", "pentestId"))
        return self.client.start_pentest_job(**body)

    def stop_pentest_job(self, space_id: str, pentest_job_id: str) -> dict[str, Any]:
        """StopPentestJob — requis : ``agentSpaceId``, ``pentestJobId``. Corps vide."""
        body = {"agentSpaceId": space_id, "pentestJobId": pentest_job_id}
        require_params("StopPentestJob", body, ("agentSpaceId", "pentestJobId"))
        return self.client.stop_pentest_job(**body)

    def batch_get_pentest_jobs(
        self,
        space_id: str,
        pentest_job_ids: Sequence[str],
    ) -> list[dict[str, Any]]:
        """BatchGetPentestJobs — requis : ``agentSpaceId``, ``pentestJobIds``.

        Retourne la liste documentée ``pentestJobs`` (objets PentestJob dont la
        clé d'identité est ``pentestJobId``).
        """
        body = {"agentSpaceId": space_id, "pentestJobIds": list(pentest_job_ids)}
        require_params("BatchGetPentestJobs", body, ("agentSpaceId", "pentestJobIds"))
        resp = self.client.batch_get_pentest_jobs(**body)
        return list(resp.get("pentestJobs", []))

    def list_pentest_job_tasks(
        self,
        space_id: str,
        pentest_job_id: str | None = None,
        **kw: Any,
    ) -> list[dict[str, Any]]:
        """ListPentestJobTasks — requis : ``agentSpaceId``.

        Liste documentée : ``taskSummaries``. C'est la SEULE source réelle des
        heures-tâches consommées : le modèle officiel ne déclare ``taskHours``
        que sur ``TaskSummary``/``Task``. ``PentestJob`` (renvoyé par
        ``BatchGetPentestJobs``) ne porte que ``maxTaskHours``, un plafond.
        """
        body = {"agentSpaceId": space_id, **kw}
        if pentest_job_id:
            body["pentestJobId"] = pentest_job_id
        require_params("ListPentestJobTasks", body, ("agentSpaceId",))
        resp = self.client.list_pentest_job_tasks(**body)
        return list(resp.get("taskSummaries", []))

    def list_pentests(self, space_id: str, **kw: Any) -> list[dict[str, Any]]:
        """ListPentests — requis : ``agentSpaceId``. Liste documentée : ``pentestSummaries``."""
        body = {"agentSpaceId": space_id, **kw}
        require_params("ListPentests", body, ("agentSpaceId",))
        resp = self.client.list_pentests(**body)
        return list(resp.get("pentestSummaries", []))

    def list_pentest_jobs_for_pentest(
        self,
        space_id: str,
        pentest_id: str,
        **kw: Any,
    ) -> list[dict[str, Any]]:
        """ListPentestJobsForPentest — requis : ``agentSpaceId``, ``pentestId``.

        Liste documentée : ``pentestJobSummaries`` (clé ``pentestJobId``).
        """
        body = {"agentSpaceId": space_id, "pentestId": pentest_id, **kw}
        require_params("ListPentestJobsForPentest", body, ("agentSpaceId", "pentestId"))
        resp = self.client.list_pentest_jobs_for_pentest(**body)
        return list(resp.get("pentestJobSummaries", []))

    def list_findings(
        self,
        space_id: str,
        *,
        pentest_job_id: str | None = None,
        code_review_job_id: str | None = None,
        **filters: Any,
    ) -> list[dict[str, Any]]:
        """ListFindings — requis : ``agentSpaceId`` ; ``pentestJobId``/``codeReviewJobId``
        optionnels et mutuellement exclusifs. Liste documentée : ``findingsSummaries``.
        """
        body = {
            "agentSpaceId": space_id,
            **job_source(pentest_job_id, code_review_job_id),
            **filters,
        }
        require_params("ListFindings", body, ("agentSpaceId",))
        resp = self.client.list_findings(**body)
        return list(resp.get("findingsSummaries", []))

    def update_finding(self, space_id: str, finding_id: str, **kw: Any) -> dict[str, Any]:
        """UpdateFinding — requis : ``agentSpaceId``, ``findingId``. Corps de réponse vide."""
        body = {"agentSpaceId": space_id, "findingId": finding_id, **kw}
        require_params("UpdateFinding", body, ("agentSpaceId", "findingId"))
        return self.client.update_finding(**body)

    def start_code_remediation(
        self,
        space_id: str,
        finding_ids: Sequence[str],
        *,
        pentest_job_id: str | None = None,
        code_review_job_id: str | None = None,
    ) -> dict[str, Any]:
        """StartCodeRemediation — requis : ``agentSpaceId``, ``findingIds`` (tableau).

        ``pentestJobId`` ou ``codeReviewJobId`` (optionnels, mutuellement
        exclusifs). Corps de réponse vide selon la documentation.
        """
        body = {
            "agentSpaceId": space_id,
            "findingIds": list(finding_ids),
            **job_source(pentest_job_id, code_review_job_id),
        }
        require_params("StartCodeRemediation", body, ("agentSpaceId", "findingIds"))
        return self.client.start_code_remediation(**body)
