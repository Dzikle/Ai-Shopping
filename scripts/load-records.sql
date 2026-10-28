-- load-records.sql - M1 loader used by scripts/load-records.ps1.
-- Runs via psql inside the postgres container with files staged at
-- /tmp/aishopping/{snapshots,records}.ndjson and -v variables supplied by the
-- wrapper script. Idempotent: safe to re-run for the same run_key.

\set ON_ERROR_STOP on

BEGIN;

CREATE TEMP TABLE stage_snapshots (doc jsonb);
\copy stage_snapshots FROM '/tmp/aishopping/snapshots.ndjson'

CREATE TEMP TABLE stage_records (doc jsonb);
\copy stage_records FROM '/tmp/aishopping/records.ndjson'

CREATE TEMP TABLE _run AS
WITH ins AS (
    INSERT INTO ingestion_runs (run_key, source_slug, status)
    VALUES (:'run_key', :'source_slug', 'running')
    ON CONFLICT (run_key) DO NOTHING
    RETURNING id
)
SELECT id FROM ins
UNION
SELECT id FROM ingestion_runs WHERE run_key = :'run_key'
LIMIT 1;

INSERT INTO raw_snapshots
    (run_id, source_slug, url, url_hash, content_hash, storage_path,
     content_type, byte_size, fetched_ts, published_ts)
SELECT (SELECT id FROM _run), :'source_slug',
       doc->>'url', doc->>'url_hash', doc->>'content_hash', doc->>'storage_path',
       doc->>'content_type', (doc->>'byte_size')::bigint,
       (doc->>'fetched_ts')::timestamptz, (doc->>'published_ts')::timestamptz
FROM stage_snapshots
ON CONFLICT (source_slug, url_hash, content_hash) DO NOTHING;

WITH ranked AS (
    SELECT doc->>'sku_key' AS sku_key,
           doc->>'listing_name' AS listing_name,
           doc->>'category' AS category,
           ROW_NUMBER() OVER (PARTITION BY doc->>'sku_key' ORDER BY doc->>'listing_name') AS rn
    FROM stage_records
    WHERE doc->>'sku_key' IS NOT NULL
)
INSERT INTO retailer_products (retailer_id, sku_key, listing_name, category)
SELECT (SELECT id FROM retailers WHERE slug = :'source_slug'), sku_key, listing_name, category
FROM ranked
WHERE rn = 1
ON CONFLICT (retailer_id, sku_key) DO UPDATE
SET listing_name = EXCLUDED.listing_name,
    category = EXCLUDED.category,
    updated_at = now();

WITH src AS (
    SELECT sr.doc,
           rp.id AS rp_id,
           st.id AS st_id,
           rs.id AS snap_id
    FROM stage_records sr
    JOIN retailer_products rp
         ON rp.retailer_id = (SELECT id FROM retailers WHERE slug = :'source_slug')
        AND rp.sku_key = sr.doc->>'sku_key'
    JOIN stores st
         ON st.retailer_id = rp.retailer_id
        AND st.external_key = sr.doc->>'store_external_key'
    LEFT JOIN raw_snapshots rs
         ON rs.source_slug = :'source_slug'
        AND rs.url_hash = sr.doc->>'snapshot_url_hash'
        AND rs.content_hash = sr.doc->>'snapshot_content_hash'
    WHERE (sr.doc->>'published_ts') IS NOT NULL
      AND (sr.doc->>'price_current') IS NOT NULL
), ins AS (
    INSERT INTO price_observations
        (retailer_product_id, store_id, currency, price_current,
         unit_price, unit_label, regular_price, discount_price, discount_pct,
         promo_type, promo_starts_on, promo_ends_on,
         availability, published_ts, fetched_ts, source_url, raw_snapshot_id)
    SELECT rp_id, st_id,
           COALESCE(doc->>'currency', 'MKD'),
           (doc->>'price_current')::numeric(12,2),
           (doc->>'unit_price')::numeric(12,2),
           doc->>'unit_label',
           (doc->>'regular_price')::numeric(12,2),
           (doc->>'discount_price')::numeric(12,2),
           (doc->>'discount_pct')::numeric(5,2),
           doc->>'promo_type',
           (doc->>'promo_starts_on')::date,
           (doc->>'promo_ends_on')::date,
           COALESCE(doc->>'availability', 'unknown'),
           (doc->>'published_ts')::timestamptz,
           (doc->>'fetched_ts')::timestamptz,
           doc->>'source_url',
           snap_id
    FROM src
    ON CONFLICT (retailer_product_id, store_id, published_ts, price_current) DO NOTHING
    RETURNING 1
)
SELECT 'observations_inserted' AS metric, count(*)::bigint AS value FROM ins;

