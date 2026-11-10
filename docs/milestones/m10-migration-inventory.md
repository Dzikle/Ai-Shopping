# M10 — Migration Inventory (Spring Boot → FastAPI)

Recorded 2026-11-09 on branch `m10-fastapi-migration` from `main` @ `185e67b`.
This is the pre-migration contract inventory required by `docs/milestones/m10-fastapi-migration-task.md`.

## 1. Baseline evidence (measured 2026-11-09, host = Windows 11, Docker Engine)

| Measurement | Result |
|---|---|
| Java unit suite (`mvn -B test` incl. Maven+compile+docker) | **14/14 OK in 9.0 s** (BasketOptimizer 3, CatalogApi 6, McpServer 5) |
| `mvn -B package -DskipTests` (cached `aoshopping-m2-repo` volume) | **3.9 s** |
| Java cold boot (`java -jar` → `GET /api/v1/health` 200) | **6.19 s** |
| Health response shape (DB down) | `{"status":"DOWN","databaseStatus":"DOWN","opensearchStatus":"FALLBACK_POSTGRESQL","activeSearchEngine":"postgresql_fallback","counts":{}}` |

Edit→verify loop today ≈ compile (9s) + package (4s) + boot (6s) ≈ **~20 s** per change even with cached Maven — this is the cost M10 must remove.

## 2. Java source files to migrate (all of `backend/src/main`, ~145 KB)

| Java file (KB) | → Python target |
|---|---|
| `AiShoppingApplication.java` (0.9) + `application.properties` | `app/config.py` + `app/main.py` (app factory, env config) |
| `controller/CatalogController.java` (4.9) | `app/routes/catalog.py` |
| `controller/BasketController.java` (2.6) | `app/routes/baskets.py` |
| `mcp/McpController.java` (4.7) | `app/mcp/routes.py` |
| `mcp/McpProtocolModels.java` (1.4) | `app/mcp/protocol.py` |
| `mcp/McpToolRegistry.java` (21.5) | `app/mcp/tool_registry.py` |
| `model/ApiModels.java` (7.0) | `app/schemas/api_models.py` (camelCase dict composers) |
| `model/BasketModels.java` (4.2) | `app/schemas/basket_models.py` |
| `repository/PostgresCatalogRepository.java` (37.6) | `app/repositories/catalog_repository.py` (same SQL) |
| `repository/BasketRepository.java` (17.3) | `app/repositories/basket_repository.py` (same SQL) |
| `service/CatalogSearchService.java` (4.7) | `app/services/catalog_search_service.py` |
| `service/BasketOptimizerService.java` (24.7) | `app/services/basket_optimizer_service.py` (same algorithm) |
| `service/OpenSearchClient.java` (13.5) | `app/services/opensearch_client.py` (same DSL bodies) |
| `service/UnitConversionUtil.java` (3.6) | `app/services/unit_conversion.py` (same rounding) |
| Tests: `BasketOptimizerTest` (13.5), `CatalogApiTest` (21.7), `McpServerTest` (10.2) | `backend_py/tests/` pytest ports |

## 3. REST endpoint inventory (exact contracts, `/api/v1` prefix)

| # | Route | Notes / defaults | Errors |
|---|---|---|---|
| 1 | `GET /health` | counts = 6 PG tables + 3 OS counts when OS up; `activeSearchEngine` = `opensearch` xor `postgresql_fallback` | never 5xx; DB down ⇒ `status=DOWN` 200 |
| 2 | `GET /stores?retailer&city` | OS page=0 size=<n items>; PG fallback identical; city filter `LOWER(s.city)=?` | OS failure → PG fallback silently |
| 3 | `GET /offers/search?q&retailer&storeKey&category&inStockOnly=false&promoOnly=false&minPrice&maxPrice&sort=price_asc&page=0&size=20` | OS multi_match `listing_name^2,canonical_name^2,category`; `sort` in {price_asc,price_desc,desc} else asc | fallback same; top-level 400 on bad JSON minPrice |
| 4 | `GET /products/compare?q&minRetailers=2&page=0&size=20` | OS `products` bool: must multi_match `canonical_name^2,normalized_tokens`, filter range retailer_count ≥ max(1,minRetailers); sort `canonical_name.keyword asc` | PG fallback via 2-CTE SQL |
| 5 | `GET /products/{id}/history` | PG only; 404 empty body when unknown | 404 |
| 6 | `GET /matches/review-queue?limit=25` | clamp 1..200; pending only; order confidence DESC, listing asc | — |
| 7 | `POST /matches/review-queue/{id}/approve` | body `{reviewedBy, reviewNotes}`; UPDATE …WHERE status='pending_review' | unknown/not-pending → Java **500** (IllegalArgumentException uncaught) — verify live, preserve or document |
| 8 | `POST /matches/review-queue/{id}/reject` | mirror of 7 | same |
| 9 | `POST /baskets/optimize` | body `BasketOptimizeRequest` (camelCase; `allowSubstitutes` default false, `inStockOnly` default true, `maxStores` clamp 1..3 default 2); coverage→exactismatch→total→storeId ordering; subset enumeration ≤3 stores | no items → 400 `{"error":"Basket must contain at least one item"}` |
| 10 | `POST /baskets/lists` | name required; items each need canonicalProductId XOR retailerProductId; qty scale-3, unit normalize | 400 `{"error":...}`; created → 201 |
| 11 | `GET /baskets/lists/{id}` | 404 empty body when unknown | 404 |
| 12 | `POST /baskets/lists/{id}/optimize` | body optional overrides; city merges list.cityFilter when absent | 404 unknown list |
| 13 | `GET /freshness?retailer&staleThresholdHours=48&quarantineWindowDays=7` | clamps 1..87600 / 1..365; empty→EMPTY, stale/quarantine→DEGRADED else FRESH | — |
| 14 | `GET /metrics` | single PG round set; `recentRuns` last 20; reviewQueue block | — |

