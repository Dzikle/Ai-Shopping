"""Shared normalization and HTML table utilities for source adapters.

Standard library only - no third-party dependencies.
Supports both Vero static HTML conventions and the shared *.proverkanaceni.mk
statutory price-check platform (Stokomak, Zito, etc.).
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from html.parser import HTMLParser
from zoneinfo import ZoneInfo

try:
    _SKOPJE = ZoneInfo("Europe/Skopje")
    _TZ_SOURCE = "zoneinfo:Europe/Skopje"
except Exception:  # pragma: no cover - tzdata missing in minimal images
    _SKOPJE = timezone(timedelta(hours=1), "CET")
    _TZ_SOURCE = "fallback:UTC+01:00"

CURRENCY = "MKD"

_SPACES_RE = re.compile(r"[ \t]+")
_ALL_WS_RE = re.compile(r"\s+")
_UNIT_RE = re.compile(r"^([0-9][0-9.,]*)\s*(.*)$")
_RANGE_SEP = re.compile(r"\s*(?:[-–]|\bдо\b)\s*", re.IGNORECASE)
_PCT_RE = re.compile(r"([0-9][0-9.,]*)\s*%")
_KNOWN_AVAILABILITY = {"да": "in_stock", "не": "out_of_stock"}

# Size patterns: multipack e.g. 4x500мл, 6*0.5л, 4Х0,5Л; or single e.g. 500гр., 0,75л, 1.5кгр
_MULTIPACK_SIZE_RE = re.compile(
    r"(?<![0-9A-Za-zА-Яа-я])(\d{1,2})\s*[xхXХ*]\s*(\d+(?:[.,]\d+)?)\s*"
    r"(кг|кгр|kg|гр|г|g|gr|мл|ml|л|l)\b\.?",
    re.IGNORECASE,
)
_SINGLE_SIZE_RE = re.compile(
    r"(?<![0-9A-Za-zА-Яа-я])(\d+(?:[.,]\d+)?)\s*"
    r"(кг|кгр|kg|гр|г|g|gr|мл|ml|л|l)(?![A-Za-zА-Яа-я])\.?",
    re.IGNORECASE,
)


def parse_price(text: str | None) -> Decimal | None:
    """Parse '879', '879.50', '71 ден.', '1.255,50 ден' style values to Decimal or None."""
    raw = _ALL_WS_RE.sub(" ", (text or "").strip())
    m = re.match(r"([0-9][0-9.,]*)", raw)
    if not m:
        return None
    num = m.group(1).strip(".,")
    if not num:
        return None
    if "," in num and "." in num:
        num = num.replace(".", "").replace(",", ".")
    elif "," in num:
        num = num.replace(",", ".")
    try:
        return Decimal(num)
    except InvalidOperation:
        return None


def parse_pct(text: str | None) -> Decimal | None:
    """Parse '10 %' or '249 ден. Попуст:31%' style percentages to Decimal or None."""
    if not text:
        return None
    raw = _ALL_WS_RE.sub(" ", text.strip())
    if "%" in raw:
        m = _PCT_RE.search(raw)
        if not m:
            return None
        return parse_price(m.group(1))
    return parse_price(raw)


def parse_promo_cell(text: str | None) -> tuple[Decimal | None, Decimal | None]:
    """Parse combined promo cell '249 ден.\\n Попуст:31%' -> (discount_price, discount_pct)."""
    if not text:
        return None, None
    raw = _ALL_WS_RE.sub(" ", text.strip())
    if not raw:
        return None, None
    discount_price = parse_price(raw)
    discount_pct = parse_pct(raw) if "%" in raw else None
    return discount_price, discount_pct


def parse_unit_price(text: str | None) -> tuple[Decimal | None, str | None]:
    """Parse unit price strings from Vero or proverkanaceni.mk:
    - '1255 ден/парче'      -> (Decimal('1255'), 'ден/парче')
    - '1кгр = 142.00 ден.'  -> (Decimal('142.00'), '1кгр')
    - '100gr = 43.75 ден.'  -> (Decimal('43.75'), '100gr')
    """
    raw = _ALL_WS_RE.sub(" ", (text or "").strip())
    if not raw:
        return None, None
    if "=" in raw:
        left, right = raw.split("=", 1)
        basis = left.strip() or None
        value = parse_price(right.strip())
        if value is None:
            return None, None
        return value, basis
    m = _UNIT_RE.match(raw)
    if not m:
        return None, None
    value = parse_price(m.group(1))
    label = m.group(2).strip() or None
    return value, label


def _parse_single_date(token: str):
    token = token.strip().rstrip(".")
    for fmt in ("%d/%m/%Y", "%d.%m.%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(token, fmt).date()
        except ValueError:
            continue
    return None


def parse_date_range(text: str | None):
    """Parse '28/10/2026 - 10/11/2026' or '18.02.2026 до 03.03.2026' -> (date, date) or (None, None)."""
    if not text:
        return None, None
    cleaned = _ALL_WS_RE.sub(" ", text.strip())
    parts = _RANGE_SEP.split(cleaned)
    if len(parts) != 2:
        return None, None
    start = _parse_single_date(parts[0])
    end = _parse_single_date(parts[1])
    if start is None or end is None:
        return None, None
    return start, end


def parse_updated(text: str | None):
    """Parse 'Последно ажурирање: 28/10/2026 8:02' or
    'Датум и време на последно ажурирање на цените: 28/10/2026 20:55' -> tz-aware datetime or None."""
    if not text:
        return None
    m = re.search(r"(\d{2}[/.]\d{2}[/.]\d{4})\s+(\d{1,2}):(\d{2})", text)
    if not m:
        return None
    d_str = m.group(1).replace(".", "/")
    dt = datetime.strptime(f"{d_str} {m.group(2)}:{m.group(3)}", "%d/%m/%Y %H:%M")
    return dt.replace(tzinfo=_SKOPJE)


def parse_availability(text: str | None) -> str:
    """Map 'Да' -> 'in_stock', 'Не' -> 'out_of_stock', other -> 'unknown'."""
    key = (text or "").strip().lower()
    return _KNOWN_AVAILABILITY.get(key, "unknown")


def normalize_name(text: str | None) -> str:
    """NFC-normalizes, collapses whitespace, uppercases, trims.
    Deliberately does NOT unify Cyrillic/Latin homoglyphs (ADR-0003).
    """
    raw = unicodedata.normalize("NFC", text or "")
    raw = raw.replace("\u00a0", " ").replace("\u2009", " ")
    return _ALL_WS_RE.sub(" ", raw).strip().upper()


def derive_sku_key(name: str | None, category: str | None) -> str:
    """Deterministic retailer-scoped product key: sha256 of normalized name + category."""
    basis = "\x1f".join([normalize_name(name), normalize_name(category or "")])
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()


def _canonical_unit_and_amount(num_str: str, unit_raw: str) -> tuple[Decimal, str] | None:
    val_str = num_str.replace(",", ".")
    # Handle 1.250гр where dot is thousands separator before гр/мл
    u = unit_raw.lower().rstrip(".")
    if u in ("гр", "г", "g", "gr", "мл", "ml") and re.fullmatch(r"\d+\.\d{3}", val_str):
        val_str = val_str.replace(".", "")
    try:
        val = Decimal(val_str)
    except InvalidOperation:
        return None
    if val <= 0:
        return None
    if u in ("кг", "кгр", "kg"):
        return (val * Decimal(1000)).normalize(), "g"
    if u in ("гр", "г", "g", "gr"):
        return val.normalize(), "g"
    if u in ("л", "l"):
        return (val * Decimal(1000)).normalize(), "ml"
    if u in ("мл", "ml"):
        return val.normalize(), "ml"
    return None


def _fmt_dec(d: Decimal) -> str:
    if d == d.to_integral():
        return str(int(d))
    return format(d.normalize(), "f")


def parse_declared_size(text: str | None) -> dict | None:
    """Extract declared pack/unit size from a listing title.

    Returns dict {
        'quantity_value': Decimal (per-unit in canonical g/ml),
        'quantity_unit': 'g' | 'ml',
        'pack_count': int,
        'normalized_size': str (e.g. '500g', '700ml', '4x500ml')
    } or None if no unambiguous size token is present.
    """
    if not text:
        return None
    m_multi = _MULTIPACK_SIZE_RE.search(text)
    if m_multi:
        pack_count = int(m_multi.group(1))
        parsed = _canonical_unit_and_amount(m_multi.group(2), m_multi.group(3))
        if parsed and pack_count > 0:
            qty_val, qty_unit = parsed
            norm = f"{pack_count}x{_fmt_dec(qty_val)}{qty_unit}" if pack_count > 1 else f"{_fmt_dec(qty_val)}{qty_unit}"
            return {
                "quantity_value": qty_val,
                "quantity_unit": qty_unit,
                "pack_count": pack_count,
                "normalized_size": norm,
            }
    m_single = _SINGLE_SIZE_RE.search(text)
    if m_single:
        parsed = _canonical_unit_and_amount(m_single.group(1), m_single.group(2))
        if parsed:
            qty_val, qty_unit = parsed
            norm = f"{_fmt_dec(qty_val)}{qty_unit}"
            return {
                "quantity_value": qty_val,
                "quantity_unit": qty_unit,
                "pack_count": 1,
                "normalized_size": norm,
            }
    return None


class RowParser(HTMLParser):
    """Collects <tr>/<td> structure with per-cell text and hrefs,
    tolerating malformed markup (missing </tr>, <b> spanning cells, <br>,
    <font> wrappers). Cell text keeps '\\n' as segment separators."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.rows: list[list[dict]] = []
        self._row: list[dict] | None = None
        self._cell: dict | None = None

    def _flush_cell(self):
        if self._cell is not None:
            self._cell["text"] = _SPACES_RE.sub(" ", self._cell["text"]).strip()
            if self._row is None:
                self._row = []
            self._row.append(self._cell)
            self._cell = None

    def _flush_row(self):
        self._flush_cell()
        if self._row is not None:
            self.rows.append(self._row)
            self._row = None

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self._flush_row()
            self._row = []
        elif tag in ("td", "th"):
            self._flush_cell()
            self._cell = {"text": "", "hrefs": []}
        elif tag == "br" and self._cell is not None:
            self._cell["text"] += "\n"
        elif tag == "a" and self._cell is not None:
            href = dict(attrs).get("href")
            if href:
                self._cell["hrefs"].append(href)

    def handle_endtag(self, tag):
        if tag in ("td", "th"):
            self._flush_cell()
        elif tag == "tr":
            self._flush_row()

    def handle_data(self, data):
        if self._cell is not None:
            self._cell["text"] += data

    def close(self):
        self._flush_row()
        super().close()


def parse_rows(html_text: str) -> list[list[dict]]:
    """Split an HTML page into rows: list of cells, each {'text', 'hrefs'}."""
    parser = RowParser()
    parser.feed(html_text)
    parser.close()
    return parser.rows


def content_hash_sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def url_hash_sha256(url: str) -> str:
    return hashlib.sha256(url.encode("utf-8")).hexdigest()
