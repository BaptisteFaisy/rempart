# Rempart — Acceptance Test Suite & Scenario Mapping

**Acceptance Criteria & Test Matrix (R1–R12)**  
*AWS MSP AI Hackathon — Track 2: Deliver AI-Driven Outcomes for Customers*  
*Specifications Reference: Cahier des charges, Chapter 21 & CONTRACT.md*

---

## 1. Acceptance Overview

The acceptance test suite validates the end-to-end functionality, security boundaries, and operational reliability of Rempart. Tests span four layers:
1. **Unit & Contract Tests**: Fast, deterministic Python pytest suites executing in memory using test doubles (`FakeStore`, `FakeSecurityAgentClient`, `FakeGitHub`, `FakeModelClient`).
2. **Infrastructure as Code (IaC) Synthesis**: AWS CDK assertions and CloudFormation template validation.
3. **API & Cross-Tenant Negative Tests**: Explicit authorization validation across all API endpoints.
4. **End-to-End Live Demonstrations**: Multi-account deployment with two seeded target applications (`ShopLite` and `BookWorm`).

### 1.1 Acceptance Scenarios Summary (R1–R12)

| Ref | Scenario Name | Test Target | Verification Method | Status |
|---|---|---|---|---|
| **R1** | Application Onboarding | Control plane onboarding workflow | Manual demo + API contract tests | `planned` |
| **R2** | Staging Delivery with Seeded Vulnerability | CI/CD gate + promotion blocking | Pytest + Demo CI workflow | `planned` |
| **R3** | Delivery Without Attack Surface Impact | Scoped commit bypass | Pytest (`test_discovery.py`) | `planned` |
| **R4** | Pentest Completion with Findings | Orchestration, triage, and ticketing | Pytest (`test_tasks.py`, `test_agent.py`) | `planned` |
| **R5** | High-Severity False Positive Guardrail | AI triage safety guardrail | Pytest (`test_guardrails.py`) | `planned` |
| **R6** | Remediation via Pull Request & Retest | Closed-loop retest & proof | Pytest (`test_tasks.py`) | `planned` |
| **R7** | Regression Detection (Reopened Finding) | Fingerprint matching & reopen status | Pytest (`test_fingerprint.py`, `test_guardrails.py`) | `planned` |
| **R8** | Task-Hour Budget Overrun | Budget gate & automated run cutoff | Pytest (`test_budget.py`, `test_tasks.py`) | `planned` |
| **R9** | Cross-Tenant Negative Authorization | Strict tenant data isolation | Pytest (`test_authz.py`, `test_routes.py`) | `planned` |
| **R10** | Deterministic Monthly Report KPIs | Zero-hallucination reporting | Pytest (`test_metrics.py`, `test_monthly.py`) | `planned` |
| **R11** | Clean Account Deployment | CDK & CloudFormation reproducibility | Pytest (`test_synth.py`, `test_client_template.py`) | `planned` |
| **R12** | Test Launch Without Valid Mandate | Legal mandate gate enforcement | Pytest (`test_tasks.py`) | `planned` |

---

## 2. Detailed Scenario Specifications

### R1: Application Onboarding
- **Objective**: Verify that a new customer application can be completely onboarded in under 30 minutes, requiring less than 10 minutes of active human configuration.
- **Preconditions**: Customer AWS account deployed with `rempart-client.template.yaml`.
- **Execution Steps**:
  1. POST `/v1/tenants` with account credentials, ExternalId, and monthly task-hour budget.
  2. Upload signed test mandate (`mandate_status="valid"`).
  3. POST `/v1/tenants/{id}/applications` declaring target domains and GitHub repositories.
  4. POST `/v1/applications/{id}/onboarding` to provision the AWS Security Agent `AgentSpace` and initiate domain verification.
- **Expected Outcome**:
  - `AgentSpace` created in client account; Route 53 DNS verification initiated.
  - Delivery and full `TestConfig` records registered in DynamoDB.
  - Elapsed human configuration time < 10 minutes; total setup time < 30 minutes.
- **Verification Mapping**:
  - Automated: `backend/tests/api/test_applications.py::test_onboard_application`
  - Automated: `backend/tests/orchestrator/test_sa_client.py::test_create_agent_space`
  - Demo: Live recorded onboarding sequence in the Rempart web portal.

---

