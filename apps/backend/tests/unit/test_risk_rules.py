"""Every risk rule, tested independently against a clean baseline context."""

from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest

from app.demo.seed import make_gstin
from app.models.enums import RiskLevel, Severity
from app.modules.identity.schemas import OrganizationSettings
from app.modules.risk import rules
from app.modules.risk.engine import run_rules, score_signals
from app.modules.risk.facts import (
    BankFact,
    HistoricalInvoice,
    InvoiceFact,
    LineFact,
    POFact,
    POLineFact,
    RiskContext,
    VendorFact,
)
from app.modules.risk.rules import ALL_RULES, Rule, SignalDraft

D = Decimal
TODAY = date(2026, 9, 27)
NOW = datetime(2026, 9, 27, 10, tzinfo=UTC)
ORG_GSTIN = make_gstin("27", "AABCD1234E")
VENDOR_GSTIN = make_gstin("27", "AAECA5678F")


def line(desc: str, qty: str, price: str, rate: str = "18") -> LineFact:
    amount = D(qty) * D(price)
    return LineFact(desc, desc.lower(), D(qty), D(price), D(rate), amount.quantize(D("0.01")))


def history(number: str, total: str, days_ago: int, status: str = "approved") -> HistoricalInvoice:
    return HistoricalInvoice(
        id=f"h-{number}",
        invoice_number=number,
        normalized_number=number.replace("-", "").upper(),
        invoice_date=TODAY - timedelta(days=days_ago),
        total=D(total),
        status=status,
        created_at=NOW - timedelta(days=days_ago),
    )


BANK = BankFact(
    last4="5678",
    fingerprint="fp-good",
    ifsc="HDFC0001234",
    status="verified",
    created_at=NOW - timedelta(days=400),
    is_change=False,
)
VENDOR = VendorFact(
    id="v1",
    name="Acme Industrial Supplies",
    gstin=VENDOR_GSTIN,
    status="active",
    created_at=NOW - timedelta(days=400),
    current_bank=BANK,
    history=(history("ACM-10", "7000.00", 60), history("ACM-11", "8000.00", 40)),
    price_history={"steel bolts m8": ((TODAY - timedelta(days=40), D("12.50")),)},
)
PO = POFact(
    id="po1",
    po_number="PO-1001",
    vendor_id="v1",
    status="open",
    total=D("29500.00"),
    invoiced_total_other=D("0"),
    lines=(
        POLineFact(
            "Steel bolts M8", "steel bolts m8", D("1000"), D("12.50"), D("12500.00"), D("0")
        ),
        POLineFact("Hex nuts M8", "hex nuts m8", D("2000"), D("2.00"), D("4000.00"), D("0")),
    ),
)
INVOICE = InvoiceFact(
    id="i1",
    invoice_number="ACM-42",
    normalized_number="ACM42",
    invoice_date=TODAY - timedelta(days=2),
    due_date=TODAY + timedelta(days=28),
    currency="INR",
    subtotal=D("6600.00"),
    tax_total=D("1188.00"),
    cgst=D("594.00"),
    sgst=D("594.00"),
    igst=None,
    total=D("7788.00"),
    vendor_name="Acme Industrial Supplies Pvt Ltd",
    vendor_gstin=VENDOR_GSTIN,
    buyer_gstin=ORG_GSTIN,
    po_number="PO-1001",
    bank_last4="5678",
    bank_fingerprint="fp-good",
    bank_ifsc="HDFC0001234",
    lines=(line("Steel bolts M8", "400", "12.50"), line("Hex nuts M8", "800", "2.00")),
    created_at=NOW,
    field_confidence={"total": 0.95, "invoice_number": 0.95},
    vendor_match_method="gstin",
)
CLEAN = RiskContext(
    invoice=INVOICE,
    vendor=VENDOR,
    purchase_order=PO,
    po_reference_unresolved=False,
    org_gstin=ORG_GSTIN,
    org_state_code="27",
    settings=OrganizationSettings(),
    today=TODAY,
)


def with_invoice(**changes: Any) -> RiskContext:
    return replace(CLEAN, invoice=replace(INVOICE, **changes))


def with_vendor(**changes: Any) -> RiskContext:
    return replace(CLEAN, vendor=replace(VENDOR, **changes))


def codes(ctx: RiskContext) -> set[str]:
    return {s.rule_code for s in run_rules(ctx).signals}


def only(rule: Rule, ctx: RiskContext) -> SignalDraft:
    signals = rule.evaluate(ctx)
    assert len(signals) == 1, signals
    return signals[0]


