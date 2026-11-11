"""Tests for the AWS Security Agent client wrapper (chapter 11.6)."""

from rempart.orchestrator.sa_client import SecurityAgentClient


class _RecordingClient:
    """Minimal boto3-like double recording the calls made by the wrapper."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    def __getattr__(self, name):
        def _call(**kwargs):
            self.calls.append((name, kwargs))
            if name == "batch_get_pentest_jobs":
                return {"pentestJobs": [{"jobId": "job-1"}]}
            if name == "list_findings":
                return {"findings": [{"findingId": "f-1"}]}
            if name == "list_pentests":
                return {"pentests": [{"pentestId": "pt-1"}]}
            if name == "list_pentest_jobs_for_pentest":
                return {"pentestJobs": [{"jobId": "job-9"}]}
            return {"ok": True}

        return _call


def test_wrapper_forwards_to_boto_client():
    boto = _RecordingClient()
    client = SecurityAgentClient(boto_client=boto)
    client.start_pentest_job("pt-1")
    assert boto.calls[-1] == ("start_pentest_job", {"pentestId": "pt-1"})


def test_create_agent_space():
    boto = _RecordingClient()
    client = SecurityAgentClient(boto_client=boto)
    client.create_agent_space("space-name")
    assert boto.calls[-1][0] == "create_agent_space"
    assert boto.calls[-1][1]["name"] == "space-name"


def test_stop_pentest_job():
    boto = _RecordingClient()
    client = SecurityAgentClient(boto_client=boto)
    client.stop_pentest_job("job-1")
    assert boto.calls[-1] == ("stop_pentest_job", {"jobId": "job-1"})


def test_batch_get_pentest_jobs_returns_list():
    client = SecurityAgentClient(boto_client=_RecordingClient())
    jobs = client.batch_get_pentest_jobs(["job-1"])
    assert jobs == [{"jobId": "job-1"}]


def test_list_findings_returns_list():
    client = SecurityAgentClient(boto_client=_RecordingClient())
    findings = client.list_findings("job-1")
    assert findings == [{"findingId": "f-1"}]


def test_list_pentests_returns_list():
    client = SecurityAgentClient(boto_client=_RecordingClient())
    assert client.list_pentests("space-1") == [{"pentestId": "pt-1"}]


def test_list_pentest_jobs_for_pentest_returns_list():
    client = SecurityAgentClient(boto_client=_RecordingClient())
    assert client.list_pentest_jobs_for_pentest("pt-1") == [{"jobId": "job-9"}]


def test_verify_target_domain():
    boto = _RecordingClient()
    client = SecurityAgentClient(boto_client=boto)
    client.verify_target_domain("space-1", "dom-1")
    assert boto.calls[-1] == (
        "verify_target_domain",
        {"agentSpaceId": "space-1", "domainId": "dom-1"},
    )


def test_start_code_remediation():
    boto = _RecordingClient()
    client = SecurityAgentClient(boto_client=boto)
    client.start_code_remediation("f-1")
    assert boto.calls[-1] == ("start_code_remediation", {"findingId": "f-1"})


def test_client_is_lazy_when_no_boto_client_injected():
    """No boto3 client is created at import time (tests must not need AWS)."""
    client = SecurityAgentClient()
    assert client._client is None