INFRA routes: `GET /mcp` (server info), `GET /mcp/sse` (single `endpoint` event, 60 s), `POST /mcp`.

## 4. Database access (JdbcTemplate → psycopg)

- Connection params via `spring.datasource.*` (`POSTGRES_HOST/PORT/DB/USER/PASSWORD` defaults `localhost/5432/ai_shopping/ai_shopping/replace_me_locally`).
- All SQL is ported 1:1 (`?`→`%s`), dynamic `IN (...)` still parameterized. `now()` stays DB-side.
- Needs: run V1..V5 migrations unchanged; scratch-DB integration scripts keep working.

## 5. OpenSearch integration

- Base URL `OPENSEARCH_URL` default `http://localhost:9200`; HTTP 3 s connect/5 s search read timeout.
- Calls: `GET {index}/_count`, `POST {index}/_search` with hand-built DSL body (multi_match, term, range, sort, from/size). Indexes/aliases: `stores`, `offers`, `products` (v1 behind aliases).
- Python: `opensearch-py` official client issuing the same DSL bodies; fallbacks preserved at the same decision points (healthy = `offers` count ≥ 0; per-endpoint try/catch → PG).

## 6. Python "reuse" map (existing code incorporated as-is)

- Adapter NDJSON worker contract, scheduler, loader (`scripts/load-records.ps1`), matcher (`matching/`), reindexer (`search/reindexer.py` build indexes/aliases) — untouched; FastAPI app is a *consumer* of the same PostgreSQL state.
- Money/quantity math already duplicated in Python workers (normalizer) must NOT be re-shuffled: Java behavior is authoritative for API math.

## 7. Config/scripts adaptation surface

| Consumer | Today | M10 change |
|---|---|---|
| `scripts/test-m3/m4/m5/m6.ps1` | docker maven run `java -jar backend/target/ai-shopping-backend-0.3.0-SNAPSHOT.jar`, env `SPRING_DATASOURCE_URL/USERNAME/PASSWORD`, port `ApiPort:8080` | launch `uv run uvicorn app.main:app` on host (or python:3.12 container without build) with `POSTGRES_*` env mapped |
| `.github/workflows/ci.yml` | JUnit step + backend JAR reuse in M3/M4/M5/M6 | pytest steps + same scripts via FastAPI |
| README/docs | Spring Boot wording | updated after parity evidence |
| `docker-compose.yml` | infra only (PG+OS) | unchanged; backend runs via uv on host for dev; optional backend service documented |

## 8. Out-of-scope (explicit non-goals this branch)

- No new retailers, no ingestion-logic changes, no schema/migration changes, no new MCP tools, no frontend.
- Java backend stays in repo until parity suite passes; removal from CI/Compose only after evidence.

## 9. Risks / watch-list for parity

1. Jackson `Instant` ISO strings vs Python `isoformat()` (fraction digits, `Z` suffix) → normalize by parsing in diff harness, but byte-diff where cheap.
2. `BigDecimal` scale-2/4 JSON numeric formatting (`75.00` vs `75.0`) → compare parsed numbers, not bytes.
3. Uncaught `IllegalArgumentException` on review queue decisions → record *actual* Java status (500 vs 400) live before porting decision.
4. `LinkedHashMap` deterministic key ordering in all DTO maps → Python dicts preserve insertion order; keep same order.
5. `Random` seed none — scheduler/loader untouched.
