# Project status — 2026-11-02

## Implemented (M0, this session)
- **Dependency verification:** Spring Boot 4.1.2 GA (stable), OpenSearch 3.9.0 (2026-09-29), PostgreSQL 18.6 (current 18.x), Java 21 LTS — all compatible with the planned stack. Recorded in ADR-0001/0002.
- **Upstream reuse audit completed:** all four candidate repos audited at pinned commits (`2f951f1` KortingKlok/archived, `aff6880` open-supermarkets, `efb2e0a` checkjebon, `36d5992` price-scraper), MIT confirmed via license blob SHAs, exact reusable file paths recorded in `docs/research/open-source-reuse-audit.md`.
- **Retailer validation:** Vero pricelist fully validated (static HTML, per-store paginated pages `{storeId}_{page}.html`, unit prices, promotions, last-updated timestamp) → recommended first source; Ramstore blocked by its own site terms pending written consent; KAM format unresolved. See `docs/research/retailer-sources.md` and ADR-0005.
- **ADRs 0001–0005** written in `docs/adr/`.
- **Baseline + CI:** `docker-compose.yml` (PostgreSQL + OpenSearch, image-pinned, healthchecked; images overridable via env for local runs), `scripts/validate-baseline.ps1` (also validates .env parsing and versions), `.github/workflows/ci.yml` (docs check + full stack up --wait + validation + teardown), `.gitattributes` (LF normalization).

