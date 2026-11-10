"""Direct Python port of mobile/lib/utils/formatters.dart (M12).

Deterministic Macedonian formatting that does not depend on runtime locale
data. Tests pin the exact outputs so the web tier and the Flutter app render
identical values. All money/quantity math stays server-side; these helpers
format server-provided numbers only.
"""

import datetime as dt
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
