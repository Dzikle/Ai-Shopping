"""Vero ingestion CLI.

Modes:
- Replay (offline, default for tests/CI):
    python -m cli --from-snapshots tests/fixtures/vero --out snapshots/vero/2026-10-28/<run_key>
- Fetch (live, polite rate-limited):
    python -m cli --url https://pricelist.vero.com.mk --stores 89 --max-pages 50 --delay 1.0 --out ...

Outputs in --out directory:
- {url_hash16}.html      raw byte-exact snapshots
- snapshots.ndjson       one JSON object per snapshot (loader contract)
- records.ndjson         one JSON object per offer record (loader contract)
- manifest.json          run metadata incl. quarantine status

Quarantine policy (AGENTS.md #6): a discovered page that contains a price-list
header but zero product rows marks the whole run quarantined; the loader must
refuse to ingest quarantined runs (data deletion is never a remedy).
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import vero

SNAPSHOT_CONTENT_TYPE = "text/html; charset=utf-8"
DEFAULT_UA = "AiShopping-M1-ingestion/0.1 (+contact: owner)"


def _now_utc():
    return datetime.now(timezone.utc)


def _dt_utc_iso(dt):
    return dt.astimezone(timezone.utc).isoformat()


def default_out_dir(run_key):
    """snapshots/{source}/{yyyy-mm-dd}/{run_key} per docs/contracts/worker-contract.md."""
    date_str = _now_utc().strftime("%Y-%m-%d")
    return str(Path("snapshots") / "vero" / date_str / run_key)


def fetch(url, delay_seconds, state):
    """Polite fetch with inter-request delay and a global max-pages cap."""
    min_interval = state.get("min_interval", 0.0)
    wait = state.get("last_request_ts")
    if wait is not None and min_interval > 0:
        elapsed = time.monotonic() - wait
        if elapsed < min_interval:
            time.sleep(min_interval - elapsed)
    req = urllib.request.Request(url, headers={"User-Agent": DEFAULT_UA})
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = resp.read()
    state["last_request_ts"] = time.monotonic()
    return data


def build_run(sources, out_dir, run_key, fetched_ts=None):
    """sources: list of dicts {url, html_text, raw_bytes} already read/fetched.

    Writes snapshots + ndjson + manifest; returns (records, manifest, paths).
    """
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    fetched = fetched_ts or _now_utc()
    fetched_iso = _dt_utc_iso(fetched)

    snapshot_lines = []
    records_all = []
    page_infos = []
    quarantined_pages = []
    seen_hashes = {}

    for src in sources:
        url = src["url"]
        text = src["html_text"]
        raw_bytes = src["raw_bytes"]
        uhash = vero.url_hash_sha256(url)
        chash = vero.content_hash_sha256(raw_bytes)
        fname = f"{uhash[:16]}.html"
        (out / fname).write_bytes(raw_bytes)

        records, info = vero.parse_page(text, url)
        info["url"] = url
        info["content_hash"] = chash
        info["storage_path"] = fname
        info["byte_size"] = len(raw_bytes)
        page_infos.append(info)

        snap = {
            "url": url,
            "url_hash": uhash,
            "content_hash": chash,
            "storage_path": fname,
            "content_type": SNAPSHOT_CONTENT_TYPE,
            "byte_size": len(raw_bytes),
            "fetched_ts": fetched_iso,
            "published_ts": (
                _dt_utc_iso(info["published_ts"]) if info["published_ts"] else None
            ),
        }
        if uhash in seen_hashes and seen_hashes[uhash] != chash:
            raise SystemExit(f"same url hash with different content: {url}")
        seen_hashes[uhash] = chash

        snapshot_idx = len(snapshot_lines)
        snapshot_lines.append(json.dumps(snap, ensure_ascii=False))
        for rec in records:
            rec_out = dict(rec)
            rec_out["fetched_ts"] = fetched_iso
            rec_out["snapshot_url_hash"] = uhash
            rec_out["snapshot_content_hash"] = chash
            rec_out["snapshot_idx"] = snapshot_idx
            records_all.append(rec_out)

        if info["header_present"] and len(records) == 0:
            quarantined_pages.append(url)

    quarantined = len(quarantined_pages) > 0
    reason = None
    if quarantined:
        reason = "pages with header but zero product rows: " + ", ".join(quarantined_pages)

    (out / "snapshots.ndjson").write_text(
        "\n".join(snapshot_lines) + ("\n" if snapshot_lines else ""), encoding="utf-8"
    )
    (out / "records.ndjson").write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in records_all)
        + ("\n" if records_all else ""),
        encoding="utf-8",
    )

    rows_seen = sum(i["rows_seen"] for i in page_infos)
    rows_skipped = sum(i["rows_skipped"] for i in page_infos)
    manifest = {
        "run_key": run_key,
        "source_slug": "vero",
        "created_at_utc": _dt_utc_iso(_now_utc()),
        "fetched_ts": fetched_iso,
        "pages_seen": len(sources),
        "rows_seen": rows_seen,
        "rows_stored": len(records_all),
        "rows_skipped": rows_skipped,
        "quarantined": quarantined,
        "quarantine_reason": reason,
        "tz_source": vero._TZ_SOURCE,
        "pages": [
            {
                "url": i["url"],
                "store_external_key": i["store_external_key"],
                "published_ts": (
                    _dt_utc_iso(i["published_ts"]) if i["published_ts"] else None
                ),
                "rows": None,
            }
            for i in page_infos
        ],
    }
    # per-page record counts
    counts = {}
    for rec in records_all:
        counts[rec["source_url"]] = counts.get(rec["source_url"], 0) + 1
    for p in manifest["pages"]:
        p["rows"] = counts.get(p["url"], 0)

    (out / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return records_all, manifest, out


def discover_snapshot_files(root: Path):
    """Return ordered sources {url, html_text, raw_bytes} from a fixtures or
    snapshots dir: files named exactly like the source ({store}_{page}.html),
    sorted by (store, page). index.html is not a price page; callers validate
    it separately via validate_index_stores."""
    sources = []
    for path in root.iterdir():
        name = path.name.lower()
        m = vero._PAGE_FILE_RE.fullmatch(name)
        if not path.is_file() or not m:
            continue
        raw_bytes = path.read_bytes()
        sources.append(
            {
                "url": f"{vero.BASE_URL}/{name}",
                "html_text": raw_bytes.decode("utf-8-sig"),
                "raw_bytes": raw_bytes,
                "_store": m.group(1),
                "_page": int(m.group(2)),
            }
        )
    sources.sort(key=lambda s: (s["_store"], s["_page"]))
    for s in sources:
        del s["_store"]
        del s["_page"]
    return sources


def validate_index_stores(root: Path, stores_in_db):
    """Cross-check index.html store list against DB store seeds (warning only)."""
    index_path = root / "index.html"
    if not index_path.exists():
        return None
    parsed = vero.parse_index(index_path.read_text(encoding="utf-8-sig"))
    keys = {s["external_key"] for s in parsed}
    db_keys = {s["external_key"] for s in stores_in_db}
    return {
        "parsed_count": len(parsed),
        "missing_in_db": sorted(keys - db_keys),
        "extra_in_db": sorted(db_keys - keys),
    }


def fetch_run(base_url, stores, max_pages, delay, out_dir, run_key):
    """Live fetch mode: index + paginated store pages with rate limiting."""
    base = base_url.rstrip("/") + "/"
    sources = []
    state = {"min_interval": delay, "last_request_ts": None}
    pages = 0
    for store in stores:
        page = 1
        while page <= max_pages:
            name = f"{store}_{page}.html"
            url = base + name
            data = fetch(url, delay, state)
            try:
                text = data.decode("utf-8-sig")
            except UnicodeDecodeError:
                text = data.decode("utf-8", errors="replace")
            sources.append({"url": url, "html_text": text, "raw_bytes": data})
            pages += 1
            _records, info = vero.parse_page(text, url)
            if info["next_page_url"]:
                page += 1
            else:
                break
        if pages >= 200:
            raise SystemExit("hard page cap reached (200) - aborting for politeness")
    records, manifest, out = build_run(sources, out_dir, run_key)
    return records, manifest, out


def main(argv=None):
    ap = argparse.ArgumentParser(description="Vero price-list ingestion (M1)")
    ap.add_argument("--from-snapshots", help="directory with captured .html pages")
    ap.add_argument("--url", help="base URL, e.g. https://pricelist.vero.com.mk")
    ap.add_argument("--stores", help="comma-separated store ids for --url mode")
    ap.add_argument("--max-pages", type=int, default=50)
    ap.add_argument("--delay", type=float, default=1.0)
    ap.add_argument(
        "--out",
        help="output directory (default: snapshots/{source}/{date}/{run_key})",
    )
    ap.add_argument("--run-key", required=True)
    args = ap.parse_args(argv)

    if args.from_snapshots:
        root = Path(args.from_snapshots)
        if not root.exists():
            raise SystemExit(f"snapshot dir not found: {root}")
        sources = discover_snapshot_files(root)
        if not sources:
            raise SystemExit("no store pages found in snapshot dir")
        out = args.out or default_out_dir(args.run_key)
        records, manifest, out = build_run(sources, out, args.run_key)
    elif args.url and args.stores:
        stores = [s.strip() for s in args.stores.split(",") if s.strip()]
        out = args.out or default_out_dir(args.run_key)
        records, manifest, out = fetch_run(
            args.url, stores, args.max_pages, args.delay, out, args.run_key
        )
    else:
        raise SystemExit("provide --from-snapshots DIR or --url URL --stores IDS")

    print(
        json.dumps(
            {
                "out": str(out),
                "pages_seen": manifest["pages_seen"],
                "rows_seen": manifest["rows_seen"],
                "rows_stored": manifest["rows_stored"],
                "rows_skipped": manifest["rows_skipped"],
                "quarantined": manifest["quarantined"],
            },
            ensure_ascii=False,
        )
    )
    return 2 if manifest["quarantined"] else 0


if __name__ == "__main__":
    sys.exit(main())
