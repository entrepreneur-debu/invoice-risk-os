"""Deterministic, explainable risk rules.

Each rule is a small class with a stable `code`, a `category`, and `evaluate(ctx)` that
returns zero or more `SignalDraft`s. Rules never call AI, the network or the database.
Wording follows the product-safety policy: rules report *signals* ("potential duplicate",
"requires review"); they never assert fraud. Documented in docs/risk-engine.md.
"""

import difflib
import statistics
from dataclasses import dataclass, field
from datetime import timedelta
from decimal import Decimal
from typing import ClassVar

from app.finance.gst import TaxInputs, check_tax_arithmetic, gstin_state_code, validate_gstin
from app.finance.money import ZERO, format_inr, money, percent_change, within_tolerance
from app.models.enums import Severity
from app.modules.risk.facts import HistoricalInvoice, LineFact, POLineFact, RiskContext

_EXCLUDED_HISTORY_STATUSES = frozenset({"failed"})


@dataclass(frozen=True)
class Evidence:
    label: str
    value: str | None
    source: str  # invoice | vendor_master | purchase_order | invoice_history | document | policy

    def as_dict(self) -> dict[str, str | None]:
        return {"label": self.label, "value": self.value, "source": self.source}


@dataclass(frozen=True)
class SignalDraft:
    rule_code: str
    category: str
    severity: Severity
    title: str
    description: str
    evidence: tuple[Evidence, ...] = field(default_factory=tuple)


def _amount(value: Decimal | None) -> str | None:
    return format_inr(value) if value is not None else None


def _ref(inv: HistoricalInvoice) -> str:
    parts = [inv.invoice_number or "(no number)"]
    if inv.invoice_date:
        parts.append(inv.invoice_date.isoformat())
    if inv.total is not None:
        parts.append(format_inr(inv.total))
    parts.append(f"status {inv.status}")
    return ", ".join(parts)


def _history(ctx: RiskContext) -> tuple[HistoricalInvoice, ...]:
    if ctx.vendor is None:
        return ()
    return tuple(h for h in ctx.vendor.history if h.status not in _EXCLUDED_HISTORY_STATUSES)


class Rule:
    code: ClassVar[str]
    category: ClassVar[str]
    description: ClassVar[str]

    def evaluate(self, ctx: RiskContext) -> list[SignalDraft]:
        raise NotImplementedError

    def signal(
        self, severity: Severity, title: str, description: str, *evidence: Evidence
    ) -> SignalDraft:
        return SignalDraft(self.code, self.category, severity, title, description, evidence)


# --- Duplicates ------------------------------------------------------------------------


class DuplicateDocumentRule(Rule):
    code = "duplicate_document"
    category = "duplicate"
    description = "The identical file (same SHA-256) was already submitted."

    def evaluate(self, ctx: RiskContext) -> list[SignalDraft]:
        matches = [
            m for m in ctx.same_document_invoices if m.status not in _EXCLUDED_HISTORY_STATUSES
        ]
        if not matches:
            return []
        return [
            self.signal(
                Severity.HIGH,
                "Potential duplicate: identical document already submitted",
                "The uploaded file is byte-for-byte identical to a previously submitted invoice.",
                Evidence("Same document fingerprint (SHA-256)", "match", "document"),
                *(
                    Evidence("Previously submitted", _ref(m), "invoice_history")
                    for m in matches[:5]
                ),
            )
        ]


class DuplicateInvoiceNumberRule(Rule):
    code = "duplicate_invoice_number"
    category = "duplicate"
    description = "Same vendor and same (normalized) invoice number as an earlier invoice."

    def evaluate(self, ctx: RiskContext) -> list[SignalDraft]:
        number = ctx.invoice.normalized_number
        if not number or ctx.vendor is None:
            return []
        matches = [h for h in _history(ctx) if h.normalized_number == number]
        if not matches:
            return []
        evidence = [
            Evidence("Same vendor", ctx.vendor.name, "vendor_master"),
            Evidence("Same invoice number", ctx.invoice.invoice_number, "invoice"),
        ]
        same_total = [m for m in matches if m.total is not None and m.total == ctx.invoice.total]
        if same_total:
            evidence.append(Evidence("Same total amount", _amount(ctx.invoice.total), "invoice"))
        evidence.extend(
            Evidence("Earlier invoice", _ref(m), "invoice_history") for m in matches[:5]
        )
        return [
            self.signal(
                Severity.HIGH,
                "Potential duplicate invoice",
                "This vendor has already submitted an invoice with the same invoice number.",
                *evidence,
            )
        ]


