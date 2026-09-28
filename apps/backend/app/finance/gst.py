"""GST (India) validation and tax arithmetic. Pure functions, fully deterministic.

GSTIN structure (15 chars): 2-digit state code, 10-char PAN, entity number,
'Z' (default), and a check character computed with the GSTN base-36 algorithm.
"""

import re
from dataclasses import dataclass
from decimal import Decimal

from app.finance.money import ZERO, money, percent_of, within_tolerance

_GSTIN_PATTERN = re.compile(r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$")
_CHARSET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"

# Standard GST slabs (percent). Rates outside this set are flagged, not rejected.
STANDARD_GST_RATES = frozenset(
    Decimal(r) for r in ("0", "0.1", "0.25", "1.5", "3", "5", "12", "18", "28", "40")
)

# Valid GST state/UT codes (01-38) plus 97 (other territory) and 99 (centre jurisdiction).
VALID_STATE_CODES = frozenset({f"{i:02d}" for i in range(1, 39)} | {"97", "99"})


def normalize_gstin(raw: str | None) -> str | None:
    if not raw:
        return None
    cleaned = re.sub(r"[\s-]", "", raw).upper()
    return cleaned or None


def gstin_check_character(first14: str) -> str:
    total = 0
    for index, char in enumerate(first14):
        value = _CHARSET.index(char)
        product = value * (2 if index % 2 else 1)
        total += product // 36 + product % 36
    return _CHARSET[(36 - total % 36) % 36]


@dataclass(frozen=True)
class GstinValidation:
    valid: bool
    reason: str | None = None


def validate_gstin(raw: str | None) -> GstinValidation:
    gstin = normalize_gstin(raw)
    if not gstin:
        return GstinValidation(False, "missing")
    if not _GSTIN_PATTERN.match(gstin):
        return GstinValidation(False, "invalid_format")
    if gstin[:2] not in VALID_STATE_CODES:
        return GstinValidation(False, "invalid_state_code")
    if gstin_check_character(gstin[:14]) != gstin[14]:
        return GstinValidation(False, "checksum_mismatch")
    return GstinValidation(True)


def gstin_state_code(raw: str | None) -> str | None:
    gstin = normalize_gstin(raw)
    return gstin[:2] if gstin and len(gstin) >= 2 and gstin[:2].isdigit() else None


@dataclass(frozen=True)
class TaxFinding:
    code: str
    message: str
    expected: Decimal | None = None
    actual: Decimal | None = None


@dataclass(frozen=True)
class TaxInputs:
    subtotal: Decimal | None
    tax_total: Decimal | None
    total: Decimal | None
    cgst: Decimal | None
    sgst: Decimal | None
    igst: Decimal | None
    line_amounts: tuple[Decimal, ...]
    line_taxable_and_rates: tuple[tuple[Decimal, Decimal], ...]
    supplier_state: str | None
    buyer_state: str | None


def check_tax_arithmetic(data: TaxInputs, tolerance: Decimal = Decimal("1.00")) -> list[TaxFinding]:
    """Deterministic GST/total consistency checks. Tolerance absorbs per-line rounding."""
    findings: list[TaxFinding] = []

    if data.line_amounts and data.subtotal is not None:
        line_sum = money(sum(data.line_amounts, ZERO))
        if not within_tolerance(data.subtotal, line_sum, absolute=tolerance):
            findings.append(
                TaxFinding(
                    "line_sum_mismatch",
                    "Sum of line amounts does not equal the subtotal",
                    expected=line_sum,
                    actual=data.subtotal,
                )
            )

    components = [c for c in (data.cgst, data.sgst, data.igst) if c is not None]
    if components and data.tax_total is not None:
        component_sum = money(sum(components, ZERO))
        if not within_tolerance(data.tax_total, component_sum, absolute=tolerance):
            findings.append(
                TaxFinding(
                    "tax_components_mismatch",
                    "CGST + SGST + IGST does not equal the total tax",
                    expected=component_sum,
                    actual=data.tax_total,
                )
            )

    tax = (
        data.tax_total
        if data.tax_total is not None
        else (money(sum(components, ZERO)) if components else None)
    )
    if data.subtotal is not None and tax is not None and data.total is not None:
        expected_total = money(data.subtotal + tax)
        if not within_tolerance(data.total, expected_total, absolute=tolerance):
            findings.append(
                TaxFinding(
                    "total_mismatch",
                    "Subtotal + tax does not equal the invoice total",
                    expected=expected_total,
                    actual=data.total,
                )
            )

    if (
        data.cgst is not None
        and data.sgst is not None
        and not within_tolerance(data.cgst, data.sgst, absolute=tolerance)
    ):
        findings.append(
            TaxFinding(
                "cgst_sgst_unequal",
                "CGST and SGST should be equal for intra-state supply",
                expected=data.cgst,
                actual=data.sgst,
            )
        )

    has_cgst_sgst = bool((data.cgst or ZERO) > ZERO or (data.sgst or ZERO) > ZERO)
    has_igst = bool((data.igst or ZERO) > ZERO)
    if has_cgst_sgst and has_igst:
        findings.append(TaxFinding("mixed_gst_types", "Invoice charges both IGST and CGST/SGST"))
    if data.supplier_state and data.buyer_state:
        intra_state = data.supplier_state == data.buyer_state
        if intra_state and has_igst:
            findings.append(
                TaxFinding(
                    "igst_on_intra_state",
                    "IGST charged although supplier and buyer are in the same state",
                )
            )
        if not intra_state and has_cgst_sgst:
            findings.append(
                TaxFinding(
                    "cgst_sgst_on_inter_state",
                    "CGST/SGST charged although supplier and buyer are in different states",
                )
            )

    if data.line_taxable_and_rates and tax is not None:
        expected_tax = money(
            sum((percent_of(amount, rate) for amount, rate in data.line_taxable_and_rates), ZERO)
        )
        if not within_tolerance(tax, expected_tax, absolute=tolerance):
            findings.append(
                TaxFinding(
                    "tax_rate_mismatch",
                    "Tax charged does not match line amounts x stated GST rates",
                    expected=expected_tax,
                    actual=tax,
                )
            )
        for _, rate in data.line_taxable_and_rates:
            if rate not in STANDARD_GST_RATES:
                findings.append(
                    TaxFinding("non_standard_rate", f"Non-standard GST rate {rate}% on a line")
                )
                break
    return findings