def test_clean_invoice_produces_no_signals() -> None:
    result = run_rules(CLEAN)
    assert result.signals == ()
    assert result.level is RiskLevel.NONE and result.score == 0
    assert result.rules_evaluated == len(ALL_RULES) and not result.rules_failed


def test_every_rule_has_unique_code_category_and_description() -> None:
    assert len({r.code for r in ALL_RULES}) == len(ALL_RULES)
    assert all(r.category and r.description for r in ALL_RULES)


# --- duplicates --------------------------------------------------------------------------


def test_duplicate_document_hash() -> None:
    ctx = replace(CLEAN, same_document_invoices=(history("ACM-42", "7788.00", 3),))
    signal = only(rules.DuplicateDocumentRule(), ctx)
    assert signal.severity is Severity.HIGH
    assert any(e.source == "document" for e in signal.evidence)


def test_duplicate_document_ignores_failed_uploads() -> None:
    ctx = replace(CLEAN, same_document_invoices=(history("X", "1", 1, status="failed"),))
    assert rules.DuplicateDocumentRule().evaluate(ctx) == []


def test_duplicate_invoice_number_normalises_formatting() -> None:
    ctx = with_vendor(history=(history("acm-42", "7788.00", 30),))
    signal = only(rules.DuplicateInvoiceNumberRule(), ctx)
    labels = [e.label for e in signal.evidence]
    assert signal.severity is Severity.HIGH
    assert {"Same vendor", "Same invoice number", "Same total amount"} <= set(labels)


def test_possible_duplicate_same_total_nearby_date_different_number() -> None:
    ctx = with_vendor(history=(history("ACM-99", "7788.00", 5),))
    signal = only(rules.PossibleDuplicateRule(), ctx)
    assert signal.severity is Severity.MEDIUM
    far = with_vendor(history=(history("ZZZ-1", "7788.00", 60),))
    assert rules.PossibleDuplicateRule().evaluate(far) == []


def test_possible_duplicate_similar_number() -> None:
    ctx = with_vendor(history=(history("ACM-421", "7788.00", 60),))
    assert only(rules.PossibleDuplicateRule(), ctx).rule_code == "possible_duplicate"


# --- vendor --------------------------------------------------------------------------------


def test_unknown_vendor() -> None:
    signal = only(rules.UnknownVendorRule(), replace(CLEAN, vendor=None, purchase_order=None))
    assert signal.severity is Severity.HIGH


def test_vendor_gstin_mismatch() -> None:
    other = make_gstin("27", "AAECZ9999Q")
    signal = only(rules.VendorGstinMismatchRule(), with_invoice(vendor_gstin=other))
    assert signal.severity is Severity.HIGH
    assert {e.value for e in signal.evidence} >= {other, VENDOR_GSTIN}


def test_vendor_matched_by_name_only() -> None:
    ctx = with_invoice(vendor_match_method="name", vendor_gstin=None)
    assert only(rules.VendorMatchedByNameRule(), ctx).severity is Severity.LOW


def test_inactive_vendor() -> None:
    assert (
        only(rules.InactiveVendorRule(), with_vendor(status="inactive")).severity is Severity.MEDIUM
    )


def test_new_vendor_low_and_high_value_medium() -> None:
    new = with_vendor(created_at=NOW - timedelta(days=5), history=())
    assert only(rules.NewVendorRule(), new).severity is Severity.LOW
    big = replace(new, invoice=replace(INVOICE, total=D("900000")))
    assert only(rules.NewVendorRule(), big).severity is Severity.MEDIUM


# --- bank ------------------------------------------------------------------------------------


def test_bank_account_mismatch() -> None:
    ctx = with_invoice(bank_fingerprint="fp-other", bank_last4="9999", bank_ifsc="YESB0009988")
    signal = only(rules.BankAccountMismatchRule(), ctx)
    assert signal.severity is Severity.HIGH
    assert "ending 9999" in {e.value for e in signal.evidence}
    assert all("fp-" not in (e.value or "") for e in signal.evidence)  # fingerprints never shown


def test_bank_details_not_on_file() -> None:
    ctx = replace(CLEAN, vendor=replace(VENDOR, current_bank=None))
    assert only(rules.BankAccountMismatchRule(), ctx).severity is Severity.MEDIUM


def test_bank_account_unverified_and_recently_changed() -> None:
    changed = replace(
        BANK, status="pending_verification", created_at=NOW - timedelta(days=3), is_change=True
    )
    ctx = with_vendor(current_bank=changed)
    assert only(rules.BankAccountUnverifiedRule(), ctx).severity is Severity.HIGH
    assert only(rules.BankAccountRecentlyChangedRule(), ctx).severity is Severity.MEDIUM
    old_change = with_vendor(
        current_bank=replace(changed, status="verified", created_at=NOW - timedelta(days=200))
    )
    assert rules.BankAccountRecentlyChangedRule().evaluate(old_change) == []