def _similar_numbers(a: str | None, b: str | None) -> bool:
    if not a or not b or a == b:
        return False
    return difflib.SequenceMatcher(None, a, b).ratio() >= 0.85 or a in b or b in a


class PossibleDuplicateRule(Rule):
    code = "possible_duplicate"
    category = "duplicate"
    description = (
        "Same vendor and identical total within 7 days of invoice date, or an "
        "invoice number that differs only slightly, under a different number."
    )

    def evaluate(self, ctx: RiskContext) -> list[SignalDraft]:
        inv = ctx.invoice
        if ctx.vendor is None or inv.total is None:
            return []
        window_start = ctx.today - timedelta(days=ctx.settings.duplicate_window_days)
        candidates = []
        for h in _history(ctx):
            if h.normalized_number and h.normalized_number == inv.normalized_number:
                continue  # handled by DuplicateInvoiceNumberRule
            if h.total is None or h.total != inv.total:
                continue
            if h.invoice_date and h.invoice_date < window_start:
                continue
            close_dates = (
                h.invoice_date is not None
                and inv.invoice_date is not None
                and abs((h.invoice_date - inv.invoice_date).days) <= 7
            )
            if close_dates or _similar_numbers(h.normalized_number, inv.normalized_number):
                candidates.append(h)
        if not candidates:
            return []
        return [
            self.signal(
                Severity.MEDIUM,
                "Possible duplicate under a different invoice number",
                "Another invoice from this vendor has the same total and a nearby date or a very "
                "similar invoice number.",
                Evidence("Same vendor", ctx.vendor.name, "vendor_master"),
                Evidence("Same total amount", _amount(inv.total), "invoice"),
                Evidence(
                    "This invoice",
                    f"{inv.invoice_number or '(no number)'}, "
                    f"{inv.invoice_date.isoformat() if inv.invoice_date else 'no date'}",
                    "invoice",
                ),
                *(Evidence("Similar invoice", _ref(c), "invoice_history") for c in candidates[:5]),
            )
        ]


# --- Vendor identity ---------------------------------------------------------------------


class UnknownVendorRule(Rule):
    code = "vendor_not_in_master"
    category = "vendor"
    description = "The invoice could not be matched to any vendor in the vendor master."

    def evaluate(self, ctx: RiskContext) -> list[SignalDraft]:
        if ctx.vendor is not None:
            return []
        return [
            self.signal(
                Severity.HIGH,
                "Vendor not found in vendor master",
                "No vendor matched this invoice by GSTIN or name. Confirm the supplier is "
                "legitimate and add or assign the vendor before approval.",
                Evidence("Vendor name on invoice", ctx.invoice.vendor_name, "invoice"),
                Evidence("Vendor GSTIN on invoice", ctx.invoice.vendor_gstin, "invoice"),
            )
        ]


class VendorGstinMismatchRule(Rule):
    code = "vendor_gstin_mismatch"
    category = "vendor"
    description = "GSTIN printed on the invoice differs from the vendor master GSTIN."

    def evaluate(self, ctx: RiskContext) -> list[SignalDraft]:
        vendor, inv = ctx.vendor, ctx.invoice
        if vendor is None or not vendor.gstin or not inv.vendor_gstin:
            return []
        if vendor.gstin == inv.vendor_gstin:
            return []
        return [
            self.signal(
                Severity.HIGH,
                "Vendor GSTIN mismatch (possible impersonation)",
                "The GSTIN on the invoice does not match the GSTIN on record for this vendor.",
                Evidence("GSTIN on invoice", inv.vendor_gstin, "invoice"),
                Evidence("GSTIN in vendor master", vendor.gstin, "vendor_master"),
                Evidence("Vendor matched by", ctx.invoice.vendor_match_method, "invoice"),
            )
        ]


class VendorMatchedByNameRule(Rule):
    code = "vendor_matched_by_name_only"
    category = "vendor"
    description = "Vendor identified by name only because no GSTIN appears on the invoice."

    def evaluate(self, ctx: RiskContext) -> list[SignalDraft]:
        if ctx.vendor is None or ctx.invoice.vendor_match_method != "name":
            return []
        if ctx.invoice.vendor_gstin:
            return []  # a GSTIN mismatch is reported by VendorGstinMismatchRule
        return [
            self.signal(
                Severity.LOW,
                "Vendor identified by name only",
                "The invoice has no GSTIN, so the vendor was matched on name. Confirm the supplier.",
                Evidence("Vendor name on invoice", ctx.invoice.vendor_name, "invoice"),
                Evidence("Matched vendor", ctx.vendor.name, "vendor_master"),
            )
        ]


