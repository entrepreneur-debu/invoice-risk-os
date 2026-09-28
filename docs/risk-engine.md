# Risk Engine

The risk engine is the core of the product. It is **deterministic, explainable and
independently testable**. AI never decides whether a signal fires, how severe it is, or
whether an invoice may be approved.

Code: `apps/backend/app/modules/risk/`, with `facts.py` (inputs), `rules.py` (rules),
`engine.py` (scoring), `builder.py` (loads facts from the database) and
`ai_assist.py` (advisory explanation).

## How it works

1. `build_context()` assembles immutable **facts**, all scoped to the invoice's organization:
   - the invoice's canonical fields and lines
   - the vendor (GSTIN, status, current bank account, 400-day invoice history, price history)
   - the linked purchase order (lines, invoiced-to-date excluding this invoice)
   - organization settings
   - other invoices with the same document hash
   - instruction-like text found in the document
2. Each rule is a pure function `evaluate(ctx) -> [SignalDraft]` with no I/O. A rule that
   throws is recorded as a visible `rule_evaluation_error` signal (medium), never silently skipped.
3. Each signal carries a **title**, a **description** and an **evidence list** of
   `{label, value, source}` rows, where source is one of:
   `invoice`, `vendor_master`, `purchase_order`, `invoice_history`, `document`, `policy`.
   Example:
   ```json
   {"rule": "duplicate_invoice_number", "severity": "high",
    "evidence": [{"label": "Same vendor", "value": "Acme…", "source": "vendor_master"},
                 {"label": "Same invoice number", "value": "ACM/2026/0042", "source": "invoice"},
                 {"label": "Same total amount", "value": "₹7,788.00", "source": "invoice"}]}
   ```
4. **Scoring** (deterministic): HIGH = 40, MEDIUM = 15, LOW = 5, INFO = 0, capped at 100.
   - **Level:** high if any high signal or score ≥ 60; medium if any medium or score ≥ 25;
     low if any low; otherwise none.
   - AI observations never count toward score or level.
5. **Concurrency:** analysis runs under a per-organization PostgreSQL advisory lock and
   commits before the lock is released. Two duplicates arriving together are analysed in
   sequence, so the second always sees the first. This was found on the real worker and
   is covered by `tests/integration/test_concurrency.py`.

Wording follows the product-safety policy: "Potential duplicate", "PO mismatch detected",
"Requires review". Signals are never findings of fraud (enforced by a test).

## Rule catalogue (engine 1.0.0)

| # | Rule code | Category | What it checks |
| --- | --- | --- | --- |
| 1 | `duplicate_document` | duplicate | The identical file (same SHA-256) was already submitted. |
| 2 | `duplicate_invoice_number` | duplicate | Same vendor and same (normalized) invoice number as an earlier invoice. |
| 3 | `possible_duplicate` | duplicate | Same vendor and identical total within 7 days of invoice date, or an invoice number that differs only slightly, under a different number. |
| 4 | `vendor_not_in_master` | vendor | The invoice could not be matched to any vendor in the vendor master. |
| 5 | `vendor_gstin_mismatch` | vendor | GSTIN printed on the invoice differs from the vendor master GSTIN. |
| 6 | `vendor_matched_by_name_only` | vendor | Vendor identified by name only because no GSTIN appears on the invoice. |
| 7 | `vendor_inactive` | vendor | Invoice from a vendor marked inactive. |
| 8 | `new_vendor` | vendor | Vendor created recently or with no earlier invoices. |
| 9 | `bank_account_mismatch` | bank | Bank account printed on the invoice differs from the vendor's account on file. |
| 10 | `bank_account_unverified` | bank | The vendor's current bank account has not been verified. |
| 11 | `bank_account_recently_changed` | bank | Vendor bank account changed within the configured alert window. |
| 12 | `po_missing` | purchase_order | No purchase order referenced although the total exceeds the PO threshold. |
| 13 | `po_not_found` | purchase_order | The PO number printed on the invoice does not exist. |
| 14 | `po_vendor_mismatch` | purchase_order | The linked PO belongs to a different vendor. |
| 15 | `po_not_open` | purchase_order | The linked PO is not open (draft, closed or cancelled). |
| 16 | `po_amount_exceeded` | purchase_order | Invoice total plus earlier invoices exceed the PO total beyond tolerance. |
| 17 | `po_line_mismatch` | purchase_order | Line-level three-way comparison: items not on the PO, quantities above the PO (including earlier invoices), unit prices above PO price + tolerance. |
| 18 | `tax_arithmetic` | tax | Deterministic checks of line sums, totals and GST components (CGST/SGST/IGST). |
| 19 | `invalid_gstin` | tax | Vendor GSTIN on the invoice fails format/state/checksum validation. |
| 20 | `buyer_gstin_mismatch` | tax | Buyer GSTIN on the invoice is not this organization's GSTIN. |
| 21 | `missing_required_fields` | data_quality | Required invoice fields could not be found on the document. |
| 22 | `low_extraction_confidence` | data_quality | Key fields were read with low confidence or extractors disagreed. |
| 23 | `date_anomaly` | data_quality | Future-dated, very old, or due-before-issue invoices. |
| 24 | `document_contains_instructions` | document | Instruction-like text aimed at an AI or reviewer was found in the document. |
| 25 | `unusual_amount` | anomaly | Total far above this vendor's median (needs at least 3 earlier invoices). |
| 26 | `unexpected_price_increase` | anomaly | Unit price for an item rose sharply versus this vendor's last invoiced price. |
| 27 | `unusual_frequency` | anomaly | Four or more invoices from the same vendor within 7 days. |
| 28 | `invoice_splitting` | anomaly | Several invoices from one vendor within a short window, each below the approval threshold but together above it. |

