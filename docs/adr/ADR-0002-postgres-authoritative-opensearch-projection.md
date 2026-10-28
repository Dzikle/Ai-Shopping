# ADR-0002: PostgreSQL authoritative, OpenSearch a rebuildable projection

- **Status:** Accepted (2026-10-28)
- **Context:** Price data must be correct and auditable (provenance, timestamps, unit sizes); search must be fast and flexible. Duplicated truth would drift.
- **Decision:** PostgreSQL (18.x) is the single source of truth for retailers, stores, products, matches, offers, price history, promotions and ingestion runs. OpenSearch (3.9.x) holds versioned index projections (`*_v1`) built only from PostgreSQL, behind aliases, rebuilt via controlled reindexing. Any index can be dropped and rebuilt without data loss. Version verification: PostgreSQL 18.6 is current stable; OpenSearch 3.9.0 released 2026-09-29.
- **Consequences:** Every projection change requires a rebuild path and alias flip. Debugging starts in PostgreSQL. OpenSearch may be unavailable without losing data.
