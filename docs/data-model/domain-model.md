# Domain model — preliminary

- `Retailer`: chain identity.
- `Store`: retailer location, geo, branch identifiers.
- `CanonicalProduct`: normalized brand, variant, pack/quantity/unit, GTIN when verified.
- `RetailerProduct`: source SKU, listing title and attributes; can map to canonical product with evidence.
- `ProductMatch`: match method, confidence, review status, evidence/version. Exact matches separated from substitutes.
- `OfferCurrent`: retailer product + store, price, currency, tax/unit price, stock and promotion, freshness.
- `PriceObservation`: immutable captured price/availability at retailer-published and collected timestamps.
- `Promotion`: source-listed discount and validity period; independent computed price-history signals.
- `IngestionRun`: source, version, status, checks, counters, errors, start/end.
- `RawSnapshot`: content hash, archive location, URL and time.
- `ShoppingList` and `PriceAlert`: future user features.

Define keys, FK constraints, unique offers per (store, retailer SKU), temporal history, deletion/withdrawal semantics and idempotent ingestion in M1 design. Prices must be decimal, not float.