# --- purchase orders -------------------------------------------------------------------------


def test_po_required_but_missing() -> None:
    ctx = replace(
        CLEAN, purchase_order=None, invoice=replace(INVOICE, po_number=None, total=D("150000"))
    )
    assert only(rules.PORequiredRule(), ctx).severity is Severity.MEDIUM


def test_po_not_found() -> None:
    ctx = replace(CLEAN, purchase_order=None, po_reference_unresolved=True)
    assert only(rules.PONotFoundRule(), ctx).rule_code == "po_not_found"


def test_po_vendor_mismatch_and_status() -> None:
    ctx = replace(CLEAN, purchase_order=replace(PO, vendor_id="v2", status="closed"))
    assert only(rules.POVendorMismatchRule(), ctx).severity is Severity.HIGH
    assert only(rules.POStatusRule(), ctx).severity is Severity.MEDIUM


def test_po_amount_exceeded_counts_earlier_invoices() -> None:
    ctx = replace(CLEAN, purchase_order=replace(PO, invoiced_total_other=D("25000.00")))
    signal = only(rules.POAmountRule(), ctx)
    assert signal.severity is Severity.HIGH
    assert any(e.label == "Cumulative" and e.value == "₹32,788.00" for e in signal.evidence)


def test_po_amount_within_tolerance_is_ok() -> None:
    ctx = replace(CLEAN, purchase_order=replace(PO, total=D("7700.00")))
    assert rules.POAmountRule().evaluate(ctx) == []  # 7788 <= 7700 + 2% (154)


def test_po_line_quantity_price_and_unordered_items() -> None:
    ctx = with_invoice(
        lines=(
            line("Steel bolts M8", "1200", "14.00"),
            line("Hex nuts M8", "100", "2.00"),
            line("Gold plated screws", "1", "999.00"),
        )
    )
    found = {s.rule_code: s for s in rules.POLineMatchRule().evaluate(ctx)}
    assert set(found) == {"po_quantity_mismatch", "po_price_mismatch", "po_item_not_ordered"}
    assert "billed 1200" in (found["po_quantity_mismatch"].evidence[1].value or "")


def test_po_quantity_includes_previously_invoiced() -> None:
    po = replace(PO, lines=(replace(PO.lines[0], invoiced_quantity_other=D("700")), PO.lines[1]))
    signals = rules.POLineMatchRule().evaluate(replace(CLEAN, purchase_order=po))
    assert [s.rule_code for s in signals] == ["po_quantity_mismatch"]


def test_po_line_fuzzy_description_match() -> None:
    matched = rules.match_po_line(line("M8 steel bolts", "1", "1"), PO.lines)
    assert matched is not None and matched.description == "Steel bolts M8"
    assert rules.match_po_line(line("Printer paper", "1", "1"), PO.lines) is None


# --- tax / data quality -------------------------------------------------------------------


def test_tax_arithmetic_total_mismatch_is_high() -> None:
    signal = only(rules.TaxArithmeticRule(), with_invoice(total=D("7888.00")))
    assert signal.severity is Severity.HIGH
    assert any("expected ₹7,788.00" in (e.value or "") for e in signal.evidence)


def test_tax_rule_uses_org_state_for_supply_type() -> None:
    ctx = with_invoice(cgst=None, sgst=None, igst=D("1188.00"), buyer_gstin=None)
    signal = only(rules.TaxArithmeticRule(), ctx)
    assert signal.severity is Severity.MEDIUM
    assert any("same state" in e.label for e in signal.evidence)


def test_invalid_gstin_and_buyer_mismatch() -> None:
    assert only(
        rules.InvalidGstinRule(), with_invoice(vendor_gstin="27AAECA5678F1ZZ")
    ).severity is (Severity.MEDIUM)
    other_buyer = make_gstin("29", "AABCD1234E")
    assert only(rules.BuyerGstinRule(), with_invoice(buyer_gstin=other_buyer)).rule_code == (
        "buyer_gstin_mismatch"
    )


def test_missing_information_is_reported_not_guessed() -> None:
    ctx = with_invoice(invoice_number=None, total=None, vendor_gstin=None)
    signal = only(rules.MissingInformationRule(), ctx)
    assert {e.value for e in signal.evidence} == {"Invoice number", "Invoice total", "Vendor GSTIN"}


