"""Deterministic financial logic: parsing, rounding, tolerances, GSTIN, GST arithmetic."""

from decimal import Decimal

import pytest

from app.demo.seed import make_gstin
from app.finance.gst import (
    TaxInputs,
    check_tax_arithmetic,
    gstin_check_character,
    gstin_state_code,
    validate_gstin,
)
from app.finance.money import (
    format_inr,
    money,
    parse_decimal,
    percent_change,
    percent_of,
    within_tolerance,
)

D = Decimal


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("1,23,456.50", D("123456.50")),
        ("123,456.50", D("123456.50")),
        ("₹ 7,788.00", D("7788.00")),
        ("Rs. 1,947", D("1947")),
        ("INR 42.5", D("42.5")),
        ("(1,000.00)", D("-1000.00")),
        (1947, D("1947")),
        (0.1, D("0.1")),
    ],
)
def test_parse_decimal_accepts_indian_and_international_grouping(
    raw: object, expected: Decimal
) -> None:
    assert parse_decimal(raw) == expected


@pytest.mark.parametrize("raw", [None, "", "abc", "12.345,67", "1,2,3", "NaN", True, "12 apples"])
def test_parse_decimal_never_guesses(raw: object) -> None:
    assert parse_decimal(raw) is None


def test_money_rounds_half_up_to_paise() -> None:
    assert money(D("10.005")) == D("10.01")
    assert money(D("10.004")) == D("10.00")
    assert money(D("-10.005")) == D("-10.01")
    # Floats would give 0.30000000000000004; Decimal stays exact.
    assert D("0.1") + D("0.2") == D("0.3")


def test_percent_of_and_change() -> None:
    assert percent_of(D("6600.00"), D("18")) == D("1188.00")
    assert percent_of(D("333.33"), D("18")) == D("60.00")
    assert percent_change(D("14.00"), D("12.50")) == D("12.00")
    assert percent_change(D("1"), D("0")) is None


def test_within_tolerance_absolute_and_percent() -> None:
    assert within_tolerance(D("100.99"), D("100"), absolute=D("1"))
    assert not within_tolerance(D("101.01"), D("100"), absolute=D("1"))
    assert within_tolerance(D("102"), D("100"), percent=D("2"))
    assert not within_tolerance(D("102.01"), D("100"), percent=D("2"))


def test_format_inr_uses_indian_grouping() -> None:
    assert format_inr(D("1234567.5")) == "₹12,34,567.50"
    assert format_inr(D("999")) == "₹999.00"
    assert format_inr(D("-100300")) == "-₹1,00,300.00"


def test_gstin_checksum_validation() -> None:
    gstin = make_gstin("27", "AAPFU0939F")
    assert validate_gstin(gstin).valid
    assert gstin_state_code(gstin) == "27"
    tampered = gstin[:14] + ("A" if gstin[14] != "A" else "B")
    assert validate_gstin(tampered).reason == "checksum_mismatch"
    assert validate_gstin("27AAPFU0939F1Z").reason == "invalid_format"
    assert validate_gstin(
        "45" + gstin[2:14] + gstin_check_character("45" + gstin[2:14])
    ).reason == ("invalid_state_code")
    assert validate_gstin(None).reason == "missing"


def _tax(**kwargs: object) -> TaxInputs:
    base: dict[str, object] = dict(
        subtotal=None,
        tax_total=None,
        total=None,
        cgst=None,
        sgst=None,
        igst=None,
        line_amounts=(),
        line_taxable_and_rates=(),
        supplier_state=None,
        buyer_state=None,
    )
    base.update(kwargs)
    return TaxInputs(**base)  # type: ignore[arg-type]


def test_consistent_intra_state_invoice_has_no_findings() -> None:
    data = _tax(
        subtotal=D("6600.00"),
        cgst=D("594.00"),
        sgst=D("594.00"),
        total=D("7788.00"),
        line_amounts=(D("5000.00"), D("1600.00")),
        line_taxable_and_rates=((D("5000.00"), D("18")), (D("1600.00"), D("18"))),
        supplier_state="27",
        buyer_state="27",
    )
    assert check_tax_arithmetic(data) == []


def test_detects_total_line_component_and_rate_errors() -> None:
    data = _tax(
        subtotal=D("20000.00"),
        igst=D("2400.00"),
        tax_total=D("2500.00"),
        total=D("24900.00"),
        line_amounts=(D("19000.00"),),
        line_taxable_and_rates=((D("20000.00"), D("12")),),
        supplier_state="33",
        buyer_state="27",
    )
    codes = {f.code for f in check_tax_arithmetic(data)}
    assert {
        "line_sum_mismatch",
        "tax_components_mismatch",
        "total_mismatch",
        "tax_rate_mismatch",
    } <= codes


def test_detects_wrong_gst_type_for_supply() -> None:
    intra_with_igst = _tax(igst=D("10"), supplier_state="27", buyer_state="27")
    inter_with_cgst = _tax(cgst=D("5"), sgst=D("5"), supplier_state="29", buyer_state="27")
    unequal = _tax(cgst=D("5"), sgst=D("9"))
    assert "igst_on_intra_state" in {f.code for f in check_tax_arithmetic(intra_with_igst)}
    assert "cgst_sgst_on_inter_state" in {f.code for f in check_tax_arithmetic(inter_with_cgst)}
    assert "cgst_sgst_unequal" in {f.code for f in check_tax_arithmetic(unequal)}


def test_rounding_within_tolerance_is_not_flagged() -> None:
    data = _tax(
        subtotal=D("333.33"),
        igst=D("60.00"),
        total=D("393.33"),
        line_taxable_and_rates=((D("111.11"), D("18")), (D("222.22"), D("18"))),
    )
    assert check_tax_arithmetic(data) == []


def test_non_standard_rate_flagged() -> None:
    data = _tax(
        subtotal=D("100"), igst=D("7"), total=D("107"), line_taxable_and_rates=((D("100"), D("7")),)
    )
    assert "non_standard_rate" in {f.code for f in check_tax_arithmetic(data)}
