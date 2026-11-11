# What Rempart adds on top of AWS Continuum

> The specification names this as the top risk (chapter 20): *"Le projet passe
> pour une simple surcouche"* — judges may conclude we wrapped a service that
> already does the job. This document answers that objection with evidence:
> every claim points to a file or a test in this repository.
>
> **We are explicit about what Continuum already does.** Overstating our own
> contribution would be the fastest way to lose credibility with an AWS judge
> who knows the service.

## What AWS Continuum already does (and we do not re-implement)

| Capability | Status |
|---|---|
| On-demand penetration testing against verified domains | Continuum |
| CI/CD gate that scopes a test to the deployed commit range and blocks promotion above a severity threshold | Continuum |
| Reusable test configurations, scheduled tests | Continuum |
| Finding detail: severity, agent confidence, risk type, CVSS, reproduction steps, verification script | Continuum |
| Remediation pull request generation | Continuum |
| Code review, threat modelling, design review | Continuum — **and we deliberately do not call these** (see below) |

Rempart calls Continuum's API and never re-implements any of it. The
`SecurityAgentClient` wrapper is a thin, contract-tested adapter:
[`backend/rempart/orchestrator/sa_client.py`](../backend/rempart/orchestrator/sa_client.py),
verified action by action against the official API reference in
[`docs/api-verification.md`](api-verification.md).

## The seven things a managed service needs that Continuum does not provide

Continuum is configured **one application at a time, by hand, inside one
account**. A managed service sold to many customers needs everything around
that. Each item below is a gap in the product, not a gap in our imagination.

### 1. Automated, repeatable onboarding

**Gap** — Continuum has no notion of "customer". Provisioning an application
means a sequence of API calls plus a CloudFormation template in the customer
account, done by hand.

**Rempart** — one `POST /v1/applications/{id}/onboarding` creates the agent
space, declares and verifies the target domain (DNS_TXT, HTTP_ROUTE or
PRIVATE_VPC), creates the delivery and full test configurations, and returns
the exact instruction the customer must apply.

*Proof*: [`backend/rempart/api/routes/onboarding.py`](../backend/rempart/api/routes/onboarding.py)
· tests [`backend/tests/api/test_onboarding_verification.py`](../backend/tests/api/test_onboarding_verification.py)
· acceptance scenario **R1** (onboarding under 30 minutes, of which under 10
minutes of human action).

### 2. Multi-tenant fleet governance with hard isolation

**Gap** — Continuum's quotas are per account and per region: **20 integrations**
(not adjustable) and **5 concurrent tests**. One central account would cap the
whole MSP at 20 customer repositories.

**Rempart** — Continuum runs in the *customer's* account, reached through a
cross-account IAM role with a unique `sts:ExternalId`; the MSP control plane
holds one fleet view. This is also the only model where a customer's findings
stay in their account and their test cost lands on their own bill.

*Proof*: [`iac/client-account/rempart-client.template.yaml`](../iac/client-account/rempart-client.template.yaml)
· least-privilege locked by test: exactly the 16 `securityagent:` actions of
Annex A, no wildcard, no IAM write permission, `sts:ExternalId` mandatory —
[`backend/tests/iac/test_client_template.py`](../backend/tests/iac/test_client_template.py)
· isolation proven end to end after a real journey: a tenant-A principal gets
**403** on every tenant-B route, and the tenant-B report contains nothing from
tenant A — [`backend/tests/integration/test_isolation_journey.py`](../backend/tests/integration/test_isolation_journey.py),
[`backend/tests/api/test_isolation.py`](../backend/tests/api/test_isolation.py),
acceptance scenario **R9**.

### 3. Budget governance with an automatic stop

**Gap** — Continuum bills per task-hour (50 $/h, per second) with **no ceiling
and no cost estimate beforehand**. The only reference is the history of the
same configuration.

**Rempart** — a monthly task-hour budget per customer, alerts at 50/80/100 %,
`StopPentestJob` mid-test at 100 %, a hard per-test cap
(`REMPART_MAX_TASK_HOURS_PER_TEST`), and a forecast of the month-end burn with
a projected exhaustion date plus a reference cost per test configuration.

*Proof*: [`backend/rempart/common/budget.py`](../backend/rempart/common/budget.py)
· auto-stop tested in [`backend/tests/orchestrator/test_tasks.py`](../backend/tests/orchestrator/test_tasks.py)
· acceptance scenario **R8** (budget exceeded mid-test → test stopped, alert sent).

### 4. Contextual triage with deterministic guardrails

**Gap** — Continuum reports severity and its own confidence. It does not know
that this application is internet-facing, handles payment data, belongs to a
customer who signed a 7-day remediation clause, or that this finding is the same
one the analyst dismissed last month.

**Rempart** — a Strands agent on AgentCore Runtime with Bedrock deduplicates
findings described differently, writes a three-sentence summary for a
non-specialist, and proposes a status. Then **code takes back control**:

- priority is recomputed by a deterministic matrix (severity × confidence ×
  exposure × data sensitivity) and the **matrix wins** on divergence;
- a "likely false positive" on a Critical or High finding is **always** forced
  to human validation — the model can never dismiss one alone;
- finding content is passed as delimited data and the system prompt forbids
  following any instruction inside it (prompt-injection resistance, tested).

*Proof*: [`backend/rempart/triage/`](../backend/rempart/triage/)
· matrix in [`backend/rempart/common/priority.py`](../backend/rempart/common/priority.py)
· guardrails in [`backend/tests/triage/test_guardrails.py`](../backend/tests/triage/test_guardrails.py)
· injection resistance in [`backend/tests/triage/test_prompt_injection.py`](../backend/tests/triage/test_prompt_injection.py)
· acceptance scenarios **R4** and **R5**.

### 5. Contractual remediation deadlines, tracked to proven closure

**Gap** — Continuum produces findings and a remediation pull request. It does
not track whether anyone fixed anything, and it has no concept of a deadline.

**Rempart** — priority P1–P4 with a contractual due date (7/30/90 days, or next
release), reminders before and after the deadline with escalation to the account
manager, a ticket opened in the customer's repository with that deadline, the
remediation pull request linked to the finding, and closure **only** when a
retest no longer shows the fingerprint — the retest job id is stored as the
proof. A finding that reappears is reopened and flagged as a regression.

*Proof*: the three Step Functions machines in
[`iac/control-plane/stacks/orchestrator.py`](../iac/control-plane/stacks/orchestrator.py)
(`RempartPentestLifecycle`, `RempartCicdIntake`, `RempartRetestClose`)
· the full journey in [`backend/tests/integration/test_full_journey.py`](../backend/tests/integration/test_full_journey.py)
· regression path in [`backend/tests/integration/test_regression_journey.py`](../backend/tests/integration/test_regression_journey.py)
· acceptance scenarios **R6** and **R7**.

### 6. Legality: no test without a signed mandate

**Gap** — Continuum requires a *verified domain*. It does not require proof that
the domain's owner authorised the test.

**Rempart** — testing a system without authorisation is a criminal offence in
France (article 323-1 of the Penal Code), so the mandate is a **blocking
condition in the product**, not a formality: no valid mandate, no test, with an
audit entry. Production tests additionally require an agreed window.

*Proof*: mandate gate in
[`backend/rempart/orchestrator/tasks.py`](../backend/rempart/orchestrator/tasks.py)
(`budget_gate`, reason `mandate_invalid`) · test windows in
[`backend/rempart/orchestrator/windows.py`](../backend/rempart/orchestrator/windows.py)
· acceptance scenario **R12** (launching a test without a valid mandate is refused).

### 7. Reporting an executive can read, and an audit trail

**Gap** — Continuum exports a test report: technical, per test, per account.

**Rempart** — a monthly report per customer in HTML and PDF where the numbers
are frozen by code first and the model only writes prose over them; a fleet
dashboard for the MSP; an immutable, read-only audit journal; and an exportable,
SHA-256-sealed evidence pack for ISO 27001 / SOC 2 reviews.

*Proof*: [`backend/rempart/reports/`](../backend/reports) —
`metrics.py` (all figures computed by code), `monthly.py`,
`evidence.py` (sealed pack, recomputable digest)
· report matches the dashboard: acceptance scenario **R10**
· audit is read-only by construction: `POST /v1/audit` returns 404/405, tested in
[`backend/tests/api/test_audit.py`](../backend/tests/api/test_audit.py).

## The one thing we deliberately refuse to sell

Continuum has two capabilities with very different economics:

| Capability | Price | Free trial |
|---|---|---|
| **Continuum for penetration testing** | 50 $/task-hour, per second | **yes** — 2 months, 400 task-hours/month for new customers |
| **Continuum for code vulnerabilities** | 200 $ per million protected lines per month **+ 10 $ per inference unit** | **no** — the pricing page states the trial applies to penetration testing only |

Our specification originally assumed code review was free in preview. It is not.
Rempart therefore calls **no** code-vulnerabilities API: a grep for
`create_code_review|start_code_review|create_threat_model|list_threats` across
the codebase returns nothing, and nobody passes `codeReviewJobId`. The
remediation pull request is requested with `pentestJobId`, which keeps it on the
penetration-testing meter.

This is a pricing decision, not a technical limitation — and it is the reason a
demo can be run at zero cost. See [`docs/free-tier-runbook.md`](free-tier-runbook.md).

## The one-sentence version

> Continuum performs the test. Rempart makes it a **sellable managed service**:
> onboarded by API, isolated per customer, capped by budget, triaged in business
> context, tracked to a contractual deadline, closed only on proof, reported to
> an executive, and auditable — with the legality of testing enforced by code.
