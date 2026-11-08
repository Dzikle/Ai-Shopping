# M8 proposal — Operations monitoring: metrics API + Prometheus metrics export

**Status:** Owner-approved & committed (approval given 2026-11-08; commit `6cfe290`).
**Depends on:** M3 (PostgreSQL-backed REST API), M4 (basket schema containers — none), M6 (V4 operations schema, freshness pipeline), M7 (review queue decisions).

## Goal

Give the operator a single, cheap, deterministic monitoring surface over the pipeline and catalog:

1. **`GET /api/v1/metrics`** — one JSON snapshot over authoritative PostgreSQL: catalog sizes, offer/observation counts, populated/stale stores, quarantined runs, the last 20 ingestion runs (with per-run counters, worker id, duration), and the Stage-2 review-queue depth (pending/approved/rejected/auto-accepted, oldest pending).
2. **`scripts/metrics.ps1`** — Prometheus text exposition exporter (`aishopping_*` namespace) scraping the same authoritative PostgreSQL state, for `node_exporter`-style pollers, Grafana agent, or a plain scheduled log line.

This follows up M6 (freshness + quarantine) and M7 (queue decisions): instead of only reacting to staleness/quarantine, the operator can set alert thresholds and review-queue plan targets from trend data.

## Owner decisions needed

1. **Metrics surface:** single `GET /api/v1/metrics` JSON endpoint + standalone Prometheus exporter script (no third-party collector, no new runtime dependency) — **proposed**; awaiting approval.
2. **Dashboard hosting:** none proposed (no Grafana/Prometheus server in compose); the exporter output is deliberately self-contained so the owner can adopt any scraper later. **Awaiting decision.**

## Architectural alignment

