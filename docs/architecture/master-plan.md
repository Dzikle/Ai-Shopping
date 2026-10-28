# Master implementation plan v0.1

**Project:** Dzikle/Ai-Shopping  
**Status:** Proposed architecture; no implementation started.  
**Initial market:** North Macedonia; future multi-country, multi-retailer and multi-category.

## Mission
Collect daily public retailer price publications, normalize rich attributes into a unified catalog, maintain store-specific current offers and price history, and expose reliable search, comparison, basket optimization and AI/MCP tools.

## Architecture boundaries

```text
Retailer HTML / JSON / PDF / CSV
    -> Store-aware source adapters (Python/TypeScript)
    -> Scheduled jobs + retry + rate limit + source snapshots
    -> Parsing / validation / normalization / identity resolution
    -> PostgreSQL canonical products, retailer SKUs, offers, history, provenance
    -> Versioned OpenSearch projections: products, offers, stores, intelligence
    -> Spring Boot REST API and bounded MCP tools
    -> Web/mobile clients and AI shopping agent
```

- Start as a modular monolith plus independent worker processes; Docker Compose first.
- PostgreSQL authoritative; OpenSearch disposable/rebuildable. Use index aliases and controlled versioned reindexing.
- Raw source snapshots stored immutably in filesystem initially; migrate to S3-compatible object store when justified.
- Distinguish **canonical product**, **retailer product**, **store-specific offer**, **timestamped price observation**, **promotion** and **product-match evidence**.
- Exact identity: verified GTIN + variant/pack checks where present. Candidate matches can use normalized names/attributes and OpenSearch; LLM only for review of ambiguous candidates. Equivalent substitutes are not exact identities.
- Never infer current availability or prices from stale snapshots; expose freshness, source URL and update time.

## Preferred stack (to verify during M0)
- Java 21 / Spring Boot backend, PostgreSQL, OpenSearch 3.x, Python adapter workers (TypeScript where reuse justifies), Redis if useful, Docker Compose, GitHub Actions, JUnit / pytest, structured logs; Prometheus/Grafana later.
- Model-agnostic AI interface; semantic retrieval is later milestone, not a baseline dependency.

## Data design
Tables envisaged: retailers, stores, canonical_products, retailer_products, product_matches, offers_current, price_observations, promotions, ingestion_runs, raw_snapshots, shopping_lists, price_alerts. Include currency, taxes, quantity, unit, stock/availability status, source capture timestamp, retailer published timestamp, source URL and run id. Define uniqueness/idempotency constraints. Prefer price history partitioning only when volumes warrant it.

## Search indexes (planned)
- `products_v1`: canonical attributes, taxonomy, normalized names, identifiers and optional embeddings.
- `offers_v1`: store-specific price, promotion and availability, source freshness.
- `stores_v1`: chain, location and geo.
- `price_intelligence_v1`: materialized recent statistics (not all raw historical observations).

Search uses barcode, exact attributes, normalized Macedonian Cyrillic/Latin terms, keyword relevance, filters, unit pricing and later vectors/hybrid. Calculations and ordering are deterministic, not delegated to LLM.

## MCP (planned, read-only first)
`search_products`, `compare_product_prices`, `get_product_details`, `get_price_history`, `find_nearby_stores`, `compare_shopping_basket`, `optimize_shopping_basket`, `find_current_discounts`, `find_price_anomalies`, `suggest_product_substitutes`.

MCP is an agent interface over the same application capabilities used by REST. Restrict scope, permissions, result counts, source provenance and freshness. Avoid direct unrestricted database/index tools for public AI agents.

## Quality and operation
- Rate limiting and legal/terms review per source.
- Job leases, idempotent retries, validation and fixture tests.
- Quarantine unexpectedly empty catalogs or large drops; do not erase prior offers.
- Run source freshness monitoring, observability, backup/recovery tests and source-level anomaly detection.
- Daily ingestion triggered after relevant publication deadlines, with retries and verified published timestamps.
- Preserve upstream MIT notices for reused code; assess third-party data licenses separately.

## Stage gates
M0 research/foundation; M1 ingest a real source; M2 matching across two sources; M3 OpenSearch and API; M4 basket optimization; M5 AI/MCP; M6 operational reliability. Each gate requires tests, evidence and owner approval. See roadmap.
