# ADR-0005: First ingestion source is Vero; Ramstore blocked pending written consent

- **Status:** Accepted (2026-10-28)
- **Context:** Validation (see `docs/research/retailer-sources.md`) found Vero publishes plain static HTML store price lists at `pricelist.vero.com.mk` with per-store pagination, unit prices, availability, promotions and a last-updated timestamp — matching our data model almost exactly. Ramstore's site terms prohibit downloading/using site content without written consent, regardless of permissive robots.txt. KAM's price list is JS-embedded with unresolved format.
- **Decision:** M1 targets Vero only. Ramstore ingestion is forbidden until the owner obtains written consent; KAM is deferred until its embedded document format is confirmed and legality re-checked.
- **Consequences:** All M1 fixtures, tests and schema design use Vero's row schema. Multi-source (M2) starts with the next validated source, not necessarily Ramstore.