class InactiveVendorRule(Rule):
    code = "vendor_inactive"
    category = "vendor"
    description = "Invoice from a vendor marked inactive."

    def evaluate(self, ctx: RiskContext) -> list[SignalDraft]:
        if ctx.vendor is None or ctx.vendor.status == "active":
            return []
        return [
            self.signal(
                Severity.MEDIUM,
                "Invoice from an inactive vendor",
                "This vendor is marked inactive in the vendor master.",
                Evidence("Vendor status", ctx.vendor.status, "vendor_master"),
            )
        ]


class NewVendorRule(Rule):
    code = "new_vendor"
    category = "vendor"
    description = "Vendor created recently or with no earlier invoices."

    def evaluate(self, ctx: RiskContext) -> list[SignalDraft]:
        vendor = ctx.vendor
        if vendor is None:
            return []
        age_days = (ctx.today - vendor.created_at.date()).days
        first_invoice = not _history(ctx)
        if age_days > ctx.settings.new_vendor_days and not first_invoice:
            return []
        high_value = (
            ctx.invoice.total is not None and ctx.invoice.total >= ctx.settings.high_value_threshold
        )
        return [
            self.signal(
                Severity.MEDIUM if high_value else Severity.LOW,
                "New vendor" + (" with a high-value invoice" if high_value else ""),
                "New vendors carry higher risk; confirm the relationship and payment details.",
                Evidence("Vendor added", f"{age_days} days ago", "vendor_master"),
                Evidence(
                    "Earlier invoices from vendor", str(len(_history(ctx))), "invoice_history"
                ),
                Evidence("Invoice total", _amount(ctx.invoice.total), "invoice"),
            )
        ]


# --- Bank account ------------------------------------------------------------------------


class BankAccountMismatchRule(Rule):
    code = "bank_account_mismatch"
    category = "bank"
    description = "Bank account printed on the invoice differs from the vendor's account on file."

    def evaluate(self, ctx: RiskContext) -> list[SignalDraft]:
        inv, vendor = ctx.invoice, ctx.vendor
        if not inv.bank_fingerprint or vendor is None:
            return []
        if vendor.current_bank is None:
            return [
                self.signal(
                    Severity.MEDIUM,
                    "Bank details on invoice are not on file",
                    "The invoice asks for payment to an account, but the vendor has no bank "
                    "account on record. Verify with the vendor through a known contact.",
                    Evidence("Account on invoice", f"ending {inv.bank_last4}", "invoice"),
                    Evidence("IFSC on invoice", inv.bank_ifsc, "invoice"),
                )
            ]
        bank = vendor.current_bank
        if bank.fingerprint == inv.bank_fingerprint and (
            not inv.bank_ifsc or bank.ifsc == inv.bank_ifsc
        ):
            return []
        return [
            self.signal(
                Severity.HIGH,
                "Potential bank-account change: invoice account differs from vendor master",
                "The invoice directs payment to a different account than the one on file. This is a "
                "common payment-diversion pattern; verify with the vendor through a known contact.",
                Evidence("Account on invoice", f"ending {inv.bank_last4}", "invoice"),
                Evidence("IFSC on invoice", inv.bank_ifsc, "invoice"),
                Evidence("Account on file", f"ending {bank.last4}", "vendor_master"),
                Evidence("IFSC on file", bank.ifsc, "vendor_master"),
            )
        ]


class BankAccountUnverifiedRule(Rule):
    code = "bank_account_unverified"
    category = "bank"
    description = "The vendor's current bank account has not been verified."

    def evaluate(self, ctx: RiskContext) -> list[SignalDraft]:
        vendor = ctx.vendor
        if vendor is None or vendor.current_bank is None:
            return []
        if vendor.current_bank.status != "pending_verification":
            return []
        return [
            self.signal(
                Severity.HIGH,
                "Vendor bank account pending verification",
                "The bank account on file has not been independently verified.",
                Evidence("Account on file", f"ending {vendor.current_bank.last4}", "vendor_master"),
                Evidence("Verification state", vendor.current_bank.status, "vendor_master"),
                Evidence(
                    "Recorded", vendor.current_bank.created_at.date().isoformat(), "vendor_master"
                ),
            )
        ]


