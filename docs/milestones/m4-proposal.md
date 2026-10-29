# M4 proposal — shopping lists, unit/quantity scaling & deterministic basket optimization

**Status:** Approved & implemented (2026-10-29).  
**Depends on:** M1 (Vero ingestion) + M2 (Stokomak & Zito ingestion, canonical identity, `product_matches`) + M3 (OpenSearch projections & Spring Boot REST API).

## Goal

Enable users and downstream AI/MCP tools (M5) to define shopping baskets (by canonical product ID or retailer product ID, with desired quantities/units) and run **deterministic**, repeatable basket pricing and optimization across single stores and multi-store combinations — with explicit missing-item semantics, unit/pack-size scaling, optional explicit substitute allowance, and full provenance (`sourceUrl`, `publishedTs`, `fetchedTs`).

## Architectural alignment (ADR-0001, ADR-0002, ADR-0003, AGENTS.md)

1. **Deterministic math in Java/SQL — never in an LLM (Master Plan):**
   - All basket totals, pack counts, unit conversions (`g`/`kg`, `ml`/`l`, `pcs`), savings calculations, and store-ranking decisions are computed deterministically in `BigDecimal` (`NUMERIC(12,2)` MKD) inside the Spring Boot service layer backed by PostgreSQL (`offers_current`).
2. **Identity vs. equivalence/substitution (ADR-0003):**
   - By default (`allowSubstitutes = false`), a basket item requested by `canonicalProductId` matches **only** verified exact-identity SKUs (`product_matches.review_status IN ('auto_accepted', 'approved')`).
   - When `allowSubstitutes = true`, if a store lacks an exact-identity offer for an item, the optimizer may propose a clearly flagged **substitute** (`isSubstitute = true`, with explicit `substituteReason` and `confidence`) from either:
     - Stage-2 `pending_review` high-overlap candidates of the same declared size, or
     - Same-category / same-unit-type alternatives matching the query tokens.
   - Substitutes are never silently merged into exact identity.
3. **Explicit missing-item behavior & store coverage:**
   - A store that carries 4 of 5 requested items must never appear "cheaper" than a store that carries all 5 items simply because the 5th item's price was omitted.
   - Single-store rankings sort primarily by **`itemsCovered DESC` (coverage ratio)**, and secondarily by **`totalMkd ASC`**. Every store result lists both `coveredItems` (with exact store offer, packs needed, line total, `publishedTs`, `sourceUrl`) and `missingItems`.
4. **Unit & quantity scaling:**
   - A basket line can specify either:
     - `count` (e.g. `2` packs of `canonicalProductId = 1116`), or
     - a target physical quantity (`desiredQuantity` + `desiredUnit`, e.g. `1000 g` or `1 l`), which deterministically computes `packsNeeded = ceil(desiredQuantityInBaseUnit / packQuantityInBaseUnit)`.

## Deliverables

1. **Schema migration `migrations/V3__m4_baskets.sql`:**
   - `shopping_lists`:
     - `id BIGSERIAL PRIMARY KEY`, `name TEXT NOT NULL`, `city_filter TEXT NULL`, `created_at TIMESTAMPTZ NOT NULL DEFAULT now()`, `updated_at TIMESTAMPTZ NOT NULL DEFAULT now()`.
   - `shopping_list_items`:
     - `id BIGSERIAL PRIMARY KEY`, `shopping_list_id BIGINT NOT NULL REFERENCES shopping_lists(id) ON DELETE CASCADE`, `canonical_product_id BIGINT NULL REFERENCES canonical_products(id)`, `retailer_product_id BIGINT NULL REFERENCES retailer_products(id)`, `item_label TEXT NULL`, `quantity NUMERIC(12,3) NOT NULL DEFAULT 1`, `unit TEXT NOT NULL DEFAULT 'pack'`, `Position INT NOT NULL DEFAULT 0`, `CHECK (canonical_product_id IS NOT NULL OR retailer_product_id IS NOT NULL)`.

2. **Deterministic Basket Optimizer & Unit Converter (`backend/.../service/BasketOptimizerService.java`, `UnitConversionUtil.java`):**
   - **Unit normalization & pack scaling**:
     - Normalizes `kg -> 1000g`, `g -> 1g`, `l -> 1000ml`, `ml -> 1ml`, `pack`/`pcs`.
     - Computes integer `packsNeeded >= 1` and `lineTotalMkd = priceCurrent * packsNeeded`.
   - **Single-Store Evaluation (`evaluateSingleStores`)**:
     - Evaluates every candidate store (filtered optionally by `city`, `retailer`, `inStockOnly`), returning coverage (`coveredCount / totalRequested`), `totalMkd`, `estimatedSavingsVsMaxSingleStoreMkd`, itemized line breakdowns with provenance, and explicit `missingItems`.
   - **Multi-Store Split Optimization (`optimizeMultiStore`)**:
     - Deterministically finds the cheapest **k-store combination** (`maxStores`, default `2`, capped at `3`) that maximizes item coverage first and minimizes total MKD second.
     - Enforces a configurable `minSplitSavingsMkd` threshold (default `0.00` MKD; if splitting across 2 stores saves less than `minSplitSavingsMkd` compared to the best single store with equal coverage, recommends the single store).
     - Produces a per-store shopping checklist (`storeAllocations`) and net savings vs. the best single-store option.

3. **REST API Endpoints (`backend/.../controller/BasketController.java`, `docs/contracts/basket-api-contract.md`):**
   - `POST /api/v1/baskets/optimize` — stateless deterministic optimization for an ad-hoc basket payload (canonical/retailer product IDs, quantities/units, `city`, `retailers`, `maxStores`, `minSplitSavingsMkd`, `allowSubstitutes`, `inStockOnly`).
   - `POST /api/v1/baskets/lists` — create a persisted shopping list (`shopping_lists` + `shopping_list_items`).
   - `GET /api/v1/baskets/lists/{listId}` — retrieve a saved shopping list and its items.
   - `POST /api/v1/baskets/lists/{listId}/optimize` — run single-store + multi-store optimization against a saved shopping list.

4. **Tests, Verification & CI (`CatalogApiTest` / `BasketOptimizerTest.java`, `scripts/test-m4.ps1`, `.github/workflows/ci.yml`):**
   - JUnit 5 unit tests covering:
     - unit conversion (`g`/`kg`, `ml`/`l`, `pack`) and `ceil` pack-scaling math;
     - missing-item ranking (a 3/3 covered store always ranks above a 2/3 covered store even if the 2/3 partial sum is smaller);
     - multi-store split optimization across Vero, Stokomak, and Zito;
     - `minSplitSavingsMkd` threshold behavior;
     - `allowSubstitutes = false` vs `allowSubstitutes = true` separation (ADR-0003).
   - End-to-end `scripts/test-m4.ps1`:
     - Populates scratch DB `ai_shopping_m4_test` with Vero + Stokomak + Zito fixtures (`V1` + `V2` + `V3` migrations).
     - Creates a persisted multi-item shopping list spanning cross-retailer canonical products and single-retailer items.
     - Verifies repeatable single-store totals, explicit missing-item reporting, and multi-store split savings via the running Spring Boot REST API.

## Exit criterion (roadmap M4)

Shopping lists, unit conversion, and deterministic single-store and multi-store basket optimization produce repeatable totals and explicit missing-item behavior over the real Vero, Stokomak, and Zito catalog data.

## Non-goals (explicitly out of M4)

Natural-language chat / MCP server exposure (M5), user authentication / multi-tenant accounts, delivery-fee modeling, and unattended cron scheduling (M6).
