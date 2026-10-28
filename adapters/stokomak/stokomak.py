"""Parser and record normalizer for the shared *.proverkanaceni.mk platform
(Stokomak, Zito, and sibling statutory price-check sites).

Standard library only - no third-party dependencies.
"""

from __future__ import annotations

import re
import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import parse_qs, urlparse

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from adapters.common import (
    CURRENCY,
    _ALL_WS_RE,
    _SKOPJE,
    _TZ_SOURCE,
    content_hash_sha256,
    derive_sku_key,
    normalize_name,
    parse_availability,
    parse_date_range,
    parse_pct,
    parse_price,
    parse_promo_cell,
    parse_rows,
    parse_unit_price,
    parse_updated,
    url_hash_sha256,
)

RETAILER_URLS = {
    "stokomak": "https://stokomak.proverkanaceni.mk",
    "zito": "https://zito.proverkanaceni.mk",
}
DEFAULT_PER_PAGE = 100

_FIXTURE_FILE_RE = re.compile(r"^(\d+)_(\d+)\.(?:html|htm)$", re.IGNORECASE)
_TOTAL_RE = re.compile(r"Прикажи\s+(\d+)\s*-\s*(\d+)\s+од\s+(\d+)\s+артикли")
_UPDATED_BLOCK_RE = re.compile(
    r"Датум и време на последно ажурирање на цените:\s*(\d{2}[/.]\d{2}[/.]\d{4}\s+\d{1,2}:\d{2})"
)
_PAGE_HREF_RE = re.compile(r"[?&]page=(\d+)")
_LEADING_NUM_RE = re.compile(r"^\d+\s+")
_DASH_CITY_RE = re.compile(r"\s+[-–]\s+")


class _SelectorParser(HTMLParser):
    """Extracts <option> entries from <select name='org'>."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self._in_org_select = False
        self._cur_option: dict | None = None
        self.options: list[dict] = []

    def handle_starttag(self, tag, attrs):
        attr_map = dict(attrs)
        if tag == "select" and attr_map.get("name") == "org":
            self._in_org_select = True
        elif tag == "option" and self._in_org_select:
            val = (attr_map.get("value") or "").strip()
            selected = "selected" in attr_map
            self._cur_option = {"value": val, "text": "", "selected": selected}

    def handle_endtag(self, tag):
        if tag == "option" and self._cur_option is not None:
            self._cur_option["text"] = _ALL_WS_RE.sub(" ", self._cur_option["text"]).strip()
            if self._cur_option["value"]:
                self.options.append(self._cur_option)
            self._cur_option = None
        elif tag == "select" and self._in_org_select:
            self._in_org_select = False

    def handle_data(self, data):
        if self._cur_option is not None:
            self._cur_option["text"] += data


class _PaginationParser(HTMLParser):
    """Extracts pagination links from <ul class='pagination'>."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self._in_pagination = False
        self._li_active = False
        self._cur_href: str | None = None
        self._cur_text = ""
        self.items: list[dict] = []

    def handle_starttag(self, tag, attrs):
        attr_map = dict(attrs)
        cls = attr_map.get("class") or ""
        if tag == "ul" and "pagination" in cls:
            self._in_pagination = True
        elif self._in_pagination and tag == "li":
            self._li_active = "active" in cls
        elif self._in_pagination and tag == "a":
            self._cur_href = attr_map.get("href")
            self._cur_text = ""

    def handle_endtag(self, tag):
        if self._in_pagination and tag == "a" and self._cur_href is not None:
            self.items.append(
                {
                    "href": self._cur_href,
                    "text": _ALL_WS_RE.sub(" ", self._cur_text).strip(),
                    "active": self._li_active,
                }
            )
            self._cur_href = None
        elif self._in_pagination and tag == "li":
            self._li_active = False
        elif self._in_pagination and tag == "ul":
            self._in_pagination = False

    def handle_data(self, data):
        if self._cur_href is not None:
            self._cur_text += data


def _infer_city(store_label: str) -> str | None:
    """Infer city when formatted like '2 Трговски - Велес' or 'КУМАНОВО 2'."""
    parts = _DASH_CITY_RE.split(store_label)
    if len(parts) >= 2 and parts[-1].strip():
        return parts[-1].strip()
    return None


