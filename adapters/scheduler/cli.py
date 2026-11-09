"""M6 Daily Ingestion Scheduler Worker CLI (stdlib-only Python 3.12).

Modes:
- Single pipeline scrape/replay pass (--once):
    python -B adapters/scheduler/cli.py --once --from-snapshots --run-tag m6-replay
    python -B adapters/scheduler/cli.py --once --live --stores-map vero=89,stokomak=1,zito=2 --max-pages 1 --run-tag m6-live-smoke
- Long-running daemon loop (--daemon):
    python -B adapters/scheduler/cli.py --daemon --target-time 08:30 --live

Delegates per-retailer parsing and snapshot generation to `adapters/vero/` and
`adapters/stokomak/` while enforcing per-retailer job leases, IPv4 preference,
exponential backoff retries, quarantine detection, and structured JSON logging.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import time
from pathlib import Path
from typing import Any

_THIS_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _THIS_DIR.parent.parent
for _p in (
    _THIS_DIR,
    _REPO_ROOT / "adapters" / "common",
    _REPO_ROOT / "adapters" / "vero",
    _REPO_ROOT / "adapters" / "stokomak",
    _REPO_ROOT / "adapters" / "kam",
):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import kam
import scheduler
import stokomak
import vero


def _load_module(name: str, file_path: Path):
    spec = importlib.util.spec_from_file_location(name, str(file_path))
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load module {name} from {file_path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


vero_cli = _load_module("vero_cli", _REPO_ROOT / "adapters" / "vero" / "cli.py")
stokomak_cli = _load_module("stokomak_cli", _REPO_ROOT / "adapters" / "stokomak" / "cli.py")
kam_cli = _load_module("kam_cli", _REPO_ROOT / "adapters" / "kam" / "cli.py")


def _parse_kv_map(raw: str | None) -> dict[str, str]:
    if not raw:
        return {}
    out: dict[str, str] = {}
    for pair in raw.split(","):
        pair = pair.strip()
        if not pair or "=" not in pair:
            continue
        k, v = pair.split("=", 1)
        out[k.strip().lower()] = v.strip()
    return out


def _parse_stores_map(raw: str | None) -> dict[str, list[str]]:
    if not raw:
        return {}
    out: dict[str, list[str]] = {}
    for entry in raw.split(";"):
        for sub in entry.split(","):
            sub = sub.strip()
            if not sub:
                continue
            if "=" in sub:
                k, val = sub.split("=", 1)
                slug = k.strip().lower()
                out.setdefault(slug, []).extend(
                    s.strip() for s in val.split(":") if s.strip()
                )
    return out


def _live_fetch_vero(
    base_url: str,
    stores: list[str],
    max_pages: int,
    delay: float,
    out_dir: str | Path,
    run_key: str,
    worker_id: str,
    max_retries: int,
    base_backoff: float,
    stream=None,
):
    base = base_url.rstrip("/") + "/"
    sources = []
    state: dict[str, Any] = {"min_interval": delay, "last_request_ts": None}
    pages = 0
    for store in stores:
        page = 1
        while page <= max_pages:
            t0 = time.monotonic()
            url = f"{base}{store}_{page}.html"
            data = scheduler.fetch_with_retry(
                url,
                delay_seconds=delay,
                state=state,
                max_retries=max_retries,
                base_backoff_seconds=base_backoff,
                force_ipv4=False,
            )
            dur_ms = int((time.monotonic() - t0) * 1000)
            try:
                text = data.decode("utf-8-sig")
            except UnicodeDecodeError:
                text = data.decode("utf-8", errors="replace")
            sources.append({"url": url, "html_text": text, "raw_bytes": data})
            pages += 1
            _records, info = vero.parse_page(text, url)
            scheduler.emit_json_log(
                "info",
                "page_fetched",
                retailer="vero",
                store=store,
                page=page,
                run_key=run_key,
                worker_id=worker_id,
                duration_ms=dur_ms,
                status="ok",
                rows=len(_records),
                stream=stream,
            )
            if info["next_page_url"]:
                page += 1
            else:
                break
        if pages >= 200:
            raise RuntimeError("hard page cap reached (200) - aborting for politeness")
    return vero_cli.build_run(sources, out_dir, run_key)


def _live_fetch_proverkanaceni(
    retailer: str,
    base_url: str,
    stores: list[str],
    max_pages: int,
    per_page: int,
    delay: float,
    out_dir: str | Path,
    run_key: str,
    worker_id: str,
    max_retries: int,
    base_backoff: float,
    stream=None,
):
    sources = []
    state: dict[str, Any] = {"min_interval": delay, "last_request_ts": None}
    pages = 0
    for store in stores:
        page = 1
        while page <= max_pages:
            t0 = time.monotonic()
            url = stokomak.build_page_url(base_url, store, page=page, per_page=per_page)
            data = scheduler.fetch_with_retry(
                url,
                delay_seconds=delay,
                state=state,
                max_retries=max_retries,
                base_backoff_seconds=base_backoff,
                force_ipv4=True,
            )
            dur_ms = int((time.monotonic() - t0) * 1000)
            try:
                text = data.decode("utf-8-sig")
            except UnicodeDecodeError:
                text = data.decode("utf-8", errors="replace")
            sources.append({"url": url, "html_text": text, "raw_bytes": data})
            pages += 1
            _records, info = stokomak.parse_page(text, url)
            scheduler.emit_json_log(
                "info",
                "page_fetched",
                retailer=retailer,
                store=store,
                page=page,
                run_key=run_key,
                worker_id=worker_id,
                duration_ms=dur_ms,
                status="ok",
                rows=len(_records),
                stream=stream,
            )
            if info["next_page_url"]:
                page += 1
            else:
                break
        if pages >= 200:
            raise RuntimeError("hard page cap reached (200) - aborting for politeness")
    return stokomak_cli.build_run(sources, out_dir, run_key, source_slug=retailer)


def _live_fetch_kam(
    base_url: str,
    stores: list[str],
    delay: float,
    out_dir: str | Path,
    run_key: str,
    worker_id: str,
    max_retries: int,
    base_backoff: float,
    stream=None,
):
    """KAM live fetch: POST the store directory, then GET each store PDF."""
    sources = []
    state: dict[str, Any] = {"min_interval": delay, "last_request_ts": None}
    dir_raw = scheduler.fetch_with_retry(
        kam.STORES_URL,
        delay_seconds=delay,
        state=state,
        max_retries=max_retries,
        base_backoff_seconds=base_backoff,
        force_ipv4=False,
        post_body=b"",
    )
    all_stores = kam.discover_stores(dir_raw)
    by_key = {s["external_key"]: s for s in all_stores}
    skipped = []
    for store in stores:
        meta = by_key.get(store)
        if meta is None or not meta.get("price_list_path"):
            skipped.append(store)
            continue
        t0 = time.monotonic()
        url = kam.build_pdf_url(base_url, meta["price_list_path"])
        data = scheduler.fetch_with_retry(
            url,
            delay_seconds=delay,
            state=state,
            max_retries=max_retries,
            base_backoff_seconds=base_backoff,
            force_ipv4=False,
            timeout_seconds=180.0,
        )
        dur_ms = int((time.monotonic() - t0) * 1000)
        sources.append({"url": url, "raw_bytes": data})
        scheduler.emit_json_log(
            "info",
            "page_fetched",
            retailer="kam",
            store=store,
            page=1,
            run_key=run_key,
            worker_id=worker_id,
            duration_ms=dur_ms,
            status="ok",
            stream=stream,
        )
    if skipped:
        scheduler.emit_json_log(
            "warn",
            "kam_stores_skipped",
            retailer="kam",
            stores=",".join(skipped),
            run_key=run_key,
            worker_id=worker_id,
            stream=stream,
        )
    if not sources:
        raise RuntimeError("no KAM price lists fetched")
    store_dir_meta = {
        "url": kam.STORES_URL,
        "content_hash": kam.content_hash_sha256(dir_raw),
        "stores": len(all_stores),
        "fetched_ts": scheduler.now_utc().isoformat(),
    }
    return kam_cli.build_run(
        sources, out_dir, run_key, store_directory=store_dir_meta
    )


def run_single_retailer(
    retailer: str,
    *,
    mode: str,
    run_tag: str,
    out_root: Path,
    lease_mgr: scheduler.LeaseManager,
    worker_id: str,
    snapshot_dir: Path | None = None,
    base_url: str | None = None,
    stores: list[str] | None = None,
    max_pages: int = 50,
    per_page: int = stokomak.DEFAULT_PER_PAGE,
    delay: float = 1.0,
    max_retries: int = 3,
    base_backoff: float = 60.0,
    stream=None,
) -> dict[str, Any]:
    date_str = scheduler.now_utc().strftime("%Y-%m-%d")
    run_key = f"{run_tag}-{retailer}"
    out_dir = out_root / retailer / date_str / run_key
    t0 = time.monotonic()

    with lease_mgr.lease(retailer, run_key, worker_id=worker_id):
        scheduler.emit_json_log(
            "info",
            "retailer_run_started",
            retailer=retailer,
            run_key=run_key,
            worker_id=worker_id,
            status="running",
            mode=mode,
            stream=stream,
        )
        if mode == "snapshots":
            snap_root = snapshot_dir or (_REPO_ROOT / scheduler.DEFAULT_FIXTURE_DIRS[retailer])
            if not snap_root.exists():
                raise RuntimeError(f"snapshot directory not found for {retailer}: {snap_root}")
            if retailer == "vero":
                sources = vero_cli.discover_snapshot_files(snap_root)
                if not sources:
                    raise RuntimeError(f"no store pages found in {snap_root}")
                _records, manifest, out_path = vero_cli.build_run(sources, out_dir, run_key)
            elif retailer == "kam":
                sources = kam_cli.discover_snapshot_files(snap_root)
                if not sources:
                    raise RuntimeError(f"no store PDFs found in {snap_root}")
                store_dir_ref = kam_cli.snapshot_store_directory(snap_root)
                store_directory = None
                if store_dir_ref:
                    _raw, stores_found = store_dir_ref
                    store_directory = {
                        "url": kam.STORES_URL,
                        "content_hash": kam.content_hash_sha256(_raw),
                        "stores": len(stores_found),
                    }
                _records, manifest, out_path = kam_cli.build_run(
                    sources, out_dir, run_key, store_directory=store_directory
                )
            else:
                url = base_url or stokomak.RETAILER_URLS[retailer]
                sources = stokomak_cli.discover_snapshot_files(snap_root, url, per_page=per_page)
                if not sources:
                    raise RuntimeError(f"no store pages found in {snap_root}")
                _records, manifest, out_path = stokomak_cli.build_run(
                    sources, out_dir, run_key, source_slug=retailer
                )
        elif mode == "live":
            url = base_url or scheduler.DEFAULT_LIVE_URLS[retailer]
            target_stores = stores or scheduler.DEFAULT_LIVE_SMOKE_STORES[retailer]
            if retailer == "vero":
                _records, manifest, out_path = _live_fetch_vero(
                    url,
                    target_stores,
                    max_pages,
                    delay,
                    out_dir,
                    run_key,
                    worker_id,
                    max_retries,
                    base_backoff,
                    stream=stream,
                )
            elif retailer == "kam":
                _records, manifest, out_path = _live_fetch_kam(
                    url,
                    target_stores,
                    delay,
                    out_dir,
                    run_key,
                    worker_id,
                    max_retries,
                    base_backoff,
                    stream=stream,
                )
            else:
                _records, manifest, out_path = _live_fetch_proverkanaceni(
                    retailer,
                    url,
                    target_stores,
                    max_pages,
                    per_page,
                    delay,
                    out_dir,
                    run_key,
                    worker_id,
                    max_retries,
                    base_backoff,
                    stream=stream,
                )
        else:
            raise ValueError(f"unsupported mode: {mode}")

        dur_ms = int((time.monotonic() - t0) * 1000)
        quarantined = bool(manifest.get("quarantined"))
        status = "quarantined" if quarantined else "completed"
        alert = None
        if quarantined:
            manifest_rows = manifest.get("pages") or manifest.get("sources") or []
            first_store = (
                manifest_rows[0]["store_external_key"]
                if manifest_rows
                else "unknown"
            )
            alert = scheduler.build_alert_payload(
                level="error",
                retailer=retailer,
                store=str(first_store),
                message=f"Quarantined: {manifest.get('quarantine_reason')}",
                run_key=run_key,
            )
            scheduler.emit_json_log(
                "error",
                "retailer_run_quarantined",
                retailer=retailer,
                store=str(first_store),
                run_key=run_key,
                worker_id=worker_id,
                duration_ms=dur_ms,
                status="quarantined",
                quarantine_reason=manifest.get("quarantine_reason"),
                stream=stream,
            )
        else:
            scheduler.emit_json_log(
                "info",
                "retailer_run_completed",
                retailer=retailer,
                run_key=run_key,
                worker_id=worker_id,
                duration_ms=dur_ms,
                status="completed",
                pages_seen=manifest["pages_seen"],
                rows_stored=manifest["rows_stored"],
                stream=stream,
            )

        return {
            "retailer": retailer,
            "run_key": run_key,
            "out_dir": str(out_path).replace("\\", "/"),
            "status": status,
            "pages_seen": manifest["pages_seen"],
            "rows_seen": manifest["rows_seen"],
            "rows_stored": manifest["rows_stored"],
            "rows_skipped": manifest["rows_skipped"],
            "quarantined": quarantined,
            "quarantine_reason": manifest.get("quarantine_reason"),
            "duration_ms": dur_ms,
            "alert": alert,
        }


def run_pipeline_pass(
    *,
    retailers: list[str],
    mode: str,
    run_tag: str,
    out_root: Path,
    lease_dir: Path,
    worker_id: str,
    snapshot_map: dict[str, str],
    stores_map: dict[str, list[str]],
    max_pages: int = 50,
    per_page: int = stokomak.DEFAULT_PER_PAGE,
    delay: float = 1.0,
    max_retries: int = 3,
    base_backoff: float = 60.0,
    stream=None,
) -> tuple[dict[str, Any], int]:
    lease_mgr = scheduler.LeaseManager(lease_dir)
    results = []
    alerts = []
    any_quarantined = False
    any_failed = False

    for slug in retailers:
        snap_dir = Path(snapshot_map[slug]) if slug in snapshot_map else None
        stores = stores_map.get(slug)
        try:
            res = run_single_retailer(
                slug,
                mode=mode,
                run_tag=run_tag,
                out_root=out_root,
                lease_mgr=lease_mgr,
                worker_id=worker_id,
                snapshot_dir=snap_dir,
                stores=stores,
                max_pages=max_pages,
                per_page=per_page,
                delay=delay,
                max_retries=max_retries,
                base_backoff=base_backoff,
                stream=stream,
            )
            results.append(res)
            if res["quarantined"]:
                any_quarantined = True
                if res.get("alert"):
                    alerts.append(res["alert"])
        except Exception as exc:
            any_failed = True
            alert = scheduler.build_alert_payload(
                level="error",
                retailer=slug,
                store="all",
                message=f"Failed: {exc}",
                run_key=f"{run_tag}-{slug}",
            )
            alerts.append(alert)
            scheduler.emit_json_log(
                "error",
                "retailer_run_failed",
                retailer=slug,
                run_key=f"{run_tag}-{slug}",
                worker_id=worker_id,
                status="failed",
                error=str(exc),
                stream=stream,
            )
            results.append(
                {
                    "retailer": slug,
                    "run_key": f"{run_tag}-{slug}",
                    "out_dir": None,
                    "status": "failed",
                    "quarantined": False,
                    "error": str(exc),
                    "alert": alert,
                }
            )

    date_str = scheduler.now_utc().strftime("%Y-%m-%d")
    summary_dir = out_root / "scheduler" / date_str / run_tag
    summary_dir.mkdir(parents=True, exist_ok=True)
    summary = {
        "run_tag": run_tag,
        "worker_id": worker_id,
        "mode": mode,
        "created_at_utc": scheduler.dt_utc_iso(scheduler.now_utc()),
        "tz_source": scheduler.TZ_SOURCE,
        "retailers": results,
        "alerts": alerts,
        "any_quarantined": any_quarantined,
        "any_failed": any_failed,
    }
    manifest_path = summary_dir / "scheduler_manifest.json"
    manifest_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    summary["manifest_path"] = str(manifest_path).replace("\\", "/")

    exit_code = 1 if any_failed else (2 if any_quarantined else 0)
    return summary, exit_code


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="M6 Daily Ingestion Scheduler Worker")
    mode_grp = ap.add_mutually_exclusive_group()
    mode_grp.add_argument("--once", action="store_true", help="execute a single pipeline pass and exit")
    mode_grp.add_argument("--daemon", action="store_true", help="run continuous scheduled loop")

    src_grp = ap.add_mutually_exclusive_group()
    src_grp.add_argument("--from-snapshots", action="store_true", help="replay from local snapshot/fixture dirs")
    src_grp.add_argument("--live", action="store_true", help="polite live HTTP scraping")

    ap.add_argument("--retailers", default="vero,stokomak,zito,kam", help="comma-separated retailer slugs")
    ap.add_argument("--snapshot-map", help="comma-separated retailer=dir overrides for --from-snapshots")
    ap.add_argument("--stores-map", help="comma-separated retailer=store1:store2 overrides for --live")
    ap.add_argument("--max-pages", type=int, default=50)
    ap.add_argument("--per-page", type=int, default=stokomak.DEFAULT_PER_PAGE)
    ap.add_argument("--delay", type=float, default=1.0)
    ap.add_argument("--max-retries", type=int, default=3)
    ap.add_argument("--base-backoff", type=float, default=60.0)
    ap.add_argument("--out-root", default="snapshots", help="root directory for snapshots and scheduler manifests")
    ap.add_argument("--lease-dir", default="snapshots/.leases", help="directory for active worker lease files")
    ap.add_argument("--run-tag", default="", help="run tag prefix (default: m6-YYYYMMDDTHHMMSSZ)")
    ap.add_argument("--worker-id", default="", help="worker identifier (default: hostname:pid)")
    ap.add_argument("--target-time", default="08:30", help="daily local HH:MM run window in Europe/Skopje")
    ap.add_argument("--interval-seconds", type=float, default=0.0, help="fixed sleep interval override for --daemon")
    ap.add_argument("--max-runs", type=int, default=0, help="max daemon iterations (0 = unlimited)")
    args = ap.parse_args(argv)

    retailers = [r.strip().lower() for r in args.retailers.split(",") if r.strip()]
    mode = "live" if args.live else "snapshots"
    worker_id = args.worker_id or scheduler.default_worker_id()
    out_root = Path(args.out_root)
    lease_dir = Path(args.lease_dir)
    snapshot_map = _parse_kv_map(args.snapshot_map)
    stores_map = _parse_stores_map(args.stores_map)

    if not args.daemon:
        run_tag = args.run_tag or ("m6-" + scheduler.now_utc().strftime("%Y%m%dT%H%M%SZ"))
        _summary, code = run_pipeline_pass(
            retailers=retailers,
            mode=mode,
            run_tag=run_tag,
            out_root=out_root,
            lease_dir=lease_dir,
            worker_id=worker_id,
            snapshot_map=snapshot_map,
            stores_map=stores_map,
            max_pages=args.max_pages,
            per_page=args.per_page,
            delay=args.delay,
            max_retries=args.max_retries,
            base_backoff=args.base_backoff,
        )
        return code

    # Daemon mode
    parts = args.target_time.split(":")
    target_h, target_m = int(parts[0]), int(parts[1])
    runs_done = 0
    last_code = 0

    while True:
        runs_done += 1
        base_tag = args.run_tag or ("m6-daemon-" + scheduler.now_utc().strftime("%Y%m%dT%H%M%SZ"))
        run_tag = f"{base_tag}-{runs_done}" if args.max_runs != 1 else base_tag
        _summary, last_code = run_pipeline_pass(
            retailers=retailers,
            mode=mode,
            run_tag=run_tag,
            out_root=out_root,
            lease_dir=lease_dir,
            worker_id=worker_id,
            snapshot_map=snapshot_map,
            stores_map=stores_map,
            max_pages=args.max_pages,
            per_page=args.per_page,
            delay=args.delay,
            max_retries=args.max_retries,
            base_backoff=args.base_backoff,
        )
        if args.max_runs and runs_done >= args.max_runs:
            break
        wait_sec = (
            args.interval_seconds
            if args.interval_seconds > 0
            else scheduler.seconds_until_next_window(target_hour=target_h, target_minute=target_m)
        )
        scheduler.emit_json_log(
            "info",
            "daemon_sleeping",
            worker_id=worker_id,
            sleep_seconds=round(wait_sec, 2),
            target_time=args.target_time,
        )
        time.sleep(wait_sec)

    return last_code


if __name__ == "__main__":
    sys.exit(main())