## Implemented (M1, this session) — owner-approved
- **Schema `migrations/V1__m1_schema.sql`** (Flyway-compatible naming, applied via psql until Spring Boot adopts Flyway): `retailers`, `stores` (17 Vero/Джамбо stores seeded from the validated index page), `retailer_products`, `ingestion_runs`, `raw_snapshots`, `offers_current`, `price_observations` (immutable, dedup on `(retailer_product_id, store_id, published_ts, price_current)`), `promotions` (`NULLS NOT DISTINCT` for nullable promo dates). NUMERIC(12,2) prices, CHECK constraints, provenance columns (`source_url`, `fetched_ts`, `published_ts`, `raw_snapshot_id`, `run_id`).
- **Vero adapter** (`adapters/vero/`, stdlib-only Python): tolerant HTMLParser for the malformed page markup; 10-column row schema; handles both header variants (page 2 discount column lacks `(со ДДВ)`); pagination links; `Да/Не` → `in_stock/out_of_stock`; Europe/Skopje timestamps (zoneinfo with +01:00 fallback); M1 `sku_key` = sha256(normalized name + category) as documented in ADR-0003.
- **CLI** (`adapters/vero/cli.py`): offline replay (`--from-snapshots`) and polite live fetch (`--url`, 1 s delay, 50 pages/store, hard 200-page cap); byte-exact snapshot storage + `snapshots.ndjson` + `records.ndjson` + `manifest.json`.
- **Quarantine policy:** header-without-rows page → run quarantined; loader refuses to ingest quarantined runs (records run, never deletes live offers — AGENTS.md #6).
- **Loader** (`scripts/load-records.sql` via `scripts/load-records.ps1`): staged COPY of NDJSON into the DB; idempotent inserts/upserts; run finalize.
- **Fixtures:** byte-exact captures of 2026-10-28 committed under `tests/fixtures/vero/` (`89_1.html` 277,348 B, `89_2.html` 287,980 B, `index.html` 3,949 B) + synthetic empty-page fixture for the quarantine test.

## Implemented (M2, this session) — owner-approved
- **Shared normalization (`adapters/common/`)**: stdlib-only shared price/unit-price/percent/promo-cell/date-range/timestamp/availability normalizer, HTML `RowParser`, and declared size extractor (`parse_declared_size`, canonicalizing mass to `g`, volume to `ml`, multipacks to `{N}x{val}{unit}`).
- **Vero refactor onto `adapters/common/`**: `adapters/vero/vero.py` delegates normalization and row parsing to `adapters/common/`; all 22 existing Vero unit tests pass unchanged.
- **Second independent adapter (`adapters/stokomak/`)**: covers the shared `*.proverkanaceni.mk` statutory price-check platform for both **Stokomak** (`stokomak.proverkanaceni.mk`) and **Zito** (`zito.proverkanaceni.mk`):
  - `<select name="org">` store discovery (`parse_index`) handling sparse `org` IDs (Zito starts at `org=2`).
  - Query-parameter store pages (`?org={org}&perPage={n}&page={k}`), 6-column standard rows and 9-column promotional rows (`299 ден.\n Попуст:23%`, `23.10.2026 до \n29.10.2026`), `1кгр = 142.00 ден.` / `100gr = ...` unit prices, pagination links, and quarantine on empty-store responses (`Нема податоци за прикажување` on Zito `org=1`).
- **Schema `migrations/V2__m2_identity.sql`** per ADR-0003:
  - `canonical_products` (`canonical_key`, `canonical_name`, `normalized_tokens`, `normalized_size`, `quantity_value`, `quantity_unit`, `pack_count`, `gtin`).
  - `product_matches` (`retailer_product_id` → `canonical_product_id`, `method`, `confidence`, `review_status`, `evidence` JSONB, review workflow fields, partial unique index `uq_product_matches_active_retailer_product` enforcing at most one active identity per `retailer_product_id`).
  - Seeds `stokomak` (81 stores) and `zito` (94 stores) from validated 2026-10-28 selectors.
- **Deterministic matching & review queue (`matching/`)**:
  - **Stage 1 (`normalized_exact_v1`)**: exact normalized word-token bag (preposition stopwords stripped) + canonical declared size → `auto_accepted` (`confidence = 1.000`). Unsized items never auto-merge.
  - **Stage 2 (`candidate_token_size_v1`)**: same canonical declared size + high token overlap (`>= 2` shared tokens, Jaccard `>= 0.60` or strict token subset) across different retailers → `pending_review` queue with full token-diff `evidence` JSONB; excluded from active price comparisons until human approval.
  - Loader `scripts/load-matches.sql` / `scripts/load-matches.ps1` upserts canonical products and matches idempotently while preserving human-reviewed rows (`WHERE reviewed_at IS NULL`).
- **Cross-retailer comparison & history report**: `scripts/report-cross-retailer.sql` + `scripts/report-cross-retailer.ps1` produces side-by-side multi-retailer price comparisons, immutable `price_observations` history per canonical product, and the Stage-2 review queue listing.
- **Fixtures:** byte-exact captures committed under `tests/fixtures/stokomak/` (selector + 3 stores: `org=1, 3, 14`) and `tests/fixtures/zito/` (selector + 3 stores: `org=2, 8, 13` + real `empty_1_1.html` quarantine capture), marked `-text` in `.gitattributes`.
- **CI:** extended `.github/workflows/ci.yml` to run all 4 unit test suites (`common`, `vero`, `stokomak`, `matching`) + `scripts/test-m1.ps1` + `scripts/test-m2.ps1`.

## Implemented (M3, this session) — owner-approved
- **Versioned OpenSearch index mappings (`search/mappings/`)** per ADR-0002:
  - `stores_v1.json`, `offers_v1.json`, `products_v1.json` (`dynamic: strict`, Macedonian/Cyrillic-compatible `text` + `.keyword` subfields, nested `offers` summaries on canonical products).
- **PostgreSQL projection exporter & atomic OpenSearch reindexer (`scripts/export-projection-docs.sql`, `search/reindexer.py`, `scripts/reindex-opensearch.ps1`)**:
  - Exports authoritative PostgreSQL state (`stores`, `offers_current`, `canonical_products` + `product_matches` with `review_status IN ('auto_accepted', 'approved')`) to NDJSON.
  - Creates physical indexes `stores_v1_<tag>`, `offers_v1_<tag>`, `products_v1_<tag>`, bulk-indexes in bounded batches, verifies `_count`, atomically swaps aliases (`stores`/`stores_v1`, `offers`/`offers_v1`, `products`/`products_v1`) via `POST /_aliases`, and deletes superseded physical indexes.
- **Spring Boot 4.1.2 (Java 21) Read-Only Search & Comparison REST API (`backend/`, `docs/contracts/search-api-contract.md`)**:
  - `GET /api/v1/health`, `GET /api/v1/stores`, `GET /api/v1/offers/search`, `GET /api/v1/products/compare`, `GET /api/v1/products/{canonicalId}/history`, `GET /api/v1/matches/review-queue`.
  - **Automatic PostgreSQL fallback (ADR-0002)**: when OpenSearch is unreachable or unpopulated, `/stores`, `/offers/search`, and `/products/compare` automatically serve from authoritative PostgreSQL tables (`sourceEngine = "postgresql_fallback"`).

## Implemented (M4, this session) — owner-approved
- **Schema `migrations/V3__m4_baskets.sql`**:
  - `shopping_lists` (`id`, `name`, `city_filter`, `created_at`, `updated_at`) and `shopping_list_items` (`shopping_list_id`, `canonical_product_id`, `retailer_product_id`, `item_label`, `quantity`, `unit` (`pack`/`pcs`/`g`/`kg`/`ml`/`l`), `position`).
- **Deterministic Unit Conversion & Basket Optimization Engine (`backend/`, `docs/contracts/basket-api-contract.md`)**:
  - `UnitConversionUtil`: normalizes `g`/`kg`, `ml`/`l`, `pack`/`pcs`, converts requested amounts to base units, and deterministically computes integer `packsNeeded = ceil(requestedBase / perSkuBase)`.
  - `BasketOptimizerService`:
    - **Single-store evaluation (`singleStoreRankings`)**: ranks stores by `itemsCovered DESC` (coverage first), then `exactMatchesCount DESC`, then `totalMkd ASC`, then `storeId ASC`. Explicitly reports `missingItems` (`no_offer_at_store`, `product_not_found_in_catalog`) so partial stores never masquerade as cheaper full baskets.
    - **Multi-store split optimization (`bestMultiStorePlan`)**: evaluates `1..maxStores` (default `2`, max `3`) store combinations, maximizing item coverage first and minimizing total MKD second, and checks `savingsVsBestSingleStoreMkd >= minSplitSavingsMkd`.
    - **Identity vs. substitution (ADR-0003)**: strict exact identity (`auto_accepted`/`approved`) by default (`allowSubstitutes = false`); when `allowSubstitutes = true`, clearly flags Stage-2 `pending_review` candidates with `isSubstitute = true`, `substituteReason = "stage2_pending_review_candidate"`, and `matchConfidence`.
  - **REST endpoints (`BasketController`)**:
    - `POST /api/v1/baskets/optimize` (stateless ad-hoc basket optimization)
    - `POST /api/v1/baskets/lists` (create persisted shopping list)
    - `GET /api/v1/baskets/lists/{listId}` (fetch persisted shopping list)
    - `POST /api/v1/baskets/lists/{listId}/optimize` (optimize persisted shopping list with optional parameter overrides)

## Implemented (M5, owner-directed 2026-11-02) — pending owner review
- **Bounded read-only MCP server (`mcp_server/`, Python 3.12 stdlib only, no DB/JVM/Docker dependency):**
  - `contract.py`: versioned tool contract (`MCP_TOOLS_VERSION = "v1"`) and every hard cap — single source of truth for schemas, docs and tests.
  - `api_client.py`: method-aware **read-only route allowlist** (6 routes; persisted list creation, review queue, writes and path traversal all raise `ReadOnlyViolation`), no-redirect opener, 10 s timeout, 2 MB response cap, 1 KB URL cap, structured `UpstreamError`.
  - `tools.py`: 9 deterministic **pass-through** handlers — `search_products`, `get_product_details`, `compare_product_prices`, `get_price_history`, `find_stores`, `find_current_discounts`, `suggest_product_substitutes`, `optimize_shopping_basket`, `get_catalog_health`. No price/unit/pack/basket arithmetic; only presentation metadata (`provenance`, `truncated`, `identityScope`, `equivalenceStatus`, `computation`).
  - `server.py`: JSON-RPC 2.0 over MCP stdio — `initialize` (protocol `2025-06-18`/`2025-03-26`), notifications, batch frames, `ping`, `tools/list`, `tools/call`; bounds on inbound frames (256 KB) and tool payloads (1 MB); protocol errors `-32700/-32600/-32601/-32602`; tool failures returned in-band with `isError: true`.
  - `cli.py`: stdio entry point (`python -B -m mcp_server.cli`), `--list-tools` contract dump, env config `AI_SHOPPING_API_BASE` / `AI_SHOPPING_API_TIMEOUT` / `AI_SHOPPING_MAX_RESPONSE_BYTES`.
  - `mock_catalog_api.py`: in-process mock of the M3/M4 REST API using the committed Vero/Stokomak/Zito prices and provenance, with request recording and forced-failure switch.
- **Identity vs. equivalence preserved (ADR-0003/ADR-0004):** `compare_product_prices`/`get_product_details` report `identityScope: "verified_identity_only"`; `suggest_product_substitutes` derives the seed category from the backend offer record and labels every candidate `equivalenceStatus: "not_verified_equivalent"`.
- **Provenance & no fabrication:** every offer-bearing result carries per-item `sourceUrl`/`publishedTs`/`fetchedTs` plus a `provenance` summary; unreachable/failed upstream returns `upstream_unavailable` / `upstream_error` (with `upstreamStatus`) instead of prices.
- **Scope correction:** the master plan's `find_nearby_stores` is **not** shipped as a radius search — the authoritative schema has no store geo-coordinates, so `find_stores` offers a city text filter and states `geoScope: "city_text_filter_only"`.
- **Docs:** `docs/milestones/m5-proposal.md`, `docs/contracts/mcp-tools-contract.md` (transport, tool catalogue, schemas, hard limits, error reasons, allowlist, client config).
- **Tests & CI:** `mcp_server/tests.py` → **31/31 OK** (protocol lifecycle, batch frames, schema/limit contract, filter forwarding, provenance, discount ordering, substitute labelling, basket payload forwarding + repeatable backend totals, invalid-line rejection without API calls, upstream 5xx/unreachable, allowlist/path-escape/redirect refusal, real stdio subprocess round-trip, `--list-tools`). `scripts/test-m5.ps1` added (contract suite + tool snapshot + optional live `initialize → tools/list → get_catalog_health` handshake). The three `ci.yml` edits are specified in `docs/ci/m5-ci-steps.md` and **await the owner** (agent token lacks `workflows` permission).

## Execution evidence (2026-10-29 → 2026-11-02, local)
- Unit tests (`python:3.12-slim` stdlib + JUnit 5 in `maven:3.9.9-eclipse-temurin-21`):
  - `adapters/common/tests.py` → **8/8 OK**
  - `adapters/vero/tests.py` → **22/22 OK**
  - `adapters/stokomak/tests.py` → **9/9 OK**
  - `matching/tests.py` → **5/5 OK**
  - `search/tests.py` → **2/2 OK**
  - `mcp_server/tests.py` → **31/31 OK** (2026-11-02, native `python3 -B mcp_server/tests.py`, stdlib only)
  - `backend` (`mvn -B test package`) → **6/6 JUnit tests OK (`CatalogApiTest` 3/3 + `BasketOptimizerTest` 3/3), BUILD SUCCESS**
- `scripts/test-m1.ps1` → **M1 TEST OK**
- `scripts/test-m2.ps1` → **M2 TEST OK**
- `scripts/test-m3.ps1` → **M3 TEST OK**
- `scripts/test-m4.ps1` → **M4 TEST OK**:
  - Applied `V1` + `V2` + `V3` migrations (`PASS v3_schema_tables_present`) and loaded Vero + Stokomak + Zito fixtures.
  - Created persisted 3-item shopping list (`PASS shopping_list_created`, `PASS shopping_list_get_verified`).
  - Verified repeatable totals across consecutive optimization runs (`PASS repeatable_basket_totals`, `bestSingle = 519.00 MKD`, `bestMulti = 498.00 MKD`).
  - Verified unit conversion & pack scaling (`800g` of `400g` product → `packsNeeded = 2`, `lineTotal = 360.00 MKD`).
  - Verified coverage-first ranking and explicit missing-item reporting (`bestSingle` covered `3/3` at Zito; partial store covered `2/3` with explicit `missingReason = no_offer_at_store`).
  - Verified 2-store split optimization (`storesUsed = 2`, `totalMkd = 498.00 MKD`, `savingsVsBestSingle = 21.00 MKD`).
  - Verified ADR-0003 substitute separation (`allowSubstitutes = false` vs `allowSubstitutes = true` on `canonicalId = 897`, `isSubstitute = true`, `confidence = 0.80`).
- **M5 verification (2026-11-02):**
  - `python3 -B mcp_server/tests.py` → **31/31 OK** — lifecycle/`tools/list` contract, bounds rejection, filter forwarding (`retailer`, `promoOnly`, `size`), provenance aggregation, discount ordering (23% → 15%), substitute labelling (`canonicalId 898` candidate only, `not_verified_equivalent`), basket forwarding (`800 g` → backend `packsNeeded = 6`, `lineTotalMkd = 374.00`; `bestSingle.totalMkd = 498.00`, `bestMulti.totalMkd = 483.50` repeatable), 11 invalid-basket cases rejected with **zero** backend calls, upstream `500` → `upstream_error` then recovery, unreachable API → `upstream_unavailable`, allowlist blocks `POST /baskets/lists`, `DELETE`, path escape and redirects, real stdio subprocess round-trip (initialize → notification → `search_products`).
  - `python3 -B mcp_server/cli.py --list-tools` → 9 tools, 6 allowlisted routes, all `readOnlyHint`.
  - Existing suites re-run unchanged: `adapters/common` 8/8, `adapters/vero` 22/22, `adapters/stokomak` 9/9, `matching` 5/5, `search` 2/2.

## Blockers / limitations
- Java, Maven, psql not installed natively on this machine (containers and CI provide them; `maven:3.9.9-eclipse-temurin-21` already cached).
- Docker image pulls fail from agent/automation shells (credential helper requires an interactive session). Workaround used: locally cached images; new images must be pulled by the owner or via CI.
- **No OpenSearch image cached locally** → local M3 integration test verifies against `search/mock_opensearch.py` + PostgreSQL fallback; CI runs against pinned `opensearchproject/opensearch:3.9.0`.
- Local Postgres runs 18.3 (cached image) via `POSTGRES_IMAGE=postgres:18.3` override; CI pins 18.6. Same major version; acceptable.
- `ceni.tinex.mk` (port 442) timed out during M2 validation and remains deferred until reachable; `ramstore.com.mk` remains blocked pending written consent.
- `*.proverkanaceni.mk` has slow/unreachable IPv6 in some environments; IPv4 reaches the host in ~0.5s.
- **M5 environment note:** the MCP layer needs no Docker/JVM/PostgreSQL, so `mcp_server/tests.py` was verified natively (Python 3.11/3.12 stdlib, 31/31). `scripts/test-m5.ps1` requires PowerShell 7 and therefore runs in CI (`pwsh`); its live handshake step needs `-ApiBase` with a running Spring Boot API.
- **Workflow permission blocker (M5):** the automation token cannot push `.github/workflows/ci.yml` (`refusing to allow a GitHub App to create or update workflow ... without workflows permission`). The M5 CI steps (doc check, `mcp_server/tests.py`, `scripts/test-m5.ps1`) are therefore documented in `docs/ci/m5-ci-steps.md` for the owner to apply; until then CI does not execute the M5 suite, though it is green when run locally and via `scripts/test-m5.ps1`.
- Local clone lives at `C:\Dev\Personal\ao shopping` (outside OneDrive ✓).

## Resolved owner decisions
- **M1 (`docs/milestones/m1-proposal.md`):** M1 scope approved; daily fetch window after 08:30 local; real Vero HTML fixtures committed; Ramstore skipped pending written consent.
- **M2 (`docs/milestones/m2-proposal.md`):** Stokomak + Zito approved; 3 stores/retailer subset for M2; exact deterministic match + Stage-2 review queue (no LLM in M2); byte-exact HTML fixtures committed.
- **M3 (`docs/milestones/m3-proposal.md`):** M3 scope approved; OpenSearch primary with automatic PostgreSQL fallback; strictly read-only `GET /api/v1/*` surface.
- **M4 (`docs/milestones/m4-proposal.md`):** M4 scope approved (persisted `shopping_lists` + stateless/persisted optimization); coverage-first ranking (`itemsCovered DESC`, then `totalMkd ASC`) with `maxStores=2..3` and `minSplitSavingsMkd`; strict exact identity by default (`allowSubstitutes=false`) and flagged Stage-2 substitutes (`isSubstitute=true`) when `allowSubstitutes=true`.
- **M5 (2026-11-02, owner instruction "proceed working on the project"):** implemented `docs/milestones/m5-proposal.md` — bounded, strictly read-only MCP tool layer over the M3/M4 REST API; nine tools; no AI-side arithmetic; `allowSubstitutes=false` default semantics preserved; `find_stores` replaces `find_nearby_stores` until authoritative store coordinates exist. **Pending owner review/approval before M6.**

## Next smallest testable task (pending owner approval of M6 scope)
M6 proposal: operational reliability — scheduled daily ingestion with job leases and retries after the 08:30 publication window, freshness/quality monitoring (quarantine alerts on empty or anomalously small catalogs), OpenSearch reindex verification, PostgreSQL backup/restore rehearsal, and measured ingestion/search performance — plus exposing read-only MCP calls in the operational dashboard. No new data sources and no write-capable agent tools in M6.
