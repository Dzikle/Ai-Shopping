# M1 proposal - ingest the Vero price list

**Status:** APPROVED by owner 2026-10-28 (scope, fixtures, fetch window, Ramstore skip). Implemented same day; evidence in docs/milestones/current-status.md and scripts/test-m1.ps1 output.
**Depends on:** M0 (this work package).

## Goal
Replay the Vero published price list into PostgreSQL as store-specific offers with full provenance, without duplicate or corrupt records, verifiable by tests and by re-running.

## Validated basis (evidence in `docs/research/retailer-sources.md`)
- Source: `https://pricelist.vero.com.mk/` - static HTML, per-store pages `{storeId}_{page}.html`, 17 stores (ВЕРО 1–14, ЏАМБО 1–3).
- Verified row schema: name, selling price (incl. VAT), unit price (`ден/парче`), availability (Да/Не), category, regular price, discount price, discount %, promo type, promo validity dates, per-page "last updated" timestamp.
- robots.txt expresses no restrictions; no ToS prohibition found on the pricelist host (unlike Ramstore, which is blocked by its site terms - ADR-0005).

## Deliverables
1. **PostgreSQL schema (Flyway migrations):** `retailers`, `stores`, `retailer_products`, `offers_current`, `price_observations`, `promotions`, `ingestion_runs`, `raw_snapshots` (M1 scope; `canonical_products`/matching tables arrive in M2).
   - Prices `NUMERIC(12,2)`, never float; offer uniqueness on `(store_id, retailer_sku_key)`; observations immutable.
2. **Worker contract v1** (`docs/contracts/worker-contract.md`): adapter = fetch → snapshot → parse → normalize → emit typed records; job state (lease, status, retries, counters) owned by PostgreSQL `ingestion_runs`; language-agnostic (Python reference implementation).
3. **Vero adapter (Python):** politeness-first fetcher (single IP, modest rate, explicit timeout, honest UA), snapshot writer, HTML table parser with fixture-driven tests using real captured pages (at least store 89 pages 1–2), pagination walker with hard page cap.
4. **Snapshot archive:** filesystem layout `snapshots/{source}/{yyyy-mm-dd}/{run_id}/{url-hash}.html` + content SHA-256 recorded in `raw_snapshots`.
5. **Ingestion run checks:** row-count sanity vs previous run, quarantine on unexpected empty/abnormal results (ADR-0004); published timestamp from the page header stored separately from fetch time.
6. **One-shot replay CLI:** `ingest vero --run-id <id>` idempotent across re-runs; rerunning produces zero duplicate observations.
7. **Tests:** parser fixtures (real HTML), normalization edge cases (Cyrillic names, missing unit price, missing discount columns), idempotency test (two runs same data → same DB state), quarantine test.
8. **CI:** existing baseline job + job that runs the parser tests against fixtures (no network in tests).

## Non-goals (explicitly out of M1)
- No canonical product identity/matching (M2), no OpenSearch writes (M3), no basket logic (M4), no AI/MCP (M5), no scheduling/cron (M6), no Ramstore or KAM access.

## Estimated shape
~1 schema migration set, 1 Python package (`adapters/vero/`), 1 contract doc, fixtures (~2 real pages committed), CI wiring. No paid services, no cloud.

## Risks / open questions for the owner
1. Vero updates ~daily (page showed 28/10/2026 8:02) - confirm acceptable fetch window (proposal: once daily after 08:30 local).
2. Discounted and non-promoted rows coexist; M1 stores both regular and current price per row - confirm.
3. Committing real captured HTML fixtures to the repo: acceptable? (They are public price publications; content-hash dedup keeps them small.)