WITH src AS (
    SELECT sr.doc,
           rp.id AS rp_id,
           st.id AS st_id
    FROM stage_records sr
    JOIN retailer_products rp
         ON rp.retailer_id = (SELECT id FROM retailers WHERE slug = :'source_slug')
        AND rp.sku_key = sr.doc->>'sku_key'
    JOIN stores st
         ON st.retailer_id = rp.retailer_id
        AND st.external_key = sr.doc->>'store_external_key'
    WHERE (sr.doc->>'published_ts') IS NOT NULL
      AND (sr.doc->>'price_current') IS NOT NULL
), ins AS (
    INSERT INTO offers_current
        (store_id, retailer_product_id, currency, price_current,
         unit_price, unit_label, regular_price, discount_price, discount_pct,
         promo_type, promo_starts_on, promo_ends_on,
         availability, published_ts, fetched_ts, source_url, run_id)
    SELECT st_id, rp_id,
           COALESCE(doc->>'currency', 'MKD'),
           (doc->>'price_current')::numeric(12,2),
           (doc->>'unit_price')::numeric(12,2),
           doc->>'unit_label',
           (doc->>'regular_price')::numeric(12,2),
           (doc->>'discount_price')::numeric(12,2),
           (doc->>'discount_pct')::numeric(5,2),
           doc->>'promo_type',
           (doc->>'promo_starts_on')::date,
           (doc->>'promo_ends_on')::date,
           COALESCE(doc->>'availability', 'unknown'),
           (doc->>'published_ts')::timestamptz,
           (doc->>'fetched_ts')::timestamptz,
           doc->>'source_url',
           (SELECT id FROM _run)
    FROM src
    ON CONFLICT (store_id, retailer_product_id) DO UPDATE SET
        currency = EXCLUDED.currency,
        price_current = EXCLUDED.price_current,
        unit_price = EXCLUDED.unit_price,
        unit_label = EXCLUDED.unit_label,
        regular_price = EXCLUDED.regular_price,
        discount_price = EXCLUDED.discount_price,
        discount_pct = EXCLUDED.discount_pct,
        promo_type = EXCLUDED.promo_type,
        promo_starts_on = EXCLUDED.promo_starts_on,
        promo_ends_on = EXCLUDED.promo_ends_on,
        availability = EXCLUDED.availability,
        published_ts = EXCLUDED.published_ts,
        fetched_ts = EXCLUDED.fetched_ts,
        source_url = EXCLUDED.source_url,
        run_id = EXCLUDED.run_id,
        updated_at = now()
    RETURNING 1
)
SELECT 'offers_upserted' AS metric, count(*)::bigint AS value FROM ins;

WITH src AS (
    SELECT DISTINCT ON (sr.doc->>'sku_key', sr.doc->>'store_external_key',
                        sr.doc->>'promo_type', sr.doc->>'promo_starts_on', sr.doc->>'promo_ends_on')
           sr.doc->>'sku_key' AS sku_key,
           sr.doc->>'store_external_key' AS store_external_key,
           sr.doc->>'promo_type' AS promo_type,
           (sr.doc->>'discount_pct')::numeric(5,2) AS discount_pct,
           (sr.doc->>'promo_starts_on')::date AS starts_on,
           (sr.doc->>'promo_ends_on')::date AS ends_on,
           sr.doc->>'source_url' AS source_url
    FROM stage_records sr
    WHERE sr.doc->>'promo_type' IS NOT NULL
      AND sr.doc->>'promo_type' <> ''
), ins AS (
    INSERT INTO promotions
        (retailer_product_id, store_id, promo_type, discount_pct,
         starts_on, ends_on, source_url, run_id)
    SELECT rp.id, st.id, s.promo_type, s.discount_pct,
           s.starts_on, s.ends_on, s.source_url, (SELECT id FROM _run)
    FROM src s
    JOIN retailer_products rp
         ON rp.retailer_id = (SELECT id FROM retailers WHERE slug = :'source_slug')
        AND rp.sku_key = s.sku_key
    JOIN stores st
         ON st.retailer_id = rp.retailer_id
        AND st.external_key = s.store_external_key
    ON CONFLICT (retailer_product_id, store_id, promo_type, starts_on, ends_on) DO NOTHING
    RETURNING 1
)
SELECT 'promotions_inserted' AS metric, count(*)::bigint AS value FROM ins;

UPDATE ingestion_runs
SET status = :'status',
    finished_at = now(),
    pages_seen = (:'pages_seen')::int,
    rows_seen = (:'rows_seen')::int,
    rows_stored = (:'rows_stored')::int,
    rows_skipped = (:'rows_skipped')::int,
    quarantined = (:'quarantined')::boolean,
    quarantine_reason = :'quarantine_reason'
WHERE run_key = :'run_key';

COMMIT;
