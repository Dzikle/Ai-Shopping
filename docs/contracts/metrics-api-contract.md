# Operations Metrics REST API Contract (`v1`)

## Overview

The M8 metrics API (`GET /api/v1/metrics`) exposes operational monitoring aggregates directly from authoritative PostgreSQL: ingestion-run throughput, live offer/catalog counts, staleness, quarantine telemetry, and Stage-2 review-queue depth.

In accordance with **ADR-0002**, **AGENTS.md (#3, #6, #8, #9)**:
1. **Authoritative source:** all counters are computed in PostgreSQL (`offers_current`, `price_observations`, `canonical_products`, `product_matches`, `ingestion_runs`, `stores`); OpenSearch is never queried for metrics (rebuildable projection).
2. **Single DB clock:** `checkedAt` and all age/window calculations use PostgreSQL `now()` (`TIMESTAMPTZ`) to eliminate worker clock skew.
3. **Read-only & bounded:** the endpoint mutates nothing; `recentRuns` is capped at the 20 most recent runs by `started_at DESC, id DESC`.

---

## Endpoint: `GET /api/v1/metrics`

No query parameters (fixed windows: staleness `48h`, quarantine lookback `7d`, recent-run window `20 rows`).

### Example Response (`200 OK`)

```json
{
  "checkedAt": "2026-11-05T08:45:00Z",
  "totalOffers": 1896,
  "totalObservations": 1896,
  "totalCanonicalProducts": 1372,
  "totalProductMatches": 3722,
  "totalPendingReview": 3400,
  "totalPopulatedStores": 7,
  "totalStaleStores": 7,
  "totalQuarantinedRuns": 1,
  "recentRuns": [
    {
      "runId": 42,
      "runKey": "m6-zito-empty",
      "sourceSlug": "zito",
      "status": "quarantined",
      "startedAt": "2026-10-29T08:35:00Z",
      "finishedAt": "2026-10-29T08:35:05Z",
      "pagesSeen": 1,
      "rowsSeen": 0,
      "rowsStored": 0,
      "rowsSkipped": 0,
      "quarantined": true,
      "quarantineReason": "pages with header but zero product rows",
      "workerId": "scheduler-host:1234",
      "durationSeconds": 5.0
    }
  ],
  "reviewQueue": {
    "totalPending": 3400,
    "totalApproved": 0,
    "totalRejected": 0,
    "totalAutoAccepted": 322,
    "oldestPendingDays": 2
  }
}
```

### Field semantics

| Field | Meaning |
|-------|---------|
| `checkedAt` | PostgreSQL `now()` at query time |
| `totalOffers` | live `offers_current` rows (never deleted on quarantine, AGENTS.md #6) |
| `totalObservations` | immutable `price_observations` rows |
| `totalCanonicalProducts` | `canonical_products` rows |
| `totalProductMatches` | all `product_matches` rows (any `review_status`) |
| `totalPendingReview` | rows with `review_status = 'pending_review'` (equals `reviewQueue.totalPending`) |
| `totalPopulatedStores` | distinct `store_id` values present in `offers_current` |
| `totalStaleStores` | populated stores with `MAX(published_ts) < now() - INTERVAL '48 hours'` |
| `totalQuarantinedRuns` | `ingestion_runs` with `quarantined = true` in the last 7 days |
| `recentRuns` | last 20 runs (any status) with per-row counters, `workerId` and `durationSeconds` (`COALESCE(finished_at, now()) - started_at`; in-flight runs report elapsed time) |
| `reviewQueue.oldestPendingDays` | `EXTRACT(DAY FROM now() - MIN(created_at))` over `pending_review` rows; `0` when the queue is empty |

## Companion Prometheus exporter (`scripts/metrics.ps1`)

For externally scraped dashboards, `scripts/metrics.ps1` emits the same aggregates from PostgreSQL in **Prometheus text exposition format** (metric namespace `aishopping_*`):

- `aishopping_ingestion_runs_total{source_slug,status}`
- `aishopping_offers_current_total{retailer_slug}`
- `aishopping_price_observations_total`
- `aishopping_canonical_products_total`
- `aishopping_product_matches_total{review_status}`
- `aishopping_stale_stores_total{retailer_slug}`
- `aishopping_quarantined_runs_total{retailer_slug}`
- `aishopping_pipeline_last_run_timestamp_seconds{retailer_slug}`
- `aishopping_populated_stores_total`
- `aishopping_pipeline_avg_duration_seconds`

Usage: `./scripts/metrics.ps1 [-Json] [-OutputFile <path>]`; database/user default from `.env` (`POSTGRES_DB`, `POSTGRES_USER`).

Note: grouped series (e.g. `aishopping_offers_current_total{retailer_slug=...}`) are emitted per matching row; when a table/window is empty, no series for that group is present in the exposition output.
