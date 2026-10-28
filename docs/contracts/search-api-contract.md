# Search & Comparison REST API Contract (`v1`)

## Overview

The M3 read-only REST API serves catalog search, store directory, cross-retailer product comparison, price history, and identity review-queue inspection.

In accordance with **ADR-0002 (PostgreSQL + OpenSearch data architecture)** and **ADR-0003 (Identity vs Equivalence)**:
1. **PostgreSQL** is the authoritative system of record (`stores`, `retailer_products`, `offers_current`, `price_observations`, `canonical_products`, `product_matches`).
2. **OpenSearch** holds rebuildable, versioned projections (`stores_v1_<tag>`, `offers_v1_<tag>`, `products_v1_<tag>`) behind stable aliases (`stores`, `stores_v1`, `offers`, `offers_v1`, `products`, `products_v1`).
3. Every search response explicitly reports `sourceEngine` (`"opensearch"` when served by OpenSearch, or `"postgresql_fallback"` when OpenSearch is unreachable and the service automatically falls back to PostgreSQL).
4. Every offer and comparison response preserves retailer/store attribution, normalized size (`normalizedSize`), price breakdown (`priceCurrent`, `regularPrice`, `discountPrice`, `unitPrice`), `publishedTs`, `fetchedTs`, and `sourceUrl`.

---

## Endpoints

### 1. `GET /api/v1/health`

Returns database health, OpenSearch projection health, active search engine mode, and row/document counts.

```json
{
  "status": "UP",
  "databaseStatus": "UP",
  "opensearchStatus": "UP",
  "activeSearchEngine": "opensearch",
  "counts": {
    "stores": 192,
    "retailer_products": 1463,
    "offers_current": 1896,
    "price_observations": 1896,
    "canonical_products": 1372,
    "product_matches": 1483,
    "opensearch_stores": 192,
    "opensearch_offers": 1896,
    "opensearch_products": 1372
  }
}
```

### 2. `GET /api/v1/stores`

Query parameters:
- `retailer` (optional): `vero`, `stokomak`, or `zito`
- `city` (optional): e.g. `Скопје`, `Битола`, `Тетово`

Response: `SearchResponse<StoreDto>` with `activeOffersCount` and `latestPublishedTs` per store.

### 3. `GET /api/v1/offers/search`

Query parameters:
- `q` (optional): full-text search query (matches `listing_name`, `canonical_name`, `category`)
- `retailer` (optional): `vero`, `stokomak`, `zito`
- `storeKey` (optional): e.g. `vero-1`, `stokomak-1`, `zito-2`
- `category` (optional): retailer category filter
- `inStockOnly` (optional, default `false`): filter `availability = 'in_stock'`
- `promoOnly` (optional, default `false`): filter active promotions
- `minPrice` / `maxPrice` (optional): MKD `price_current` bounds
- `sort` (optional, default `price_asc`): `price_asc` or `price_desc`
- `page` (optional, default `0`), `size` (optional, default `20`)

Response: `SearchResponse<OfferDto>`.

### 4. `GET /api/v1/products/compare`

Returns canonical products matched across multiple retailers (`review_status IN ('auto_accepted', 'approved')` only — Stage-2 `pending_review` candidates are never mixed into comparisons).

Query parameters:
- `q` (optional): search query on canonical product name / tokens
- `minRetailers` (optional, default `2`): minimum distinct retailers offering the canonical product
- `page` (optional, default `0`), `size` (optional, default `20`)

Response: `SearchResponse<ProductComparisonDto>` containing `cheapestMkd`, `highestMkd`, `spreadMkd`, `latestPublishedTs`, and per-retailer offer summaries (`RetailerOfferSummaryDto`).

### 5. `GET /api/v1/products/{canonicalId}/history`

Returns `ProductHistoryResponse` with ordered `price_observations` across all matched retailers and stores for the given `canonicalId`, or HTTP `404` if `canonicalId` does not exist.

### 6. `GET /api/v1/matches/review-queue`

Query parameters:
- `limit` (optional, default `25`, max `200`)

Returns `List<ReviewQueueItemDto>` for Stage-2 `pending_review` candidate matches ordered by `confidence DESC`, including `evidence` JSON (`shared_tokens`, `jaccard`, `normalized_size`).