1. **PostgreSQL remains sole authority (ADR-0002):** all metrics are computed in SQL from `offers_current`, `price_observations`, `canonical_products`, `product_matches`, `ingestion_runs`, `stores`; OpenSearch is never queried.
2. **DB clock only (M6 convention):** `checkedAt` and all staleness/age math use PostgreSQL `now()`.
3. **Quarantine visibility (AGENTS.md #6):** quarantined runs are visible; live offers are never touched.
4. **Bounded and read-only:** the endpoint mutates nothing; `recentRuns` is strictly `LIMIT 20`; both windows are fixed (staleness `48h`, quarantine `7d`), mirroring `/api/v1/freshness` defaults.
5. **No paid APIs, no LLM calls (AGENTS.md #2).**

## Deliverables (implemented)

### 1. REST endpoint `GET /api/v1/metrics`
- `CatalogController.metrics()` → `CatalogSearchService.getMetrics()` → `PostgresCatalogRepository.getMetrics()`.
- Response models in `ApiModels`: `MetricsResponse`, `PipelineRunMetricDto`, `ReviewQueueMetricDto` (documented in `docs/contracts/metrics-api-contract.md`).

### 2. Repository SQL
- Catalog counters (`COUNT(*)` over the four core tables), populated store count (`COUNT(DISTINCT store_id)`), stale stores (`HAVING MAX(published_ts) < now() - INTERVAL '48 hours'`), quarantined 7-day runs, recent 20 runs with `durationSeconds = COALESCE(finished_at, now()) - started_at` (in-flight runs report elapsed seconds), review-queue counts by `review_status` plus `oldestPendingDays = EXTRACT(DAY FROM now() - MIN(created_at))` over `pending_review`.
- **Correctness fix applied during this work:** `EXTRACT(EPOCH FROM ...)` returns `numeric` on PostgreSQL ≥ 14 (JDBC → `BigDecimal`); the mapper now uses `::double precision` in SQL — prevents a `ClassCastException` that a mocked JUnit test alone would not catch.

### 3. `scripts/metrics.ps1` (stdlib-only PowerShell + psql)
- Emits Prometheus exposition format (`# HELP`/`# TYPE` + `aishopping_ingestion_runs_total{source_slug=...,status=...}`, `aishopping_offers_current_total{retailer_slug=...}`, `aishopping_price_observations_total`, `aishopping_canonical_products_total`, `aishopping_product_matches_total{review_status=...}`, `aishopping_stale_stores_total{retailer_slug=...}`, `aishopping_quarantined_runs_total{retailer_slug=...}`, `aishopping_pipeline_last_run_timestamp_seconds{retailer_slug=...}`, `aishopping_populated_stores_total`, `aishopping_pipeline_avg_duration_seconds`), or `-Json`.
- DB/user default from `.env`; `-OutputFile` supports scrapers (`metrics.txt`); non-grouped counters always present, grouped series omitted when empty.

### 4. Tests
- JUnit: `CatalogApiTest.testMetricsEndpointReportsRunsAndReviewQueue` — verifies the response shape (catalog counters, stale/quarantine counts, recent-run visibility and status, queue depths) and Mockito-verifies the repository delegation. Total JUnit: **14** (was 13).
- Python suites untouched (52 Python tests across `common`/`vero`/`stokomak`/`matching`/`search`/`scheduler`).

## Non-goals (explicitly out of M8, pending owner decision)

- Hosting a Prometheus/Grafana stack in `docker-compose.yml`
- Alert thresholds on metrics (M6's pluggable `alert.ps1` hook remains the sole alert surface)
- Historical metric persistence (time-series retention) — should be added by the owner's scraper, not this repository
- WebSocket/streaming metrics

## Risks & mitigations

| Risk | Mitigation |
|------|------------|
| `numeric` → `Double` JDBC mismatch on `EXTRACT(EPOCH ...)` (PG ≥ 14) | `::double precision` cast in SQL; contract documents `durationSeconds` as fractional seconds |
| Scraping overhead by long-running aggregations | All queries are simple counts/HAVING over indexed tables; `LIMIT 20` bounds `recentRuns` |
| Groups omitted in exposition when empty | Documented in the contract; consumers must treat missing series as zero |
| Double source (JSON API vs Prometheus export) drifting | Both read the identical tables/windows; contract lists the exact metric names; tests pin the JSON shape |

## Validation evidence (2026-11-08, local)

- **JUnit:** `docker run --rm -v "$PWD/backend:/w" -w /w maven:3.9.9-eclipse-temurin-21 mvn -B test` → `Tests run: 14, Failures: 0, Errors: 0, Skipped: 0` (`CatalogApiTest` 6/6, `BasketOptimizerTest` 3/3, `McpServerTest` 5/5), BUILD SUCCESS.
- **Migration chain:** fresh throwaway DB `m8_metrics_test` via `scripts/apply-migrations.ps1` → V1+V2+V3+V4 applied, `MIGRATIONS OK` (Vero 17 stores, Stokomak 81, Zito 94 seeded).
- **Prometheus exporter** (`scripts/metrics.ps1 -Database m8_metrics_test`) with 2 seeded `ingestion_runs` (completed `vero` 95 s, quarantined `zito` 5 s):
  - `aishopping_ingestion_runs_total{source_slug="vero",status="completed"} 1`
  - `aishopping_ingestion_runs_total{source_slug="zito",status="quarantined"} 1`
  - `aishopping_pipeline_avg_duration_seconds 50` (mean of 95/5 — verifies the duration math)
  - `aishopping_pipeline_last_run_timestamp_seconds{retailer_slug="vero"} 1794154600` / `{zito} 1794158200` (epoch math verified)
  - `aishopping_quarantined_runs_total{retailer_slug="zito"} 1`
- **JSON mode** (`-Json`) verified; grouped series omitted for empty offer/observation tables (documented).
- Throwaway DB dropped afterwards; no other databases touched.
- Two bugs found and fixed by this validation round: (1) outer `r.slug` in the stale-stores query had to be `sub.slug` (would have failed at first non-empty use); (2) unescaped PowerShell `2>$null` under `$ErrorActionPreference='Stop'` could mask query errors — exporter now surfaces failures plainly via `$LASTEXITCODE`.
