"""Tests for fake clients (Security Agent, Model Client, GitHub, S3)."""

from tests.fakes import (
    FakeGitHub,
    FakeModelClient,
    FakeS3,
    FakeSecurityAgentClient,
)


def test_fake_security_agent_client_lifecycle():
    sa = FakeSecurityAgentClient()
    space = sa.create_agent_space("space-test")
    space_id = space["agentSpaceId"]

    dom = sa.create_target_domain(space_id, "api.example.com")
    assert dom["domain"] == "api.example.com"
    v = sa.verify_target_domain(space_id, dom["domainId"])
    assert v["status"] == "VERIFIED"

    pt = sa.create_pentest(space_id, {"kind": "delivery"})
    job = sa.start_pentest_job(pt["pentestId"])
    job_id = job["jobId"]

    # Seed findings with explicit fields
    sa.seed_finding(
        job_id,
        severity="High",
        confidence="High",
        risk_type="IDOR",
        entry_point="/orders/{id}",
        parameter="id",
        title="Bypass tenant check",
    )
    findings = sa.list_findings(job_id)
    assert len(findings) == 1
    assert findings[0]["riskType"] == "IDOR"
    assert findings[0]["parameter"] == "id"

    # Batch get jobs
    batch = sa.batch_get_pentest_jobs([job_id])
    assert len(batch) == 1
    assert batch[0]["status"] == "COMPLETED"

    # Remediation
    rem = sa.start_code_remediation(findings[0]["findingId"])
    assert "remediationPrUrl" in rem


def test_fake_model_client():
    mc = FakeModelClient(canned_response='{"proposal": "confirmed"}')
    res = mc.invoke("classify this finding")
    assert res == '{"proposal": "confirmed"}'
    assert len(mc.calls) == 1


def test_fake_github():
    gh = FakeGitHub(token="test")
    issue = gh.create_issue("owner", "repo", "Bug title", "Issue body", ["security", "P1"])
    assert "https://github.com/owner/repo/issues/1" in issue["html_url"]
    assert issue["number"] == 1
    gh.close_issue("owner", "repo", 1, "Closed after retest")
    assert gh.issues[0]["state"] == "closed"


def test_fake_s3():
    s3 = FakeS3()
    s3.put_object("bucket-rempart", "report.pdf", b"%PDF-1.4...", ContentType="application/pdf")
    obj = s3.get_object("bucket-rempart", "report.pdf")
    assert obj["Body"] == b"%PDF-1.4..."
    assert obj["ContentType"] == "application/pdf"
