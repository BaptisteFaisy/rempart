# Judge FAQ — Rempart (AWS MSP AI Hackathon, Track 2)

> Short, sourced answers to the questions judges are most likely to ask
> (anticipated in [`deepening-100-pistes.md`](deepening-100-pistes.md) #97).
> Every technical claim links to the file or test that proves it. Every
> limitation below is stated **as it really is** — nothing is deployed on AWS
> yet ([`submission-checklist.md`](submission-checklist.md)).

## How much does it cost, and how is the budget bounded?

Continuum bills **50 $/task-hour** with no native ceiling. Rempart bounds it
four ways: a monthly task-hour budget per customer with alerts at 50/80/100 %
and `StopPentestJob` mid-test at 100 %
([`backend/rempart/common/budget.py`](../backend/rempart/common/budget.py),
auto-stop tested in [`backend/tests/orchestrator/test_tasks.py`](../backend/tests/orchestrator/test_tasks.py));
a hard per-test cap (`REMPART_MAX_TASK_HOURS_PER_TEST`, default **5** —
[`backend/rempart/common/config.py`](../backend/rempart/common/config.py)); a
`free_tier_only` lock refusing any real test (HTTP 402, audited) until free-tier
eligibility is confirmed; and AWS Budgets alarms per account. The demo itself
costs **0 $**: the trial gives 2 months + 400 task-hours/month, and the public
portal runs on a frozen dataset. See [`free-tier-runbook.md`](free-tier-runbook.md).

## How is multi-tenant isolation guaranteed — and proven?

Continuum runs in the **customer's own account**, reached through a
cross-account IAM role with a unique `sts:ExternalId` and exactly the 16
least-privilege actions of Annex A, no wildcard — locked by tests
([`backend/tests/iac/test_least_privilege.py`](../backend/tests/iac/test_least_privilege.py)).
In the control plane, every route resolves a Cognito principal and checks role +
tenant before any read ([`backend/rempart/common/tenant.py`](../backend/rempart/common/tenant.py)).
Proven end to end: a tenant-A principal gets **403** on every tenant-B route and
tenant-B's report contains nothing from tenant A
([`backend/tests/integration/test_isolation_journey.py`](../backend/tests/integration/test_isolation_journey.py),
[`backend/tests/api/test_isolation.py`](../backend/tests/api/test_isolation.py)).
The audit journal is read-only by construction (POST → 404/405,
[`backend/tests/api/test_audit.py`](../backend/tests/api/test_audit.py)).

## What happens if AWS Continuum is unavailable?

Honestly: there is **no automatic fallback to another scanner** — that is a
documented open design question
([`deepening-100-pistes.md`](deepening-100-pistes.md) #65), not code. What
exists today: runs end in an explicit terminal status (`failed`/`stopped`,
[`backend/rempart/orchestrator/task_types.py`](../backend/rempart/orchestrator/task_types.py)),
the polling loop is capped at 4 h (240 iterations,
[`iac/control-plane/stacks/orchestrator.py`](../iac/control-plane/stacks/orchestrator.py)),
and alarms fire on orchestrator task failures and on CI/CD discovery failing or
silent for 30 min ([`iac/control-plane/stacks/observability.py`](../iac/control-plane/stacks/observability.py)).
The refused-run gate also requeues instead of losing a release window
(concurrency quota, [`backend/rempart/orchestrator/concurrency.py`](../backend/rempart/orchestrator/concurrency.py)).

## Why not just use an existing tool (SAST/DAST/bug bounty)?

Those tools detect; none of them run the **managed service**: signed-mandate
gate, per-customer budget with auto-stop, fleet view across customers,
contractual deadlines (P1 = 7 days) with reminders, closure **only** on retest
proof, executive-readable monthly report, sealed evidence pack for ISO 27001 /
SOC 2. Each gap is listed with its proving file in
[`what-rempart-adds.md`](what-rempart-adds.md). We do not claim measured parity
with a bug bounty program — that comparison is an open measurement question
([`deepening-100-pistes.md`](deepening-100-pistes.md) #45).

## Isn't this just a thin wrapper around Continuum?

The wrapper is deliberate and thin only where it should be: the
`SecurityAgentClient` adapter re-implements nothing
([`backend/rempart/orchestrator/sa_client.py`](../backend/rempart/orchestrator/sa_client.py),
verified action by action in [`api-verification.md`](api-verification.md)).
Everything a sellable service needs on top — onboarding by API, tenant
isolation, budget governance, contextual triage with deterministic guardrails,
deadline tracking to proven closure, mandate enforcement, executive reporting —
is the seven documented gaps in
[`what-rempart-adds.md`](what-rempart-adds.md), each pointing to code and tests.
Continuum has no notion of "customer", no ceiling, no deadline, no mandate.

## What is the real share of AI, and what are its guardrails?

Two AI layers: **Continuum's agents** perform the pentest (AWS side);
**Rempart's triage agent** (Strands on AgentCore Runtime, Bedrock) deduplicates,
summarises for a non-specialist and proposes a status — then **code takes back
control**: the deterministic priority matrix wins on divergence, a "likely false
positive" on Critical/High is always forced to human validation, and report
figures are computed by code with the model writing prose only
([`backend/rempart/reports/metrics.py`](../backend/rempart/reports/metrics.py):
*"No language model ever takes part in a number"*). Guardrails tested in
[`backend/tests/triage/test_guardrails.py`](../backend/tests/triage/test_guardrails.py);
a real prompt-injection hole was found and fixed
([`backend/tests/triage/test_prompt_injection.py`](../backend/tests/triage/test_prompt_injection.py)).

## What is actually deployed — and what isn't? (honest answer)

**Nothing is deployed on AWS to date** — no credentials were available during
development. The public portal
(https://tradoooo.github.io/rempart/) runs on a **frozen demo dataset**
([`demo/seed/demo-dataset.json`](../demo/seed/demo-dataset.json), 34 items);
**no real pentest has been executed**, all code is validated against fakes
([`submission-checklist.md`](submission-checklist.md) items 3 and 5;
[`deepening-100-pistes.md`](deepening-100-pistes.md) #84–#85). The first real
test is deliberately held until **23 November 2026** so the 2-month free trial
still covers judging on 22 January 2027 (specification § 16.2).

## Why don't you use Continuum's code review / threat modelling?

A pricing decision, not a technical one: code review costs **200 $ per million
protected lines per month + 10 $ per inference unit** and is **not** covered by
the free trial (which applies to penetration testing only). Rempart therefore
calls **no** code-vulnerabilities API — a grep for
`create_code_review|start_code_review|create_threat_model|list_threats` across
the codebase returns nothing, and remediation PRs are requested with
`pentestJobId` to stay on the pentest meter. Details and the pricing table:
[`what-rempart-adds.md`](what-rempart-adds.md), § "The one thing we deliberately
refuse to sell". This is also what makes a zero-cost demo possible.

## How are the figures and KPIs computed?

Every number is computed by plain Python from stored timestamps and states —
deterministically, recomputable by a third party from raw data:
[`backend/rempart/reports/metrics.py`](../backend/rempart/reports/metrics.py)
(month freezing, KPIs), closure only when a retest no longer shows the
fingerprint, with the retest job id stored as proof
([`backend/tests/integration/test_full_journey.py`](../backend/tests/integration/test_full_journey.py)).
The monthly report must match the dashboard (acceptance scenario **R10**,
[`acceptance.md`](acceptance.md)), and the evidence pack is sealed with a
recomputable SHA-256
([`backend/rempart/reports/evidence.py`](../backend/rempart/reports/evidence.py)).
The model never produces a figure — prose only.

## What was the hardest part?

Making the system **trustworthy enough to sell**, and the tests proved it was
not automatic: the end-to-end journey tests found **two real bugs** that ~350
unit tests had missed (the remediation PR was never requested; a reopened
finding kept a stale closure proof —
[`submission-checklist.md`](submission-checklist.md), "End-to-end journey
tests"); a genuine **prompt-injection hole** existed in the triage prompt
formatting and was fixed with `sanitize_untrusted()`; and the 13-month
retention was configured in CDK but **no code ever wrote `expire_at`**, so
nothing would ever have been purged
([`backend/rempart/common/store.py`](../backend/rempart/common/store.py),
[`backend/tests/common/test_retention.py`](../backend/tests/common/test_retention.py)).

## (Bonus — likely judge question) What about GDPR and the legality of testing?

Testing without authorisation is a criminal offence in France (art. 323-1 Penal
Code), so the mandate is a **blocking condition in the product**: no valid
mandate, no test — enforced twice (API 403 in
[`backend/rempart/api/routes/runs.py`](../backend/rempart/api/routes/runs.py),
orchestrator refusal `mandate_invalid`, audited, in
[`backend/rempart/orchestrator/gates.py`](../backend/rempart/orchestrator/gates.py);
scenario R12). The MSP acts as a GDPR **processor**: DPA template, 13-month TTL
retention, EU region (`eu-west-3`), AWS as sub-processor — see
[`docs/legal/dpa-template.md`](legal/dpa-template.md),
[`docs/legal/mandate-template.md`](legal/mandate-template.md) and
[`docs/legal/responsibility-matrix.md`](legal/responsibility-matrix.md)
(templates pending lawyer review, stated as such).
