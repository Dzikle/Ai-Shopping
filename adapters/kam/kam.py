"""Parser and record normalizer for KAM Market (kam.com.mk) statutory
per-store PDF price lists (M9).

Standard library only - no third-party dependencies.

Source shape: one PDF per store (https://kam.com.mk/{Y}/{M}/{D}/{storeId}.pdf),
referenced from the shop directory JSON (POST /ShopsWeb/LoadShopList).

PDF format (fixed statutory sheet, %PDF-1.7, classic xref):
- one FlateDecode content stream per page; a leading cm transform, drawn
  10-line column grid and 14 horizontal rules define a 9-column table with
  a two-band header and N uniform data rows below;
- text is glyph-coded via subset TrueType fonts; /ToUnicode CMaps restore
  Cyrillic/digit text; glyphs flow with Td as RELATIVE moves per PDF spec;
- the page footnote above the grid repeats
  "Датум и време на последно ажурирање на цените: DD.MM.YYYY h:MM:SStt",
  which is the per-store published timestamp.
"""

from __future__ import annotations

import json
import re
import sys
import zlib
from datetime import datetime, timedelta, timezone
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from adapters.common import (
    CURRENCY,
    _ALL_WS_RE,
    _SKOPJE,
    content_hash_sha256,
    derive_sku_key,
    parse_availability,
    parse_date_range,
    parse_price,
    parse_pct,
    parse_promo_cell,
    parse_unit_price,
    url_hash_sha256,
)

STORES_URL = "https://kam.com.mk/ShopsWeb/LoadShopList"
BASE_URLS = {"kam": "https://kam.com.mk"}
SNAPSHOT_CONTENT_TYPE = "application/pdf"

_FIXTURE_FILE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})_(\d+)\.pdf$", re.IGNORECASE)

FOOTER_KEYWORD = "Датум"
FOOTER_DATE_RE = re.compile(r"(\d{1,2})\.(\d{1,2})\.(\d{4})")
FOOTER_TIME_RE = re.compile(r"(\d{1,2}):(\d{2}):(\d{2})\s*(AM|PM|am|pm)?")

HEADER_KEYWORDS = {
    "name": ("Назив",),
    "sale_price": ("Продажн",),
    "unit_price": ("Единичн",),
    "description": ("Опис",),
    "availability": ("Достапност",),
    "regular_price": ("Редовн",),
    "discount_price": ("Цена со попуст",),
    "promo_type": ("поттикнува",),
    "promo_note": ("Времетраење",),
}

REQUIRED_FIELDS = ("name", "sale_price", "regular_price")


class PDFError(ValueError):
    """Raised when the PDF structure itself is unusable (caller quarantines)."""


def parse_updated(footer_text: str | None):
    """Parse the statutory footnote date+time into a tz-aware datetime.

    Token positions may be scrambled across spans; date and time tokens are
    located independently and the statutory keywords must both be present.
    """
    if not footer_text or FOOTER_KEYWORD not in footer_text or "цените" not in footer_text:
        return None
    md = FOOTER_DATE_RE.search(footer_text)
    mt = FOOTER_TIME_RE.search(footer_text)
    if not md or not mt:
        return None
    hour = int(mt.group(1))
    ampm = (mt.group(4) or "").upper()
    if ampm == "AM" and hour == 12:
        hour = 0
    elif ampm == "PM" and hour != 12:
        hour += 12
    try:
        naive = datetime(
            int(md.group(3)),
            int(md.group(2)),
            int(md.group(1)),
            hour,
            int(mt.group(2)),
            int(mt.group(3)),
        )
    except ValueError:
        return None
    try:
        return naive.replace(tzinfo=_SKOPJE)
    except Exception:
        return (naive - timedelta(hours=1)).replace(tzinfo=timezone.utc)


