"""Direct Python port of mobile/lib/utils/formatters.dart (M12).

Deterministic Macedonian formatting that does not depend on runtime locale
data. Tests pin the exact outputs so the web tier and the Flutter app render
identical values. All money/quantity math stays server-side; these helpers
format server-provided numbers only.
"""

import datetime as dt
import re
from decimal import Decimal, InvalidOperation


def _group_integer(digits: str) -> str:
    parts = []
    for i, ch in enumerate(digits):
        if i > 0 and (len(digits) - i) % 3 == 0:
            parts.append(".")
        parts.append(ch)
    return "".join(parts)


def format_number(value, decimals: int = 2) -> str:
    text = f"{Decimal(str(value)):.{decimals}f}"
    negative = text.startswith("-")
    unsigned = text[1:] if negative else text
    whole, _, fraction = unsigned.partition(".")
    grouped = _group_integer(whole)
    body = f"{grouped},{fraction}" if fraction else grouped
    return f"-{body}" if negative else body


def format_mkd(value) -> str:
    return f"{format_number(value, decimals=2)} \u0434\u0435\u043d."


def format_quantity(value) -> str:
    dec = Decimal(str(value))
    if dec == dec.to_integral_value():
        return format_number(dec, decimals=0)
    text = f"{dec:.3f}".rstrip("0").rstrip(".")
    decimals = len(text.split(".")[1]) if "." in text else 0
    return format_number(Decimal(text), decimals=decimals)


def _two(value: int) -> str:
    return f"{value:02d}"


def format_date(value) -> str:
    """ISO instant/date string -> `dd.mm.yyyy` (UTC date part); None -> en dash."""
    if value is None or (isinstance(value, str) and not value.strip()):
        return "\u2013"
    if isinstance(value, dt.datetime):
        stamp = value
    else:
        text = str(value).replace("Z", "+00:00")
        try:
            stamp = dt.datetime.fromisoformat(text)
        except ValueError:
            return "\u2013"
    return f"{_two(stamp.day)}.{_two(stamp.month)}.{stamp.year}"


def format_datetime(value) -> str:
    """ISO instant string -> `dd.mm.yyyy hh:mm` (UTC); None -> en dash."""
    if value is None or (isinstance(value, str) and not value.strip()):
        return "\u2013"
    if isinstance(value, dt.datetime):
        stamp = value
    else:
        text = str(value).replace("Z", "+00:00")
        try:
            stamp = dt.datetime.fromisoformat(text)
        except ValueError:
            return "\u2013"
    return f"{format_date(stamp)} {_two(stamp.hour)}:{_two(stamp.minute)}"


def mk_noun(value, singular: str, plural: str) -> str:
    """Pick the Macedonian noun form for a count (1 -> singular, 11 excepted)."""
    try:
        n = int(value or 0)
    except (TypeError, ValueError):
        return plural
    return singular if n % 10 == 1 and n % 100 != 11 else plural


def format_price_range(min_value, max_value) -> str:
    """`85,00–99,00 ден.`; a single value renders once."""
    if min_value is None and max_value is None:
        return "\u2013"
    if min_value is not None and max_value is not None and _same(min_value, max_value):
        return format_mkd(min_value)
    if min_value is None:
        return format_mkd(max_value)
    if max_value is None:
        return format_mkd(min_value)
    return f"{format_number(min_value)}\u2013{format_number(max_value)} \u0434\u0435\u043d."


def _same(a, b) -> bool:
    try:
        return Decimal(str(a)) == Decimal(str(b))
    except (InvalidOperation, ValueError):
        return str(a) == str(b)


# Unit-price labels from retailer feeds are untrusted text. A 64 MKD label
# referring to "1 гр" for a 32 MKD / 500g package is arithmetically
# inconsistent, and must not be shown as "64 ден./гр" or silently re-labelled.
_SIZE_RE = re.compile(r"(?:(\d+)x)?(\d+(?:[.,]\d+)?)(g|ml)$", re.IGNORECASE)
_UNIT_BASIS_RE = re.compile(
    r"(?:(\d+(?:[.,]\d+)?)\s*)?(кгр|кг|kg|гр|gr|г|g|мл|ml|л|l)\.?$",
    re.IGNORECASE,
)


def _unit_basis(label: str):
    """Return (denominator in g/ml, base unit, display label) or None."""
    basis = label.strip().lower().replace("\u00a0", " ")
    # Retailers also publish variants such as "ден/кг" or "ден/парче".
    if basis.startswith("ден/"):
        basis = basis[4:].strip()
    if basis in {"парче", "парчe", "бр", "бр.", "пар"}:
        return Decimal(1), "piece", "парче"
    match = _UNIT_BASIS_RE.fullmatch(basis)
    if match is None:
        return None
    amount = Decimal((match.group(1) or "1").replace(",", "."))
    if amount <= 0:
        return None
    unit = match.group(2).lower()
    if unit in {"кг", "кгр", "kg"}:
        quantity, base_unit, label_unit = amount * 1000, "g", "кг"
    elif unit in {"гр", "gr", "г", "g"}:
        quantity, base_unit, label_unit = amount, "g", "г"
    elif unit in {"л", "l"}:
        quantity, base_unit, label_unit = amount * 1000, "ml", "л"
    else:
        quantity, base_unit, label_unit = amount, "ml", "мл"
    display = label_unit if amount == 1 else f"{format_quantity(amount)} {label_unit}"
    return quantity, base_unit, display


def unit_price_for_offer(offer):
    """Render only a source-provided price whose denominator is credible.

    This is a validation/presentation check, NOT a source-price correction.
    Never generate a replacement unit-price amount from pack arithmetic.
    Compare against both current and regular selling price because some
    retailers publish the regular unit price during a promotion.
    """
    source_amount, source_basis = offer.get("unitPrice"), offer.get("unitLabel")
    if source_amount is None or not source_basis:
        return {"text": None, "warning": False}
    try:
        unit_price = Decimal(str(source_amount))
        if not unit_price.is_finite() or unit_price <= 0:
            return {"text": None, "warning": True}
        basis = _unit_basis(str(source_basis))
        if basis is None:
            return {"text": None, "warning": True}
        denominator, dimension, display_label = basis
        size = str(offer.get("normalizedSize") or "").strip()
        size_match = _SIZE_RE.fullmatch(size)
        prices = []
        for key in ("priceCurrent", "regularPrice"):
            if offer.get(key) is not None:
                value = Decimal(str(offer[key]))
                if value.is_finite() and value > 0:
                    prices.append(value)
        if not prices:
            return {"text": None, "warning": True}
        if dimension == "piece":
            expected = prices
        elif size_match is not None and size_match.group(3).lower() == dimension:
            pack_count = Decimal(size_match.group(1) or "1")
            pack_quantity = Decimal(size_match.group(2).replace(",", ".")) * pack_count
            if pack_quantity <= 0:
                return {"text": None, "warning": True}
            expected = [value * denominator / pack_quantity for value in prices]
        else:
            return {"text": None, "warning": True}
        # Two-decimal statutory prices/rounding, with a small relative
        # allowance; a 1000x wrong gram/kg denominator cannot pass.
        if not any(
            abs(unit_price - value) <= max(Decimal("0.05"), abs(value) * Decimal("0.02"))
            for value in expected
        ):
            return {"text": None, "warning": True}
        return {"text": f"{format_mkd(unit_price)}/{display_label}", "warning": False}
    except (InvalidOperation, ValueError, TypeError, ArithmeticError):
        return {"text": None, "warning": True}
