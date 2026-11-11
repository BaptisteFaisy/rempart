# Submission checklist — AWS MSP AI Hackathon, Track 2

> Source: `docs/cahier-des-charges-tests-intrusion-continu.md` § 18.1.
> Deadline: **Friday 11 December 2026, 12:00 PT** (21:00 Paris).
> Judging ends 22 January 2027 — the solution must stay online until then.
>
> Statuses are honest as of **11 November 2026**. Nothing is deployed on AWS
> yet: no credentials were available. Everything under "code" is done and
> green; everything under "runtime" is blocked on the AWS account.

| # | Requirement | Status | Proof / what is left |
|---|---|---|---|
| 1 | Track 2 selected, AWS AI service named | **to do** (form) | Text ready: [`devpost-submission.md`](devpost-submission.md). Service to name: AWS Continuum (penetration testing) + Amazon Bedrock via Strands Agents on AgentCore Runtime. |
| 2 | Description in English: features, problem, measured outcomes | **done** | [`devpost-submission.md`](devpost-submission.md) § Description, How we built it, three measured outcomes. |
| 3 | Public URL of the portal, with demo credentials in the test instructions | **blocked** | Portal is built and tested ([`portal/`](../portal), 13 vitest tests, `npm run build` green). Needs `cdk deploy` of the `portal` stack (S3 + CloudFront) and a Cognito demo user. Placeholders `https://PORTAL_URL`, `JUDGE_USER`, `JUDGE_PASSWORD` in [`judging-test-instructions.md`](judging-test-instructions.md). |
| 4 | Private repo shared with `testing@devpost.com` and `aws-msp@amazon.com` | **to do** (1 command, at submission time) | Repo is already private. Command ready below. Do it **close to the deadline**, not before: sharing early gives reviewers access to unfinished work. |
| 5 | The code really calls an AWS AI service at runtime | **blocked** | Calls are written and unit-tested against the official API reference ([`docs/api-verification.md`](api-verification.md)), but never executed against AWS. Needs credentials + one real `StartPentestJob`. Note: the free trial starts at the **first** pentest — the spec (§ 16.2) says do not run it before **23 November 2026** so the 2-month trial still covers judging on 22 January 2027. |
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
| Deadline reminders (EF-COR-06) | **in progress** | `rempart/orchestrator/reminders.py` — upcoming / overdue / escalate, with an anti-spam guard so a looping scanner does not re-notify. |
| Risk acceptance (EF-COR-07) | **in progress** | `Finding.risk_review_at`, restricted to the client's `client_security` role (an MSP analyst cannot accept a risk on the customer's behalf), justification mandatory. |
| Test windows (EF-ORC-08) | **in progress** | `Application.test_windows` — a full test on production outside an agreed window is refused; CI/CD gate tests are never blocked by a window. |

## Command for item 4 (run at submission time)

```bash
gh api repos/BaptisteFaisy/rempart/collaborators/testing-devpost \
  -X PUT -f permission=pull
gh api repos/BaptisteFaisy/rempart/collaborators/aws-msp \
  -X PUT -f permission=pull
```

Replace the login names with the accounts Devpost and AWS actually publish in
the hackathon FAQ — the specification quotes the **email addresses**
(`testing@devpost.com`, `aws-msp@amazon.com`), and GitHub invites a collaborator
by username, not by email. Confirm the exact usernames on
https://aws-agentic-msp.devpost.com/ before running this.

## Blockers, in the order they must be cleared

1. **AWS credentials** — one IAM user (`rempart-deployer`) with an access key,
   region `eu-west-3`. Unblocks items 3 and 5 and the whole demo.
2. **Is the AWS account new?** The 2-month / 400 task-hours free trial is
   granted to *new* Continuum customers. If the account is old, the first test
   costs real money (~173 $ for a simple API). This decides whether we run a
   real test or demo on recorded data.
3. **Mergify app authorised on `rempart`** — otherwise every PR waits for a
   human merge.
4. **`AUTOMERGE_PAT` secret** — otherwise the conflict agent can resolve but not
   publish.
5. **Do not run the first pentest before 23 November 2026** (specification
   § 16.2), so the free trial still covers judging on 22 January 2027.
