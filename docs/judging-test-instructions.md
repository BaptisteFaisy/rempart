# Test instructions for judges — Rempart

> Text to paste into the Devpost "testing instructions" field.
> Placeholders in `CAPITALS` are filled in at deployment time
> (see [`submission-checklist.md`](submission-checklist.md) for blockers).

## What you are looking at

Rempart is a managed continuous penetration-testing service. An MSP runs one
control plane; each customer keeps AWS Continuum in their **own** AWS account.
At every release, Continuum tests the deployed change, Rempart triages the
findings, opens a ticket with a contractual deadline, requests a remediation
pull request, and closes the finding only when a retest proves it is gone.

**Portal:** `https://PORTAL_URL`

## Demo credentials

| Role | Login | Password | What it can do |
|---|---|---|---|
| Judge (read-only) | `JUDGE_USER` | `JUDGE_PASSWORD` | Browse every page, see all findings and KPIs. Buttons are disabled and a banner reads "Judge demo — read-only". |
| Analyst (guided tour only) | `ANALYST_USER` | `ANALYST_PASSWORD` | Confirm or correct a triage proposal. Use this only if the video is unavailable. |

The judge account maps to the `demo` role: read access to the demo tenant, one
on-demand test per day on the minimal scope, no write access. This is enforced
server-side, not hidden in the UI.

**Nothing to install.** A browser is enough.

## Ten-minute guided tour

### 1. Fleet view (1 min) — `Fleet`

Log in with the judge account. You land on the MSP fleet dashboard: two demo
customers, each in its own AWS account.

*Look for:* the four headline KPIs — median delivery-to-result time, share of
P1/P2 findings stopped before production, deadline compliance, application
coverage. Below them, the customer ranking with open findings by priority.

### 2. One application (1 min) — `Tenant` → `Application`

Open customer A, then application **ShopLite**.

*Look for:* criticality `high`, exposed to the internet, handles personal data
— these three attributes drive the triage matrix. Also the agent space id, the
verified domain, and the two test configurations ("delivery" and "full").

### 3. A release gets blocked (2 min) — `Application` → `Run`

Open the most recent CI/CD run. This is the test Continuum ran on the deployed
commit range, triggered by the pipeline gate, not by us.

*Look for:* trigger `cicd`, the commit range, the scope decision, status
`blocked`, the duration, the **task-hours consumed** and the estimated cost in
dollars. Task-hours are Continuum's billing unit (50 $/task-hour, billed per
second).

### 4. Triage queue (2 min) — `TriageQueue`

This is the core of the product. The finding is an IDOR on `/orders/{id}`: a
logged-in customer can read another customer's orders by changing an id.

*Look for:* the AI proposal — a three-sentence plain summary for a
non-specialist, a technical summary, priority **P1**, due date **7 days**,
references (CWE-639, OWASP A01), and the justification. The finding sits in
`pending_validation` **because it is Critical**: the model is never allowed to
settle a Critical or High finding on its own. Priority was recomputed by the
deterministic matrix after the model answered.

Click **Confirm** (with the analyst account, or watch it in the video). A GitHub
issue is created with the summary, the proof and the deadline; the finding moves
to `in_remediation`.

### 5. Remediation and proof of closure (2 min) — `Finding`

Open the finding's detail page.

*Look for:* the remediation pull request Continuum generated, linked to the
finding; then the retest run; then the finding **closed with the retest job id
as proof**. Closure is never declared by the model — it requires a retest in
which the fingerprint no longer appears. If it reappears, the finding is
reopened and flagged as a regression.

### 6. Budget (1 min) — `Budget`

*Look for:* task-hours consumed this month against the contractual budget, the
50 / 80 / 100 % thresholds, and the auto-stop switch. At 100 % the orchestrator
calls `StopPentestJob` mid-test — acceptance scenario R8.

### 7. Monthly report (1 min) — `Reports`

*Look for:* the executive summary in plain language, then the indicator tables.
Every number is computed by code from recorded timestamps; the model only writes
the prose. Download the PDF to check the two formats match.

## The three measured outcomes

| Outcome | Where to read it |
|---|---|
| Delivery → test result | Run page (deployment event timestamp vs test end) |
| Serious findings stopped before production | Fleet and Tenant KPIs |
| Mean time to remediate, by priority | Tenant KPIs and the monthly report |

## Fallback if AWS Continuum is unavailable

Continuum for penetration testing was in preview during this hackathon, and the
free trial starts at the **first** test. If the service is unreachable, or the
budget is exhausted, the portal still serves the **last real run**: findings,
triage proposals, tickets, retest proofs and the monthly report are persisted in
DynamoDB and S3, so every screen above renders from stored data. The recorded
walkthrough in the submission video shows the same flow with real timestamps.

## Reproducing the tests locally

```bash
git clone <repo-url> && cd rempart
python3 -m venv .venv && .venv/bin/pip install -r backend/requirements-ci.txt

cd backend && ../.venv/bin/python -m pytest tests -q     # 188 tests
cd ..     && .venv/bin/python -m pytest demo -q          #  12 tests
cd backend && ../.venv/bin/ruff check rempart tests      # lint

cd ../portal && npm ci && npx vitest run && npm run build # 13 tests + build
```

No AWS account, no credentials and no network access are needed: every AWS and
GitHub call is injected and faked in tests (`backend/tests/fakes_*.py`).

To see the seeded vulnerabilities in the demo apps:

```bash
VULN_IDOR=1 python3 demo/app-a/app.py    # ShopLite, IDOR on /orders/<id>
VULN_SQLI=1 VULN_ADMIN=1 python3 demo/app-b/app.py   # BookWorm, SQLi + open admin
```

Setting the flags to `0` switches each app to its corrected behaviour — that is
how we demonstrate the "fixed, then regression" path.

## Repository access

This private repository is shared with `testing@devpost.com` and
`aws-msp@amazon.com`, and contains the code, the infrastructure as code, the
specification, the design document and these instructions.

- Design document: [`docs/HLD.md`](HLD.md)
- Acceptance scenarios R1–R12: [`docs/acceptance.md`](acceptance.md)
- Functional specification (French, internal working document):
  [`docs/cahier-des-charges-tests-intrusion-continu.md`](cahier-des-charges-tests-intrusion-continu.md)

## What we deliberately did not build

So the gap is not mistaken for a bug: Jira/ServiceNow/GitLab ticketing, Slack
and Teams notifications, threat modelling and design review are in the
post-hackathon scope (specification § 5.2). Rempart also never calls the
"Continuum for code vulnerabilities" capability, which is billed separately
(200 $ per million protected lines per month) and is not covered by the free
trial.