def discover_stores(directory_json: bytes | str) -> list[dict]:
    """Parse the POST /ShopsWeb/LoadShopList JSON -> list of
    {external_key, name, address, city, latitude, longitude, price_list_path}."""
    if isinstance(directory_json, bytes):
        directory_json = directory_json.decode("utf-8-sig", errors="replace")
    entries = json.loads(directory_json)
    if not isinstance(entries, list):
        raise ValueError("unexpected KAM store directory payload (not an array)")
    stores = []
    seen = set()
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        try:
            ext = str(int(entry["Id"]))
        except (KeyError, TypeError, ValueError):
            continue
        if ext in seen:
            continue
        seen.add(ext)
        lat = lon = None
        coords = str(entry.get("Coordinates") or "")
        m = re.match(r"\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*$", coords)
        if m:
            lat, lon = m.group(1), m.group(2)
        files = entry.get("ShopFiles") if isinstance(entry.get("ShopFiles"), list) else []
        relative = None
        if files:
            rp = str(files[0].get("RelativePath") or "").strip()
            if re.fullmatch(r"\d{4}/\d{2}/\d{2}/\d+\.pdf", rp, re.IGNORECASE):
                relative = rp.lower()
        stores.append(
            {
                "external_key": ext,
                "name": (str(entry.get("Name") or "").strip() or None),
                "address": (str(entry.get("Address") or "").strip() or None),
                "city": (str(entry.get("City") or "").strip() or None),
                "latitude": lat,
                "longitude": lon,
                "price_list_path": relative,
            }
        )
    stores.sort(key=lambda s: s["external_key"])
    return stores


def build_pdf_url(base_url: str, relative_path: str) -> str:
    return f"{base_url.rstrip('/')}/{relative_path.lstrip('/')}"


# ------------------------------------------------------------------ PDF core

_OBJECT_RE = re.compile(rb"(?m)^(\d+) 0 obj\b")


def _object_map(data: bytes) -> dict[int, bytes]:
    objs: dict[int, bytes] = {}
    for m in _OBJECT_RE.finditer(data):
        num = int(m.group(1))
        start = m.end()
        end = data.find(b"endobj", start)
        if end == -1:
            continue
        objs[num] = data[start:end]
    return objs


def _inflate_stream(body: bytes) -> bytes | None:
    sm = re.search(rb"stream\r?\n", body)
    if not sm:
        return None
    raw = body[sm.end():]
    end = raw.rfind(b"endstream")
    if end != -1:
        raw = raw[:end]
    try:
        return zlib.decompress(raw)
    except zlib.error:
        return None


def _page_numbers_in_tree(objs: dict[int, bytes]) -> list[int]:
    """Enumerate page objects strictly in /Pages /Kids tree order."""
    root = None
    for num, body in objs.items():
        if re.search(rb"/Type\s*/Pages\b", body):
            pk = re.search(rb"/Parent\s+(\d+) 0 R", body)
            if not pk or int(pk.group(1)) not in objs:
                root = num
    if root is None:
        raise PDFError("page tree root not found")
    order: list[int] = []

    def walk(node: int):
        body = objs.get(node)
        if body is None:
            return
        km = re.search(rb"/Kids\s*\[(.*?)\]", body, re.DOTALL)
        if not km:
            return
        for m in re.finditer(rb"(\d+) 0 R", km.group(1)):
            child = int(m.group(1))
            cbody = objs.get(child, b"")
            if re.search(rb"/Type\s*/Pages\b", cbody):
                walk(child)
            elif re.search(rb"/Type\s*/Page\b", cbody):
                order.append(child)

    walk(root)
    return order


def _parse_cmap(text: str) -> dict[int, str]:
    """Parse a /ToUnicode CMap body into {glyph_code: unicode string}."""
    cmap: dict[int, str] = {}
    for rg in re.findall(r"beginbfrange(.*?)endbfrange", text, re.DOTALL):
        for m in re.finditer(
            r"<([0-9a-fA-F]+)>\s*<([0-9a-fA-F]+)>\s*<([0-9a-fA-F]+)>", rg
        ):
            lo, hi, base = int(m.group(1), 16), int(m.group(2), 16), int(m.group(3), 16)
            for code in range(lo, hi + 1):
                cmap[code] = chr(base + (code - lo))
    for bfc in re.findall(r"beginbfchar(.*?)endbfchar", text, re.DOTALL):
        for m in re.finditer(r"<([0-9a-fA-F]+)>\s*(?:<([0-9a-fA-F]+)>|\[(.*?)\])", bfc):
            src = int(m.group(1), 16)
            if m.group(2):
                cmap[src] = chr(int(m.group(2), 16))
            else:
                seq = re.sub(r"\s+", "", m.group(3) or "")
                chars = [
                    chr(int(seq[i:i + 4], 16))
                    for i in range(0, len(seq), 4)
                    if seq[i:i + 4] != "0000"
                ]
                cmap[src] = "".join(chars)
    return cmap


