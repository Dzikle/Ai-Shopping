# Project status — 2026-10-28

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
  - `GET /api/v1/health` — database + OpenSearch status, active search engine (`opensearch` vs `postgresql_fallback`), and table/index counts.
  - `GET /api/v1/stores?retailer=&city=` — store catalog with active offer counts and latest `publishedTs`.
  - `GET /api/v1/offers/search` — full-text query (`q`), retailer, storeKey, category, `inStockOnly`, `promoOnly`, `minPrice`, `maxPrice`, `sort` (`price_asc`/`price_desc`), pagination, preserving full provenance (`sourceUrl`, `publishedTs`, `fetchedTs`, `runId`).
  - `GET /api/v1/products/compare?q=&minRetailers=2` — side-by-side multi-retailer comparison (`cheapestMkd`, `highestMkd`, `spreadMkd`, `latestPublishedTs`, per-retailer offer summaries) strictly restricted to verified identity matches (`auto_accepted`/`approved`).
  - `GET /api/v1/products/{canonicalId}/history` — ordered `price_observations` timeline across retailers and stores.
  - `GET /api/v1/matches/review-queue` — read-only inspection of Stage-2 `pending_review` candidate pairs and their `evidence` JSON.
  - **Automatic PostgreSQL fallback (ADR-0002)**: when OpenSearch is unreachable or unpopulated, `/stores`, `/offers/search`, and `/products/compare` automatically serve from authoritative PostgreSQL tables (`sourceEngine = "postgresql_fallback"`).

## Execution evidence (2026-10-28, local)
- Unit tests (`python:3.12-slim` stdlib + JUnit 5 in `maven:3.9.9-eclipse-temurin-21`):
  - `adapters/common/tests.py` → **8/8 OK**
  - `adapters/vero/tests.py` → **22/22 OK**
  - `adapters/stokomak/tests.py` → **9/9 OK**
  - `matching/tests.py` → **5/5 OK**
  - `search/tests.py` → **2/2 OK** (atomic alias swap across `v1_run1` → `v1_run2`, old physical index deletion, `_search` filtering/sorting)
  - `backend` (`mvn -B test package`) → **3/3 JUnit tests OK, BUILD SUCCESS** (`ai-shopping-backend-0.3.0-SNAPSHOT.jar`)
- `scripts/test-m1.ps1` → **M1 TEST OK** (1000 observations/offers/promotions, idempotent second pass, all 8 asserts PASS).
- `scripts/test-m2.ps1` → **M2 TEST OK**:
  - Loaded 3 retailers (`vero`: 1000 rows, `stokomak`: 400 rows across 3 stores `1, 3, 14`, `zito`: 500 rows / 496 unique store offers across 3 stores `2, 8, 13`).
  - First & second pass counts (`observations,offers,promotions,snapshots,retailer_products,canonical_products,stage1_matches,stage2_queue`): `1896,1896,1053,11,1672,1372,1381,20` (100% idempotent).
- `scripts/test-m3.ps1` → **M3 TEST OK**:
  - Exported PostgreSQL projections and ran two consecutive OpenSearch reindex passes (`v1_pass1` → `v1_pass2`): `192` stores, `1,896` offers, `1,372` canonical products indexed; aliases `stores`, `offers`, `products` atomically swapped to `*_v1_v1_pass2` and `*_v1_v1_pass1` deleted (`PASS opensearch_alias_swap_v1_pass2`).
  - Booted `ai-shopping-backend-0.3.0-SNAPSHOT.jar` container and verified all 6 REST endpoints against OpenSearch (`sourceEngine = "opensearch"`, 17 Vero stores, 400 Stokomak offers, 6 cross-retailer canonical product comparisons, 2 observations for canonicalId `1116`, 20 `pending_review` items).
  - Stopped OpenSearch container and verified automatic fallback to PostgreSQL (`sourceEngine = "postgresql_fallback"`) returning identical totals (`6` cross-retailer comparisons, `400` Stokomak offers).

## Blockers / limitations
- Java, Maven, psql not installed natively on this machine (containers and CI provide them; `maven:3.9.9-eclipse-temurin-21` already cached).
- Docker image pulls fail from agent/automation shells (credential helper requires an interactive session). Workaround used: locally cached images; new images must be pulled by the owner or via CI.
- **No OpenSearch image cached locally** → local M3 integration test verifies against `search/mock_opensearch.py` + PostgreSQL fallback; CI runs against pinned `opensearchproject/opensearch:3.9.0`.
- Local Postgres runs 18.3 (cached image) via `POSTGRES_IMAGE=postgres:18.3` override; CI pins 18.6. Same major version; acceptable.
- `ceni.tinex.mk` (port 442) timed out during M2 validation and remains deferred until reachable; `ramstore.com.mk` remains blocked pending written consent.
- `*.proverkanaceni.mk` has slow/unreachable IPv6 in some environments; IPv4 reaches the host in ~0.5s.
- Local clone lives at `C:\Dev\Personal\ao shopping` (outside OneDrive ✓).

## Resolved owner decisions
- **M1 (`docs/milestones/m1-proposal.md`):** M1 scope approved; daily fetch window after 08:30 local; real Vero HTML fixtures committed; Ramstore skipped pending written consent.
- **M2 (`docs/milestones/m2-proposal.md`):** Stokomak + Zito approved; 3 stores/retailer subset for M2; exact deterministic match + Stage-2 review queue (no LLM in M2); byte-exact HTML fixtures committed.
- **M3 (`docs/milestones/m3-proposal.md`):** M3 scope approved; OpenSearch primary with automatic PostgreSQL fallback; strictly read-only `GET /api/v1/*` surface.

## Next smallest testable task (pending owner approval of M4 scope)
M4 proposal: single-store vs multi-store basket optimization engine (itemized basket pricing, missing-item handling, store-split savings threshold, and verified substitution rules separate from product identity per ADR-0003).
