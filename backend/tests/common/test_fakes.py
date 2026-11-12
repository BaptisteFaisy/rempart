"""Tests for fake clients (Security Agent, Model Client, GitHub, S3)."""

import pytest

from tests.fakes import (
    FakeGitHub,
    FakeModelClient,
    FakeS3,
    FakeSecurityAgentClient,
)


def test_fake_security_agent_client_lifecycle():
    """Cycle de vie complet, avec les noms de la doc officielle (2025-09-06)."""
    sa = FakeSecurityAgentClient()
    space_id = sa.create_agent_space("space-test")["agentSpaceId"]

    dom = sa.create_target_domain("api.example.com", "DNS_TXT")
    assert dom["domainName"] == "api.example.com"
    assert sa.verify_target_domain(dom["targetDomainId"])["status"] == "VERIFIED"

    pt = sa.create_pentest(space_id, "Livraison ShopLite")
    job_id = sa.start_pentest_job(space_id, pt["pentestId"])["pentestJobId"]

    sa.seed_finding(
        job_id,
        severity="High",
        confidence="High",
        risk_type="IDOR",
        entry_point="/orders/{id}",
        parameter="id",
        title="Bypass tenant check",
    )
    findings = sa.list_findings(space_id, pentest_job_id=job_id)
    assert len(findings) == 1
    # Forme OFFICIELLE d'un FindingSummary : ni `entryPoint`, ni `parameter`,
    # ni `description` (ils n'existent pas dans l'API réelle).
    assert findings[0]["riskType"] == "IDOR"
    assert findings[0]["riskLevel"] == "HIGH"
    assert findings[0]["confidence"] == "HIGH"
    assert findings[0]["name"] == "Bypass tenant check"
    assert findings[0]["agentSpaceId"] == space_id
    assert "entryPoint" not in findings[0]
    assert "parameter" not in findings[0]
    assert "description" not in findings[0]

    # Le DÉTAIL vient de BatchGetFindings : description et emplacement réel.
    details = sa.batch_get_findings(space_id, [findings[0]["findingId"]])
    assert len(details) == 1
    assert details[0]["description"] == "Detailed description"
    assert details[0]["codeLocations"][0]["filePath"] == "/orders/{id}"
    assert details[0]["codeLocations"][0]["label"] == "id"

    batch = sa.batch_get_pentest_jobs(space_id, [job_id])
    assert len(batch) == 1
    assert batch[0]["status"] == "COMPLETED"
    assert batch[0]["pentestJobId"] == job_id

    rem = sa.start_code_remediation(space_id, [findings[0]["findingId"]],
                                    pentest_job_id=job_id)
    assert "pullRequestUrl" in rem


def test_fake_security_agent_client_valide_les_requis():
    """Un paramètre requis manquant lève ValueError (protection anti-régression)."""
    sa = FakeSecurityAgentClient()
    with pytest.raises(ValueError, match="agentSpaceId"):
        sa.start_pentest_job("", "pt-1")
    with pytest.raises(ValueError, match="findingIds"):
        sa.start_code_remediation("space-1", [])
    with pytest.raises(ValueError, match="targetDomainName"):
        sa.create_target_domain("")


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