def _page_font_map(objs: dict[int, bytes], page_body: bytes) -> dict[str, int]:
    fm = re.search(rb"/Font\s*<<\s*([^>]+)>>", page_body)
    if fm:
        return {a.decode(): int(b) for a, b in re.findall(rb"/(\w+)\s+(\d+) 0 R", fm.group(1))}
    rm = re.search(rb"/Resources\s+(\d+) 0 R", page_body)
    if rm:
        res = objs.get(int(rm.group(1)))
        if res is not None:
            fm = re.search(rb"/Font\s*<<\s*([^>]+)>>", res)
            if fm:
                return {
                    a.decode(): int(b)
                    for a, b in re.findall(rb"/(\w+)\s+(\d+) 0 R", fm.group(1))
                }
    return {}


def _page_content(objs: dict[int, bytes], page_body: bytes) -> bytes:
    cm = re.search(rb"/Contents\s*\[\s*(\d+) 0 R", page_body)
    if not cm:
        cm = re.search(rb"/Contents\s+(\d+) 0 R", page_body)
    if not cm:
        raise PDFError("page without /Contents")
    content = _inflate_stream(objs.get(int(cm.group(1)), b""))
    if content is None:
        raise PDFError("page content inflate failed")
    return content


def _decode_literal(raw: str) -> bytes:
    raw = raw.replace("\\(", "(").replace("\\)", ")").replace("\\\\", "\\")
    return raw.encode("latin-1", "replace")


_OPS_RE = re.compile(
    rb"/(\w+)\s+([\d.]+)\s+Tf"
    rb"|([-\d.]+)\s+([-\d.]+)\s+Tm"
    rb"|([-\d.]+)\s+([-\d.]+)\s+Td"
    rb"|\[((?:[^\[\]\\]|\\.)*)\]\s*TJ"
    rb"|\(((?:[^()\\]|\\.)*)\)\s*Tj"
    rb"|\bBT\b|\bET\b"
)


def _extract_spans(
    content: bytes, fmap: dict[str, int], cmaps: dict[int, dict[int, str]]
) -> list[tuple[float, float, str]]:
    """Walk text ops with PDF-accurate semantics and return positioned spans.

    Each span is (x, y, text) where (x, y) is the text position at the point
    the span began flowing; words continue by glyph advance without position
    ops between Tj's, so spans are bucketed into grid cells by their anchor
    alone. Relative Td moves accumulate; a Td that looks like an in-cell line
    break (small |dx|, |dy| in [5,30]) continues the same flow and appends
    a space-joined newline marker later (words are joined with spaces).
    """
    x = y = 0.0
    cur_font: bytes | None = None
    spans: list[tuple[float, float, str]] = []
    parts: list[str] = []
    ax = ay = 0.0
    started = False

    def flush():
        nonlocal parts, started
        if parts and started:
            text = _ALL_WS_RE.sub(" ", " ".join(parts)).strip()
            if text:
                spans.append((ax, ay, text))
        parts, started = [], False

    def feed(lit: bytes, target_x: float, target_y: float):
        nonlocal ax, ay, started
        if not lit:
            return
        fobj = fmap.get((cur_font or b"").decode("latin-1"))
        table = cmaps.get(fobj, {}) if fobj is not None else {}
        s = "".join(table.get(b, "?") for b in lit)
        s = _ALL_WS_RE.sub(" ", s).strip()
        if s:
            parts.append(s)
            if not started:
                ax, ay = target_x, target_y
                started = True

    for m in _OPS_RE.finditer(content):
        if m.group(1):
            cur_font = m.group(1)
        elif m.group(3) is not None:  # Tm
            flush() if parts else None
            x, y = float(m.group(3)), float(m.group(4))
        elif m.group(5) is not None:  # Td
            dx, dy = float(m.group(5)), float(m.group(6))
            if parts and abs(dx) <= 1.5 and 5.0 <= abs(dy) <= 30.0:
                parts.append("\x01")  # soft line break within the same cell
            else:
                flush() if parts else None
            x, y = x + dx, y + dy
        elif m.group(7) is not None:  # TJ
            seg = m.group(7)
            chunks = re.findall(rb"\(((?:[^()\\]|\\.)*)\)", seg)
            feed(b"".join(_decode_literal(c.decode("latin-1")) for c in chunks), x, y)
        elif m.group(8) is not None:  # Tj
            feed(_decode_literal(m.group(8).decode("latin-1")), x, y)
        else:  # BT/ET closing tags land here only for ET-group end
            flush()
    flush()
    # soften internal markers into spaces per bucket join expectations
    return [(a, b, t.replace("\x01", " ")) for a, b, t in spans]


