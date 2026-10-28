-- load-matches.sql - M2 loader for canonical_products and product_matches.
-- Runs via psql inside the postgres container with files staged at
-- /tmp/aishopping/{canonical_products,product_matches}.ndjson.
-- Idempotent and preserves human-reviewed rows (reviewed_at IS NOT NULL).

\set ON_ERROR_STOP on

BEGIN;

CREATE TEMP TABLE stage_canonical_products (doc jsonb);
\copy stage_canonical_products FROM '/tmp/aishopping/canonical_products.ndjson'

CREATE TEMP TABLE stage_product_matches (doc jsonb);
\copy stage_product_matches FROM '/tmp/aishopping/product_matches.ndjson'

WITH ins AS (
    INSERT INTO canonical_products
        (canonical_key, canonical_name, normalized_tokens, normalized_size,
         quantity_value, quantity_unit, pack_count, gtin)
    SELECT doc->>'canonical_key',
           doc->>'canonical_name',
           doc->>'normalized_tokens',
           doc->>'normalized_size',
           (doc->>'quantity_value')::numeric(12,3),
           doc->>'quantity_unit',
           COALESCE((doc->>'pack_count')::int, 1),
           doc->>'gtin'
    FROM stage_canonical_products
    WHERE doc->>'canonical_key' IS NOT NULL
    ON CONFLICT (canonical_key) DO UPDATE SET
        canonical_name = EXCLUDED.canonical_name,
        normalized_tokens = EXCLUDED.normalized_tokens,
        normalized_size = EXCLUDED.normalized_size,
        quantity_value = EXCLUDED.quantity_value,
        quantity_unit = EXCLUDED.quantity_unit,
        pack_count = EXCLUDED.pack_count,
        updated_at = now()
    RETURNING 1
)
SELECT 'canonical_products_upserted' AS metric, count(*)::bigint AS value FROM ins;

WITH src AS (
    SELECT DISTINCT ON (rp.id, cp.id)
           rp.id AS rp_id,
           cp.id AS cp_id,
           m.doc->>'method' AS method,
           (m.doc->>'confidence')::numeric(4,3) AS confidence,
           m.doc->>'review_status' AS review_status,
           COALESCE(m.doc->'evidence', '{}'::jsonb) AS evidence
    FROM stage_product_matches m
    JOIN retailers r
         ON r.slug = m.doc->>'source_slug'
    JOIN retailer_products rp
         ON rp.retailer_id = r.id
        AND rp.sku_key = m.doc->>'sku_key'
    JOIN canonical_products cp
         ON cp.canonical_key = m.doc->>'canonical_key'
    ORDER BY rp.id, cp.id, (m.doc->>'confidence')::numeric(4,3) DESC
), ins AS (
    INSERT INTO product_matches
        (retailer_product_id, canonical_product_id, method, confidence, review_status, evidence)
    SELECT rp_id, cp_id, method, confidence, review_status, evidence
    FROM src
    ON CONFLICT (retailer_product_id, canonical_product_id) DO UPDATE SET
        method = EXCLUDED.method,
        confidence = EXCLUDED.confidence,
        review_status = EXCLUDED.review_status,
        evidence = EXCLUDED.evidence,
        updated_at = now()
    WHERE product_matches.reviewed_at IS NULL
    RETURNING 1
)
SELECT 'product_matches_upserted' AS metric, count(*)::bigint AS value FROM ins;

COMMIT;
