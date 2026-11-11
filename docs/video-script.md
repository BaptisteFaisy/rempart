# Video script — Rempart (3 minutes, English)

> Timing follows § 17.2 of the specification. Rules from § 18.1: public on
> YouTube, **English**, **no third-party brand visible**, **no third-party
> music**. A Continuum test takes about an hour, so sequences are **recorded in
> advance and edited together**, with the **real timestamps on screen**.
>
> The video must show both sides: the customer account console and the MSP
> console, the repository and the pipeline. Never a single screen.
>
> Before recording: hide bookmarks, extensions and personal tabs; use a clean
> browser profile; zoom to 110 % so text is readable at 1080p; no notification
> pop-ups.

---

## 0:00 – 0:20 — The problem and the promise

| On screen | Voice-over | Overlay |
|---|---|---|
| Static title card on a plain background, then cut to the portal's Fleet page, empty of any customer branding. | "A mid-size company ships code every week, and penetration-tests its application once a year. Between two tests, every release can open a vulnerability that nobody is looking for. The report arrives weeks later as a PDF. Nobody tracks the fixes. The next test finds the same findings again." | `Rempart — continuous penetration testing as a managed subscription` |
| Same Fleet page, now populated with two customers and their KPIs. | "Rempart makes the test continuous. At every release, AWS Continuum tests the change and blocks production if something serious appears. The MSP triages, tracks to proven closure, and reports every month." | `AWS MSP AI Hackathon · Track 2` |

Pace: two sentences per shot. No music, or a royalty-free bed recorded by us.

---

## 0:20 – 0:50 — Onboarding an application

| On screen | Voice-over | Overlay |
|---|---|---|
| MSP portal → Tenant → "New application" form being filled: name `ShopLite`, criticality `high`, exposed to internet `yes`, data `personal`. | "Onboarding starts in the MSP portal. The customer, their AWS account, the plan and the monthly task-hour budget." | `Step 1/6 — customer record` |
| Cut to the **customer's** AWS console: CloudFormation stack created from a single template. Show the stack's Outputs: the cross-account role ARN and the ExternalId. | "In their own account, the customer deploys one CloudFormation template. It creates the cross-account role with a unique external id, the pipeline role and the log groups." | `Step 2/6 — one template, customer account` |
| Back to the portal: the onboarding page showing the agent space id, the target domain, and the DNS TXT record to create. Then the domain flips to `VERIFIED`. | "The control plane creates the agent space, declares the target domain, and shows the DNS record to create. The domain is verified — Continuum only tests verified domains." | `Step 3/6 — CreateAgentSpace · CreateTargetDomain · VerifyTargetDomain` |
| Portal: the two test configurations appear — "delivery" and "full" — plus the mandate file marked `valid`. | "Two test configurations are created: one for each delivery, one full monthly test. The signed test mandate is filed. Without a valid mandate, no test can start." | `Step 6/6 — mandate valid` |

Show the real API call names at least once: judges must see the code calls AWS.

---

## 0:50 – 1:30 — A release introduces a vulnerability, the gate blocks it

| On screen | Voice-over | Overlay |
|---|---|---|
| Code editor: a diff on `GET /orders/{id}` removing the ownership check. Commit message `feat: expose order details`. | "A developer merges a change. It removes an ownership check on the order endpoint." | `commit a1b2c3d` |
| GitHub Actions run page: deploy to staging green, then the Rempart gate step starts. | "The pipeline deploys to staging and the gate starts a test limited to the deployed commit range." | `pentest-gate.yml · scope: deployed range` |
| **Customer** AWS console, Continuum: the pentest job appears, status `RUNNING`, task-hours counter climbing. | "Continuum tests the change inside the customer's own account. Task-hours accumulate on their bill, not ours." | `task-hours 0.4 → 1.2` |
| The pipeline step turns red; the promotion to production does not happen. | "A Critical finding is confirmed. The gate blocks promotion to production." | `BLOCKED — severity threshold reached` |
| Portal, Run page: trigger `cicd`, status `blocked`, duration, task-hours, estimated cost. | "Rempart detected the test within five minutes, pulled the findings, and recorded the cost." | `run job-4f2a · blocked · 1.4 task-hours · 70 $` |

Timestamp overlay rule: show the **deployment time** and the **test end time**
in the same frame, so the delivery-to-result delay is readable without
narration.

---

## 1:30 – 2:10 — Triage, ticket, remediation, proof of closure