def test_low_confidence_and_conflicts() -> None:
    ctx = with_invoice(field_confidence={"total": 0.3}, extraction_conflicts=("invoice_number",))
    signal = only(rules.ExtractionConfidenceRule(), ctx)
    assert len(signal.evidence) == 2


@pytest.mark.parametrize(
    ("changes", "expected"),
    [
        ({"invoice_date": TODAY + timedelta(days=10)}, Severity.MEDIUM),
        ({"invoice_date": TODAY - timedelta(days=500), "due_date": None}, Severity.LOW),
        ({"due_date": TODAY - timedelta(days=30)}, Severity.LOW),
    ],
)
def test_date_anomalies(changes: dict[str, object], expected: Severity) -> None:
    assert only(rules.DateAnomalyRule(), with_invoice(**changes)).severity is expected


def test_document_instructions_detected() -> None:
    ctx = replace(CLEAN, injection_indicators=("ignore previous instructions",))
    assert only(rules.DocumentInstructionsRule(), ctx).severity is Severity.MEDIUM


# --- behavioural anomalies ------------------------------------------------------------------


def test_unusual_amount_needs_history_and_threshold() -> None:
    hist = tuple(history(f"H-{i}", "1000.00", 20 + i) for i in range(4))
    big = replace(
        CLEAN, vendor=replace(VENDOR, history=hist), invoice=replace(INVOICE, total=D("5000.00"))
    )
    signal = only(rules.UnusualAmountRule(), big)
    assert any(e.value == "5.0x" for e in signal.evidence)
    too_little_history = replace(big, vendor=replace(VENDOR, history=hist[:2]))
    assert rules.UnusualAmountRule().evaluate(too_little_history) == []


def test_price_increase_against_vendor_history() -> None:
    ctx = with_invoice(lines=(line("Steel bolts M8", "10", "14.00"),))
    signal = only(rules.PriceIncreaseRule(), ctx)
    assert "+12.00%" in (signal.evidence[0].value or "")
    small = with_invoice(lines=(line("Steel bolts M8", "10", "13.00"),))  # +4% < 10%
    assert rules.PriceIncreaseRule().evaluate(small) == []


def test_unusual_frequency() -> None:
    recent = tuple(history(f"R-{i}", "10.00", 1) for i in range(3))
    assert only(rules.UnusualFrequencyRule(), with_vendor(history=recent)).severity is Severity.LOW


def test_invoice_splitting() -> None:
    settings = OrganizationSettings(high_value_threshold=D("10000"))
    split = replace(
        CLEAN, settings=settings, vendor=replace(VENDOR, history=(history("S-1", "6000.00", 3),))
    )
    signal = only(rules.InvoiceSplittingRule(), split)
    assert signal.severity is Severity.HIGH
    assert any(e.label == "Combined total" and e.value == "₹13,788.00" for e in signal.evidence)


# --- engine ------------------------------------------------------------------------------------


def test_scoring_levels() -> None:
    def s(sev: Severity) -> SignalDraft:
        return SignalDraft("x", "c", sev, "t", "d")

    assert score_signals([]) == (0, RiskLevel.NONE)
    assert score_signals([s(Severity.LOW)]) == (5, RiskLevel.LOW)
    assert score_signals([s(Severity.MEDIUM)]) == (15, RiskLevel.MEDIUM)
    assert score_signals([s(Severity.LOW)] * 5) == (25, RiskLevel.MEDIUM)
    assert score_signals([s(Severity.HIGH)]) == (40, RiskLevel.HIGH)
    assert score_signals([s(Severity.HIGH)] * 4)[0] == 100


def test_failing_rule_is_recorded_not_silently_passed() -> None:
    class Broken(Rule):
        code = "broken"
        category = "test"
        description = "raises"

        def evaluate(self, ctx: RiskContext) -> list[SignalDraft]:
            raise ZeroDivisionError

    result = run_rules(CLEAN, (Broken(),))
    assert result.rules_failed == ("broken",)
    assert result.signals[0].rule_code == "rule_evaluation_error"
    assert result.level is RiskLevel.MEDIUM


def test_signals_never_claim_fraud() -> None:
    worst = replace(
        CLEAN,
        vendor=None,
        purchase_order=None,
        po_reference_unresolved=True,
        same_document_invoices=(history("X", "1", 1),),
        injection_indicators=("ignore previous instructions",),
        invoice=replace(INVOICE, total=D("1"), vendor_gstin="BAD"),
    )
    for signal in run_rules(worst).signals:
        text = f"{signal.title} {signal.description}".lower()
        assert "fraudulent" not in text and "is fraud" not in text
