# Freshness & Quarantine Monitoring REST API Contract (`v1`)

## Overview

The M6 Freshness API (`GET /api/v1/freshness`) exposes authoritative ingestion freshness, store staleness, and quarantine telemetry directly from PostgreSQL (`retailers`, `stores`, `offers_current`, `ingestion_runs`).

In accordance with **ADR-0002**, **ADR-0004**, and **AGENTS.md (#3, #6, #8)**:
1. **Authoritative timestamps:** All age calculations use PostgreSQL's `now()` (`TIMESTAMPTZ`) to eliminate clock skew between worker containers and the database.
2. **Quarantine visibility:** Runs that encounter header-only/empty catalog pages are recorded in `ingestion_runs` with `status = 'quarantined'` and `quarantined = true` without modifying or deleting live rows in `offers_current`.
3. **Store-level staleness:** Populated stores whose `MAX(published_ts)` lags `now()` by more than `staleThresholdHours` (default `48` hours) are reported in `staleStores`.

---

## Endpoint: `GET /api/v1/freshness`

### Query Parameters
- `retailer` (optional): filter by retailer slug (`vero`, `stokomak`, `zito`).
- `staleThresholdHours` (optional, default `48`, bounded `1..87600`): maximum allowed age in hours for a store's `MAX(published_ts)` before it is flagged as stale.
- `quarantineWindowDays` (optional, default `7`, bounded `1..365`): lookback window in days for quarantined `ingestion_runs`.

### Status semantics
- `"FRESH"` — `totalOffers > 0`, `totalStaleStores == 0`, and `totalQuarantinedRuns == 0`.
- `"DEGRADED"` — `totalOffers > 0`, and either `totalStaleStores > 0` or `totalQuarantinedRuns > 0`.
- `"EMPTY"` — `totalOffers == 0`.

### Example Response (`200 OK`)

```json
{
  "status": "FRESH",
  "checkedAt": "2026-10-29T08:45:00Z",
  "staleThresholdHours": 48,
  "quarantineWindowDays": 7,
  "totalOffers": 1896,
  "totalPopulatedStores": 7,
  "totalStaleStores": 0,
  "totalQuarantinedRuns": 0,
  "retailers": [
    {
      "retailerSlug": "stokomak",
      "retailerName": "Stokomak",
      "seededStoresCount": 81,
      "populatedStoresCount": 3,
      "offerCount": 420,
      "latestPublishedTs": "2026-10-28T23:00:00Z",
      "oldestPublishedTs": "2026-10-28T23:00:00Z",
      "latestFetchedTs": "2026-10-29T08:31:12Z",
      "staleStoresCount": 0,
      "staleStores": [],
      "quarantinedRunsCount": 0,
      "lastCompletedRunKey": "m6-daily-stokomak",
      "lastCompletedAt": "2026-10-29T08:31:20Z"
    }
  ],
  "quarantinedRuns": []
}
```