Severities: duplicate document or number, unknown vendor, GSTIN mismatch, bank-account
mismatch, unverified bank account, PO vendor mismatch, PO amount exceeded, invoice
splitting and total arithmetic mismatch are **high**. Most others are **medium**.
Name-only vendor match, low extraction confidence, unusual frequency, new vendor (below
the high-value threshold) and minor date issues are **low**.

## Deterministic financial logic

All amounts are Python `Decimal`, never floating point (`app/finance/`).

- **Parsing:** accepts Indian (`1,23,456.50`) and international grouping, currency
  prefixes (₹, Rs., INR) and accounting negatives `(1,000.00)`. Ambiguous strings
  (e.g. European `12.345,67`, words) become *unknown*, never guessed.
- **Rounding:** ROUND_HALF_UP to 2 decimal places (GST practice). Quantities use 3 decimal places.
- **GST checks** (`finance/gst.py`):
  - sum of line amounts = subtotal
  - CGST + SGST + IGST = total tax
  - subtotal + tax = total
  - CGST = SGST
  - no mixed IGST and CGST/SGST
  - IGST only for inter-state and CGST/SGST only for intra-state supply (from the GSTIN
    state codes, falling back to the organization's state)
  - line amount × stated rate = tax charged
  - rates outside the standard slabs are flagged
- **Tolerance:** `amount_tolerance_absolute` (default ₹1.00) absorbs per-line rounding.
  PO comparisons use `price_tolerance_percent` and `quantity_tolerance_percent`.
- **GSTIN:** format, valid state code (01–38, 97, 99) and the GSTN base-36 check character.
  PAN consistency is checked for vendors.
- **Duplicates:**
  - exact: same vendor + normalized invoice number (`INV-0042` = `inv 42`), or same
    document SHA-256 anywhere in the organization
  - similar: same vendor + identical total, with an invoice date within 7 days or an
    invoice number similarity ≥ 0.85
  - no embeddings or LLMs are involved
- **PO matching:** the PO is found by normalized number. Lines match on normalized
  description (exact first, then token overlap ≥ 0.6). Quantity includes quantities
  already invoiced against the PO by other non-rejected invoices.

Tests: `tests/unit/test_finance.py` and `tests/unit/test_risk_rules.py` (every rule
against a clean baseline, plus scoring, failure isolation and wording).

## Configuration (per organization, Settings page)

The approval threshold, "PO required above", tolerances, duplicate look-back, unusual-amount
multiplier, price-increase alert, splitting window, new-vendor period, bank-change alert
window, and which risk levels require a second approver. Every change is audited with
before and after values.

## Extending

Add a `Rule` subclass with a unique `code`, a `category` and a `description`. Keep it
pure, return evidence rows with sources, add it to `ALL_RULES`, add a unit test against
`CLEAN` plus a single perturbation, and bump `ENGINE_VERSION` when behaviour changes.
