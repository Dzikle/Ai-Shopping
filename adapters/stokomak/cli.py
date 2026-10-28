"""Ingestion CLI for the shared *.proverkanaceni.mk platform (Stokomak, Zito).

Modes:
- Replay (offline, default for tests/CI):
    python -B adapters/stokomak/cli.py --retailer stokomak --from-snapshots tests/fixtures/stokomak --run-key m2-stokomak-test
    python -B adapters/stokomak/cli.py --retailer zito --from-snapshots tests/fixtures/zito --run-key m2-zito-test
- Fetch (live, polite rate-limited):
    python -B adapters/stokomak/cli.py --retailer stokomak --url https://stokomak.proverkanaceni.mk --stores 1,3,14 --max-pages 5 --delay 1.0 --run-key ...
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

_THIS_DIR = Path(__file__).resolve().parent
if str(_THIS_DIR) not in sys.path:
    sys.path.insert(0, str(_THIS_DIR))

import stokomak

SNAPSHOT_CONTENT_TYPE = "text/html; charset=utf-8"
DEFAULT_UA = "AiShopping-M2-ingestion/0.1 (+contact: owner)"


def _now_utc():
    return datetime.now(timezone.utc)


def _dt_utc_iso(dt):
    return dt.astimezone(timezone.utc).isoformat()


def default_out_dir(retailer: str, run_key: str) -> str:
    date_str = _now_utc().strftime("%Y-%m-%d")
    return str(Path("snapshots") / retailer / date_str / run_key)


def _infer_retailer(from_snapshots: str | None, url: str | None, explicit: str | None) -> str:
    if explicit:
        return explicit.strip().lower()
    for candidate in (from_snapshots or "", url or ""):
        low = candidate.lower()
        for slug in stokomak.RETAILER_URLS:
            if slug in low:
                return slug
    return "stokomak"


def fetch(url: str, delay_seconds: float, state: dict) -> bytes:
    """Polite fetch with inter-request delay."""
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


def build_run(sources, out_dir, run_key, source_slug="stokomak", fetched_ts=None):
    """sources: list of dicts {url, html_text, raw_bytes} already read/fetched.

    Writes snapshots + ndjson + manifest; returns (records, manifest, out_path).
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
        uhash = stokomak.url_hash_sha256(url)
        chash = stokomak.content_hash_sha256(raw_bytes)
        fname = f"{uhash[:16]}.html"
        (out / fname).write_bytes(raw_bytes)

        records, info = stokomak.parse_page(text, url)
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
        "source_slug": source_slug,
        "created_at_utc": _dt_utc_iso(_now_utc()),
        "fetched_ts": fetched_iso,
        "pages_seen": len(sources),
        "rows_seen": rows_seen,
        "rows_stored": len(records_all),
        "rows_skipped": rows_skipped,
        "quarantined": quarantined,
        "quarantine_reason": reason,
        "tz_source": stokomak._TZ_SOURCE,
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
    counts = {}
    for rec in records_all:
        counts[rec["source_url"]] = counts.get(rec["source_url"], 0) + 1
    for p in manifest["pages"]:
        p["rows"] = counts.get(p["url"], 0)

    (out / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return records_all, manifest, out


def discover_snapshot_files(root: Path, base_url: str, per_page: int = stokomak.DEFAULT_PER_PAGE):
    """Return ordered sources {url, html_text, raw_bytes} from a fixtures dir.
    Files named {org}_{page}.html map to {base_url}/?org={org}&perPage={per_page}&page={page}.
    index.html and empty_*.html are ignored by normal discovery and tested explicitly.
    """
    sources = []
    for path in root.iterdir():
        name = path.name
        m = stokomak._FIXTURE_FILE_RE.fullmatch(name)
        if not path.is_file() or not m:
            continue
        org = int(m.group(1))
        page = int(m.group(2))
        raw_bytes = path.read_bytes()
        url = stokomak.build_page_url(base_url, org, page=page, per_page=per_page)
        sources.append(
            {
                "url": url,
                "html_text": raw_bytes.decode("utf-8-sig", errors="replace"),
                "raw_bytes": raw_bytes,
                "_org": org,
                "_page": page,
            }
        )
    sources.sort(key=lambda s: (s["_org"], s["_page"]))
    for s in sources:
        del s["_org"]
        del s["_page"]
    return sources


def fetch_run(base_url, stores, max_pages, per_page, delay, out_dir, run_key, source_slug):
    """Live fetch mode: paginated store pages with rate limiting and hard cap."""
    sources = []
    state = {"min_interval": delay, "last_request_ts": None}
    pages = 0
    for store in stores:
        page = 1
        while page <= max_pages:
            url = stokomak.build_page_url(base_url, store, page=page, per_page=per_page)
            data = fetch(url, delay, state)
            try:
                text = data.decode("utf-8-sig")
            except UnicodeDecodeError:
                text = data.decode("utf-8", errors="replace")
            sources.append({"url": url, "html_text": text, "raw_bytes": data})
            pages += 1
            _records, info = stokomak.parse_page(text, url)
            if info["next_page_url"]:
                page += 1
            else:
                break
        if pages >= 200:
            raise SystemExit("hard page cap reached (200) - aborting for politeness")
    records, manifest, out = build_run(
        sources, out_dir, run_key, source_slug=source_slug
    )
    return records, manifest, out


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Stokomak / Zito (proverkanaceni.mk) ingestion CLI (M2)"
    )
    ap.add_argument("--retailer", choices=sorted(stokomak.RETAILER_URLS.keys()), help="retailer slug")
    ap.add_argument("--from-snapshots", help="directory with captured {org}_{page}.html pages")
    ap.add_argument("--url", help="base URL, e.g. https://stokomak.proverkanaceni.mk")
    ap.add_argument("--stores", help="comma-separated org ids for --url mode")
    ap.add_argument("--per-page", type=int, default=stokomak.DEFAULT_PER_PAGE)
    ap.add_argument("--max-pages", type=int, default=50)
    ap.add_argument("--delay", type=float, default=1.0)
    ap.add_argument("--out", help="output directory (default: snapshots/{retailer}/{date}/{run_key})")
    ap.add_argument("--run-key", required=True)
    args = ap.parse_args(argv)

    retailer = _infer_retailer(args.from_snapshots, args.url, args.retailer)
    base_url = args.url or stokomak.RETAILER_URLS[retailer]

    if args.from_snapshots:
        root = Path(args.from_snapshots)
        if not root.exists():
            raise SystemExit(f"snapshot dir not found: {root}")
        sources = discover_snapshot_files(root, base_url, per_page=args.per_page)
        if not sources:
            raise SystemExit("no store pages found in snapshot dir")
        out = args.out or default_out_dir(retailer, args.run_key)
        records, manifest, out = build_run(
            sources, out, args.run_key, source_slug=retailer
        )
    elif args.url and args.stores:
        stores = [s.strip() for s in args.stores.split(",") if s.strip()]
        out = args.out or default_out_dir(retailer, args.run_key)
        records, manifest, out = fetch_run(
            base_url,
            stores,
            args.max_pages,
            args.per_page,
            args.delay,
            out,
            args.run_key,
            retailer,
        )
    else:
        raise SystemExit("provide --from-snapshots DIR or --url URL --stores IDS")

    print(
        json.dumps(
            {
                "out": str(out),
                "source_slug": manifest["source_slug"],
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