def parse_index(html_text: str) -> list[dict]:
    """Parse selector <select name='org'> -> list of {external_key, name, address, city, selected}."""
    p = _SelectorParser()
    p.feed(html_text)
    p.close()
    stores = []
    seen = set()
    for opt in p.options:
        ext = opt["value"]
        if ext in seen:
            continue
        seen.add(ext)
        name = opt["text"]
        city = _infer_city(name)
        stores.append(
            {
                "external_key": ext,
                "name": name,
                "address": None,
                "city": city,
                "selected": opt["selected"],
            }
        )
    return stores


def build_page_url(base_url: str, org: str | int, page: int = 1, per_page: int = DEFAULT_PER_PAGE) -> str:
    base = base_url.rstrip("/")
    return f"{base}/?org={org}&perPage={per_page}&page={page}"


def parse_page(html_text: str, url: str | None = None):
    """Parse one proverkanaceni.mk store price page (6-col standard and 9-col promo rows).

    Returns (records, info).
    """
    info = {
        "store_external_key": None,
        "store_name": None,
        "published_ts": None,
        "total_articles": None,
        "current_page": 1,
        "next_page_url": None,
        "prev_page_url": None,
        "max_page": None,
        "rows_seen": 0,
        "rows_skipped": 0,
        "promo_rows_seen": 0,
        "header_present": False,
        "empty_notice": False,
    }

    if url:
        parsed = urlparse(url)
        qs = parse_qs(parsed.query)
        if "org" in qs and qs["org"]:
            info["store_external_key"] = qs["org"][0]
        if "page" in qs and qs["page"]:
            try:
                info["current_page"] = int(qs["page"][0])
            except ValueError:
                pass

    stores = parse_index(html_text)
    for st in stores:
        if st.get("selected"):
            if not info["store_external_key"]:
                info["store_external_key"] = st["external_key"]
            info["store_name"] = st["name"]
            break
    if info["store_external_key"] and not info["store_name"]:
        for st in stores:
            if st["external_key"] == info["store_external_key"]:
                info["store_name"] = st["name"]
                break

    m_upd = _UPDATED_BLOCK_RE.search(html_text)
    if m_upd:
        info["published_ts"] = parse_updated(m_upd.group(0))
    else:
        info["published_ts"] = parse_updated(html_text)

    m_tot = _TOTAL_RE.search(html_text)
    if m_tot:
        info["total_articles"] = int(m_tot.group(3))

    pag = _PaginationParser()
    pag.feed(html_text)
    pag.close()
    page_nums = []
    for item in pag.items:
        m_p = _PAGE_HREF_RE.search(item["href"])
        pnum = int(m_p.group(1)) if m_p else None
        if item["active"] and pnum is not None:
            info["current_page"] = pnum
        if pnum is not None:
            page_nums.append((pnum, item["href"], item["text"]))
    if page_nums:
        info["max_page"] = max(p for p, _, _ in page_nums)
        cur = info["current_page"]
        for pnum, href, txt in page_nums:
            if txt in ("»", "&raquo;") or (pnum == cur + 1 and info["next_page_url"] is None):
                info["next_page_url"] = href
            if txt in ("«", "&laquo;") or (pnum == cur - 1 and info["prev_page_url"] is None):
                info["prev_page_url"] = href

    records = []
    for row in parse_rows(html_text):
        ncells = len(row)
        joined = " ".join(c["text"] for c in row)

        if "Назив на стока" in joined:
            info["header_present"] = True
            continue
        if ncells == 3 and "Цена со попуст" in joined:
            continue
        if "Нема податоци" in joined:
            info["empty_notice"] = True
            continue

        if ncells not in (6, 9):
            continue

        info["rows_seen"] += 1
        name = row[0]["text"]
        price = parse_price(row[1]["text"])
        unit_price, unit_label = parse_unit_price(row[2]["text"])
        category = row[3]["text"] or None
        availability = parse_availability(row[4]["text"])
        regular_price = parse_price(row[5]["text"])

        discount_price = None
        discount_pct = None
        promo_type = None
        promo_start = None
        promo_end = None

        if ncells == 9:
            info["promo_rows_seen"] += 1
            discount_price, discount_pct = parse_promo_cell(row[6]["text"])
            promo_type = row[7]["text"] or None
            promo_start, promo_end = parse_date_range(row[8]["text"])

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
                "published_ts": None,
                "source_url": url,
            }
        )

    published = info["published_ts"]
    if published is not None:
        published_iso = published.isoformat()
        for rec in records:
            rec["published_ts"] = published_iso

    return records, info
