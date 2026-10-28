"""Vero price-list HTML parser and record normalizer.

Parses the static price-list pages published at https://pricelist.vero.com.mk/
(page format validated 2026-10-28, see docs/research/retailer-sources.md and
tests/fixtures/vero/). Standard library only - no third-party dependencies.

Contract (see docs/contracts/vero-adapter-contract.md):
- parse_page()   -> (records, info) for one {storeId}_{page}.html document
- parse_index()  -> list of store descriptors for index.html
- normalization helpers shared with the CLI record builder
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

BASE_URL = "https://pricelist.vero.com.mk"

# Prices are published in MKD (denari); the pages do not repeat the currency.
CURRENCY = "MKD"

_PAGE_FILE_RE = re.compile(r"(\d+)_(\d+)\.(?:html|htm)$")
_STORE_LINK_RE = re.compile(r"(\d+)_1\.(?:html|htm)$")
_DASH_RE = re.compile(r"\s+[–-]\s*")
_SPACES_RE = re.compile(r"[ \t]+")
_ALL_WS_RE = re.compile(r"\s+")
_UNIT_RE = re.compile(r"^([0-9][0-9.,]*)\s*(.*)$")
_RANGE_SEP = re.compile(r"\s*[-–]\s*")
_KNOWN_AVAILABILITY = {"Да": "in_stock", "Не": "out_of_stock"}


def parse_price(text):
    """Parse '879', '879.50', '1.255,50 ден' style values to Decimal or None."""
    raw = _ALL_WS_RE.sub(" ", (text or "").strip())
    m = re.match(r"([0-9][0-9.,]*)", raw)
    if not m:
        return None
    num = m.group(1).strip(".,")
    if "," in num and "." in num:
        num = num.replace(".", "").replace(",", ".")
    elif "," in num:
        num = num.replace(",", ".")
    try:
        return Decimal(num)
    except InvalidOperation:
        return None


def parse_pct(text):
    """Parse '10 %' style percentages to Decimal or None."""
    return parse_price((text or "").replace("%", "").strip())


def parse_unit_price(text):
    """Parse '1255 ден/парче' -> (Decimal, 'ден/парче') or (None, None)."""
    raw = _ALL_WS_RE.sub(" ", (text or "").strip())
    m = _UNIT_RE.match(raw)
    if not m:
        return None, None
    value = parse_price(m.group(1))
    label = m.group(2).strip() or None
    return value, label


def parse_date_range(text):
    """Parse '28/10/2026 - 10/11/2026' -> (date, date) or (None, None)."""
    if not text:
        return None, None
    parts = _RANGE_SEP.split(text.strip())
    if len(parts) != 2:
        return None, None
    try:
        start = datetime.strptime(parts[0], "%d/%m/%Y").date()
        end = datetime.strptime(parts[1], "%d/%m/%Y").date()
    except ValueError:
        return None, None
    return start, end


def parse_updated(text):
    """Parse 'Последно ажурирање: 28/10/2026 8:02' -> tz-aware datetime or None."""
    if not text:
        return None
    m = re.search(r"(\d{2}/\d{2}/\d{4})\s+(\d{1,2}):(\d{2})", text)
    if not m:
        return None
    dt = datetime.strptime(f"{m.group(1)} {m.group(2)}:{m.group(3)}", "%d/%m/%Y %H:%M")
    return dt.replace(tzinfo=_SKOPJE)


def normalize_name(text):
    """Normalization for the M1 sku_key derivation.

    NFC-normalizes, collapses whitespace, uppercases, trims.
    Deliberately does NOT unify Cyrillic/Latin homoglyphs - identity
    resolution is M2 work (ADR-0003).
    """
    raw = unicodedata.normalize("NFC", text or "")
    raw = raw.replace("\u00a0", " ").replace("\u2009", " ")
    return _ALL_WS_RE.sub(" ", raw).strip().upper()


def derive_sku_key(name, category):
    """M1 product key: sha256 of normalized name + category (documented limitation)."""
    basis = "\x1f".join([normalize_name(name), normalize_name(category or "")])
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()


class _RowParser(HTMLParser):
    """Collects <tr>/<td> structure with per-cell text and first href,
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


def parse_rows(html_text):
    """Split a page into rows: list of cells, each {'text', 'href'}."""
    parser = _RowParser()
    parser.feed(html_text)
    parser.close()
    return parser.rows