def _grid(content: bytes):
    """Return (vertical_xs, horizontal_ys) clustered from path operators."""
    vs: list[float] = []
    hs: list[float] = []
    for m in re.finditer(
        rb"([-\d.]+)\s+([-\d.]+)\s+m((?:\s+[-\d.]+\s+[-\d.]+\s+l)+)", content
    ):
        x0, y0 = float(m.group(1)), float(m.group(2))
        for sm in re.finditer(rb"([-\d.]+)\s+([-\d.]+)\s+l", m.group(3)):
            x1, y1 = float(sm.group(1)), float(sm.group(2))
            if abs(x0 - x1) < 0.7:
                vs.append(x0)
            elif abs(y0 - y1) < 0.7:
                hs.append(y0)
            x0, y0 = x1, y1
    for m in re.finditer(rb"([-\d.]+)\s+([-\d.]+)\s+([\d.]+)\s+([\d.]+)\s+re", content):
        x, y, w, h = (float(m.group(i)) for i in (1, 2, 3, 4))
        if 0 < abs(w) <= 0.7:
            vs.append(x)
        elif 0 < abs(h) <= 0.7:
            hs.append(y)

    def cluster(vals: list[float], tol: float = 1.0) -> list[float]:
        out: list[float] = []
        for v in sorted(vals):
            if not out or out[-1] < v - tol:
                out.append(v)
        return out

    return cluster(vs), cluster(hs)


def _pick_data_bands(hys: list[float]):
    """Choose the bottom-most run of uniform-height rule bands as data rows.

    Returns (data_bands, header_y_top) where data_bands is a list of
    (y0, y1) ordered visually top-to-bottom and header_y_top is the top
    edge of the first data row (everything above it belongs to the header
    block, including the two-band statutory header).
    """
    bands = list(zip(hys, hys[1:]))
    heights = [b[1] - b[0] for b in bands]
    n = len(bands)
    best = None
    for start in range(n):
        base = heights[start]
        if not 12.0 <= base <= 65.0:
            continue
        end = start
        while end + 1 < n:
            h = heights[end + 1]
            if not (0.75 * base <= h <= 1.35 * base):
                break
            end += 1
        run = bands[start:end + 1]
        touches_bottom = abs(bands[start][0] - hys[0]) <= 1.0
        score = (touches_bottom, end - start + 1)
        if best is None or score > best[0]:
            best = (score, run)
    if not best:
        return [], None
    run = best[1]
    header_y_top = max(y1 for _y0, y1 in run)
    return list(reversed(run)), header_y_top


def _cell_text(spans_in_cell: list[str]) -> str:
    tokens = []
    for t in spans_in_cell:
        for w in t.split():
            if w.strip(".,") != "":
                tokens.append(w)
    return _ALL_WS_RE.sub(" ", " ".join(tokens)).strip()


def _is_readable(text: str) -> bool:
    body = text.replace(" ", "")
    if not body:
        return True
    return body.count("?") <= int(len(body) * 0.2)


