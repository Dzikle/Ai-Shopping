-- Read-only, complete active-match export for matching/reconciliation_audit.py.
-- Execute via psql INSIDE the postgres container. The only output is a CSV
-- file in the container filesystem; no database tables or records are changed.
\set ON_ERROR_STOP on
BEGIN TRANSACTION READ ONLY;
\copy (SELECT r.slug AS source_slug, rp.sku_key, rp.id AS retailer_product_id, rp.listing_name, cp.id AS canonical_product_id, cp.canonical_key, pm.id AS match_id, pm.review_status, COALESCE(pm.reviewed_at::text, '') AS reviewed_at FROM product_matches pm JOIN retailer_products rp ON rp.id = pm.retailer_product_id JOIN retailers r ON r.id = rp.retailer_id JOIN canonical_products cp ON cp.id = pm.canonical_product_id WHERE pm.review_status IN ('auto_accepted', 'approved') ORDER BY rp.id, pm.id) TO '/tmp/aishopping/current_active_matches.csv' WITH (FORMAT csv, HEADER true, ENCODING 'UTF8')
COMMIT;
