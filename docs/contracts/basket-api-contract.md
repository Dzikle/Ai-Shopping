# Shopping Lists & Deterministic Basket Optimization REST API Contract (`v1`)

## Overview

The M4 Basket API enables users and downstream AI/MCP tools to create persisted shopping lists and run **deterministic**, repeatable single-store and multi-store basket optimization over the authoritative PostgreSQL catalog (`offers_current`, `canonical_products`, `retailer_products`, `product_matches`, `stores`).

### Key Invariants (ADR-0001, ADR-0002, ADR-0003)

1. **Deterministic `BigDecimal` math**: All pack counts, unit conversions (`g`/`kg`, `ml`/`l`, `pack`/`pcs`), store subtotals, and savings are computed deterministically in Java (`NUMERIC(12,2)` MKD).
2. **Coverage-first single-store ranking**: Single-store results sort by:
   - `itemsCovered DESC` (coverage ratio first — a store missing items never outranks a store covering more items merely because its partial sum is smaller)
   - `exactMatchesCount DESC` (exact canonical identity preferred over substitutes)
   - `totalMkd ASC` (lowest total price in MKD)
   - `storeId ASC` (deterministic tie-breaker)
3. **Explicit missing-item behavior**: Every `SingleStoreBasketResultDto` and `MultiStorePlanDto` includes `missingItems` with item index, requested product ID/name, requested quantity/unit, and machine-readable reason (`no_offer_at_store`, `no_offer_in_selected_stores`, `product_not_found_in_catalog`).
4. **Identity vs. substitution (ADR-0003)**:
   - Default `allowSubstitutes = false`: uses only verified identity matches (`review_status IN ('auto_accepted', 'approved')`).
   - When `allowSubstitutes = true`: allows Stage-2 `pending_review` candidates as clearly flagged substitutes (`isSubstitute = true`, `substituteReason = "stage2_pending_review_candidate"`, `matchConfidence`).
5. **Multi-store split threshold (`minSplitSavingsMkd`)**: Evaluates 1..`maxStores` combinations (default `2`, max `3`) and reports `savingsVsBestSingleStoreMkd` and `meetsMinSavingsThreshold`.

---

## Endpoints

### 1. `POST /api/v1/baskets/optimize`

Stateless deterministic optimization for an ad-hoc shopping basket.

**Request body:**
```json
{
  "items": [
    { "canonicalProductId": 101, "quantity": 800, "unit": "g", "itemLabel": "Кадаиф" },
    { "canonicalProductId": 102, "quantity": 2, "unit": "pack", "itemLabel": "Кроасан Милка" },
    { "retailerProductId": 501, "quantity": 1, "unit": "pack", "itemLabel": "Vero-only item" }
  ],
  "city": null,
  "retailers": ["vero", "stokomak", "zito"],
  "maxStores": 2,
  "minSplitSavingsMkd": 15.00,
  "allowSubstitutes": false,
  "inStockOnly": true
}
```

**Response (`200 OK`):** `BasketOptimizationResponse` containing:
- `bestSingleStore`: top-ranked `SingleStoreBasketResultDto`
- `singleStoreRankings`: ordered list of `SingleStoreBasketResultDto` across candidate stores
- `bestMultiStorePlan`: optimal `MultiStorePlanDto` across up to `maxStores` stores, with `storeAllocations`, `savingsVsBestSingleStoreMkd`, `meetsMinSavingsThreshold`, and `recommendationReason`

### 2. `POST /api/v1/baskets/lists`

Persists a new shopping list in `shopping_lists` and `shopping_list_items`.

**Request body:**
```json
{
  "name": "Неделна корпа",
  "cityFilter": null,
  "items": [
    { "canonicalProductId": 101, "quantity": 800, "unit": "g", "itemLabel": "Кадаиф" },
    { "canonicalProductId": 102, "quantity": 2, "unit": "pack", "itemLabel": "Кроасан" }
  ]
}
```

**Response (`201 Created`):** `ShoppingListDto` with resolved product names, normalized sizes, quantities, and units.

### 3. `GET /api/v1/baskets/lists/{listId}`

Returns `ShoppingListDto` (`200 OK`) or `404 Not Found`.

### 4. `POST /api/v1/baskets/lists/{listId}/optimize`

Runs deterministic single-store and multi-store basket optimization for the persisted shopping list `listId` (accepting optional override fields `city`, `retailers`, `maxStores`, `minSplitSavingsMkd`, `allowSubstitutes`, `inStockOnly`).
