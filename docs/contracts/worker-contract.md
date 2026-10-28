# Worker contract v1 (M1)

Applies to every source adapter (reference implementation: `adapters/vero/`).
Adapters are replaceable modules behind this contract; downstream consumers
(POSgreSQL loader now, services later) depend only on the artifacts defined
here, never on a source's page format.

## Pipeline stages

```
fetch -> snapshot -> parse -> normalize -> emit records
```

1. **Fetch** - single host, modest rate (>= 1 s between requests), explicit
   timeout, honest User-Agent, hard page cap per run. Offline replay from
   captured files is an allowed fetch substitute (used by tests/CI).
2. **Snapshot** - raw response bytes stored unmodified under
   `snapshots/{source}/{yyyy-mm-dd}/{run_key}/{url_hash16}.html`; sha256 of
   URL and bytes recorded; content never re-fetched when hashes match.
3. **Parse** - source markup to typed rows; malformed markup tolerated;
   unknown values become NULL, never fabricated.
4. **Normalize** - currencies, availability enums, timestamps (source-local
   zone resolved explicitly), decimal text (never float).
5. **Emit** - `records.ndjson`, `snapshots.ndjson`, `manifest.json`.

## Run state

Job state is owned by PostgreSQL (`ingestion_runs`), keyed by caller-provided
`run_key` (unique). The adapter is stateless across runs. Counters
(`pages_seen`, `rows_seen`, `rows_stored`, `rows_skipped`) and final status
(`running`, `completed`, `quarantined`, `failed`) are written by the loader
from the manifest.

## Quarantine (ADR-0004)

Abnormal catalogs (header present but zero rows, row-count collapse vs the
previous run of the same store) mark the run `quarantined`. Quarantined runs
are recorded but not ingested unless overridden. Live offers are never deleted
because a new run looks empty or abnormal.

## Idempotency

Replaying the same run (same `run_key`, same snapshots) must not create new
`price_observations` or `promotions`; `offers_current` is upserted;
`raw_snapshots` deduplicates on `(source_slug, url_hash, content_hash)`.
Observations are immutable once written; corrections are new observations.

## Provenance

Every observation carries: `source_url`, `fetched_ts`, `published_ts`
(retailer-declared, zone-resolved), and a link to the stored snapshot
(`raw_snapshot_id`). Snapshot bytes are the audit trail; source timestamps,
pack sizes/units and location-specific prices are never discarded.
