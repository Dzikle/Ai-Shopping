# M2 proposal — multiple sources + canonical identity

**Status:** Approved & implemented (2026-10-28).
**Owner decisions:** Stokomak + Zito on `*.proverkanaceni.mk`; 3-store subset per retailer; deterministic exact match + Stage-2 review queue (no LLM in M2); byte-exact HTML fixtures committed.
**Depends on:** M1 (done: Vero schema, adapter, loader, fixtures, idempotent replay).

## Goal

Two or more independent retailers loaded into PostgreSQL with canonical product
identity per ADR-0003, and a verified exact product comparison across retailers.

## Validated second-source basis (live checks, 2026-10-28)

The statutory "Проверка на цени" app family is hosted on a shared platform
(`*.proverkanaceni.mk`, IIS) used by several chains - one adapter parameterized
by retailer subdomain can cover all of them:

| Retailer | URL | Status at check | Notes |
| --- | --- | --- | --- |
| Stokomak | `stokomak.proverkanaceni.mk` | **REACHABLE** (live fetch OK) | 85 stores; store 1 = 2689 articles; prices updated `28/10/2026 20:55` |
| Zito | `zito.proverkanaceni.mk` | **REACHABLE** (live fetch OK) | ~94 stores; org ids are sparse and start at 2 (selector parsing required, not guessing); prices updated `28/10/2026 20:56`; org with zero articles returns "Нема податоци" page |
| Top Market | `topmarket.proverkanaceni.mk` | transport error at check time | same app family, retry later |
| Maxi Market / МАКОИЛ-ПАМ / МКБ Миса / Стокомак-Србија | `*.proverkanaceni.mk` | not checked / reachable | same app |
| Tinex | `ceni.tinex.mk` (self-hosted, port 442) | **UNREACHABLE** (TCP timeout from local network and webfetch; last known-good crawl Feb 2026) | same schema family; defer until reachable |

Format differences from Vero (drives the "independent adapter" work):
- Query-param pages `?org={org}&perPage={n}&page={k}` instead of static
  `{storeId}_{page}.html` files.
- Non-promo rows omit the three promo `<td>` cells entirely (Vero always has 10).
- Unit price format `1кгр = 142.00 ден.` vs Vero's `1255 ден/парче`.
- Promo format `249 ден. Попуст:31%`, dates `18.02.2026 до 03.03.2026`
  (dot dates, `до` separator) vs Vero's `10 %` and `28/10/2026 - 10/11/2026`.
- Total-count line `Прикажи 1 - 20 од 2689 артикли`; updated line
  `Датум и време на последно ажурирање на цените: ...`.

robots/terms: no robots.txt on `stokomak.proverkanaceni.mk` (404 = no
restrictions); `stokomak.com.mk` robots allows crawling (only WP admin paths
blocked). The price-check sites are the retailers' own statutory public price
publications. Politeness rules apply (see risks).

## Deliverables

1. **`adapters/common/`** - shared normalization used by all adapters:
   name normalization (NFC, whitespace, case), price parsing (`71 ден.`,
   `1.255,50`), percent parsing (`10 %`, `Попуст:31%`), date/range parsing
   (`28/10/2026 - 10/11/2026`, `18.02.2026 до 03.03.2026`), unit-price parsing
   (`1255 ден/парче`, `1кгр = 142.00 ден.`), availability mapping.
2. **Vero adapter refactor onto `adapters/common/`** - behavior unchanged,
   all 22 existing tests stay green (regression proof).
3. **`adapters/stokomak/`** (same worker contract, parameterized by retailer
   subdomain, covers Stokomak + Zito): selector parsing (org values + store
   names), store-page parsing (6/9-column variants), pagination walker,
   quarantine on empty-results pages, snapshot/records/manifest emission.
4. **`migrations/V2__m2_identity.sql`** per ADR-0003:
   `canonical_products` (canonical id, normalized attributes, declared size),
   `product_matches` (`retailer_product_id` -> `canonical_product_id`, method,
   confidence, review_status, evidence JSONB, review workflow fields).
5. **`matching/` package**: deterministic stage-1 exact-normalized match;
   stage-2 candidate generation (brand + size tokens) -> review queue;
   **no LLM in the merge path** (ADR-0003: LLM may only review ambiguous pairs,
   and even then a human approves); matches emitted as ndjson + loader.
6. **Cross-retailer comparison evidence**:
   `scripts/report-cross-retailer.ps1` + SQL - canonical products offered by
   >= 2 retailers with same-day prices side by side, plus price history
   listing per canonical product from `price_observations`.
7. **Tests + CI**: Stokomak/Zito fixtures committed (same byte-exact policy),
   matcher tests, cross-retailer comparison test, idempotency for the second
   source, CI extended.

## Exit criterion (roadmap M2)

Verified exact product comparison across retailers: a reproducible report of
canonical products with offers from both Vero and Stokomak/Zito, matching
evidence recorded, zero silent merges.

## Non-goals (explicitly out of M2)

OpenSearch projection (M3), baskets (M4), AI/MCP (M5), scheduling (M6),
Tinex until reachable, Ramstore (blocked by its terms), KAM (unresolved
format), LLM-assisted merging (only review, and even that is out of M2 scope).

## Risks / limitations

- Shared platform = single operational point for several retailers; politeness
  limits will be conservative (1 req/s default, hard caps), and the platform
  blocks browser copy/devtools (statutory publication nonetheless).
- Offer history: `price_observations` is already immutable and accumulates
  history, but real multi-day history requires scheduled daily runs (M6). M2
  demonstrates the history mechanism on current + replayed data only.
- Zito org ids are sparse; store discovery must come from the selector page.
- Cross-retailer overlap depends on brand-name SKUs; produce-and-own-brand
  items may not match exactly - expected and documented.
