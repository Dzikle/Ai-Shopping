-- READ-ONLY audit; safe to run against a live PostgreSQL database.
-- Usage: psql -X -v ON_ERROR_STOP=1 -f scripts/audit-catalog-correctness.sql
-- Does NOT change identities, offers, history, review records or search indexes.
-- Review all matches before approving any data reconciliation.

\echo '1. Verified canonical groups with conflicting percentage variants'
WITH fat_variants AS (
    SELECT pm.canonical_product_id,
           r.slug AS retailer,
           rp.id AS retailer_product_id,
           rp.listing_name,
           substring(rp.listing_name FROM '([0-9]+([.,][0-9]+)?)[[:space:]]*%') AS percentage
      FROM product_matches pm
      JOIN retailer_products rp ON rp.id = pm.retailer_product_id
      JOIN retailers r ON r.id = rp.retailer_id
     WHERE pm.review_status IN ('auto_accepted', 'approved')
), conflicting AS (
    SELECT canonical_product_id
      FROM fat_variants
     WHERE percentage IS NOT NULL
     GROUP BY canonical_product_id
    HAVING COUNT(DISTINCT percentage) > 1
)
SELECT cp.id AS canonical_id, cp.canonical_name,
       fv.retailer, fv.retailer_product_id, fv.listing_name, fv.percentage
  FROM conflicting c
  JOIN canonical_products cp ON cp.id = c.canonical_product_id
  JOIN fat_variants fv ON fv.canonical_product_id = c.canonical_product_id
 ORDER BY cp.id, fv.retailer, fv.retailer_product_id;

\echo '2. Potential opposite with/without variants sharing verified identity'
WITH modifiers AS (
    SELECT pm.canonical_product_id,
           bool_or(rp.listing_name ~* '(^|[[:space:]])СО[[:space:]]') AS has_with,
           bool_or(rp.listing_name ~* '(^|[[:space:]])БЕЗ[[:space:]]') AS has_without
      FROM product_matches pm
      JOIN retailer_products rp ON rp.id = pm.retailer_product_id
     WHERE pm.review_status IN ('auto_accepted', 'approved')
     GROUP BY pm.canonical_product_id
)
SELECT cp.id, cp.canonical_name, cp.normalized_size
  FROM modifiers m
  JOIN canonical_products cp ON cp.id = m.canonical_product_id
 WHERE m.has_with AND m.has_without
 ORDER BY cp.id;

\echo '3. Suspicious per-gram source labels (review full package and source before correction)'
SELECT r.slug, s.name AS store_name, rp.id AS retailer_product_id,
       rp.listing_name, oc.price_current, oc.regular_price,
       oc.unit_price, oc.unit_label, oc.published_ts, oc.source_url
  FROM offers_current oc
  JOIN stores s ON s.id = oc.store_id
  JOIN retailers r ON r.id = s.retailer_id
  JOIN retailer_products rp ON rp.id = oc.retailer_product_id
 WHERE oc.unit_price IS NOT NULL
   AND oc.unit_label ~* '^1[[:space:]]*(гр|г|g|gr)[[:space:].]*$'
 ORDER BY r.slug, rp.listing_name, s.name
 LIMIT 100;

\echo '4. Current offer data freshness per retailer (publication vs fetch times)'
SELECT r.slug AS retailer,
       count(*) AS current_offers,
       count(DISTINCT oc.store_id) AS stores_with_offers,
       max(oc.published_ts) AS last_published,
       max(oc.fetched_ts) AS last_fetched,
       now() - max(oc.published_ts) AS publication_age
  FROM offers_current oc
  JOIN stores s ON s.id = oc.store_id
  JOIN retailers r ON r.id = s.retailer_id
 GROUP BY r.slug
 ORDER BY r.slug;

\echo '5. Recent run outcomes (never delete healthy offers after failed/quarantined runs)'
SELECT source_slug, status, started_at, finished_at,
       rows_seen, rows_stored, quarantined, quarantine_reason
  FROM ingestion_runs
 ORDER BY started_at DESC
 LIMIT 40;
