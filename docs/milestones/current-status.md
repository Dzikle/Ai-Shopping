# Project status — 2026-11-08

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

## Implemented (M5, this session) — owner-approved
- **Contract & Protocol Specification (`docs/contracts/mcp-tools-contract.md`, `docs/milestones/m5-proposal.md`)**:
  - Full Model Context Protocol (MCP) `2024-11-05` spec with 7 bounded, read-only tools:
    `search_products`, `compare_product_prices`, `get_price_history`, `list_stores`, `find_current_discounts`, `optimize_shopping_basket`, `suggest_product_substitutes`.
  - Input bounds enforced outside prompts (e.g. `size <= 25`, `items <= 20`, `maxStores <= 3`).
  - Zero backend LLM calls / paid AI APIs; the client agent (Claude Desktop, Antigravity, etc.) handles natural language while the backend deterministically calculates prices, unit scaling, and projections.
  - Data provenance (`sourceUrl`, `publishedTs`, `fetchedTs`, store attribution) and `dataFreshness` envelopes on every tool result.
- **Spring Boot 4.1.2 Streamable HTTP / JSON-RPC 2.0 MCP Endpoint (`backend/src/main/java/mk/aishopping/mcp/`)**:
  - `McpProtocolModels`: Type-safe JSON-RPC 2.0 request, response, error, tool definitions, tool call results, and content blocks.
  - `McpToolRegistry`: Registry and execution dispatching for all 7 tools, delegating to `CatalogSearchService` and `BasketOptimizerService` with parameter boundary checks and freshness timestamps.
  - `McpController`: `@RestController` at `/mcp` supporting `initialize`, `notifications/initialized`, `ping`, `tools/list`, `tools/call`, `GET /mcp` (discovery), and `GET /mcp/sse`.
- **JUnit 5 Unit Test Suite (`backend/src/test/java/mk/aishopping/McpServerTest.java`)**:
  - 5 tests verifying protocol handshake, tool catalog enumeration (7 tools), tool calls (`search_products`, `optimize_shopping_basket`), unknown method handling, and GET `/mcp` discovery info. Total JUnit tests: 12 (`CatalogApiTest` 4, `BasketOptimizerTest` 3, `McpServerTest` 5).

## Implemented (M6, 2026-11-04) — owner-approved
- **Schema `migrations/V4__m6_operations.sql`**:
  - Adds `worker_id` (`TEXT`) to `ingestion_runs`.
  - Adds partial unique index `uq_ingestion_runs_running_per_source` on `ingestion_runs (source_slug) WHERE status = 'running'` preventing concurrent overlapping runs for the same retailer.
  - Adds freshness and quarantine lookup indexes (`idx_ingestion_runs_source_started`, `idx_ingestion_runs_quarantined_started`).
- **Scheduler worker (`adapters/scheduler/`, stdlib-only Python 3.12)**:
  - `LeaseManager`: atomic lockfile + DB-compatible job leases per retailer (`worker_id = "{hostname}:{pid}"`, TTL expiration).
  - `fetch_with_retry` & `compute_backoff_seconds`: polite inter-page delay, exponential backoff (`1m, 2m, 4m, 8m`, capped at `30m`), `Retry-After` HTTP header support, and `prefer_ipv4_context` (`socket.AF_INET` resolution for `*.proverkanaceni.mk`).
  - `seconds_until_next_window`: daily `08:30` `Europe/Skopje` run window calculation.
  - `cli.py`: `--once` (manual/CI pass) and `--daemon` (continuous loop), supporting both `--from-snapshots` (offline replay) and `--live` (rate-limited live scraping), structured JSON logs to stdout, and `scheduler_manifest.json`.