class BankAccountRecentlyChangedRule(Rule):
    code = "bank_account_recently_changed"
    category = "bank"
    description = "Vendor bank account changed within the configured alert window."

    def evaluate(self, ctx: RiskContext) -> list[SignalDraft]:
        vendor = ctx.vendor
        if vendor is None or vendor.current_bank is None or not vendor.current_bank.is_change:
            return []
        changed = vendor.current_bank.created_at.date()
        age = (ctx.today - changed).days
        if age > ctx.settings.bank_change_alert_days:
            return []
        return [
            self.signal(
                Severity.MEDIUM,
                "Vendor bank account changed recently",
                "Payments shortly after a bank-account change deserve extra scrutiny.",
                Evidence("Changed on", changed.isoformat(), "vendor_master"),
                Evidence("Days since change", str(age), "vendor_master"),
                Evidence("Alert window", f"{ctx.settings.bank_change_alert_days} days", "policy"),
            )
        ]


# --- Purchase order ----------------------------------------------------------------------


class PORequiredRule(Rule):
    code = "po_missing"
    category = "purchase_order"
    description = "No purchase order referenced although the total exceeds the PO threshold."

    def evaluate(self, ctx: RiskContext) -> list[SignalDraft]:
        threshold = ctx.settings.require_po_above
        inv = ctx.invoice
        if threshold is None or inv.total is None or inv.total < threshold:
            return []
        if ctx.purchase_order is not None or inv.po_number:
            return []
        return [
            self.signal(
                Severity.MEDIUM,
                "Purchase order required but missing",
                "Invoices above the configured amount must reference a purchase order.",
                Evidence("Invoice total", _amount(inv.total), "invoice"),
                Evidence("PO required above", _amount(threshold), "policy"),
            )
        ]


class PONotFoundRule(Rule):
    code = "po_not_found"
    category = "purchase_order"
    description = "The PO number printed on the invoice does not exist."

    def evaluate(self, ctx: RiskContext) -> list[SignalDraft]:
        if not ctx.po_reference_unresolved:
            return []
        return [
            self.signal(
                Severity.MEDIUM,
                "Referenced purchase order not found",
                "The invoice cites a PO number that does not exist in this organization.",
                Evidence("PO number on invoice", ctx.invoice.po_number, "invoice"),
            )
        ]


class POVendorMismatchRule(Rule):
    code = "po_vendor_mismatch"
    category = "purchase_order"
    description = "The linked PO belongs to a different vendor."

    def evaluate(self, ctx: RiskContext) -> list[SignalDraft]:
        po, vendor = ctx.purchase_order, ctx.vendor
        if po is None or vendor is None or po.vendor_id == vendor.id:
            return []
        return [
            self.signal(
                Severity.HIGH,
                "PO mismatch detected: purchase order issued to another vendor",
                "The purchase order referenced by this invoice was issued to a different vendor.",
                Evidence("PO number", po.po_number, "purchase_order"),
                Evidence("Invoice vendor", vendor.name, "vendor_master"),
            )
        ]


class POStatusRule(Rule):
    code = "po_not_open"
    category = "purchase_order"
    description = "The linked PO is not open (draft, closed or cancelled)."

    def evaluate(self, ctx: RiskContext) -> list[SignalDraft]:
        po = ctx.purchase_order
        if po is None or po.status == "open":
            return []
        return [
            self.signal(
                Severity.MEDIUM,
                f"Purchase order is {po.status}",
                "Invoices should be billed against open purchase orders.",
                Evidence("PO number", po.po_number, "purchase_order"),
                Evidence("PO status", po.status, "purchase_order"),
            )
        ]