| On screen | Voice-over | Overlay |
|---|---|---|
| Portal → Triage Queue. The finding card: IDOR on `/orders/{id}`, severity Critical, confidence High. | "The triage agent runs on Strands Agents with Amazon Bedrock. It deduplicates, writes a plain summary, and proposes a status." | `Strands · AgentCore Runtime · Bedrock` |
| Zoom on the plain summary, then on priority `P1` and due date `+7 days`. | "The priority is not the model's opinion: a deterministic matrix combines severity, confidence, exposure and data sensitivity. The code recomputes it, and the matrix wins." | `P1 · due in 7 days · matrix-computed` |
| The finding shows `pending_validation`. The analyst clicks **Confirm**. | "Because the finding is Critical, the model cannot settle it alone. An analyst confirms in one click." | `ENF-IA-02 — human decision required` |
| GitHub: the issue appears with summary, proof and deadline. | "A ticket opens in the customer's repository, with its contractual deadline." | `issue #42 · P1 · due 18 Nov` |
| The remediation pull request generated by Continuum, linked to the finding; the developer merges it. | "Continuum generates the remediation pull request. The developer reviews and merges." | `StartCodeRemediation · PR #43` |
| The retest run, then the finding page flipping to `closed`, with the retest job id shown as proof. | "The merge triggers a retest. The fingerprint no longer appears, so the finding is closed — with the retest job id as proof. If it came back, it would be reopened as a regression." | `closed · proof: job-7c1e` |

This is the segment that answers the "isn't it just a wrapper?" objection. Say
the words *proof of closure* on camera.

---

## 2:10 – 2:40 — The fleet and the monthly report

| On screen | Voice-over | Overlay |
|---|---|---|
| Portal → Fleet, two customers side by side, KPI tiles. | "Across the fleet: two customers, each in their own AWS account, one control plane." | `2 tenants · 2 applications · 100 % coverage` |
| Zoom on the three measured outcomes. | "Delivery to result: under two hours on a simple API. Serious findings stopped before production: one hundred percent this month. Mean time to remediate a P1: three days." | `measured, computed by code` |
| Portal → Budget: task-hours consumed, the 50/80/100 % thresholds, auto-stop on. | "Every customer has a task-hour budget with alerts at fifty, eighty and one hundred percent, and an automatic stop." | `budget 12.4 / 40 task-hours` |
| Portal → Reports: the monthly report opens; scroll the executive summary, then the indicator tables; click download and show the PDF. | "On the first working day of the month, the indicators are frozen and the model writes the executive summary from those frozen numbers. Never the other way round." | `HTML + PDF · numbers frozen first` |

---

## 2:40 – 3:00 — Architecture, results, and what scales

| On screen | Voice-over | Overlay |
|---|---|---|
| The architecture diagram from the HLD, animated in two layers: customer account, then MSP control plane. | "Continuum runs in the customer account because AWS caps integrations at twenty per account and region, and concurrent tests at five. One account per customer is the only model that scales — and it keeps each customer's findings and their test bill inside their own account." | `20 integrations · 5 concurrent tests · per account per region` |
| Terminal: `cdk deploy` output summary, then the client template being deployed in a fresh account. | "The control plane is AWS CDK. A new customer is one CloudFormation template." | `1 template = 1 customer` |
| Terminal: the test suite running green. | "Two hundred and fifty-two automated tests. Every job in CI answers in under five minutes, enforced by a guard that fails the build otherwise." | `252 tests · CI ≤ 5 min` |
| End card. | "Rempart: the penetration test becomes a subscription, with a remediation deadline and proof of closure." | `Rempart · github.com/BaptisteFaisy/rempart` |

---

## Recording checklist

- [ ] Clean browser profile, no bookmarks bar, no extensions, no notifications.
- [ ] Terminal font ≥ 16 pt, dark theme, no shell prompt leaking paths or tokens.
- [ ] Both consoles visible during the release segment: **customer** account and
      **MSP** account, each labelled on screen.
- [ ] Real timestamps on screen for every test (recorded in advance, edited).
- [ ] No third-party brand, logo or product name other than AWS and our own.
- [ ] No third-party music. Either silence or a bed we recorded.
- [ ] English voice-over; English UI (the portal is English-only by design).
- [ ] Total runtime 2:50 – 3:10.
- [ ] Public YouTube link, unlisted is **not** accepted by the rules.
- [ ] The three measured outcomes appear on screen as numbers, not as claims.
