"""CLI for deterministic product identity matching and review-queue generation.

Usage:
  python -B matching/cli.py --run-dirs snapshots/vero/...,snapshots/stokomak/...,snapshots/zito/... --out snapshots/matching/2026-10-28/m2-match
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from matching.matcher import MATCHER_VERSION, match_products


def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_products_from_run_dirs(run_dirs: list[Path]) -> list[dict]:
    products = []
    for rdir in run_dirs:
        manifest_path = rdir / "manifest.json"
        records_path = rdir / "records.ndjson"
        if not manifest_path.exists() or not records_path.exists():
            raise SystemExit(f"missing manifest.json or records.ndjson in {rdir}")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("quarantined"):
            raise SystemExit(f"refusing quarantined run dir in matcher: {rdir}")
        source_slug = manifest["source_slug"]
        for line in records_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            products.append(
                {
                    "source_slug": source_slug,
                    "sku_key": rec["sku_key"],
                    "listing_name": rec["listing_name"],
                    "category": rec.get("category"),
                }
            )
    return products


def write_match_outputs(canonical_list: list[dict], matches_list: list[dict], out_dir: Path) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "canonical_products.ndjson").write_text(
        "\n".join(json.dumps(c, ensure_ascii=False) for c in canonical_list)
        + ("\n" if canonical_list else ""),
        encoding="utf-8",
    )
    (out_dir / "product_matches.ndjson").write_text(
        "\n".join(json.dumps(m, ensure_ascii=False) for m in matches_list)
        + ("\n" if matches_list else ""),
        encoding="utf-8",
    )

    stage1 = [m for m in matches_list if m["review_status"] == "auto_accepted"]
    stage2 = [m for m in matches_list if m["review_status"] == "pending_review"]
    cross_ckeys = {
        m["canonical_key"]
        for m in stage1
        if m.get("evidence", {}).get("cross_retailer")
    }
    summary = {
        "matcher_version": MATCHER_VERSION,
        "created_at_utc": _now_utc_iso(),
        "canonical_products": len(canonical_list),
        "cross_retailer_canonical_products": len(cross_ckeys),
        "stage1_auto_accepted": len(stage1),
        "stage2_pending_review": len(stage2),
        "out": str(out_dir),
    }
    (out_dir / "matches_manifest.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return summary


def main(argv=None):
    ap = argparse.ArgumentParser(description="Deterministic product matcher (M2 / ADR-0003)")
    ap.add_argument(
        "--run-dirs",
        required=True,
        help="comma-separated adapter output directories containing manifest.json + records.ndjson",
    )
    ap.add_argument("--out", required=True, help="output directory for matching NDJSON files")
    args = ap.parse_args(argv)

    rdirs = [Path(p.strip()) for p in args.run_dirs.split(",") if p.strip()]
    products = load_products_from_run_dirs(rdirs)
    canonical_list, matches_list = match_products(products)
    summary = write_match_outputs(canonical_list, matches_list, Path(args.out))
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