class POAmountRule(Rule):
    code = "po_amount_exceeded"
    category = "purchase_order"
    description = "Invoice total plus earlier invoices exceed the PO total beyond tolerance."

    def evaluate(self, ctx: RiskContext) -> list[SignalDraft]:
        po, inv = ctx.purchase_order, ctx.invoice
        if po is None or inv.total is None:
            return []
        cumulative = money(po.invoiced_total_other + inv.total)
        allowed = money(
            po.total
            + max(
                ctx.settings.amount_tolerance_absolute,
                po.total * ctx.settings.price_tolerance_percent / Decimal(100),
            )
        )
        if cumulative <= allowed:
            return []
        return [
            self.signal(
                Severity.HIGH,
                "PO mismatch detected: invoiced amount exceeds purchase order",
                "Together with earlier invoices, this invoice bills more than the PO allows.",
                Evidence("PO total", _amount(po.total), "purchase_order"),
                Evidence(
                    "Already invoiced against PO",
                    _amount(po.invoiced_total_other),
                    "invoice_history",
                ),
                Evidence("This invoice", _amount(inv.total), "invoice"),
                Evidence("Cumulative", _amount(cumulative), "invoice"),
                Evidence("Allowed (with tolerance)", _amount(allowed), "policy"),
            )
        ]


def match_po_line(line: LineFact, po_lines: tuple[POLineFact, ...]) -> POLineFact | None:
    """Exact normalized description first, then best token-overlap match >= 0.6."""
    for po_line in po_lines:
        if po_line.normalized == line.normalized:
            return po_line
    tokens = set(line.normalized.split())
    best: tuple[float, POLineFact | None] = (0.0, None)
    for po_line in po_lines:
        po_tokens = set(po_line.normalized.split())
        if not tokens or not po_tokens:
            continue
        score = len(tokens & po_tokens) / len(tokens | po_tokens)
        if score > best[0]:
            best = (score, po_line)
    return best[1] if best[0] >= 0.6 else None


class POLineMatchRule(Rule):
    code = "po_line_mismatch"
    category = "purchase_order"
    description = (
        "Line-level three-way comparison: items not on the PO, quantities above "
        "the PO (including earlier invoices), unit prices above PO price + tolerance."
    )

    def evaluate(self, ctx: RiskContext) -> list[SignalDraft]:
        po, inv, settings = ctx.purchase_order, ctx.invoice, ctx.settings
        if po is None or not inv.lines:
            return []
        signals: list[SignalDraft] = []
        not_on_po, qty_issues, price_issues = [], [], []
        for line in inv.lines:
            po_line = match_po_line(line, po.lines)
            if po_line is None:
                not_on_po.append(Evidence("Item not on PO", line.description, "invoice"))
                continue
            if line.quantity is not None:
                billed = line.quantity + po_line.invoiced_quantity_other
                allowed_qty = po_line.quantity * (1 + settings.quantity_tolerance_percent / 100)
                if billed > allowed_qty:
                    qty_issues.append(
                        Evidence(
                            f"Quantity: {line.description}",
                            f"billed {billed} (this invoice {line.quantity}) vs PO {po_line.quantity}",
                            "purchase_order",
                        )
                    )
            if (
                line.unit_price is not None
                and line.unit_price > po_line.unit_price
                and not within_tolerance(
                    line.unit_price, po_line.unit_price, percent=settings.price_tolerance_percent
                )
            ):
                price_issues.append(
                    Evidence(
                        f"Unit price: {line.description}",
                        f"{format_inr(line.unit_price)} vs PO {format_inr(po_line.unit_price)}",
                        "purchase_order",
                    )
                )
        tolerance = Evidence(
            "Tolerances",
            f"price {settings.price_tolerance_percent}%, "
            f"quantity {settings.quantity_tolerance_percent}%",
            "policy",
        )
        if qty_issues:
            signals.append(
                SignalDraft(
                    "po_quantity_mismatch",
                    self.category,
                    Severity.MEDIUM,
                    "Quantity mismatch detected against purchase order",
                    "Billed quantities exceed the ordered quantities.",
                    (Evidence("PO number", po.po_number, "purchase_order"), *qty_issues, tolerance),
                )
            )
        if price_issues:
            signals.append(
                SignalDraft(
                    "po_price_mismatch",
                    self.category,
                    Severity.MEDIUM,
                    "Price mismatch detected against purchase order",
                    "Unit prices are higher than agreed on the purchase order.",
                    (
                        Evidence("PO number", po.po_number, "purchase_order"),
                        *price_issues,
                        tolerance,
                    ),
                )
            )
        if not_on_po:
            signals.append(
                SignalDraft(
                    "po_item_not_ordered",
                    self.category,
                    Severity.MEDIUM,
                    "Invoice contains items not on the purchase order",
                    "Some invoiced items could not be matched to any PO line.",
                    (Evidence("PO number", po.po_number, "purchase_order"), *not_on_po[:10]),
                )
            )
        return signals


# --- Tax and arithmetic ------------------------------------------------------------------


