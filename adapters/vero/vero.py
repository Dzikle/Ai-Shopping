"""Vero price-list HTML parser and record normalizer.

Parses the static price-list pages published at https://pricelist.vero.com.mk/
(page format validated 2026-10-28, see docs/research/retailer-sources.md and
tests/fixtures/vero/). Standard library only - no third-party dependencies.

Contract (see docs/contracts/vero-adapter-contract.md):
- parse_page()   -> (records, info) for one {storeId}_{page}.html document
- parse_index()  -> list of store descriptors for index.html
- normalization helpers re-exported from adapters.common
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from adapters.common import (
    CURRENCY,
    RowParser as _RowParser,
    _ALL_WS_RE,
    _SKOPJE,
    _SPACES_RE,
    _TZ_SOURCE,
    content_hash_sha256,
    derive_sku_key,
    normalize_name,
    parse_availability,
    parse_date_range,
    parse_pct,
    parse_price,
    parse_rows,
    parse_unit_price,
    parse_updated,
    url_hash_sha256,
)

BASE_URL = "https://pricelist.vero.com.mk"

_PAGE_FILE_RE = re.compile(r"(\d+)_(\d+)\.(?:html|htm)$")
_STORE_LINK_RE = re.compile(r"(\d+)_1\.(?:html|htm)$")
_DASH_RE = re.compile(r"\s+[–-]\s*")


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
        availability = parse_availability(row[3]["text"])
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
