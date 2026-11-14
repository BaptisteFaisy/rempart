# Runbook — first real AWS Continuum test

> Target date: **23 November 2026**. Purpose: execute one minimal real
> penetration test while preserving the two-month trial through judging on
> 22 January 2027. This is a gated procedure: **eligibility is checked before
> any `StartPentestJob` request**.

## Non-negotiable gates

- Do not run the first real test before **23/11/2026**.
- The target is the **customer account**, not the MSP control-plane account.
- Keep `REMPART_FREE_TIER_ONLY=1` enabled.
- Do not set `free_tier_confirmed=true` from a code path or assumption. Set it
  only after the two eligibility checks below have been recorded.
- If eligibility is absent, ambiguous or negative: stop, preserve the frozen
  demo, and do not call `POST /v1/applications/{id}/runs` or
  `StartPentestJob`.

## Evidence sheet — complete before unlocking

| Field | Required value |
|---|---|
| Check date/time | UTC timestamp on 23/11/2026 or later |
| Customer account | Account ID, redacted in video assets if needed |
| Test region | Continuum region used for the customer account |
| Billing check | Screenshot showing the account is eligible for the free tier |
| Continuum check | Screenshot showing the free trial is available and unused |
| Operator | Name/handle of the person who verified the checks |
| Tenant | Rempart tenant ID |
| Decision | `eligible` or `stop` |
| Evidence location | Restricted local evidence path, never a secret or token |

The evidence must contain no password, access key, session token or temporary
Cognito credential.

## Phase 0 — preflight, no billable call

1. Confirm the calendar gate: today is **23/11/2026 or later**.
2. Confirm the live deployment: CloudFront portal is online, Cognito is
   `ACTIVE`, and the API responds as expected. Public URLs and configuration
   are in [`portal-deployment.md`](portal-deployment.md).
3. Confirm the customer-account CloudFormation stack is present:
   `iac/client-account/rempart-client.template.yaml`. Verify the
   `rempart-operator` role, `sts:ExternalId`, verified target domain and budget
   alarm. Do not paste the ExternalId value into the repository or video.
4. Confirm the application has an agent space, a verified target domain and a
   minimal scope. Use the onboarding status endpoint before continuing.
5. Confirm a short UTC test window covering the planned run. A production full
   test outside this window must be refused.
6. Confirm the budget gate, the five-task-hour per-test cap and AWS Budgets are
   enabled. The frozen demo remains the fallback at zero cost.

No step in this phase starts a pentest.

## Phase 1 — verify free-trial eligibility first

Perform both checks in the **customer account** and record the evidence sheet:

1. AWS Console → **Billing → Free Tier**: confirm the account is eligible.
2. AWS Continuum console: confirm the interface offers **Start your free
   trial** and does not show a consumed or billable trial.
3. Confirm the region is supported and is the region configured for this
   customer integration.
4. Compare the screenshots with the account and region in the evidence sheet.
5. If any check fails or cannot be proved, set the decision to `stop` and use
   the frozen demo. Do not unlock the tenant.

Only after all checks pass, and after a human reviews the evidence, update the
specific Rempart tenant's `free_tier_confirmed` flag. Never disable
`REMPART_FREE_TIER_ONLY` globally.

## Phase 2 — start the minimal test

1. Configure one application, one verified domain and the smallest agreed
   scope. Use `blocking_threshold=Critical` for this first run.
2. Confirm the test window and budget one more time.
3. Start through the Rempart run API. The API gate must accept the request only
   because the tenant is explicitly confirmed. If it returns
   `free_tier_not_confirmed` or HTTP 402, stop; do not retry around the gate.
4. Capture the customer Continuum console before and after the start, with
   timestamps and job status visible. Blur account identifiers where needed.
5. Record the returned run/job identifier in restricted evidence. Never record
   credentials or authorization headers.

The first point at which `StartPentestJob` may be reached is after the completed
Phase 1 evidence and human approval. There is no dry-run substitute for this
gate, so the safe preflight is the API refusal with the tenant still locked.

## Phase 3 — observe and stop safely

- Follow the run through the portal and API: status, elapsed time, task-hours,
  estimated cost and findings.
- Keep the five-task-hour cap active. The orchestrator must call
  `StopPentestJob` at the cap, and AWS Budgets remains the independent second
  safety net.
- Stop manually if consumption, scope or account identity is unexpected.
- Do not start a second concurrent test for this first validation.

Useful views: portal **Run**, **Budget**, **Triage** and the customer Continuum
console. The public GitHub Pages portal remains a frozen offline demo and must
not be described as this live run.

## Phase 4 — collect, triage and prove closure

1. Confirm findings were collected into the target tenant only.
2. Capture the finding, the deterministic priority, SLA and
   `pending_validation` state for Critical/High findings.
3. Record the analyst decision and the remediation PR.
4. After the fix is merged, run the retest only through the same guarded path.
5. Close only when the retest no longer finds the fingerprint; retain the
   retest job ID as proof.
6. Compare task-hours and timestamps with the portal report.

## Abort and rollback

Stop and keep the tenant locked if account, region, scope, eligibility,
budget or job status is unexpected. Use the run stop endpoint for an active
job, then verify the final status and cost. Do not destroy the control plane or
customer stack until evidence has been exported and reviewed.

After the test, revoke temporary test access, remove transient local evidence
that contains identifiers, and set `free_tier_confirmed=false` if the tenant
must be locked again. Keep only redacted evidence needed for the submission.

## If the eligibility check fails

Use the frozen dataset and the existing video fallback. Do not make a paid test
to obtain a screenshot. Update the submission checklist to say that the real
runtime call remains blocked and record the reason outside the public video.
