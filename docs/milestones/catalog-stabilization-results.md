# Catalogue correctness and mobile-web stabilization — verification record

**Date:** 2026-11-10  
**Branch:** `fix/catalog-correctness-stabilization` (PR #7)  
**Status:** CODE CHANGES COMMITTED, live data repair NOT DONE, live verification NOT VERIFIED.

## Observed problems

1. The live comparison screenshot showed Olympus Greek yogurt **0% fat** grouped with **2% fat** (both 150 g). `matching/matcher.py` discarded all one-character tokens, thus removed the fat-percent digits. The matcher also removed meaning-bearing `СО` and `БЕЗ`.
2. The live search screenshot showed a 500 g KAM bread at 32 MKD with a unit-price annotation resembling **64 MKD / 1 g**. That price/denominator combination is inconsistent. The web template had displayed the unvalidated upstream pair verbatim.
3. Mobile navigation wrapped awkwardly and the search form used too much vertical space.
4. Freshness screenshots showed last published 2026-11-08 for KAM and 2026-10-28 for Vero, Stokomak and Zito. Whether the scheduler is failing or the source listings are unchanged is **not established**.

## Code changes

- `matching/matcher.py`: v2 signature preserves percent modifiers (`PCT0`, `PCT2`, etc.), one-character numeric variant tokens, and `СО`/`БЕЗ`. Existing `normalized_exact_v1` database method name remains for schema compatibility.
- `matching/tests.py`: adds tests for Olympus 0% vs 2%, decimal percentage equivalence, sugar/lactose variants and exact cross-retailer resolution.
- `web/app/formatting.py` + `main.py` + `templates/search.html`: show source-provided unit price only if the basis is understood and is approximately consistent with stated package quantity and a published current/regular sale price. Normalize unit-label presentation without changing numerical unit price. For inconsistent or unrecognized data, show `ед. цена непотврдена`, retain the source link and original API fields, and **do not** invent a corrected unit price.
- `web/tests/test_formatting.py`, `web/tests/test_pages.py`: regression cases for 500 g bread at 32 MKD with the misleading 64 MKD / g label, valid 64 MKD / kg, 100 g basis, litre and multipack, and server-rendered warning.
- `web/app/templates/search.html` + `static/site.css`: grouped search controls, balanced mobile navigation and more compact offer cards; no JS dependency for HTML content.
- `scripts/audit-catalog-correctness.sql`: **read-only** audit for contradictory verified fat percentages, with/without modifiers, suspect per-gram source labels, retailer offer freshness and recent run outcomes.
- `docs/contracts/matching-contract.md`: explains v2 signature behavior and migration safety.

## Verification matrix

| Check | Status | Notes |
|---|---|---|
| Correct matcher code committed | PASS | Signature no longer discards percentage and variant distinctions |
| Matcher regression tests | PENDING CI | See PR #7 GitHub Actions |
| Web unit-price validation code committed | PASS | Source numeric amount never re-labelled without basis verification |
| Web regression tests | PENDING CI | See PR #7 GitHub Actions |
| Existing M1–M14 regression suite | PENDING CI | CI jobs include adapter/matcher, FastAPI, web and Flutter |
| Browser smoke at 390 px + desktop | NOT VERIFIED | CSS/HTML changes require a new rendered screenshot |
| Original retailer source PDF verified for bread unit basis | NOT VERIFIED | Do not claim the source label is actually kg |
| Actual PostgreSQL canonical records reconciled | NOT DONE | No DB writes, migrations or OpenSearch reindex executed |
| Retailer scheduler freshness investigated against live host | NOT VERIFIED | Read-only SQL prepared; needs host/database access |
| Live AI and basket flows after repaired identities | NOT VERIFIED | Requires approved data repair and test run |

## Required owner-approved follow-up — database reconciliation

**Do not deploy the matching-signature fix alone and assume existing canonical IDs change.**

The existing `scripts/load-matches.sql` only upserts; it does not detach old auto-accepted matches. The partial unique index `uq_product_matches_active_retailer_product` prevents a retailer product being attached to a second active canonical identity while the old active row remains. A naive reload can either leave the wrong groups intact or fail with a constraint violation.

1. Back up the authoritative PostgreSQL database and immutable raw snapshots. Record affected canonical IDs, source SKUs, human-reviewed rows, basket references and historical observations.
2. Execute `scripts/audit-catalog-correctness.sql` **read-only**. Generate v2 match output on a disposable restored database and calculate an exact old→new identity diff.
3. Review manually approved/rejected rows; don't overwrite them. Produce a transactional reconciliation plan with explicit preconditions and rollback. Obtain owner approval for the *actual* database mutation.
4. Rebuild OpenSearch projections only after relational data reconciliation. Verify exact comparisons, price histories, AI candidates, basket optimization and any local basket entries pointing at superseded canonical IDs.
5. Recheck the source PDF for the specific bread's unit label. Only fix the parser or stored unit label if source evidence supports the change; otherwise keep the UI warning.

## Freshness investigation checklist

Compare `ingestion_runs.status`, quarantine reasons, last published timestamps, last fetched timestamps, source HTTP/PDF availability, scheduler execution logs and expected update cadence. Repeated retrieval of an unchanged published list is not the same thing as a scheduler failure. Do not delete healthy offers on failed ingestion.

## Deployment boundary

No live production data, Cloudflare Tunnel deployment, OpenSearch index, external AI credentials or Java rollback tree was modified by this PR. UI/browser changes remain unverified until rendered in a real browser.
