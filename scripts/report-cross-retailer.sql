-- report-cross-retailer.sql - M2 cross-retailer price comparison and observation history report.
-- Only verified matches (review_status IN ('auto_accepted', 'approved')) participate in comparisons;
-- ambiguous candidates in 'pending_review' are reported separately in the review queue section.

\set ON_ERROR_STOP on
\pset pager off

\echo '=== 1. CROSS-RETAILER EXACT PRODUCT COMPARISON (VERIFIED IDENTITY ONLY) ==='
WITH active_offers AS (
    SELECT cp.id AS canonical_id,
           cp.canonical_name,
           cp.normalized_size,
           r.slug AS retailer_slug,
           rp.listing_name,
           MIN(oc.price_current) AS retailer_min_price,
           MAX(oc.price_current) AS retailer_max_price,
           COUNT(DISTINCT oc.store_id) AS store_count,
           MAX(oc.published_ts) AS latest_published_ts,
           MAX(pm.method) AS match_method,
           MIN(pm.confidence) AS min_confidence
    FROM canonical_products cp
    JOIN product_matches pm
         ON pm.canonical_product_id = cp.id
        AND pm.review_status IN ('auto_accepted', 'approved')
    JOIN retailer_products rp
         ON rp.id = pm.retailer_product_id
    JOIN retailers r
         ON r.id = rp.retailer_id
    JOIN offers_current oc
         ON oc.retailer_product_id = rp.id
    GROUP BY cp.id, cp.canonical_name, cp.normalized_size, r.slug, rp.listing_name
), multi_retailer AS (
    SELECT canonical_id
    FROM active_offers
    GROUP BY canonical_id
    HAVING COUNT(DISTINCT retailer_slug) >= 2
)
SELECT ao.canonical_name,
       ao.normalized_size AS size,
       COUNT(DISTINCT ao.retailer_slug) AS retailers,
       MIN(ao.retailer_min_price) AS cheapest_mkd,
       MAX(ao.retailer_max_price) AS highest_mkd,
       (MAX(ao.retailer_max_price) - MIN(ao.retailer_min_price)) AS spread_mkd,
       STRING_AGG(
           ao.retailer_slug || ': ' || ao.retailer_min_price || ' MKD (' || ao.listing_name || ')',
           ' | ' ORDER BY ao.retailer_min_price, ao.retailer_slug
       ) AS side_by_side_offers
FROM active_offers ao
JOIN multi_retailer mr ON mr.canonical_id = ao.canonical_id
GROUP BY ao.canonical_id, ao.canonical_name, ao.normalized_size
ORDER BY ao.canonical_name;

\echo ''
\echo '=== 2. PRICE OBSERVATION HISTORY FOR CROSS-RETAILER CANONICAL PRODUCTS ==='
WITH cross_canonicals AS (
    SELECT cp.id AS canonical_id, cp.canonical_name, cp.normalized_size
    FROM canonical_products cp
    JOIN product_matches pm
         ON pm.canonical_product_id = cp.id
        AND pm.review_status IN ('auto_accepted', 'approved')
    JOIN retailer_products rp ON rp.id = pm.retailer_product_id
    JOIN offers_current oc ON oc.retailer_product_id = rp.id
    GROUP BY cp.id, cp.canonical_name, cp.normalized_size
    HAVING COUNT(DISTINCT rp.retailer_id) >= 2
)
SELECT cc.canonical_name,
       cc.normalized_size AS size,
       r.slug AS retailer,
       s.external_key AS store_key,
       s.name AS store_name,
       po.price_current AS price_mkd,
       po.availability,
       po.published_ts
FROM cross_canonicals cc
JOIN product_matches pm
     ON pm.canonical_product_id = cc.canonical_id
    AND pm.review_status IN ('auto_accepted', 'approved')
JOIN retailer_products rp ON rp.id = pm.retailer_product_id
JOIN retailers r ON r.id = rp.retailer_id
JOIN price_observations po ON po.retailer_product_id = rp.id
JOIN stores s ON s.id = po.store_id
ORDER BY cc.canonical_name, r.slug, s.external_key::int, po.published_ts DESC;

\echo ''
\echo '=== 3. STAGE-2 REVIEW QUEUE SAMPLE (PENDING_REVIEW - NOT MERGED) ==='
SELECT r.slug AS source_retailer,
       rp.listing_name AS source_listing,
       cp.canonical_name AS candidate_target,
       cp.normalized_size AS size,
       pm.confidence,
       pm.review_status,
       pm.evidence->'shared_tokens' AS shared_tokens
FROM product_matches pm
JOIN retailer_products rp ON rp.id = pm.retailer_product_id
JOIN retailers r ON r.id = rp.retailer_id
JOIN canonical_products cp ON cp.id = pm.canonical_product_id
WHERE pm.review_status = 'pending_review'
ORDER BY pm.confidence DESC, rp.listing_name
LIMIT 15;
