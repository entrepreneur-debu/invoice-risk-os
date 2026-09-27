# Product Overview

> **Every invoice gets checked before your business pays it.**
> The payment firewall for your business.

## Customer and problem

**Who:** finance and accounts-payable (AP) teams at Indian small and mid-sized
businesses. Typically 50–5,000 vendor invoices a month, a small AP team, and payments
made by bank transfer (NEFT/RTGS/IMPS) after someone "checks" the invoice.

**Problem:** payment mistakes and fraud come from a small set of recurring patterns that
manual checks miss under time pressure:

- the same invoice paid twice (resubmitted, renumbered or re-scanned)
- payment diverted to a changed or impersonated bank account
- billing above the purchase order in price, quantity or total
- GST arithmetic errors, wrong GST type (IGST vs CGST/SGST), or the wrong buyer GSTIN
  (lost input tax credit)
- invoices from unknown or new vendors, unusual amounts, split invoices that dodge
  approval limits

## Product promise

Before any invoice is paid, the system:

1. stores the original document and extracts its data with provenance;
2. runs deterministic, explainable risk checks against the vendor master, purchase
   orders and invoice history;
3. adds an AI explanation (Gemini) that is clearly labelled and never decides anything;
4. routes the invoice to a human reviewer, and to a second approver when the value or
   risk requires it;
5. records every step in a tamper-evident audit trail.

**Humans remain the control point.** The system never pays, never auto-approves and never
auto-rejects. Signals say "potential duplicate" or "requires review", never "fraud".

## V1 scope (implemented)

| Area | Included in V1 |
| --- | --- |
| Access | Sign-up and sign-in, organizations (multi-tenant), invitations, roles (owner, admin, reviewer, viewer) |
| Vendors | Vendor master with GSTIN/PAN validation, encrypted bank accounts with change history, independent verification, audited reveal |
| Purchase orders | POs with lines; server-computed totals; invoiced-to-date tracking |
| Ingestion | Manual upload (PDF/PNG/JPEG), SSRF-safe URL import, email ingestion (token-authenticated inbound endpoint + CLI) |
| Extraction | Gemini document extraction and text-layer heuristics, merged with per-field provenance |
| Risk | 28 deterministic rules: duplicates, vendor identity, bank account, PO three-way checks, GST/tax arithmetic, data quality, anomalies, splitting, prompt injection |
| AI | Gemini explanation of the rule evidence, schema-validated and advisory only |
| Review | Review queue, evidence view, approve / reject / request changes / comment, second approver, override (risk accepted) with reason |
| Audit | Hash-chained, append-only audit log with integrity verification |
| Other | In-app notifications, dashboard and analytics from real data |

## V1 exclusions (deliberate)

- Payment execution, bank integrations and payment files (the system never moves money)
- ERP or accounting-system integrations (Tally, Zoho Books, SAP) and GST portal (GSTN) lookups
- Email or Slack notification delivery (in-app only; channel abstraction in place)
- Direct mailbox connectors (Gmail, Microsoft 365); the inbound webhook works with any relay
- Billing and subscriptions, SSO/SAML, MFA
- Multi-currency conversion (non-INR amounts are stored and shown, not converted)
- OCR for scanned images without AI (scans rely on Gemini; without it they need manual entry)

## Success metrics (for pilots)

Measured from the product's own data (see [pilot-guide.md](pilot-guide.md)):

| Metric | Definition |
| --- | --- |
| Coverage | Share of paid invoices that went through the system before payment (target ≥ 90%) |
| Detection | Invoices flagged by duplicate or bank-account rules and then rejected (count and value) |
| Precision | Share of high-severity signals that reviewers did not dismiss as false positives |
| Review turnaround | Median hours from "review required" to decision |
| Extraction quality | Share of invoices needing no manual correction of key fields |
| Adoption | Weekly active reviewers; invoices processed per week |

## Pilot assumptions

- One legal entity per organization, with an INR-invoice majority and a GSTIN on file.
- Vendor master and open POs can be loaded at the start (manually or by later import).
- Reviewers have a known, independent contact at each vendor for bank-change verification.
- The pilot customer accepts invoice documents being processed by Google's Gemini API,
  or turns AI extraction off per organization (see [ai.md](ai.md)).
