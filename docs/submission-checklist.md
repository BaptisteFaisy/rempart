# Submission checklist — AWS MSP AI Hackathon, Track 2

> Source: `docs/cahier-des-charges-tests-intrusion-continu.md` § 18.1.
> Deadline: **Friday 11 December 2026, 12:00 PT** (21:00 Paris).
> Judging ends 22 January 2027 — the solution must stay online until then.
>
> Statuses are honest as of **14 November 2026**. Cognito is active, the
> CloudFront portal and API are online, and the remaining runtime gate is the
> first real Continuum test. It must not start before **23 November 2026** and
> must not be unlocked until the customer account's free-trial eligibility is
> verified and recorded. See [`deployment-eu-north-1.md`](deployment-eu-north-1.md),
> [`portal-deployment.md`](portal-deployment.md), and
> [`runbook-premier-test.md`](runbook-premier-test.md).

| # | Requirement | Status | Proof / what is left |
|---|---|---|---|
| 1 | Track 2 selected, AWS AI service named | **to do** (form) | Text ready: [`devpost-submission.md`](devpost-submission.md). Service to name: AWS Continuum (penetration testing) + Amazon Bedrock via Strands Agents on AgentCore Runtime. |
| 2 | Description in English: features, problem, measured outcomes | **done** | [`devpost-submission.md`](devpost-submission.md) § Description, How we built it, three measured outcomes. |
| 3 | Public URL of the portal, with demo credentials in the test instructions | **done** | GitHub Pages remains the free judging demo: https://tradoooo.github.io/rempart/. The AWS-backed portal is online at https://d1o2xnfrq8xomh.cloudfront.net and the API is online at https://qm6dmdkgdg.execute-api.eu-north-1.amazonaws.com. Cognito is **active** with authorization-code + PKCE; the hosted domain and callback configuration are recorded in [`portal-deployment.md`](portal-deployment.md). Keep public judging on the frozen, offline dataset; do not expose customer data. |
| 4 | Private repo shared with `testing@devpost.com` and `aws-msp@amazon.com` | **decision needed** | The repository is currently **public** (it was created private; the visibility changed outside this work). The specification asks for a *private* repo shared with the two judge accounts. A public repo is generally accepted by Devpost, but it exposes the French specification — commercial strategy, pricing hypotheses, schedule. **Your call**: keep it public, or set it back to private (GitHub Pages keeps working on a Pro plan) and invite the judge accounts at submission time. |
| 5 | The code really calls an AWS AI service at runtime | **blocked until 23 Nov** | Calls are written and unit-tested against the official API reference ([`docs/api-verification.md`](api-verification.md)). The first real `StartPentestJob` is reserved for **23 November 2026** and is forbidden until the customer account's free-trial eligibility has been checked in Billing and Continuum, recorded in the run evidence, and confirmed for the tenant. Follow [`runbook-premier-test.md`](runbook-premier-test.md); if eligibility is absent or ambiguous, use the frozen demo and do not start a job. |
| 6 | Video ~3 minutes, public on YouTube, English, no third-party brand or music | **out of scope for the agent** | Script written and timed: [`video-script.md`](video-script.md). The user records and edits. |
| 7 | Architecture diagram | **done** | Mermaid diagrams in [`HLD.md`](HLD.md) (control plane + customer account) and in [`README.md`](../README.md); sequence diagram of a delivery and finding lifecycle state diagram in the specification § 11.4-11.5. |
| 8 | Design document (HLD) | **done** | [`HLD.md`](HLD.md). |
| 9 | If the project reuses existing work: what changed during the period | **n/a** | Rempart was started from scratch on 10 November 2026. Commit `d24edad` is the first commit of the repository. |

## Extra items we track beyond the official list