- **Quarantine & alerting pipeline (`scripts/load-records.ps1`, `scripts/alert.ps1`, `scripts/alert.sh`, `scripts/run-daily-pipeline.ps1`)**:
  - Quarantined runs are recorded in `ingestion_runs` (`status = 'quarantined'`, `quarantined = true`) while refusing to touch `offers_current`, `price_observations`, or `promotions` (AGENTS.md #6).
  - Pluggable alerting hook (`scripts/alert.ps1` / `scripts/alert.sh`) emits single-line structured JSON alerts to stderr, optional `$env:AISHOPPING_ALERT_LOG`, and optional webhook `$env:AISHOPPING_ALERT_WEBHOOK_URL`.
- **Freshness & quarantine REST API (`GET /api/v1/freshness`, `docs/contracts/freshness-api-contract.md`, `scripts/check-freshness.ps1`)**:
  - Reports overall `status` (`FRESH` / `DEGRADED` / `EMPTY`), authoritative DB `checkedAt` (`SELECT now()`), per-retailer `latestPublishedTs`, `oldestPublishedTs`, `latestFetchedTs`, `populatedStoresCount`, `offerCount`, `lastCompletedRunKey`, store-level `staleStores` (`ageHours > staleThresholdHours`, default 48h), and `quarantinedRuns` (default 7d window).
- **Additional retailer discovery (`docs/research/retailer-sources.md`, 2026-11-04)**:
  - **KAM (`kam.com.mk`):** Resolved format — `POST https://kam.com.mk/ShopsWeb/LoadShopList` returns JSON for 86 stores with daily per-store PDF price lists at `https://kam.com.mk/{YYYY}/{MM}/{DD}/{storeId}.pdf` (verified `%PDF-1.7`, ~478 KB).
  - **Konto (`kontomarket.com.mk/cenovnik`):** Identified store links pointing to `https://ceni.tinex.mk:442/?org={org}&search=&perPage=20` (same platform as Tinex; currently blocked by `ceni.tinex.mk:442` TCP timeout).
  - **Reptil (`reptilmarketi.mk`):** Identified WordPress REST store directory at `https://cms.reptilmarketi.mk/wp-json/wp/v2/pages/8` (30 stores).

## Execution evidence (2026-11-04, local)
- Unit tests (`python:3.12-slim` stdlib + JUnit 5 in `maven:3.9.9-eclipse-temurin-21`):
  - `adapters/common/tests.py` → **8/8 OK**
  - `adapters/vero/tests.py` → **22/22 OK**
  - `adapters/stokomak/tests.py` → **9/9 OK**
  - `matching/tests.py` → **5/5 OK**
  - `search/tests.py` → **2/2 OK**
  - `adapters/scheduler/tests.py` → **6/6 OK**
  - `backend` (`mvn -B test package`) → **13/13 JUnit tests OK (`CatalogApiTest` 5/5 + `BasketOptimizerTest` 3/3 + `McpServerTest` 5/5), BUILD SUCCESS** (re-verified 2026-11-05 via cached `maven:3.9.9-eclipse-temurin-21`; the original 12/12 line predates the M7 test method).
- `scripts/test-m1.ps1` → **M1 TEST OK**
- `scripts/test-m2.ps1` → **M2 TEST OK**
- `scripts/test-m3.ps1` → **M3 TEST OK**
- `scripts/test-m4.ps1` → **M4 TEST OK**
- `scripts/test-m5.ps1` → **M5 TEST OK**
- `scripts/test-m6.ps1` → **M6 TEST OK**:
  - Applied `V1` + `V2` + `V3` + `V4` migrations and executed `scripts/run-daily-pipeline.ps1 -FromSnapshots` twice: `PASS daily_pipeline_pass1 (counts=1896,1896,1372,3)`, `PASS daily_pipeline_idempotent (counts=1896,1896,1372,3)`.
  - Verified `/api/v1/freshness` and `scripts/check-freshness.ps1`:
    - `PASS freshness_endpoint_healthy (status=FRESH, totalOffers=1896, populatedStores=7)`
    - `PASS check_freshness_script_pass`
    - `PASS freshness_stale_store_detection (staleStores=7)`
  - Verified quarantine refusal, alerting, and live-offer preservation using `tests/fixtures/zito/empty_1_1.html`:
    - `PASS pipeline_quarantine_exit_code_2`
    - `PASS offers_preserved_on_quarantine (offers_current=1896)`
    - `PASS alert_hook_emitted_json (retailer=zito, runKey=m6-quarantine-test-zito)`
    - `PASS freshness_reports_quarantined_run (quarantinedRuns=1)`
    - `PASS check_freshness_fails_on_quarantine`

## CI stabilization (2026-11-05)
Previous CI runs (M4/M6/M7 pushes plus an M3 fix probe) still failed at the "M1 integration test" step despite the local evidence above. Root causes, found and fixed:
1. **Windows-only shell invocation:** every integration script spawned `& powershell` (Windows PowerShell), which does not exist on Ubuntu runners. Fixed by resolving the shell per OS (`$psExe = if ($env:OS -eq 'Windows_NT') { 'powershell' } else { 'pwsh' }`) in all 8 scripts (`scripts/test-m1..m6.ps1`, `scripts/run-daily-pipeline.ps1`, `scripts/load-records.ps1`) and replacing all 28 call sites; plus a Linux-sapient WorkerId hostname fallback in `load-records.ps1`.
2. **Root-owned docker-mount directories:** on Linux the first `docker run -v` with a not-yet-existing `snapshots/` subdirectory creates it `root:root` 0755, so the M3 reindexer's `New-Item -Path snapshots/opensearch/<tag>` was permission-denied and the nested reindex script exited 1 with silently empty stdout. Fixed by pre-creating `snapshots/{vero,stokomak,zito,matching,opensearch,scheduler}` in CI before the integration steps so runner-owned directories already exist when docker mounts them.
3. **Runner pin:** `ubuntu-latest` has migrated to Ubuntu 26 (per runner-images#14748); the job is now pinned to `ubuntu-24.04` for deterministic pwsh (7.4.x) behavior.
4. **CI health waits tightened for 2-vCPU runners:** mock OpenSearch ready-loop 45 s and Spring Boot ready-loops 45-90 s (were 10-20 s), because boot can exceed 20 s in CI with the baseline OpenSearch container running concurrently.
5. **Failure visibility for restricted gh tokens:** logical test scripts now emit `::error::` workflow annotations and `docker logs --tail 15` dumps on container-start failure, so failures are diagnosable via `gh run view` even when run logs are admin-only (HTTP 403). A `trap` handler in `test-m1.ps1`/`test-m2.ps1` and catch blocks in m3-m6 surface the failing assertion message.

### CI verification evidence (2026-11-05)
- Run 41937544513 on commit d95dbd8: **first fully green CI run** on `Dzikle/Ai-Shopping` (all 14 steps OK: docs check, baseline stack incl. OpenSearch 3.9.0/Postgres on CI, 6 Python suites, 13 JUnit tests, M1-M6 integration, teardown) — previously CI had never been green (runs 40826031422, 41917304993, 41915901526 all failed at M1/M3).
- Run 41938782736 on commit 628c7e2 (post debug-notice cleanup): still green, no diagnostic annotations, job time 4m23s.

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
- **M4 (`docs/milestones/m4-proposal.md`):** M4 scope approved (persisted `shopping_lists` + stateless/persisted optimization); coverage-first ranking (`itemsCovered DESC`, then `totalMkd ASC`) with `maxStores=2..3` and `minSplitSavingsMkd`; strict exact identity by default (`allowSubstitutes=false`) and flagged Stage-2 substitutes (`isSubstitute=true`) when `allowSubstitutes=true`.
- **M5 (`docs/milestones/m5-proposal.md`):** M5 scope approved; bounded read-only MCP server at `/mcp` inside Spring Boot backend (reuses services, single deployable); 7 tools; strict bounds; zero paid LLM APIs; data provenance and freshness envelope.
- **M6 (`docs/milestones/m6-proposal.md`):** M6 scope approved and implemented (2026-11-04); stdlib Python scheduler worker (`adapters/scheduler/`), `V4__m6_operations.sql` lease/freshness schema, `/api/v1/freshness` endpoint, pluggable alert hooks (`scripts/alert.ps1`, `scripts/alert.sh`), `scripts/run-daily-pipeline.ps1`, and `scripts/test-m6.ps1`.
- **M7 (`docs/milestones/m7-proposal.md`):** M7 scope approved (2026-11-05); Stage-2 review-queue decision authority is the human operator (no LLM in the loop); `pending_review` → `approved`/`rejected` with audit trail (`reviewed_by`, `reviewed_at`, `review_notes`); approved matches join exact cross-retailer comparisons after reindex.

## Implemented (M7) — owner-approved (2026-11-05)
- **Stage-2 review queue REST API** (`backend/`): `POST /api/v1/matches/review-queue/{id}/approve` and `POST /api/v1/matches/review-queue/{id}/reject` endpoints; `ReviewQueueActionRequest` body (`reviewedBy`, `reviewNotes`); returns `ReviewQueueDecisionDto` with `matchId`, `reviewStatus`, `reviewedBy`, `reviewNotes`.
- **Repository layer** (`PostgresCatalogRepository.java`): `approveMatch()` / `rejectMatch()` — conditional UPDATE on `product_matches` where `review_status = 'pending_review'`, sets `reviewed_by`, `reviewed_at = now()`, `review_notes`, `updated_at`; throws `IllegalArgumentException` if match not found or not pending.
- **Service layer** (`CatalogSearchService.java`): delegates approve/reject to repository.
- **CLI** (`scripts/review-queue.ps1`): `--List` (shows pending candidates with shared tokens, confidence, size), `--Approve <id> --ReviewedBy <user> [--Notes]`, `--Reject <id> --ReviewedBy <user> [--Notes]`.
- **Tests:** `CatalogApiTest.testReviewQueueApproveAndRejectEndpoints` verifies approve+reject round-trip with Mockito verify. Total JUnit: 13.
- **Validation:** All 13 backend JUnit tests pass; all Python unit tests pass (scheduler 6, common 8, vero 22, stokomak 9, matching 5, search 2).

## Implemented (M8) — owner-approved (2026-11-08)
- **Metrics REST API (`GET /api/v1/metrics`, `docs/contracts/metrics-api-contract.md`)**: single read-only JSON snapshot from authoritative PostgreSQL — catalog counters (`totalOffers`, `totalObservations`, `totalCanonicalProducts`, `totalProductMatches`), `totalPendingReview`, populated/stale store counts, 7-day quarantined runs, last 20 ingestion runs (per-run page/row counters, `workerId`, fractional `durationSeconds` — in-flight runs report elapsed time), and Stage-2 review-queue depth (`pending`/`approved`/`rejected`/`autoAccepted`, `oldestPendingDays`). DB-clock `checkedAt`, `LIMIT 20` bound, no OpenSearch queries (ADR-0002).
  - Fix applied: `EXTRACT(EPOCH ...)` returns `numeric` on PG ≥ 14 (JDBC `BigDecimal`), so the SQL casts `::double precision` to avoid a runtime `ClassCastException` that mocked tests alone would not catch.
- **Prometheus exporter (`scripts/metrics.ps1`)**: emits exposition format (`aishopping_*` namespace, documented metric list) or `-Json`; `-OutputFile` for scrapers; DB/user from `.env`; grouped series omitted when empty (documented).
- **Tests:** `CatalogApiTest.testMetricsEndpointReportsRunsAndReviewQueue` (JUnit 13 → 14 all green).
- **Execution evidence (local, 2026-11-08):**
  - JUnit via `maven:3.9.9-eclipse-temurin-21`: `Tests run: 14, Failures: 0, Errors: 0` — BUILD SUCCESS.
  - Fresh `m8_metrics_test` DB + V1..V4 migrations via `scripts/apply-migrations.ps1` → `MIGRATIONS OK`; seeded 2 runs (completed vero 95 s, quarantined zito 5 s):
    - `aishopping_pipeline_avg_duration_seconds 50` (verifies duration math), correct per-status/per-retailer series, epoch timestamps verified; JSON mode OK; throwaway DB dropped, no other DBs touched.
  - Two exporter bugs found by validation and fixed: outer-scope alias `r.slug` → `sub.slug` in the stale-stores query; removed stderr-suppression (`2>$null`) that could mask failing psql queries under `$ErrorActionPreference='Stop'`.
- **CI:** unchanged — existing matrix (docs, baseline stack, 6 Python suites, JUnit M1-M6 integration) covers the new files; see proposal for staged follow-ups.
- **Committed** as `6cfe290` (`feat(m8): metrics API and Prometheus exporter`).

**Next candidate tasks (Post-M8):**
1. **KAM PDF adapter (`adapters/kam/`):** Ingest daily per-store PDF price lists discovered via `POST https://kam.com.mk/ShopsWeb/LoadShopList` (`https://kam.com.mk/{YYYY}/{MM}/{DD}/{storeId}.pdf`). Requires PDF table parsing (new dependency decision needed — currently stdlib-only).
2. **Tinex/Konto adapter (`adapters/tinex/`):** Reuse the shared `adapters/stokomak` parser against the Tinex platform (`ceni.tinex.mk:442`, same `?org={org}` scheme as Stokomak/Zito; Konto store links point at it) once the endpoint is reachable again; then M5/M6 freshness coverage extends automatically.
3. **Alert thresholds on M8 metrics:** owner decision from m8-proposal non-goals — plumb `aishopping_*` series into `scripts/alert.ps1` thresholds (e.g. stale-store count > 0, review queue depth > N) and optional hosted dashboard for run history + queue depth.
