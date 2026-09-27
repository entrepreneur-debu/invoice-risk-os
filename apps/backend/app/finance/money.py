"""Money and quantity arithmetic with `Decimal`.

All financial values are `Decimal`. Parsing accepts Indian and international digit
grouping ("1,23,456.50", "123,456.50") and a leading currency symbol. Rounding is
ROUND_HALF_UP to 2 decimal places, matching Indian GST invoicing practice.
"""

import re
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

TWO_PLACES = Decimal("0.01")
QUANTITY_PLACES = Decimal("0.001")
ZERO = Decimal("0")

_CURRENCY_PREFIX = re.compile(r"^(?:₹|rs\.?|inr|usd|\$|eur|€|£)\s*", re.IGNORECASE)
_GROUPED_NUMBER = re.compile(r"^-?\d{1,3}(?:,\d{2,3})*(?:\.\d+)?$|^-?\d+(?:\.\d+)?$")


def parse_decimal(raw: object) -> Decimal | None:
    """Parses a money/quantity value. Returns None when it is not a clean number.

    Never guesses: ambiguous strings (e.g. "12.345,67" European format, words) are None.
    """
    if raw is None or isinstance(raw, bool):
        return None
    if isinstance(raw, Decimal):
        return raw if raw.is_finite() else None
    if isinstance(raw, int):
        return Decimal(raw)
    if isinstance(raw, float):
        # Floats only arrive from JSON; go through repr to avoid binary artefacts.
        return parse_decimal(repr(raw))
    text = str(raw).strip()
    text = _CURRENCY_PREFIX.sub("", text).strip().replace(" ", "")
    if text.startswith("(") and text.endswith(")"):
        text = "-" + text[1:-1]
    if not text or not _GROUPED_NUMBER.match(text):
        return None
    try:
        value = Decimal(text.replace(",", ""))
    except InvalidOperation:
        return None
    return value if value.is_finite() else None


def money(value: Decimal) -> Decimal:
    return value.quantize(TWO_PLACES, rounding=ROUND_HALF_UP)


def quantity(value: Decimal) -> Decimal:
    return value.quantize(QUANTITY_PLACES, rounding=ROUND_HALF_UP)


def percent_of(amount: Decimal, rate_percent: Decimal) -> Decimal:
    return money(amount * rate_percent / Decimal(100))


def within_tolerance(
    actual: Decimal, expected: Decimal, *, absolute: Decimal = ZERO, percent: Decimal = ZERO
) -> bool:
    """True when |actual - expected| <= max(absolute, percent% of |expected|)."""
    allowed = max(absolute, abs(expected) * percent / Decimal(100))
    return abs(actual - expected) <= allowed


def percent_change(new: Decimal, old: Decimal) -> Decimal | None:
    if old == ZERO:
        return None
    return ((new - old) / old * Decimal(100)).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)


def format_inr(value: Decimal) -> str:
    """Formats with Indian digit grouping, e.g. 1234567.5 -> '₹12,34,567.50'."""
    sign = "-" if value < 0 else ""
    whole, _, fraction = f"{abs(money(value)):.2f}".partition(".")
    if len(whole) > 3:
        head, tail = whole[:-3], whole[-3:]
        groups: list[str] = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        whole = ",".join([*groups, tail])
    return f"{sign}₹{whole}.{fraction}"
