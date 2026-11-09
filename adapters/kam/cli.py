"""Ingestion CLI for KAM Market per-store PDF price lists (M9).

Modes:
- Replay (offline, default for tests/CI):
    python -B adapters/kam/cli.py --from-snapshots tests/fixtures/kam --run-key m9-kam-test
    (fixture dir contains shops_{date}.json plus {date}_{store}.pdf files)
- Fetch (live, polite rate-limited):
    python -B adapters/kam/cli.py --url https://kam.com.mk --stores 73,46 --delay 1.0 --run-key m9-kam-live
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import sys
import time
import urllib.request
from pathlib import Path

_THIS_DIR = Path(__file__).resolve().parent
if str(_THIS_DIR) not in sys.path:
    sys.path.insert(0, str(_THIS_DIR))

import kam

DEFAULT_UA = (
    "Mozilla/5.0 (compatible; AiShopping-M9-ingestion/0.1; +contact: owner)"
)
STORES_TIMEOUT = 60
PDF_TIMEOUT = 120
PDF_PAGE_LIMIT = None


def _now_utc():
    return _dt.datetime.now(_dt.timezone.utc)


def _dt_utc_iso(dt):
    if isinstance(dt, str):
        return dt
    return dt.astimezone(_dt.timezone.utc).isoformat()


def default_out_dir(retailer: str, run_key: str) -> str:
    date_str = _now_utc().strftime("%Y-%m-%d")
    return str(Path("snapshots") / retailer / date_str / run_key)


def fetch(url: str, delay_seconds: float, state: dict, timeout: int, method: str = "GET") -> bytes:
    """Polite fetch with inter-request delay, returning raw bytes."""
    min_interval = state.get("min_interval", 0.0)
    wait = state.get("last_request_ts")
    if wait is not None and min_interval > 0:
        elapsed = time.monotonic() - wait
        if elapsed < min_interval:
            time.sleep(min_interval - elapsed)
    req = urllib.request.Request(
        url,
        headers={"User-Agent": DEFAULT_UA, "Content-Type": "application/x-www-form-urlencoded"},
        data=b"" if method == "POST" else None,
        method=method,
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = resp.read()
    state["last_request_ts"] = time.monotonic()
    return data


def load_store_directory(base_url: str, delay_seconds: float, state: dict) -> tuple[bytes, list[dict]]:
    raw = fetch(kam.STORES_URL, delay_seconds, state, timeout=STORES_TIMEOUT, method="POST")
    return raw, kam.discover_stores(raw)


def build_run(
    sources,
    out_dir,
    run_key,
    source_slug="kam",
    fetched_ts=None,
    store_directory=None,
):
    """sources: list of {url, raw_bytes} already fetched. Writes snapshot
    bytes, snapshots.ndjson, records.ndjson and manifest.json."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    fetched = fetched_ts or _now_utc()
    fetched_iso = _dt_utc_iso(fetched)

    snapshot_lines = []
    records_all = []
    page_infos = []
    quarantined_sources = []
    seen_hashes = {}

    for src in sources:
        url = src["url"]
        raw_bytes = src["raw_bytes"]
        uhash = kam.url_hash_sha256(url)
        chash = kam.content_hash_sha256(raw_bytes)
        fname = f"{uhash[:16]}.pdf"
        (out / fname).write_bytes(raw_bytes)

        records, info = kam.parse_pdf(raw_bytes, url=url)
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
            "content_type": kam.SNAPSHOT_CONTENT_TYPE,
            "byte_size": len(raw_bytes),
            "fetched_ts": fetched_iso,
            "published_ts": _dt_utc_iso(info["published_ts"]) if info["published_ts"] else None,
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

        if info["quarantined"]:
            quarantined_sources.append(
                f"{url} ({'; '.join(info['quarantine_reasons']) or 'unknown'})"
            )

    quarantined = len(quarantined_sources) > 0
    reason = None
    if quarantined:
        reason = "quarantined sources: " + " | ".join(quarantined_sources)

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
        "tz_source": "zoneinfo:Europe/Skopje",
        "store_directory": store_directory,
        "sources": [
            {
                "url": i["url"],
                "store_external_key": i["store_external_key"],
                "published_ts": _dt_utc_iso(i["published_ts"]) if i["published_ts"] else None,
                "rows": None,
                "quarantined": i["quarantined"],
            }
            for i in page_infos
        ],
    }
    counts = {}
    for rec in records_all:
        counts[rec["source_url"]] = counts.get(rec["source_url"], 0) + 1
    for p in manifest["sources"]:
        p["rows"] = counts.get(p["url"], 0)

    (out / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return records_all, manifest, out


def discover_snapshot_files(root: Path):
    """Fixture replay: {date}_{store}.pdf files map to
    {base}/{Y}/{M}/{D}/{store}.pdf. shops_{date}.json, when present, is
    parsed and reported as store_directory provenance."""
    sources = []
    by_date_stores: dict[str, set[str]] = {}
    for path in sorted(root.iterdir()):
        if not path.is_file():
            continue
        if path.name.startswith("shops_") and path.name.endswith(".json"):
            date = path.name[len("shops_"):-len(".json")]
            try:
                stores = kam.discover_stores(path.read_bytes())
            except Exception:
                continue
            by_date_stores[date] = {s["external_key"] for s in stores}
    for path in sorted(root.iterdir()):
        m = kam._FIXTURE_FILE_RE.fullmatch(path.name)
        if not path.is_file() or not m:
            continue
        date, store = m.group(1), m.group(2)
        if date in by_date_stores and store not in by_date_stores[date]:
            raise SystemExit(f"fixture {path.name}: store not in reference directory JSON")
        relative = f"{date.replace('-', '/')}/{store}.pdf"
        url = kam.build_pdf_url(kam.BASE_URLS["kam"], relative)
        sources.append({"url": url, "raw_bytes": path.read_bytes()})
    if not sources:
        raise SystemExit("no store PDFs found in snapshot dir")
    return sources


def snapshot_store_directory(root: Path) -> tuple[bytes, list[dict]] | None:
    for path in sorted(root.iterdir()):
        if path.is_file() and path.name.startswith("shops_") and path.name.endswith(".json"):
            raw = path.read_bytes()
            return raw, kam.discover_stores(raw)
    return None


def fetch_run(base_url, store_ids, delay, out_dir, run_key):
    """Live fetch: shop directory via POST LoadShopList, then per-store PDFs."""
    state = {"min_interval": delay, "last_request_ts": None}
    dir_raw, stores = load_store_directory(base_url, delay, state)
    wanted = [s.strip() for s in store_ids.split(",") if s.strip()]
    by_key = {s["external_key"]: s for s in stores}
    sources = []
    skipped = []
    for sid in wanted:
        st = by_key.get(sid)
        if st is None or not st.get("price_list_path"):
            skipped.append(sid)
            continue
        url = kam.build_pdf_url(base_url, st["price_list_path"])
        data = fetch(url, delay, state, timeout=PDF_TIMEOUT)
        sources.append({"url": url, "raw_bytes": data})
    if skipped:
        print(f"# skipped (unknown or no price list): {','.join(skipped)}", file=sys.stderr)
    if not sources:
        raise SystemExit("no store price lists fetched")
    store_dir_meta = {
        "url": kam.STORES_URL,
        "content_hash": kam.content_hash_sha256(dir_raw),
        "stores": len(stores),
        "fetched_ts": _dt_utc_iso(_now_utc()),
    }
    records, manifest, out = build_run(
        sources, out_dir, run_key, store_directory=store_dir_meta
    )
    return records, manifest, out


def main(argv=None):
    ap = argparse.ArgumentParser(description="KAM Market (kam.com.mk) ingestion CLI (M9)")
    ap.add_argument("--retailer", choices=sorted(kam.BASE_URLS.keys()), help="retailer slug")
    ap.add_argument("--from-snapshots", help="directory with {date}_{store}.pdf fixtures")
    ap.add_argument("--url", help="base URL, e.g. https://kam.com.mk")
    ap.add_argument("--stores", help="comma-separated store ids for --url mode")
    ap.add_argument("--delay", type=float, default=1.0)
    ap.add_argument("--out", help="output directory (default: snapshots/kam/{date}/{run_key})")
    ap.add_argument("--run-key", required=True)
    args = ap.parse_args(argv)

    base_url = kam.BASE_URLS[(args.retailer or "kam")]

    if args.from_snapshots:
        root = Path(args.from_snapshots)
        if not root.exists():
            raise SystemExit(f"snapshot dir not found: {root}")
        sources = discover_snapshot_files(root)
        store_dir_ref = snapshot_store_directory(root)
        store_directory = None
        if store_dir_ref:
            raw, stores = store_dir_ref
            store_directory = {
                "file": next(p.name for p in sorted(root.iterdir()) if p.name.startswith("shops_") and p.suffix == ".json"),
                "content_hash": kam.content_hash_sha256(raw),
                "stores": len(stores),
            }
        out = args.out or default_out_dir("kam", args.run_key)
        records, manifest, out = build_run(
            sources, out, args.run_key, store_directory=store_directory
        )
    elif args.url and args.stores:
        out = args.out or default_out_dir((args.retailer or "kam"), args.run_key)
        records, manifest, out = fetch_run(
            args.url, args.stores, args.delay, out, args.run_key
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