def parse_page(
    objs: dict[int, bytes], page_num: int, cmaps_cache: dict[int, dict[int, str]] | None
) -> dict:
    body = objs[page_num]
    content = _page_content(objs, body)
    fmap = _page_font_map(objs, body)
    if cmaps_cache is None:
        cmaps_cache = {}
    for fobj in fmap.values():
        if fobj in cmaps_cache:
            continue
        fbody = objs.get(fobj)
        if not fbody:
            cmaps_cache[fobj] = {}
            continue
        um = re.search(rb"/ToUnicode\s+(\d+) 0 R", fbody)
        text = _inflate_stream(objs.get(int(um.group(1)), b"")) if um else None
        cmaps_cache[fobj] = _parse_cmap(text.decode("latin-1")) if text else {}
    cmaps = {k: cmaps_cache[k] for k in fmap.values()}

    spans = _extract_spans(content, fmap, cmaps)
    vxs, hys = _grid(content)
    col_edges = list(zip(vxs, vxs[1:]))
    data_bands, header_y_top = _pick_data_bands(hys)

    footer_spans = [(y, x, s) for x, y, s in spans if hys and y >= hys[-1]]
    footer_spans.sort(key=lambda t: (-t[0], t[1]))
    footer_text = _ALL_WS_RE.sub(" ", " ".join(s for _y, _x, s in footer_spans))

    headers = {i: [] for i in range(len(col_edges))}
    data_rows: list[dict[str, str]] = []

    ci_of = lambda x: next(
        (i for i, (x0, x1) in enumerate(col_edges) if x0 <= x < x1), None
    )
    header_zone = [
        (x, s)
        for x, y, s in spans
        if header_y_top is not None and header_y_top <= y < hys[-1]
    ]
    label_edges = {i: [] for i in range(len(col_edges))}
    for x, s in header_zone:
        ci = ci_of(x)
        if ci is not None:
            label_edges[ci].append(s)
    labels = {}
    for ci, frags in label_edges.items():
        if frags:
            labels[ci] = _ALL_WS_RE.sub(" ", " ".join(frags))

    for (y0, y1) in data_bands:
        bucket: dict[int, list[tuple[float, str]]] = {}
        for x, y, s in spans:
            if not (y0 <= y < y1):
                continue
            ci = ci_of(x)
            if ci is None:
                continue
            bucket.setdefault(ci, []).append((y, s))
        cells = {}
        for ci, frags in bucket.items():
            frags.sort(key=lambda t: (-t[0], t[1]))
            cells[ci] = _cell_text([s for _y, s in frags])
        data_rows.append(cells)

    column_map = {}
    used: set[int] = set()
    for field, keys in HEADER_KEYWORDS.items():
        for ci in sorted(labels):
            if ci in used:
                continue
            if any(k in labels[ci] for k in keys):
                column_map[field] = ci
                used.add(ci)
                break

    return {
        "spans_len": len(spans),
        "vlines": vxs,
        "hlines": hys,
        "data_rows": data_rows,
        "header_labels": {str(k): v for k, v in labels.items()},
        "column_map": column_map,
        "published_text": footer_text,
    }