### R2: Staging Delivery with Seeded Vulnerability
- **Objective**: Ensure that a commit introducing a critical vulnerability (e.g., IDOR in `ShopLite`) triggers the CI/CD gate, executes AWS Security Agent, and blocks pipeline promotion within 2 hours.
- **Preconditions**: `ShopLite` application active in staging; `VULN_IDOR=1` flag enabled.
- **Execution Steps**:
  1. Developer merges commit enabling vulnerable endpoint (`/orders/<id>` IDOR).
  2. GitHub Actions runs `.github/workflows/gate.yml`, notifying Rempart via POST `/v1/events/deployment`.
  3. Security Agent executes scoped pentest against the commit range.
  4. Finding severity evaluated against the application's blocking threshold (`Critical`).
- **Expected Outcome**:
  - Security Agent identifies IDOR vulnerability (Severity: High/Critical, Confidence: High).
  - CI/CD gate exits with non-zero failure code, halting staging promotion.
  - Total elapsed turnaround from deploy to block < 2 hours (API target).
- **Verification Mapping**:
  - Automated: `demo/app-a/tests/test_app.py::test_idor_vulnerability_present`
  - Automated: `backend/tests/orchestrator/test_discovery.py::test_discover_cicd_runs`
  - Demo: GitHub Actions workflow log showing pipeline gate failure on seeded commit.

---

### R3: Delivery Without Attack Surface Impact
- **Objective**: Validate that commits altering non-exposed application logic (e.g., internal documentation, backend helper utilities) bypass deep testing without blocking CI/CD promotion.
- **Preconditions**: Target application pipeline active in staging.
- **Execution Steps**:
  1. Push documentation/refactor commit that touches no exposed HTTP routes.
  2. CI/CD gate executes commit analysis with Security Agent.
- **Expected Outcome**:
  - Security Agent resolves `scope_decision="no_attack_surface_change"`.
  - Pipeline succeeds immediately without launching lengthy dynamic crawls.
  - Scope decision recorded in Rempart audit logs.
- **Verification Mapping**:
  - Automated: `backend/tests/orchestrator/test_discovery.py::test_skip_non_attack_surface_commit`
  - Automated: `backend/tests/orchestrator/test_tasks.py::test_poll_run_no_findings`

---

### R4: Pentest Completion with Findings
- **Objective**: Confirm that upon completion of a pentest job, findings are ingested, fingerprinted, triaged, assigned SLAs, and transformed into tracking tickets within 5 minutes.
- **Preconditions**: Pentest job finishes with raw findings in `FakeSecurityAgentClient`.
- **Execution Steps**:
  1. Execute Step Functions task `collect_findings`.
  2. Execute `dispatch_triage` calling the Strands triage agent.
  3. Execute `create_tickets`.
- **Expected Outcome**:
  - Finding assigned deterministic priority (e.g., `P1`).
  - Summaries generated (3-sentence plain summary + technical summary).
  - SLA calculated (`due_at = created_at + 7 days`).
  - GitHub tracking issue opened with SLA and reproduction steps.
- **Verification Mapping**:
  - Automated: `backend/tests/orchestrator/test_tasks.py::test_collect_and_triage_flow`
  - Automated: `backend/tests/triage/test_agent.py::test_run_triage_emits_valid_proposal`
  - Automated: `backend/tests/common/test_priority.py::test_compute_priority_matrix`

---

### R5: High-Severity False Positive Guardrail
- **Objective**: Enforce **ENF-IA-02**: the AI triage agent is strictly forbidden from autonomously dismissing Critical or High severity findings as false positives.
- **Preconditions**: Raw finding with `severity="High"` passed to triage.
- **Execution Steps**:
  1. Model returns `proposed_status="LIKELY_FALSE_POSITIVE"`.
  2. Apply `rempart.triage.guardrails.enforce()`.
- **Expected Outcome**:
  - Status overridden to `TO_VERIFY`.
  - Flag `needs_human_validation` forced to `True`.
  - Finding placed in MSP analyst queue with state `pending_validation`.
  - Finding cannot transition to `false_positive` without an explicit human analyst action.
- **Verification Mapping**:
  - Automated: `backend/tests/triage/test_guardrails.py::test_high_severity_false_positive_requires_human`
  - Automated: `backend/tests/api/test_findings.py::test_analyst_decision_endpoint`

---

### R6: Remediation via Pull Request & Retest
- **Objective**: Validate the full closed-loop remediation path: automated remediation PR generation, customer merge, automated retest, and evidence-backed ticket closure.
- **Preconditions**: Verified finding in state `confirmed`.
- **Execution Steps**:
  1. POST `/v1/findings/{id}/remediation` triggers `StartCodeRemediation`.
  2. Customer merges the resulting PR in staging (`VULN_IDOR=0`).
  3. Automated retest job triggered via `retest` pipeline run.
  4. Retest executes and detects zero instances of the fingerprinted flaw.