| Item | Status | Proof |
|---|---|---|
| Acceptance scenarios R1–R12 | **done** (mapped) | [`acceptance.md`](acceptance.md) — each scenario points to an automated test or a documented demo step. |
| Test instructions for judges | **done** (placeholders) | [`judging-test-instructions.md`](judging-test-instructions.md). |
| CI budget ≤ 5 min, enforced | **done** | 9 workflows, `ci-budget` guard fails any job declaring more; measured backend 1 m 07 s, IaC 1 m 04 s, demo 35 s, portal 22 s, budget 8 s. |
| Merge automation | **partial** | `.mergify.yml` is committed and correct, but the **Mergify GitHub App is not authorised on this repository** yet (verified: on `BaptisteFaisy/Crypte` PRs are merged by `app/mergify`, here Mergify does not react). Action: GitHub Settings → Applications → Mergify → configure → add `rempart`, and activate the Merge Queue product in the Mergify dashboard. |
| Conflict-resolution agent (InferHub) | **partial** | Code + workflow + 39 tests committed. Secret `INFERHUB_API_KEY` and variables `INFERHUB_AGENT_RESOLVE`, `INFERHUB_BASE_URL`, `INFERHUB_MODEL` are set. **Missing: secret `AUTOMERGE_PAT`** (owner token). Without it the workflow falls back to `github.token`: a bot push puts workflows in `action_required`, so the PR loses its required checks and becomes unstuck-able. |
| Contributor `GaiaSG94` | **invited, pending** | Invitation `342772446`, permission `write`, not expired. Waiting on their acceptance. |
| Zero-cost guarantee | **done** | [`free-tier-runbook.md`](free-tier-runbook.md). Two coded locks, both tested: `REMPART_FREE_TIER_ONLY=1` (default) makes the budget gate **and** `POST /v1/applications/{id}/runs` refuse any real test until `Tenant.free_tier_confirmed` is true — reason `free_tier_not_confirmed`, HTTP 402, audited; `REMPART_MAX_TASK_HOURS_PER_TEST=5` stops a test past 5 task-hours even with a wide monthly budget. Both wired into the CDK Lambda environments. Rempart calls no "code vulnerabilities" API, the one capability outside the free trial. |
| Frozen demo dataset | **done** | `scripts/seed_demo.py` → `demo/seed/demo-dataset.json` (34 items: 2 tenants, 2 applications, 4 test configs, 6 runs, 6 findings across the whole lifecycle, 10 decisions, budgets, 2 monthly reports). 8 tests assert the dataset, including that priorities match the deterministic matrix and that the committed JSON equals what the generator produces. This is what makes the judge tour cost 0 $. |
| Local demo server (no AWS) | **done** | `scripts/serve_local.py` — stdlib only, serves the frozen dataset through the **real** API handlers and the **real** authorisation layer. Verified live: `/v1/tenants` returns the 2 tenants, `/v1/tenants/demo-a/kpis` returns computed KPIs, a tenant-A principal hitting a tenant-B route gets **403**, `POST /v1/audit` gets **404** (journal not writable). Start it, then `cd portal && npm run dev:local`. |
| End-to-end journey tests | **done** | `backend/tests/integration/` — 18 tests playing chapter 8 in full (onboarding → run → collect → triage → analyst decision via the API → ticket → remediation PR → retest → closure with proof → monthly report), plus the regression path (R7) and tenant isolation after a real journey (R9). **These found two real bugs** that 357 unit tests had missed: the remediation PR was never requested (the ticket had already set `in_remediation`, which `request_remediation` excluded), and a reopened finding kept the proof of a closure that was no longer true. |
| CDK ↔ code handler contract | **done** | `backend/tests/iac/test_handler_contract.py` asserts every Lambda handler declared in CDK exists with an `(event, context)` signature. `test_lambda_code.py` adds 9 tests proving no Lambda ships inline placeholder code. Verified by re-injecting the placeholder on purpose: the tests fail and name it. |
| Real code in Lambdas | **done** | `create_python_lambda` used `Code.from_inline` with a stub body — the deployment would have created **empty** functions. Now `Code.from_asset(backend/)` plus a dependency layer (`scripts/build_lambda_layer.sh`: fpdf2, requests, strands-agents) and X-Ray tracing on every function. |
| 13-month retention (ENF-DATA-01) | **done** | CDK had configured `time_to_live_attribute` but **no code ever wrote `expire_at`**, so nothing would ever be purged. Every write now stamps it; `Store.set_expire_at` handles the 30-day end-of-contract purge. 8 tests. |
| Audit evidence pack (EF-RAP-04) | **done** | `rempart/reports/evidence.py` — self-contained, deterministic JSON + offline-readable HTML, sealed with a recomputable SHA-256. Carries the decision chain per finding (author, action, justification, timestamp), closure proofs, exceptions, audit journal and frozen KPIs. No exploitation detail leaves the pack (ENF-SEC-05). 16 tests. |
| Observability (ENF-OBS-01) | **done** | `stacks/observability.py` — alarms on API errors/p95 (2 s budget)/throttles, on each of the 8 orchestrator tasks, on CI/CD discovery failing **or silent for 30 min**, on failed executions of the 3 state machines, and on DynamoDB write throttling. All routed to SNS. 9 tests. |
| Portal authentication (EF-POR-01) | **done** | `portal/src/auth/` — Cognito authorization-code + PKCE via Web Crypto, no new dependency (+4 kB bundle). Role and tenant come from id-token claims, exactly what `resolve_principal` reads. The persona picker throws when Cognito is configured, so a judge cannot self-assign a role. Demo mode preserved with an explicit banner. 19 vitest tests. |
| Per-customer policy (EF-ADM-01) | **done** | `Tenant.policy` + `rempart/common/priority.py::compute_priority_with_policy` + routes `GET/PUT /v1/tenants/{id}/policy` and `GET /v1/settings/defaults`. Only `platform_admin` writes; a client targeting another tenant gets 403. |
| Triage memory (EF-TRI-09) | **done** | `rempart/triage/memory.py` — past human decisions on the same fingerprint drive the next proposal, most recent wins, per application. The matrix still computes priority and a Critical/High finding still requires a human, memory or not. |
| Deadline reminders (EF-COR-06) | **done** | `rempart/orchestrator/reminders.py` — classifies each open finding as `upcoming` / `overdue` / `escalate`, notifies through the existing `deadline_overdue` kind, and writes an audit event so a looping scanner **never re-notifies** (anti-spam without adding a model field). Scheduled hourly in CDK; `now` is injectable so all 13 tests are deterministic. |
| Risk acceptance (EF-COR-07) | **done** | `Finding.risk_review_at` / `risk_review_by`, restricted to the client's `client_security` role — an MSP analyst gets 403 (specification ch. 6), a client from another tenant gets 403, and an empty justification gets 400. Survives a `to_item`/`from_item` round trip. |
| Screenshots in the repo (idea #42) | **done** | The repository had **no image at all**. `scripts/capture_screenshots.sh` starts the local API + Vite, captures the portal pages with headless Chrome and stops itself. Images committed in `docs/img/`, embedded in the README (5 secondary ones folded in `<details>`). Reproducible by anyone, no AWS account, no cost. For the submission video, use [`video-capture-checklist.md`](video-capture-checklist.md): it separates frozen-demo portal captures from real customer-account evidence captured only after the 23/11 gate. |
| Prompt-injection resistance proven (idea #11) | **done** | A **real hole was found and fixed**: `format_finding_for_prompt` interpolated finding content unescaped, so a description containing `</finding>` could close the data block and inject an instruction. Fixed by `sanitize_untrusted()`; the contract is now exactly one opening and one closing tag regardless of content. 42 tests prove: priority unchanged despite the injected instruction, a model that DID yield is caught by `enforce` (matrix wins + human validation forced), delimiter inviolable, no write tool other than `submit_triage_proposal`, hostile content cannot break the pipeline. |
| Domain verification choice (idea #33) | **done** | Official doc confirms three methods: `DNS_TXT | HTTP_ROUTE | PRIVATE_VPC`. **`HTTP_ROUTE` needs no DNS access** — publishing a token on a route is enough, which removes the need to buy a DNS zone for a demo. Onboarding was hard-coded to `DNS_TXT`; the method is now a validated parameter (400 before any AWS call) and the response returns an actionable instruction per domain. 9 tests. |
| "Not just a wrapper" narrative (idea #78) | **done** | [`what-rempart-adds.md`](what-rempart-adds.md) — states plainly what Continuum already does, then the 7 gaps a managed service must fill, each with the file or test that proves it. Answers the top risk of specification chapter 20. |
| Least privilege locked by test (idea #30) | **done** | `tests/iac/test_least_privilege.py`, 24 tests: exactly the 16 `securityagent:` actions of Annex A (extra ones are named in the failure), no wildcard action, no IAM write, `sts:ExternalId` mandatory, GitHub OIDC role scoped to one repo and to the `sts.amazonaws.com` audience, pipeline role writes only to its own log group, `Resource: "*"` tolerated only for `securityagent`. |
| Concurrent-test quota (EF-ORC-05, idea #36) | **done** | AWS allows 5 concurrent tests per account per region; nothing held a 6th, so it failed at AWS and nobody replayed it — the customer silently lost their release window. `orchestrator/concurrency.py` + gate refusal `concurrency_quota_reached`, audited, quota overridable by environment. 14 tests. |
| Loop guards on machines B and C (idea #90) | **not needed** | Verified: `RempartCicdIntake` and `RempartRetestClose` are **linear** (no `Wait`, no cycle). Only machine A loops and already has its 240-iteration ceiling. The concern raised in the roadmap was unfounded and is withdrawn. |
| GitHub webhook closing the loop (idea #51) | **done** (code + IaC, not yet deployed) | `POST /v1/events/github` — HMAC on the **raw** bytes (`X-Hub-Signature-256`), shared secret read from SSM SecureString, per-repository rate limit. A merged PR finds the finding by `remediation_pr_url` **scoped to the repository's own application**, sets `to_retest`, and starts `RempartPentestLifecycle` with `trigger: "retest"`, `jobType: REVALIDATION` and `selectedFindingIds`. Inside machine A the retest branch sits **after** the "run completed" choice, never before: a job stopped by the budget gate must not reach `close_or_reopen`, or an empty run would close findings that are still there. Execution names are derived from (finding, PR) so a GitHub replay cannot start a second paid test. Proof sheet: [`preuves/2026-11-14-boucle-pr-mergee.md`](preuves/2026-11-14-boucle-pr-mergee.md). Still blocked: deploying the route needs an AWS session. |
| Budget forecast (idea #44) | **done** | Was stale in this file: `GET /v1/tenants/{id}/forecast` (`reports/forecast.py`, EF-BUD-04) shipped on 12/11 and is live on the deployed API (verified by direct Lambda invocation, 13/11). Burn rate on elapsed days, edge cases covered (no run, first of month, zero budget, overspent budget), fully deterministic. |
| Bridge to `marge-msp` (idea #54) | **not started** | Export Rempart task-hours per client in Marge's ingestion format. Two projects of the same hackathon feeding each other. |

| Test windows (EF-ORC-08) | **done** | `Application.test_windows` + `orchestrator/windows.py::is_within_window` (pure, injectable, handles windows crossing midnight). A **full** test on **production** outside an agreed window is refused with `outside_test_window` and audited; `delivery` (CI/CD gate) tests and staging are never blocked — blocking a release cannot wait for a window. |

## Command for item 4 (run at submission time)

```bash
gh api repos/Tradoooo/rempart/collaborators/testing-devpost \
  -X PUT -f permission=pull
gh api repos/Tradoooo/rempart/collaborators/aws-msp \
  -X PUT -f permission=pull
```

Replace the login names with the accounts Devpost and AWS actually publish in
the hackathon FAQ — the specification quotes the **email addresses**
(`testing@devpost.com`, `aws-msp@amazon.com`), and GitHub invites a collaborator
by username, not by email. Confirm the exact usernames on
https://aws-agentic-msp.devpost.com/ before running this.

## Blockers, in the order they must be cleared

1. **Free-trial eligibility for the customer account** — on 23 November, verify
   AWS Billing → Free Tier and the Continuum console before any start request.
   Record the account, region, timestamp, evidence screenshot and operator in
   [`runbook-premier-test.md`](runbook-premier-test.md). If either check is
   missing, ambiguous or negative, stop and use the frozen demo.
2. **AWS credentials and deployment session** — use the least-privilege
   deployment session already documented for the control plane; never place
   credentials in the repository or screenshots.
3. **Mergify app authorised on `rempart`** — otherwise every PR waits for a
   human merge.
4. **`AUTOMERGE_PAT` secret** — otherwise the conflict agent can resolve but not
   publish.
5. **Date gate** — do not run the first pentest before **23 November 2026** so
   the two-month trial still covers judging on 22 January 2027.

**Hard stop:** no `StartPentestJob`—directly or through the run API—until item 1
is complete and `free_tier_confirmed` is explicitly set for the target tenant.
The default `REMPART_FREE_TIER_ONLY=1` must remain enabled.
