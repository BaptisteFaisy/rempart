# Video capture checklist — Rempart

> Capture the portal from the frozen demo unless a section is explicitly marked
> **LIVE**. The public video must not imply that frozen data came from a live
> Continuum campaign. Use a clean browser profile, English UI, 110% zoom, no
> bookmarks, notifications, credentials or third-party branding.

## Capture rules

- Record at 1920×1080, 30 fps; keep text readable.
- Add the overlay `frozen demo data` to every portal capture from GitHub Pages
  or local demo data.
- Label the two environments in-frame: `CUSTOMER ACCOUNT` and `MSP CONTROL
  PLANE`.
- For live captures, show real timestamps and the relevant account/region, but
  redact account IDs, ExternalId values, email addresses and job tokens.
- Never show passwords, access keys, session tokens, authorization headers or
  temporary Cognito credentials.
- Do not capture the hosted Cognito login with a personal account or expose
  browser storage.
- Keep the original capture plus a trimmed edit so timestamps can be checked.

## Portal captures — frozen demo, safe before 23/11

| ID | Screen / route | What must be visible | Use |
|---|---|---|---|
| P01 | Fleet `/fleet` | Two tenants, KPI cards, open findings by priority | Fleet intro |
| P02 | Tenant `/tenants/demo-a` | Customer account boundary, budget and policy summary | Customer model |
| P03 | Application `/applications/app-shop` | ShopLite, verified domain, agent space, delivery/full configs | Onboarding |
| P04 | Run `/runs/run-app-shop-1` | CI/CD trigger, scope, blocked status, task-hours, estimated cost | Gate story |
| P05 | Triage `/triage` | IDOR finding, plain-language proposal, model write boundary | AI triage |
| P06 | Finding `/findings/f-app-shop-0` | P1, seven-day SLA, `pending_validation`, human confirmation | Deterministic matrix |
| P07 | Budget `/budget` | 50/80/100% thresholds, forecast and auto-stop | Cost governance |
| P08 | Reports `/reports` | HTML report, deterministic indicators and PDF download | Monthly reporting |
| P09 | Evidence `/evidence` | Sealed dossier and recomputable SHA-256 | Proof of closure |
| P10 | Audit `/audit` | Immutable, read-only audit events | Governance |
| P11 | Policy `/policy` | Contract Correction Policy and P1–P4 matrix | Customer policy |
| P12 | Industrialization `/industrialization` | Coverage and automation metrics | Scale |

Use `scripts/capture_screenshots.sh` for reproducible local captures. Keep the
portal banner visible or add the `frozen demo data` chip in the edit.

## AWS and repository captures — live, only after the 23/11 gate

These shots are optional until the free-trial eligibility evidence is complete.
If the gate fails, replace them with the portal fallback and say `demo data`.

| ID | Screen | Capture requirement | Use |
|---|---|---|---|
| L01 | Eligibility evidence | Billing Free Tier + Continuum `Start your free trial` available; timestamp and customer account context | Before any start |
| L02 | Customer CloudFormation | Client template stack, role output and ExternalId label; blur values | Cross-account setup |
| L03 | GitHub Actions | Staging deploy green, `pentest-gate.yml` starting the gate | Release trigger |
| L04 | Customer Continuum | First job with `RUNNING`, scope and real timestamp | Real test |
| L05 | GitHub Actions | Gate blocked, promotion skipped, matching test end timestamp | Security gate |
| L06 | MSP portal Run | Live run identifier, status, task-hours and cost; no frozen-data label | Live handoff |
| L07 | MSP portal Triage/Finding | Collected finding, P1, seven-day SLA and human validation state | Triage |
| L08 | GitHub remediation | Continuum remediation PR, review and merge; no secrets | Remediation |
| L09 | Customer Continuum retest | Retest job and timestamp after merge | Closure proof |
| L10 | MSP portal Evidence/Finding | Closed state, retest job ID and SHA-256 evidence | Proven closure |
| L11 | MSP portal Reports | Live timestamps and values matching the run | Outcome |

## Video assembly map

- **Scene 1–2:** board/design capture; no portal claim.
- **Scene 3 steps 1–3:** L02–L05 if live; otherwise P03/P04 with fallback voice.
- **Scene 3 step 4–5:** P05/P06, labelled frozen demo unless the live portal
  state is captured after the run.
- **Scene 3 step 6:** L08–L10 if the retest exists; otherwise use P09/P10 and
  the fallback line.
- **Scene 4:** P01, P07, P08 and P09, all labelled frozen demo where applicable.
- **Scene 5–7:** architecture animation and board; do not add unmeasured live
  outcomes.

## Final review before export

- [ ] Every portal shot is marked `frozen demo data` or has a live-run source.
- [ ] Customer account and MSP control plane are visibly distinguished.
- [ ] Eligibility evidence was captured before any real start request.
- [ ] No shot displays a password, token, ExternalId value or personal data.
- [ ] Live timestamps match the run and retest records.
- [ ] The public YouTube export is English, about three minutes, and contains
      no third-party music or brand visible in the frame.