class TaxArithmeticRule(Rule):
    code = "tax_arithmetic"
    category = "tax"
    description = "Deterministic checks of line sums, totals and GST components (CGST/SGST/IGST)."

    _HIGH = frozenset({"total_mismatch"})

    def evaluate(self, ctx: RiskContext) -> list[SignalDraft]:
        inv = ctx.invoice
        findings = check_tax_arithmetic(
            TaxInputs(
                subtotal=inv.subtotal,
                tax_total=inv.tax_total,
                total=inv.total,
                cgst=inv.cgst,
                sgst=inv.sgst,
                igst=inv.igst,
                line_amounts=tuple(line.amount for line in inv.lines if line.amount is not None),
                line_taxable_and_rates=tuple(
                    (line.amount, line.tax_rate)
                    for line in inv.lines
                    if line.amount is not None and line.tax_rate is not None
                ),
                supplier_state=gstin_state_code(inv.vendor_gstin),
                buyer_state=gstin_state_code(inv.buyer_gstin) or ctx.org_state_code,
            ),
            tolerance=ctx.settings.amount_tolerance_absolute,
        )
        if not findings:
            return []
        severity = Severity.HIGH if any(f.code in self._HIGH for f in findings) else Severity.MEDIUM
        evidence = [
            Evidence(
                f.message,
                (
                    f"expected {_amount(f.expected)}, invoice shows {_amount(f.actual)}"
                    if f.expected is not None
                    else None
                ),
                "invoice",
            )
            for f in findings
        ]
        return [
            self.signal(
                severity,
                "GST/tax arithmetic inconsistency",
                "Amounts on the invoice do not add up. Figures were recomputed in code from the "
                "extracted values.",
                *evidence,
                Evidence(
                    "Rounding tolerance", _amount(ctx.settings.amount_tolerance_absolute), "policy"
                ),
            )
        ]


class InvalidGstinRule(Rule):
    code = "invalid_gstin"
    category = "tax"
    description = "Vendor GSTIN on the invoice fails format/state/checksum validation."

    def evaluate(self, ctx: RiskContext) -> list[SignalDraft]:
        gstin = ctx.invoice.vendor_gstin
        if not gstin:
            return []
        result = validate_gstin(gstin)
        if result.valid:
            return []
        return [
            self.signal(
                Severity.MEDIUM,
                "Invalid vendor GSTIN",
                "The GSTIN printed on the invoice is not a valid GSTIN.",
                Evidence("GSTIN on invoice", gstin, "invoice"),
                Evidence("Validation result", result.reason, "invoice"),
            )
        ]


class BuyerGstinRule(Rule):
    code = "buyer_gstin_mismatch"
    category = "tax"
    description = "Buyer GSTIN on the invoice is not this organization's GSTIN."

    def evaluate(self, ctx: RiskContext) -> list[SignalDraft]:
        buyer = ctx.invoice.buyer_gstin
        if not buyer or not ctx.org_gstin or buyer == ctx.org_gstin:
            return []
        return [
            self.signal(
                Severity.MEDIUM,
                "Invoice addressed to a different GSTIN",
                "The buyer GSTIN on the invoice does not match your organization's GSTIN, which "
                "affects input tax credit.",
                Evidence("Buyer GSTIN on invoice", buyer, "invoice"),
                Evidence("Organization GSTIN", ctx.org_gstin, "policy"),
            )
        ]


# --- Data quality --------------------------------------------------------------------------


class MissingInformationRule(Rule):
    code = "missing_required_fields"
    category = "data_quality"
    description = "Required invoice fields could not be found on the document."

    def evaluate(self, ctx: RiskContext) -> list[SignalDraft]:
        inv = ctx.invoice
        required = {
            "Invoice number": inv.invoice_number,
            "Invoice date": inv.invoice_date,
            "Invoice total": inv.total,
            "Vendor name": inv.vendor_name or (ctx.vendor.name if ctx.vendor else None),
        }
        if (inv.currency or "INR") == "INR":
            required["Vendor GSTIN"] = inv.vendor_gstin
        missing = [label for label, value in required.items() if value in (None, "")]
        if not missing:
            return []
        return [
            self.signal(
                Severity.MEDIUM,
                "Missing invoice information",
                "Some required fields were not found. Unknown values are left blank, never guessed; "
                "enter them manually after checking the document.",
                *(Evidence("Missing", label, "invoice") for label in missing),
            )
        ]


