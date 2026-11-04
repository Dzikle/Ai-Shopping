# M6 proposal — Live daily ingestion scheduler, freshness monitor & automated pipeline

**Status:** Owner-approved & implemented (2026-11-04).
**Depends on:** M5 (MCP server, deterministic basket optimizer, REST API, OpenSearch projections, canonical identity & matching).

## Goal

Automate the end-to-end daily price ingestion pipeline for Vero, Stokomak, and Zito:
- Polite live scraping after retailer publication deadlines
- Quarantine detection & alerting for abnormal/empty catalogs
- Freshness monitoring with `/api/v1/freshness` endpoint
- Deterministic reindex of OpenSearch projections
- Idempotent, retryable, observable pipeline runs

## Owner decisions needed

1. **Scheduler mechanism:** Cron (systemd/timer) vs. Redis-backed worker queue vs. Spring `@Scheduled` inside backend?
2. **Alerting channel:** Log-only, webhook (Slack/Discord/Teams), email, or Prometheus Alertmanager?
3. **Run window:** Exact local time after 08:30 (Vero) — confirm per-retailer publication schedules.
4. **Retention:** How long to keep raw snapshots on disk before archival to S3-compatible store?

## Architectural alignment (ADR-0001, ADR-0002, ADR-0003, ADR-0004, AGENTS.md)

