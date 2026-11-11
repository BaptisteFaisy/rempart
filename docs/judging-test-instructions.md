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

## Running the demo locally with zero AWS cost

No AWS account, no credentials, no bill. The whole product runs on
`127.0.0.1`: the React portal, the **real** chapter-14 `lambda_handler`, and the
frozen demo dataset.

```bash
# 1. Check that everything mounts (lists the served routes, exits 0, never blocks)
python3 scripts/serve_local.py --check

# 2. Terminal 1 — local API on http://127.0.0.1:8000
python3 scripts/serve_local.py

# 3. Terminal 2 — portal dependencies (once)
cd portal && npm ci

# 4. Terminal 2 — portal wired to the local API
npm run dev:local          # then open http://localhost:5173/fleet
```

Want the portal alone, with no server at all? `npm run dev:offline`
(`VITE_USE_MOCKS=1`) serves the same frozen dataset in the browser and shows a
permanent orange **OFFLINE DEMO MODE** banner, so nobody mistakes it for live
data.

### What is actually running

`scripts/serve_local.py` is a Python **standard-library** HTTP server (no new
dependency, Python or npm). It loads `demo/seed/demo-dataset.json` into the
in-memory `FakeStore`, injects the `FakeSecurityAgentClient`, translates every
request into an API Gateway HTTP API v2 event and calls
`rempart.api.app.lambda_handler` — the same function that runs in Lambda, with
the same router, the same authorization matrix and the same tenant isolation.

There is **one** dataset. `scripts/seed_demo.py` generates it,
`demo/seed/demo-dataset.json` stores it, the local API serves it and the offline
portal imports the very same file. Two demo customers, two applications, four
test configurations, six runs, six findings covering the whole lifecycle
(`new`, `pending_validation`, `confirmed`, `in_remediation`, `closed` with a
retest proof), ten decisions, consumed budgets and two monthly reports.

### Demo identity — not an authentication mechanism

Two headers are turned into synthetic Cognito claims so that `resolve_principal`
and tenant isolation behave exactly as in production:

| Header | Default | Claim |
|---|---|---|
| `X-Demo-Role` | `platform_admin` | `cognito:groups` |
| `X-Demo-Tenant` | `demo-a` for `client_*` / `executive` / `demo` | `custom:tenant_id` |

Anyone can claim any role here, which is why the server only ever binds to
`127.0.0.1`. The roles are still enforced: a `client_security` principal of
tenant `demo-b` gets a real **403** on tenant `demo-a`.

```bash
curl -s http://127.0.0.1:8000/v1/tenants | head -c 200
curl -s 'http://127.0.0.1:8000/v1/findings?tenant_id=demo-b'
curl -s http://127.0.0.1:8000/v1/tenants/demo-a/kpis
curl -s -H 'X-Demo-Role: client_security' -H 'X-Demo-Tenant: demo-b' \
     http://127.0.0.1:8000/v1/tenants/demo-a     # -> 403
```

KPI and budget routes read the current month in production; the frozen dataset
covers **October 2026**, so the demo server pins `period`/`month` to the dataset
month unless the caller passes one explicitly. An explicit parameter always wins.

### What this mode does NOT show

- **No real AWS Continuum test.** The Security Agent client is faked: no
  penetration test runs, no task-hour is consumed, nothing is billed.
- **The anti-billing guard stays on.** `free_tier_only=True` and the demo tenants
  have `free_tier_confirmed=False`, so `POST /v1/applications/{id}/runs` returns
  **402** on purpose (see `docs/free-tier-runbook.md`). The local demo cannot
  trigger a billable test even by accident.
- No Cognito, DynamoDB, S3, Step Functions, GitHub or SES: everything lives in
  memory and is **lost on restart**.
- Two listing routes are not in the chapter-14 contract yet
  (`GET /v1/tenants/{id}/applications`, `GET /v1/tenants/{id}/reports`), so the
  Tenant and Reports pages report the API error in API mode instead of inventing
  rows. They render normally in offline mode. The store methods behind them
  already exist; exposing them is a backend follow-up.

Full details, options and the test list: [`scripts/README-local-demo.md`](../scripts/README-local-demo.md).

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
