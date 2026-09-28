# Pilot Guide

How to run a V1 pilot with a real customer, locally or on a staging deployment.

## 1. Pilot workflow (weeks 0–6)

| Week | Activity |
| --- | --- |
| 0 | Deploy (staging on Google Cloud, or a local machine). Create the organization; the owner invites 1 admin and 1–3 reviewers. Set the organization GSTIN and approval policy (Settings). Decide on AI data sharing (Settings → AI assistance). |
| 0–1 | Load the vendor master: top vendors with GSTIN and **verified** bank accounts (entered by one person, verified by another via a known phone number). Load open purchase orders. |
| 1–4 | **Shadow mode:** every incoming invoice is uploaded (or emailed to the inbound address) *before* the existing payment process. Reviewers decide in the product; the existing payment process continues unchanged. |
| 2 | First calibration review: signals dismissed as noise lead to adjustments of tolerances and thresholds (Settings; audited). |
| 4–6 | **Gate mode:** payments are released only for invoices approved in the product. |
| 6 | Pilot review using the measurement framework below. |

## 2. Demo data and seeding strategy

- `docker compose exec worker python -m app.cli seed-demo` creates a **synthetic**
  organization: 4 users (one per role), 3 vendors (one with a pending bank change),
  2 POs and 7 invoices. Each invoice demonstrates rules: a clean one, a resubmitted
  duplicate, over-billing and a price increase, a diverted bank account, an unknown
  vendor, GST arithmetic errors with an unverified bank change, and a document
  containing prompt-injection text.
- All names, GSTINs (valid check digits), PANs and bank numbers are fabricated for demos.
  **Never seed real customer data.** Seeding refuses to run with `APP_ENV=production`.
- For a customer pilot, start with an empty organization (signup) and load the customer's
  real vendors and POs through the UI.

## 3. Measurement framework

All figures come from the product's own records (Dashboard, Risk page and audit log).
Nothing is estimated.

| Question | Where | Metric |
| --- | --- | --- |
| Are invoices going through the system? | Dashboard, "Invoices received" vs the customer's payment run | Coverage % |
| Did it catch anything? | Dashboard, "Prevented payments (measured)" | Count and value of invoices flagged by duplicate/bank rules **and** rejected by a reviewer |
| Are signals useful? | Risk page, "Signals overridden"; audit `risk.signal_resolved` with `dismissed` | Precision = 1 − dismissed / total high signals |
| Is review fast enough? | Risk page, review turnaround | Median hours from review requested to decision |
| Is extraction good enough? | Audit `invoice.modified` | Share of invoices needing manual corrections |
| Is AI helping? | Invoice review, AI status | Share of invoices with `ai_status=succeeded`; reviewer feedback |

Record a baseline in week 0: the customer's historical duplicate and incident rate and
their current review time.

## 4. Pilot success criteria (suggested)

- ≥ 90% of paid invoices processed before payment
- Zero duplicate or diverted-bank payments on processed invoices
- ≥ 70% of high-severity signals judged useful (not dismissed)
- Median review turnaround ≤ 1 business day

## 5. Known pilot constraints

See the "Known limitations" section of [final-build-report.md](final-build-report.md).
The main ones:
- no email or Slack notifications (in-app only)
- no ERP import
- no password reset (operator-assisted)
- scanned-image invoices need Gemini, or manual entry