def parse_pdf(data: bytes, url: str | None = None, max_pages: int | None = None):
    """Parse a full KAM store PDF -> (records, info). Never raises for
    content problems; failures land in info['quarantine_reasons']."""
    info = {
        "store_external_key": None,
        "published_ts": None,
        "pages_seen": 0,
        "rows_seen": 0,
        "rows_skipped": 0,
        "rows_stored": 0,
        "header_present": False,
        "columns": None,
        "quarantine_reasons": [],
        "quarantined": False,
        "notes": [],
    }
    if url:
        m = re.search(r"/(\d+)\.pdf", url)
        if m:
            info["store_external_key"] = m.group(1)
    records: list[dict] = []
    published_first = None
    page_published: dict[int, str] = {}
    try:
        objs = _object_map(data)
        pages = _page_numbers_in_tree(objs)
    except PDFError as exc:
        info["quarantine_reasons"].append(f"pdf structure error: {exc}")
        info["quarantined"] = True
        return [], info
    if not pages:
        info["quarantine_reasons"].append("no pages in PDF")
        info["quarantined"] = True
        return [], info
    if max_pages is not None:
        pages = pages[:max_pages]

    cmaps_cache: dict[int, dict[int, str]] = {}
    for pi, pn in enumerate(pages):
        pno = pi + 1
        try:
            pg = parse_page(objs, pn, cmaps_cache)
        except (PDFError, zlib.error, KeyError, ValueError) as exc:
            info["quarantine_reasons"].append(f"page {pno} error: {exc}")
            continue
        info["pages_seen"] += 1
        if info["columns"] is None and len(pg["column_map"]) >= 5:
            info["columns"] = pg["column_map"]
        register = parse_updated(pg["published_text"])
        current_ts = register.isoformat() if register else None
        if register is None:
            info["notes"].append(f"page {pno}: timestamp footnote not found")
        else:
            page_published[pno] = current_ts
            if published_first is None:
                published_first = register

        cm = pg["column_map"]
        if "name" not in cm or not pg["data_rows"]:
            if pg["data_rows"]:
                info["quarantine_reasons"].append(
                    f"page {pno}: statutory header not identified"
                )
            continue
        info["header_present"] = True
        required_missing = [f for f in REQUIRED_FIELDS if f not in cm]
        if required_missing:
            info["quarantine_reasons"].append(
                f"page {pno}: statutory columns missing: {','.join(required_missing)}"
            )
            continue

        ci_name = cm["name"]
        ci_sale = cm.get("sale_price")
        ci_unit = cm.get("unit_price")
        ci_desc = cm.get("description")
        ci_avail = cm.get("availability")
        ci_reg = cm["regular_price"]
        ci_disc = cm.get("discount_price")
        ci_type = cm.get("promo_type")
        ci_note = cm.get("promo_note")
        unreadable = [0]

        for rownum, cells in enumerate(pg["data_rows"], 1):
            info["rows_seen"] += 1
            name = cells.get(ci_name, "")

            def val(ci):
                if ci is None:
                    return ""
                return cells.get(ci, "")

            price = parse_price(val(ci_sale)) or parse_price(val(ci_reg))
            regular = parse_price(val(ci_reg))
            unit_price, unit_label = parse_unit_price(val(ci_unit))
            discount_text = val(ci_disc)
            discount_price, discount_pct = parse_promo_cell(discount_text) if discount_text else (None, None)
            if discount_price is None and discount_text:
                discount_price = parse_price(discount_text)
            discount_pct2 = parse_pct(discount_text) if "%" in discount_text else None
            if discount_pct is None:
                discount_pct = discount_pct2
            promo_type = val(ci_type) or None
            promo_start, promo_end = parse_date_range(val(ci_note))
            availability = parse_availability(val(ci_avail))
            if promo_type and not _is_readable(promo_type):
                unreadable[0] += 1
                promo_type = None
            if not name or price is None or price <= 0:
                info["rows_skipped"] += 1
                continue
            records.append(
                {
                    "store_external_key": info["store_external_key"],
                    "sku_key": derive_sku_key(name, None),
                    "listing_name": _ALL_WS_RE.sub(" ", name).strip(),
                    "category": None,
                    "currency": CURRENCY,
                    "price_current": str(price),
                    "unit_price": str(unit_price) if unit_price is not None else None,
                    "unit_label": unit_label,
                    "regular_price": str(regular) if regular is not None else None,
                    "discount_price": str(discount_price) if discount_price is not None else None,
                    "discount_pct": str(discount_pct) if discount_pct is not None else None,
                    "promo_type": promo_type,
                    "promo_starts_on": promo_start.isoformat() if promo_start else None,
                    "promo_ends_on": promo_end.isoformat() if promo_end else None,
                    "availability": availability,
                    "published_ts": current_ts,
                    "source_url": url,
                }
            )
        if unreadable[0]:
            info["notes"].append(
                f"page {pno}: {unreadable[0]} unreadable promo_type cells stored as null"
            )

    if records and not info["header_present"]:
        info["quarantine_reasons"].append("product rows without statutory header")
        info["quarantined"] = True
        records = []
    if len(set(page_published.values())) > 1:
        info["notes"].append("page timestamps differ; per-page published_ts used")
    if not records:
        info["quarantine_reasons"].append("no product rows parsed")
        info["quarantined"] = True
    info["rows_stored"] = len(records)
    info["published_ts"] = published_first.astimezone(timezone.utc).isoformat() if published_first else None
    return records, info