- **Expected Outcome**:
  - Finding transitions to `closed`.
  - Attribute `closed_by_run_id` set to the retest job ID.
  - Linked GitHub tracking issue closed with audit proof comment.
- **Verification Mapping**:
  - Automated: `backend/tests/orchestrator/test_tasks.py::test_close_finding_on_clean_retest`
  - Automated: `demo/app-a/tests/test_app.py::test_idor_vulnerability_fixed`
  - Demo: Live PR merge and automated issue closure walk-through.

---

### R7: Regression Detection (Reopened Finding)
- **Objective**: Verify that if a previously closed vulnerability reappears in a subsequent release, Rempart detects the regression via fingerprint matching and reopens it.
- **Preconditions**: Finding `f-01` with fingerprint `fp-abc` is in state `closed`.
- **Execution Steps**:
  1. Commit reintroduces flaw into staging.
  2. Step Functions task `collect_findings` processes new raw finding with matching fingerprint `fp-abc`.
  3. Apply triage guardrails.
- **Expected Outcome**:
  - New finding detected as regression (`is_regression=True`).
  - Finding state updated to `reopened`.
  - Regression event logged in audit trail; alert dispatched to account manager.
- **Verification Mapping**:
  - Automated: `backend/tests/common/test_fingerprint.py::test_fingerprint_deterministic`
  - Automated: `backend/tests/triage/test_guardrails.py::test_detect_regression_on_closed_fingerprint`
  - Automated: `backend/tests/orchestrator/test_tasks.py::test_reopen_regressed_finding`

---

### R8: Task-Hour Budget Overrun
- **Objective**: Confirm that when a tenant exhausts their monthly task-hour allocation ($50/hour rate), active pentests are automatically halted and new tests are blocked.
- **Preconditions**: Tenant with `monthly_budget_hours=10.0` and `hours_used=9.8`.
- **Execution Steps**:
  1. Run consumes 0.5 additional task-hours during polling loop.
  2. Task `poll_run` evaluates `rempart.common.budget.check_budget()`.
- **Expected Outcome**:
  - Total consumption reaches 10.3 hours (103% threshold).
  - Automated stop invoked via `securityagent:StopPentestJob`.
  - Run marked with `status="stopped"`.
  - Notification sent to client security contact and account manager.
  - Subsequent runs rejected at `budget_gate`.
- **Verification Mapping**:
  - Automated: `backend/tests/common/test_budget.py::test_budget_thresholds_and_auto_stop`
  - Automated: `backend/tests/orchestrator/test_tasks.py::test_budget_gate_blocks_when_exhausted`
  - Automated: `backend/tests/orchestrator/test_tasks.py::test_poll_stops_run_on_budget_exceeded`

---

### R9: Cross-Tenant Negative Authorization
- **Objective**: Enforce **ENF-SEC-01**: verify that an authenticated principal from Tenant A is strictly denied access to resources belonging to Tenant B across every API endpoint.
- **Preconditions**: Principals `user_a` (Tenant A) and `user_b` (Tenant B) configured in `FakeStore`.
- **Execution Steps**:
  1. Dispatch HTTP requests with `user_a` credentials against Tenant B resources:
     - `GET /v1/tenants/tenant-b`
     - `GET /v1/applications/{tenant-b-app-id}`
     - `GET /v1/findings?tenant_id=tenant-b`
     - `POST /v1/findings/{tenant-b-finding-id}/decision`
     - `GET /v1/tenants/tenant-b/reports`
- **Expected Outcome**:
  - Every unauthorized call returns HTTP 403 Forbidden.
  - Zero data payload returned; security audit log records authorization failure.
- **Verification Mapping**:
  - Automated: `backend/tests/common/test_tenant.py::test_authorize_read_and_write`
  - Automated: `backend/tests/api/test_authz.py::test_cross_tenant_negative_matrix`

---

### R10: Deterministic Monthly Report KPIs
- **Objective**: Verify **ENF-IA-01**: all monthly metrics, MTTR statistics, SLA compliance ratios, and cost computations are derived strictly by code from recorded timestamps, never hallucinated by an LLM.
- **Preconditions**: Completed runs and findings recorded across closed billing period.
- **Execution Steps**:
  1. Execute `compute_kpis(store, tenant_id="tenant-a", period="2026-11")`.
  2. Execute `freeze_month()`.
  3. Generate monthly report via `build_monthly_report()`.
- **Expected Outcome**:
  - KPIs in generated HTML/PDF report match exact numbers on MSP dashboard.
  - Task-hours, MTTR, and SLA percentages computed mathematically.
  - LLM used solely for executive narrative synthesis based on frozen numbers.
