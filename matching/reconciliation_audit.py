"""READ-ONLY audit of stored active identities against current matcher signatures.

Input is the CSV exported by scripts/export-match-identity-audit.sql.
This utility NEVER connects to a DB and NEVER emits mutation SQL. An old
canonical ID cannot safely be replaced by a new hash without owner review.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from matching.matcher import MATCHER_VERSION, extract_signature

COLUMNS = (
    "source_slug", "sku_key", "retailer_product_id", "listing_name",
    "canonical_product_id", "canonical_key", "match_id", "review_status",
    "reviewed_at",
)
REPORT_COLUMNS = (
    "classification", "source_slug", "sku_key", "retailer_product_id",
    "match_id", "canonical_product_id", "old_canonical_key",
    "proposed_canonical_key", "old_group_splits", "new_key_spans_old_groups",
    "review_status", "reviewed_at", "listing_name",
)


def audit_rows(rows: list[dict[str, str]]) -> dict:
    """Classify every active match; all proposed changes are review-only."""
    if not rows:
        raise ValueError("Empty input: refusing to declare an empty database safe")
    old_to_new: dict[int, set[str]] = defaultdict(set)
    new_to_old: dict[str, set[int]] = defaultdict(set)
    seen_products: set[int] = set()
    records: list[dict] = []

    for row in rows:
        if any(key not in row for key in COLUMNS):
            raise ValueError("Missing input columns; use the supplied SQL export")
        try:
            product_id = int(row["retailer_product_id"])
            canonical_id = int(row["canonical_product_id"])
            match_id = int(row["match_id"])
        except (ValueError, TypeError) as exc:
            raise ValueError("Invalid numeric ID in match export") from exc
        if min(product_id, canonical_id, match_id) <= 0:
            raise ValueError("Match export contains a nonpositive ID")
        if product_id in seen_products:
            raise ValueError(f"Multiple verified identities for retailer product {product_id}")
        seen_products.add(product_id)
        status = (row.get("review_status") or "").strip()
        if status not in {"auto_accepted", "approved"}:
            raise ValueError("Input includes non-active matching status")
        if not (row.get("source_slug") and row.get("sku_key") and row.get("canonical_key")):
            raise ValueError("Source identity or canonical key is missing")

        signature = extract_signature(row.get("listing_name"))
        new_key = signature["canonical_key"] if signature is not None else ""
        if new_key:
            old_to_new[canonical_id].add(new_key)
            new_to_old[new_key].add(canonical_id)
        protected = status == "approved" or bool((row.get("reviewed_at") or "").strip())
        if protected:
            classification = "HUMAN_REVIEW_PROTECTED"
        elif not new_key:
            classification = "UNMATCHABLE_NEEDS_REVIEW"
        elif new_key != row["canonical_key"]:
            classification = "AUTO_KEY_CHANGED"
        else:
            classification = "UNCHANGED"

        records.append({
            "classification": classification,
            "source_slug": row["source_slug"],
            "sku_key": row["sku_key"],
            "retailer_product_id": product_id,
            "match_id": match_id,
            "canonical_product_id": canonical_id,
            "old_canonical_key": row["canonical_key"],
            "proposed_canonical_key": new_key,
            "review_status": status,
            "reviewed_at": row.get("reviewed_at") or "",
            "listing_name": row.get("listing_name") or "",
        })

    split_groups = {old: keys for old, keys in old_to_new.items() if len(keys) > 1}
    consolidation_candidates = {key: ids for key, ids in new_to_old.items() if len(ids) > 1}
    for rec in records:
        rec["old_group_splits"] = rec["canonical_product_id"] in split_groups
        rec["new_key_spans_old_groups"] = (
            bool(rec["proposed_canonical_key"])
            and rec["proposed_canonical_key"] in consolidation_candidates
        )
    records.sort(key=lambda x: (x["canonical_product_id"], x["retailer_product_id"]))
    changed = [r for r in records if r["classification"] != "UNCHANGED"
               or r["old_group_splits"] or r["new_key_spans_old_groups"]]
    summary = {
        "matcher_version": MATCHER_VERSION,
        "source_rows": len(records),
        "auto_key_changed": sum(r["classification"] == "AUTO_KEY_CHANGED" for r in records),
        "human_review_protected": sum(r["classification"] == "HUMAN_REVIEW_PROTECTED" for r in records),
        "missing_signature": sum(r["classification"] == "UNMATCHABLE_NEEDS_REVIEW" for r in records),
        "split_canonical_group_ids": sorted(split_groups),
        "consolidation_candidate_group_count": len(consolidation_candidates),
        "review_rows": len(changed),
        "safe_to_apply_automatically": False,
        "database_mutations_performed": 0,
    }
    return {"summary": summary, "all_rows": records, "review_rows": changed}


def read_export(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames or not set(COLUMNS).issubset(reader.fieldnames):
            raise ValueError("CSV schema mismatch (export scripts/export-match-identity-audit.sql)")
        return list(reader)


def _write_csv(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=REPORT_COLUMNS)
        writer.writeheader()
        writer.writerows({key: row.get(key, "") for key in REPORT_COLUMNS} for row in rows)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only v2 product-match impact audit")
    parser.add_argument("--input", required=True, type=Path, help="Active matches CSV export")
    parser.add_argument("--out", required=True, type=Path, help="Local output directory")
    args = parser.parse_args(argv)
    report = audit_rows(read_export(args.input))
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "summary.json").write_text(
        json.dumps(report["summary"], ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    _write_csv(args.out / "all_matches.csv", report["all_rows"])
    _write_csv(args.out / "review_required.csv", report["review_rows"])
    print(json.dumps(report["summary"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