1. **PostgreSQL remains sole authority (ADR-0002):** Pipeline writes to `ingestion_runs`, `raw_snapshots`, `retailer_products`, `offers_current`, `price_observations`, `promotions`. OpenSearch is rebuilt via `scripts/reindex-opensearch.ps1` after each successful run.
2. **Quarantine policy (ADR-0004, AGENTS.md #6):** Empty or header-only catalog pages → run marked `quarantined`; loader refuses to ingest; prior `offers_current` preserved.
3. **Identity vs substitution (ADR-0003):** Matching runs after load; only `auto_accepted`/`approved` matches flow into OpenSearch `products_v1` and cross-retailer comparisons.
4. **Provenance & freshness (AGENTS.md #3, #8):** Every offer carries `source_url`, `published_ts`, `fetched_ts`, `run_id`. Freshness endpoint exposes min/max `published_ts` per retailer/store.
5. **No paid APIs / cloud resources (AGENTS.md #2):** Scheduler runs locally or in CI; no managed services.

## Deliverables

### 1. Scheduler worker (`adapters/scheduler/`)
- **Python stdlib-only** (consistent with other adapters)
- **Entry point:** `adapters/scheduler/cli.py`
- **Modes:**
  - `--once` — single pipeline run (for manual/CI invocation)
  - `--daemon` — long-running loop with configurable interval (default 24h, aligned to local 08:30)
- **Per-retailer scraping:** Delegates to existing adapter CLIs (`adapters/vero/cli.py --url --stores`, `adapters/stokomak/cli.py --retailer stokomak --url --stores`, etc.)
- **Job lease:** `ingestion_runs` row with `status = 'running'`, `started_at`, `worker_id` (hostname + PID); prevents concurrent runs for same retailer.
- **Retry/backoff:** Exponential backoff (1m, 2m, 4m, 8m, max 30m) on transient network errors; max 3 retries per store page.
- **Structured JSON logs** to stdout (timestamp, level, retailer, store, page, duration_ms, status).

### 2. Pipeline orchestration script (`scripts/run-daily-pipeline.ps1`)
PowerShell wrapper for CI/local use:
```
1. docker compose up -d --wait postgres
2. For each retailer (vero, stokomak, zito):
     docker run --rm -v "${PWD}:/w" -w /w python:3.12-slim \
       python -B adapters/<retailer>/cli.py --url --stores --out snapshots/<retailer>/<date>/<run_key> --run-key <run_key>
     ./scripts/load-records.ps1 -OutDir snapshots/<retailer>/<date>/<run_key> -RunKey <run_key>
3. docker run --rm -v "${PWD}:/w" -w /w python:3.12-slim \
     python -B matching/cli.py --run-dirs "snapshots/vero/...,snapshots/stokomak/...,snapshots/zito/..." \
     --out snapshots/matching/<date>/<match_key>
   ./scripts/load-matches.ps1 -OutDir snapshots/matching/<date>/<match_key>
4. ./scripts/reindex-opensearch.ps1 -VersionTag v1_<date>_<run_key>
5. ./scripts/report-cross-retailer.ps1
6. ./scripts/check-freshness.ps1  (new — see below)
```

### 3. Freshness monitor (`scripts/check-freshness.ps1` + backend endpoint)
- **Backend:** `GET /api/v1/freshness` → returns per-retailer/store:
  - `latestPublishedTs`, `oldestPublishedTs`, `offerCount`, `staleStores` (no offers updated in > 48h)
  - `quarantinedRuns` (last 7 days)
- **Script:** Queries endpoint, exits non-zero if any retailer has `staleStores > 0` or `quarantinedRuns > 0`; emits JSON for CI/alerting.

### 4. Alerting hook (pluggable)
- Interface: `scripts/alert.sh` / `scripts/alert.ps1` receiving JSON payload:
  ```json
  { "level": "warn|error", "retailer": "vero", "store": "89", "message": "Quarantined: empty catalog page", "runKey": "..." }
  ```
- Default implementation: writes to stderr (captured by CI/logs). Owner can replace with webhook call.

### 5. Tests & CI (`scripts/test-m6.ps1`, `.github/workflows/ci.yml`)
- **Unit tests:** Scheduler lease logic, backoff, quarantine detection, freshness query.
- **Integration test (`test-m6.ps1`):**
  1. Spin up scratch DB + backend
  2. Run pipeline once with `--from-snapshots` (fixtures) → verify end-to-end
  3. Run pipeline with `--url` against **one live store per retailer** (smoke test, rate-limited)
  4. Assert `/api/v1/freshness` shows recent `published_ts` for those stores
  5. Assert no quarantined runs for the smoke test
- **CI:** Extend workflow to run `test-m6.ps1` nightly (schedule: `0 9 * * *` UTC ≈ 11:00 local) against live endpoints (opt-in via secret).

### 6. Documentation updates
- `docs/milestones/current-status.md` — add M6 implemented section
- `README.md` — add "Running the M6 daily pipeline" section
- `docs/contracts/freshness-api-contract.md` — OpenAPI spec for `/api/v1/freshness`

## Exit criterion (roadmap M6)

Unattended daily runs execute successfully with measured freshness and quality:
- All three retailers scraped politely after publication deadline
- Zero data loss: PostgreSQL authoritative state preserved, OpenSearch rebuilt atomically
- Quarantine alerts fire on abnormal catalogs; prior offers never deleted
- Freshness endpoint reflects actual `published_ts` lag per store
- CI nightly run passes smoke test against live retailers

## Non-goals (explicitly out of M6)

- Multi-country / multi-category expansion (future milestones)
- Kubernetes / managed cloud deployment
- Authentication / multi-tenant scheduling
- Vector embeddings / semantic search (M7+)
- S3/MinIO snapshot archival (deferred until disk pressure justifies)

## Risks & mitigations

| Risk | Mitigation |
|------|------------|
| Retailer HTML changes break parser | Fixture regression tests; quarantine on parse failure; alert on schema drift |
| IPv6 unreliability on `*.proverkanaceni.mk` | Force IPv4 via `curl --ipv4` / Python `socket.AF_INET`; retry with backoff |
| Rate limiting / IP blocking | 1s delay between pages, 50 pages/store cap, respect `Retry-After` headers |
| Clock skew between worker and DB | Use `TIMESTAMPTZ` from PostgreSQL (`now()`) for all timestamps; worker reads DB time at start |
| Concurrent pipeline runs | `ingestion_runs` lease row with `status='running'` + unique partial index on `(retailer, status)` where status='running' |