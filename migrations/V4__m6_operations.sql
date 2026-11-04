-- V4__m6_operations.sql — M6 schema: scheduler worker leases, concurrency guard,
-- and freshness/quarantine monitoring indexes on ingestion_runs.

SET client_encoding = 'UTF8';

BEGIN;

ALTER TABLE ingestion_runs
    ADD COLUMN IF NOT EXISTS worker_id TEXT;

-- Prevent concurrent 'running' ingestion runs for the same retailer source_slug.
CREATE UNIQUE INDEX IF NOT EXISTS uq_ingestion_runs_running_per_source
    ON ingestion_runs (source_slug)
    WHERE status = 'running';

CREATE INDEX IF NOT EXISTS idx_ingestion_runs_source_started
    ON ingestion_runs (source_slug, started_at DESC);

CREATE INDEX IF NOT EXISTS idx_ingestion_runs_quarantined_started
    ON ingestion_runs (quarantined, started_at DESC)
    WHERE quarantined = true;

COMMIT;
