# Active product-identity reconciliation — read-only preflight

**Date:** 2026-11-10  
**State:** Tooling prepared and committed; **NO live database change has been made**.  
**Baseline:** Matching signature `m2.v2` from catalog stabilization PR #7 (merged at `3e74336`).  
**Purpose:** Generate a reproducible impact report before migrating persisted `m2.v1`-era verified canonical mappings.

## Why this matters

In the real-data acceptance report, canonical product **2634** included Olympus 0%-fat yogurt and a Vero listing at **2%** (retailer product **984**). PR #7 fixed the matching algorithm, **not historical PostgreSQL rows**. Historical matches, basket references and OpenSearch projections may still refer to the previous canonical ID.

The original `scripts/load-matches.sql` only **upserts**; it never detaches old verified associations. A retailer product cannot have two active canonical identities due to `uq_product_matches_active_retailer_product`. The loader in this branch **fails closed** if staged auto-accepted matches would change an already-active canonical key. No automatic migration or destructive cleanup has been added.

## Execute the audit without any DB changes

Run from the repository root on the machine hosting the PostgreSQL Docker Compose stack. For the previously documented local dataset:

```powershell
./scripts/run-match-identity-audit.ps1 -Database ai_shopping_m10_diff_py
```

This runs `scripts/export-match-identity-audit.sql` inside a **READ ONLY PostgreSQL transaction**, copies only source product/match metadata to a local CSV, and processes it locally with Python's standard library.

Alternatively, for an already-exported CSV:

```powershell
python -B matching/reconciliation_audit.py --input path/to/current_active_matches.csv --out snapshots/matching/audit-manual
```

The CSV must contain the columns produced by `export-match-identity-audit.sql`. The input is the complete set of currently verified mappings, not just a sample, to correctly count group splits/consolidation candidates.

**Outputs:**

- `summary.json`: total verified rows, changed auto-accepted keys, protected human reviews, missing signatures, split legacy canonical IDs and consolidation candidates; `safe_to_apply_automatically=false`.
- `all_matches.csv`: every active mapping with the proposed v2 key and review classification.
- `review_required.csv`: changed or suspicious mappings. Inspect the old/new key and all members of split legacy groups.

The report never generates SQL UPDATE/DELETE, connects to a model provider or changes OpenSearch. CSV listing names are untrusted source text; avoid enabling spreadsheet macros or automatic formula execution when opening them.

## Important review gates

1. Save the audit outputs and a PostgreSQL backup. Confirm row counts and at least whether canonical ID 2634 is impacted as expected. Report any `UNMATCHABLE_NEEDS_REVIEW`, `HUMAN_REVIEW_PROTECTED` and consolidation candidates.
2. On a **disposable restored database**, generate a proposal for old canonical IDs → new v2 keys/IDs. Explicitly preserve reviewed approvals/rejections, GTIN/manual matches, untouched offers and immutable `price_observations`.
3. Assess history aggregation, basket requests, product detail URLs, local saved canonical IDs and OpenSearch projections. A new hashed canonical key can result in a **new integer canonical ID**; treat this as a client compatibility/migration issue.
4. Review per-record change counts, human exceptions and rollback plan. Only then seek **separate owner approval** to apply the concrete migration. Apply atomically and rebuild OpenSearch after verifying PostgreSQL.
5. Validate with real `GET /api/v1/products/compare`, history, basket optimization and Flutter/web checks. Do not call the bug resolved in deployed data until a real comparison shows the fat variants separated.

## Verification and limits

| Item | Status |
|---|---|
| Matcher v2 code and tests | Verified by PR #7 CI #45 (success) |
| Read-only export/analyzer written | Implemented in this branch |
| Protected loader preflight | Implemented in this branch; inspect CI checks |
| Unit/CLI tests for analyzer | Included in `matching/tests.py`; inspect CI checks |
| Actual PostgreSQL audit on the 5,145-offer dataset | **NOT RUN by this assistant** — no direct DB access |
| Reconciliation transaction, backup restoration, OpenSearch rebuild | **NOT RUN** (requires reviewed plan/explicit approval) |
| New real-data screenshots | **NOT VERIFIED** |

## Separate acceptance follow-ups

The open integrated-acceptance PR #6 (branch `integrated-acceptance`, based on older main) contains a real-dataset verification report and screenshots, but must be rebased/reviewed separately and should not be confused with the new reconciliation work. Its additional observation that basket API quantities `0` or `-2` may silently coerce to one pack should be handled as a **separate API-validation change**, not hidden in a data-repair PR.

Retailer publication freshness also needs scheduler/run-history investigation on the host; a 2026-10-28 published date by itself does not prove ingestion is stopped.