- **Verification Mapping**:
  - Automated: `backend/tests/reports/test_metrics.py::test_deterministic_kpis_calculation`
  - Automated: `backend/tests/reports/test_monthly.py::test_report_html_and_pdf_generation`

---

### R11: Clean Account Deployment
- **Objective**: Validate **ENF-REP-01**: the MSP control plane and client account infrastructure can be synthesized and deployed from code without manual interventions.
- **Preconditions**: Clean AWS CLI environment and CDK environment.
- **Execution Steps**:
  1. Synthesize CDK control plane (`cdk synth`).
  2. Validate client CloudFormation template (`rempart-client.template.yaml`).
- **Expected Outcome**:
  - CDK synthesis emits valid CloudFormation template with DynamoDB, Cognito, Lambdas, and Step Functions.
  - Client template defines least-privilege `rempart-operator` role with `sts:ExternalId` condition and required `securityagent:*` actions.
- **Verification Mapping**:
  - Automated: `backend/tests/iac/test_synth.py::test_cdk_synth_produces_stacks`
  - Automated: `backend/tests/iac/test_client_template.py::test_client_cfn_template_validity`

---

### R12: Test Launch Without Valid Mandate
- **Objective**: Enforce **ENF-LEG-01**: no pentest job can be dispatched unless the target application belongs to a tenant with a signed, active, and unexpired test mandate.
- **Preconditions**: Tenant record configured with `mandate_status="pending"` or `"expired"`.
- **Execution Steps**:
  1. Invoke Step Functions task `budget_gate` with a pentest launch payload.
  2. Attempt API launch via POST `/v1/applications/{id}/runs`.
- **Expected Outcome**:
  - `budget_gate` returns `allowed=False` with error code `MANDATE_INVALID`.
  - API returns HTTP 400 Bad Request with explicit message: "Signed test mandate required".
  - Pentest job never dispatched to AWS Security Agent.
- **Verification Mapping**:
  - Automated: `backend/tests/orchestrator/test_tasks.py::test_budget_gate_rejects_missing_mandate`
  - Automated: `backend/tests/api/test_runs.py::test_launch_run_rejected_without_mandate`

_Process check v2: full CI (backend, portal, demo, iac) + Mergify queue._

---

### ENF-PERF-01: Triage Throughput (50 findings < 5 minutes)
- **Objective**: Validate **ENF-PERF-01** (Cahier des charges, chapter 10): triage of 50 findings completes in under 5 minutes, with portal pages served in under 2 seconds.
- **Preconditions**: In-memory test doubles only (`FakeStore`, `FakeSecurityAgentClient`, `FakeGitHub`); no network, no AWS, deterministic 50-finding batch (mixed severities/confidences/risk types/entry points, including duplicates and one regression).
- **Execution Steps**:
  1. Run the measured chain `collect_findings` → `run_triage` → `enforce` on the 50-finding batch (`time.perf_counter()`, best of 5 runs, seeding excluded).
  2. Run `compute_kpis` and `freeze_month` on a realistic month (5 applications, 50 runs, 200 findings).
  3. Measure the marginal cost of `find_by_fingerprint` at 50 and 200 known findings.
- **Expected Outcome**:
  - Full triage of 50 findings under a 1.0 s test threshold — measured **2.5 ms** on the reference machine, i.e. ~100,000× under the 5-minute contractual budget (threshold rationale: 300 s would detect no regression at all).
  - Accuracy preserved at volume: all 50 raw findings accounted for (47 created + 2 duplicates + 1 regression), one finding per fingerprint, no duplicate ticket, regression detected, Critical/High still queued for human validation.
  - `compute_kpis` under 0.5 s (**measured 1.0 ms**) and `freeze_month` under 2.0 s (**measured 2.3 ms**), with figures matching an independent recomputation (ENF-IA-01).
  - Documented, not fixed: `find_by_fingerprint` and `guardrails._check_regression` are linear in the stored volume (O(n × base)); `list_findings` default `limit=100` can silently truncate duplicate/regression lookups.
- **Not covered here**: the portal 2-second page latency (front-end + network + API, to be measured on the deployed portal) and the real duration of a Continuum/Security Agent test (AWS-dependent).
- **Verification Mapping**:
  - Automated: `backend/tests/performance/test_triage_throughput.py::test_enf_perf_01_triage_of_50_findings_meets_budget`
  - Automated: `backend/tests/performance/test_triage_throughput.py::test_fingerprint_lookup_cost_stays_bounded_when_volume_grows`
  - Automated: `backend/tests/performance/test_kpis_throughput.py::test_compute_kpis_on_200_findings_meets_budget`
  - Reference: `backend/tests/performance/README.md` (measured figures, thresholds and rationale, optimization leads)