class ExtractionConfidenceRule(Rule):
    code = "low_extraction_confidence"
    category = "data_quality"
    description = "Key fields were read with low confidence or extractors disagreed."

    _KEY_FIELDS = ("total", "invoice_number", "vendor_gstin", "bank_account_number", "invoice_date")

    def evaluate(self, ctx: RiskContext) -> list[SignalDraft]:
        inv = ctx.invoice
        evidence = [
            Evidence(f"Low confidence: {name}", f"{inv.field_confidence[name]:.2f}", "invoice")
            for name in self._KEY_FIELDS
            if name in inv.field_confidence and 0 < inv.field_confidence[name] < 0.5
        ]
        evidence += [
            Evidence("Extractors disagree", name, "invoice") for name in inv.extraction_conflicts
        ]
        if not evidence:
            return []
        return [
            self.signal(
                Severity.LOW,
                "Check extracted values against the document",
                "Some key values were hard to read or read differently by the two extractors.",
                *evidence,
            )
        ]


class DateAnomalyRule(Rule):
    code = "date_anomaly"
    category = "data_quality"
    description = "Future-dated, very old, or due-before-issue invoices."

    def evaluate(self, ctx: RiskContext) -> list[SignalDraft]:
        inv = ctx.invoice
        if inv.invoice_date is None:
            return []
        if inv.invoice_date > ctx.today + timedelta(days=1):
            return [
                self.signal(
                    Severity.MEDIUM,
                    "Invoice is future-dated",
                    "The invoice date is later than today.",
                    Evidence("Invoice date", inv.invoice_date.isoformat(), "invoice"),
                )
            ]
        signals = []
        if (ctx.today - inv.invoice_date).days > 365:
            signals.append(
                self.signal(
                    Severity.LOW,
                    "Invoice is more than a year old",
                    "Old invoices may already have been paid.",
                    Evidence("Invoice date", inv.invoice_date.isoformat(), "invoice"),
                )
            )
        if inv.due_date and inv.due_date < inv.invoice_date:
            signals.append(
                self.signal(
                    Severity.LOW,
                    "Due date is before the invoice date",
                    "The dates on the invoice are inconsistent.",
                    Evidence("Invoice date", inv.invoice_date.isoformat(), "invoice"),
                    Evidence("Due date", inv.due_date.isoformat(), "invoice"),
                )
            )
        return signals


class DocumentInstructionsRule(Rule):
    code = "document_contains_instructions"
    category = "document"
    description = "Instruction-like text aimed at an AI or reviewer was found in the document."

    def evaluate(self, ctx: RiskContext) -> list[SignalDraft]:
        if not ctx.injection_indicators:
            return []
        return [
            self.signal(
                Severity.MEDIUM,
                "Document contains instruction-like text",
                "The document includes text that tries to instruct an automated system or reviewer. "
                "It was treated as data and had no effect, but it is unusual for a genuine invoice.",
                *(Evidence("Text found", text, "document") for text in ctx.injection_indicators),
            )
        ]


# --- Behavioural anomalies ------------------------------------------------------------------


class UnusualAmountRule(Rule):
    code = "unusual_amount"
    category = "anomaly"
    description = "Total far above this vendor's median (needs at least 3 earlier invoices)."

    def evaluate(self, ctx: RiskContext) -> list[SignalDraft]:
        inv = ctx.invoice
        totals = [h.total for h in _history(ctx) if h.total is not None and h.status != "rejected"]
        if inv.total is None or len(totals) < 3:
            return []
        median = Decimal(statistics.median(totals))
        if median <= ZERO:
            return []
        multiplier = ctx.settings.unusual_amount_multiplier
        if inv.total <= median * multiplier:
            return []
        ratio = (inv.total / median).quantize(Decimal("0.1"))
        return [
            self.signal(
                Severity.MEDIUM,
                "Unusual amount for this vendor",
                "This invoice is much larger than this vendor's typical invoice.",
                Evidence("Invoice total", _amount(inv.total), "invoice"),
                Evidence("Vendor median", _amount(money(median)), "invoice_history"),
                Evidence("Ratio to median", f"{ratio}x", "invoice_history"),
                Evidence("Invoices considered", str(len(totals)), "invoice_history"),
                Evidence("Threshold", f"{multiplier}x median", "policy"),
            )
        ]