def parse_page(html_text, url):
    """Parse one store price page.

    Returns (records, info); info includes store_external_key (from URL),
    published_ts, next/prev page hrefs, rows_seen, rows_skipped, header flag.
    """
    info = {
        "store_external_key": None,
        "store_name_h1": None,
        "published_ts": None,
        "next_page_url": None,
        "prev_page_url": None,
        "rows_seen": 0,
        "rows_skipped": 0,
        "header_present": False,
        "header_discount_has_ddv": None,
    }
    if url:
        m = _PAGE_FILE_RE.search(url)
        if m:
            info["store_external_key"] = m.group(1)

    records = []
    for row in parse_rows(html_text):
        hrefs = [h for c in row for h in c["hrefs"]]
        joined = " ".join(c["text"] for c in row)
        ncells = len(row)

        if "ажурирање" in joined:
            info["published_ts"] = parse_updated(joined)
            continue

        if "Назив на стока" in joined:
            info["header_present"] = True
            info["header_discount_has_ddv"] = "со ДДВ" in row[6]["text"] if ncells > 6 else None
            continue

        page_m = re.search(r"Страна\s+(\d+)", joined)
        if page_m and ncells <= 3:
            if ncells >= 2 and row[0]["text"]:
                info["store_name_h1"] = row[0]["text"]
            cur = int(page_m.group(1))
            for href in hrefs:
                pm = _PAGE_FILE_RE.search(href) if href else None
                if not pm:
                    continue
                num = int(pm.group(2))
                if num > cur and info["next_page_url"] is None:
                    info["next_page_url"] = href
                elif num < cur and info["prev_page_url"] is None:
                    info["prev_page_url"] = href
            continue

        if ncells != 10:
            continue
        info["rows_seen"] += 1

        name = row[0]["text"]
        price = parse_price(row[1]["text"])
        unit_price, unit_label = parse_unit_price(row[2]["text"])
        availability = _KNOWN_AVAILABILITY.get(row[3]["text"].strip(), "unknown")
        category = row[4]["text"] or None
        regular_price = parse_price(row[5]["text"])
        discount_price = parse_price(row[6]["text"])
        discount_pct = parse_pct(row[7]["text"])
        promo_type = row[8]["text"] or None
        promo_start, promo_end = parse_date_range(row[9]["text"])

        if not name or price is None or price <= 0:
            info["rows_skipped"] += 1
            continue

        records.append(
            {
                "store_external_key": info["store_external_key"],
                "sku_key": derive_sku_key(name, category),
                "listing_name": _ALL_WS_RE.sub(" ", name).strip(),
                "category": category,
                "currency": CURRENCY,
                "price_current": str(price),
                "unit_price": str(unit_price) if unit_price is not None else None,
                "unit_label": unit_label,
                "regular_price": str(regular_price) if regular_price is not None else None,
                "discount_price": str(discount_price) if discount_price is not None else None,
                "discount_pct": str(discount_pct) if discount_pct is not None else None,
                "promo_type": promo_type,
                "promo_starts_on": promo_start.isoformat() if promo_start else None,
                "promo_ends_on": promo_end.isoformat() if promo_end else None,
                "availability": availability,
                "published_ts": None,  # backfilled after loop
                "source_url": url,
            }
        )

    published = info["published_ts"]
    if published is not None:
        published_iso = published.isoformat()
        for rec in records:
            rec["published_ts"] = published_iso
    return records, info


def parse_index(html_text):
    """Parse index.html -> list of {external_key, name, address, city}."""
    stores = []
    seen = set()
    for row in parse_rows(html_text):
        for cell in row:
            hrefs = [h for h in cell["hrefs"] if _STORE_LINK_RE.search(h)]
            if not hrefs:
                continue
            m = _STORE_LINK_RE.search(hrefs[0])
            ext = m.group(1)
            if ext in seen:
                continue
            lines = [ln.strip() for ln in cell["text"].split("\n")]
            lines = [ln for ln in lines if ln]
            if len(lines) < 2:
                continue
            nm = re.match(r"(ВЕРО|ЏАМБО)\s*(\d+)$", lines[0])
            if not nm:
                continue
            name = f"{nm.group(1)} {nm.group(2)}"
            address = " ".join(lines[1:])
            parts = _DASH_RE.split(address)
            city = parts[-1].strip() if len(parts) >= 2 and parts[-1] else None
            seen.add(ext)
            stores.append(
                {"external_key": ext, "name": name, "address": address, "city": city}
            )
    return stores


def content_hash_sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def url_hash_sha256(url: str) -> str:
    return hashlib.sha256(url.encode("utf-8")).hexdigest()
