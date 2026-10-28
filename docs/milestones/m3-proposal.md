# M3 proposal — versioned OpenSearch projections & search/comparison REST API

**Status:** Approved & implemented (2026-10-28).
**Depends on:** M1 (Vero ingestion) + M2 (Stokomak & Zito ingestion, canonical identity, `product_matches`).

## Goal

Expose the authoritative PostgreSQL catalog (`retailers`, `stores`, `canonical_products`, `retailer_products`, `product_matches`, `offers_current`, `price_observations`, `promotions`) through versioned, rebuildable OpenSearch projections (`*_v1` behind aliases) and a Spring Boot (Java 21) REST API for product search, filtering, store-level comparison, and price history — with explicit source provenance and freshness on every response.

## Architectural alignment (ADR-0001, ADR-0002, ADR-0003)

1. **PostgreSQL remains sole authority (ADR-0002):**
   - OpenSearch indexes are disposable projections built exclusively from PostgreSQL state.
   - Reindexing writes to a timestamped/versioned physical index (e.g. `offers_v1_<run_id>`), verifies document counts, and atomically flips the read alias (`offers` / `offers_v1`) via `_aliases`.
   - Dropping all OpenSearch indexes and re-running reindex restores 100% of search state with zero data loss.
2. **Identity vs. substitution (ADR-0003):**
   - Cross-retailer product comparison endpoints join only verified identity matches (`product_matches.review_status IN ('auto_accepted', 'approved')`).
   - Ambiguous `pending_review` candidates are never folded into canonical comparisons; a read-only review-queue endpoint exposes them separately with their `evidence` JSON.
3. **Provenance & freshness (AGENTS.md #3, #8):**
   - Every offer and comparison response includes `retailerSlug`, `storeExternalKey`, `storeName`, `priceCurrent`, `unitPrice`, `unitLabel`, `regularPrice`, `discountPrice`, `discountPct`, `promoType`, `availability`, `publishedTs`, `fetchedTs`, and `sourceUrl`.

## Deliverables

1. **Versioned OpenSearch index templates & reindex pipeline (`search/` / `backend/`):**
   - Index mappings and alias management for:
     - `products_v1` (alias `products`): canonical products + unmerged retailer products, normalized Macedonian Cyrillic tokens, size/unit fields, retailer coverage count, min/max current price.
     - `offers_v1` (alias `offers`): store-specific current offers with price, unit price, promo metadata, availability, `published_ts`, `fetched_ts`, `source_url`, and canonical product link (when verified).
     - `stores_v1` (alias `stores`): retailer slug/name, store external key, name, address, city.
   - Deterministic reindex runner (`scripts/reindex-opensearch.ps1` + backend/CLI reindexer) that reads from PostgreSQL, bulk-indexes into a fresh target index, and atomically swaps aliases.

2. **Spring Boot (Java 21) REST API (`backend/`):**
   - Built with `maven:3.9.9-eclipse-temurin-21` (cached locally and in CI), Flyway validation compatible with `migrations/V1__*.sql` and `V2__*.sql`.
   - Read-only REST endpoints:
     - `GET /api/v1/health` — DB + OpenSearch projection status and index document counts.
     - `GET /api/v1/stores?retailer=&city=` — list stores with active offer counts and latest `published_ts`.
     - `GET /api/v1/offers/search?q=&retailer=&storeId=&category=&inStockOnly=&promoOnly=&minPrice=&maxPrice=&sort=&page=&size=` — search and filter store offers with provenance and freshness.
     - `GET /api/v1/products/compare?q=&minRetailers=2` — side-by-side cross-retailer comparison for canonical products (`auto_accepted`/`approved` matches only), returning per-retailer min/max prices, store counts, spread, and individual store offers.
     - `GET /api/v1/products/{canonicalId}/history` — immutable `price_observations` timeline across retailers and stores for a canonical product.
     - `GET /api/v1/matches/review-queue` — read-only inspection of `pending_review` Stage-2 candidate pairs and their `evidence` JSONB.

3. **Tests, verification & CI (`scripts/test-m3.ps1`, `.github/workflows/ci.yml`):**
   - JUnit 5 tests for query building, alias swap, comparison aggregation, and controller contracts (`mvn test` inside `maven:3.9.9-eclipse-temurin-21`).
   - End-to-end `scripts/test-m3.ps1`: loads M1+M2 fixtures into PostgreSQL, runs reindex into OpenSearch, verifies alias swap and index counts, queries REST endpoints, and asserts exact prices, store attribution, and `published_ts` freshness.
   - CI workflow extended to run backend tests, OpenSearch reindex, and `scripts/test-m3.ps1` against live PostgreSQL 18.6 + OpenSearch 3.9.0.

## Exit criterion (roadmap M3)

Real products from Vero, Stokomak, and Zito searchable and comparable via the REST API with verified source URLs, store attribution, and `published_ts` freshness; OpenSearch indexes demonstrably disposable and rebuildable from PostgreSQL in one command.

## Non-goals (explicitly out of M3)

Shopping basket optimization (M4), MCP/AI agent tools and vector embeddings (M5), scheduled unattended cron jobs and alerting (M6), write/mutation endpoints for public clients.

## Local environment note

`maven:3.9.9-eclipse-temurin-21` and `postgres:18.3` are already cached on this machine; `opensearchproject/opensearch:3.9.0` is not yet in the local Docker image cache (and non-interactive shells cannot pull new images due to the Windows credential helper). Either:
- you run `docker pull opensearchproject/opensearch:3.9.0` once in a normal terminal so `scripts/test-m3.ps1` runs against live local OpenSearch 3.9.0, **or**
- the API also supports a PostgreSQL-backed search fallback / MockOpenSearch test harness locally while full OpenSearch 3.9.0 runs in CI.