class PriceIncreaseRule(Rule):
    code = "unexpected_price_increase"
    category = "anomaly"
    description = "Unit price for an item rose sharply versus this vendor's last invoiced price."

    def evaluate(self, ctx: RiskContext) -> list[SignalDraft]:
        if ctx.vendor is None:
            return []
        threshold = ctx.settings.price_increase_alert_percent
        evidence = []
        for line in ctx.invoice.lines:
            history = ctx.vendor.price_history.get(line.normalized)
            if not history or line.unit_price is None:
                continue
            last_date, last_price = history[-1]
            change = percent_change(line.unit_price, last_price)
            if change is not None and change > threshold:
                evidence.append(
                    Evidence(
                        f"Price increase: {line.description}",
                        f"{format_inr(last_price)} ({last_date.isoformat()}) -> "
                        f"{format_inr(line.unit_price)} (+{change}%)",
                        "invoice_history",
                    )
                )
        if not evidence:
            return []
        return [
            self.signal(
                Severity.MEDIUM,
                "Unexpected price increase",
                "Unit prices are higher than this vendor charged previously.",
                *evidence,
                Evidence("Alert above", f"{threshold}%", "policy"),
            )
        ]


class UnusualFrequencyRule(Rule):
    code = "unusual_frequency"
    category = "anomaly"
    description = "Four or more invoices from the same vendor within 7 days."

    def evaluate(self, ctx: RiskContext) -> list[SignalDraft]:
        if ctx.vendor is None:
            return []
        since = ctx.invoice.created_at - timedelta(days=7)
        recent = [h for h in _history(ctx) if h.created_at >= since]
        if len(recent) + 1 < 4:
            return []
        return [
            self.signal(
                Severity.LOW,
                "Unusual invoice frequency",
                "This vendor submitted several invoices in a short period.",
                Evidence(
                    "Invoices in last 7 days (incl. this)", str(len(recent) + 1), "invoice_history"
                ),
            )
        ]


class InvoiceSplittingRule(Rule):
    code = "invoice_splitting"
    category = "anomaly"
    description = (
        "Several invoices from one vendor within a short window, each below the "
        "approval threshold but together above it."
    )

    def evaluate(self, ctx: RiskContext) -> list[SignalDraft]:
        inv, vendor = ctx.invoice, ctx.vendor
        threshold = ctx.settings.high_value_threshold
        if vendor is None or inv.total is None or inv.total >= threshold:
            return []
        anchor = inv.invoice_date or inv.created_at.date()
        window = ctx.settings.split_invoice_window_days
        related = [
            h
            for h in _history(ctx)
            if h.status != "rejected"
            and h.total is not None
            and h.total < threshold
            and abs(((h.invoice_date or h.created_at.date()) - anchor).days) <= window
        ]
        combined = money(inv.total + sum((h.total or ZERO for h in related), ZERO))
        if len(related) < 1 or combined < threshold:
            return []
        return [
            self.signal(
                Severity.HIGH,
                "Potential invoice splitting",
                "Multiple invoices each below the approval threshold together exceed it, which can "
                "indicate an attempt to avoid additional approval.",
                Evidence("This invoice", _amount(inv.total), "invoice"),
                *(Evidence("Related invoice", _ref(h), "invoice_history") for h in related[:5]),
                Evidence("Combined total", _amount(combined), "invoice_history"),
                Evidence("Approval threshold", _amount(threshold), "policy"),
                Evidence("Window", f"{window} days", "policy"),
            )
        ]


ALL_RULES: tuple[Rule, ...] = (
    DuplicateDocumentRule(),
    DuplicateInvoiceNumberRule(),
    PossibleDuplicateRule(),
    UnknownVendorRule(),
    VendorGstinMismatchRule(),
    VendorMatchedByNameRule(),
    InactiveVendorRule(),
    NewVendorRule(),
    BankAccountMismatchRule(),
    BankAccountUnverifiedRule(),
    BankAccountRecentlyChangedRule(),
    PORequiredRule(),
    PONotFoundRule(),
    POVendorMismatchRule(),
    POStatusRule(),
    POAmountRule(),
    POLineMatchRule(),
    TaxArithmeticRule(),
    InvalidGstinRule(),
    BuyerGstinRule(),
    MissingInformationRule(),
    ExtractionConfidenceRule(),
    DateAnomalyRule(),
    DocumentInstructionsRule(),
    UnusualAmountRule(),
    PriceIncreaseRule(),
    UnusualFrequencyRule(),
    InvoiceSplittingRule(),
)
