"""AWS Security Agent client (section 11.6 actions) with lazy boto3."""

from typing import Any


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
        return self.client.create_agent_space(name=name, **kw)

    def create_target_domain(self, space_id: str, domain: str, **kw: Any) -> dict[str, Any]:
        return self.client.create_target_domain(agentSpaceId=space_id, domain=domain, **kw)

    def verify_target_domain(self, space_id: str, domain_id: str) -> dict[str, Any]:
        return self.client.verify_target_domain(agentSpaceId=space_id, domainId=domain_id)

    def create_pentest(self, space_id: str, config: dict[str, Any]) -> dict[str, Any]:
        return self.client.create_pentest(agentSpaceId=space_id, configuration=config)

    def start_pentest_job(self, pentest_id: str, **kw: Any) -> dict[str, Any]:
        return self.client.start_pentest_job(pentestId=pentest_id, **kw)

    def stop_pentest_job(self, job_id: str) -> dict[str, Any]:
        return self.client.stop_pentest_job(jobId=job_id)

    def batch_get_pentest_jobs(self, job_ids: list[str]) -> list[dict[str, Any]]:
        resp = self.client.batch_get_pentest_jobs(jobIds=list(job_ids))
        return list(resp.get("pentestJobs", resp.get("jobs", [])))

    def list_pentests(self, space_id: str) -> list[dict[str, Any]]:
        resp = self.client.list_pentests(agentSpaceId=space_id)
        return list(resp.get("pentests", []))

    def list_pentest_jobs_for_pentest(self, pentest_id: str) -> list[dict[str, Any]]:
        """List jobs of a pentest (used by CI/CD discovery when available)."""
        resp = self.client.list_pentest_jobs_for_pentest(pentestId=pentest_id)
        return list(resp.get("pentestJobs", resp.get("jobs", [])))

    def list_findings(self, job_id: str) -> list[dict[str, Any]]:
        resp = self.client.list_findings(jobId=job_id)
        return list(resp.get("findings", []))

    def update_finding(self, finding_id: str, **kw: Any) -> dict[str, Any]:
        return self.client.update_finding(findingId=finding_id, **kw)

    def start_code_remediation(self, finding_id: str, **kw: Any) -> dict[str, Any]:
        return self.client.start_code_remediation(findingId=finding_id, **kw)
