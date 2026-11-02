# M5 proposal — bounded, read-only MCP server & AI tool layer

**Status:** Implemented on owner instruction (2026-11-02), pending owner review.
**Depends on:** M3 (search/comparison REST API) + M4 (basket optimization REST API).

## Goal

Expose the authoritative catalog and the deterministic M3/M4 computations to AI
agents through a **small, bounded, strictly read-only Model Context Protocol (MCP)
server**. The agent gets real offer data with provenance; every price, unit
conversion, pack count, basket total and saving remains the backend's
deterministic `BigDecimal` result.

## Architectural alignment (ADR-0001, ADR-0002, ADR-0004, AGENTS.md)

1. **No arithmetic in the AI layer (Master Plan, ADR-0001).**
   The MCP tools never compute, round, estimate or aggregate prices. They
   forward parameters to the REST API and return its payload unchanged, adding
   only presentation metadata (`provenance`, `truncated`, `identityScope`,
   `equivalenceStatus`, `computation`).
2. **PostgreSQL authoritative, OpenSearch a projection (ADR-0002).**
   The MCP server holds no data store of its own. It has no database driver and
   no OpenSearch client; it only speaks to the allowlisted read-only REST routes
   plus the stateless `POST /api/v1/baskets/optimize` computation.
3. **Identity is not equivalence (ADR-0003/ADR-0004).**
   `compare_product_prices` and `get_product_details` report
   `identityScope: "verified_identity_only"`. `suggest_product_substitutes`
   labels every candidate `equivalenceStatus: "not_verified_equivalent"` and
   never blends candidates into identity results.
4. **Provenance and quarantine (AGENTS.md #3, #6).**
   Every offer-bearing result carries `sourceUrl`, `publishedTs`, `fetchedTs`
   (per item) and a `provenance` summary; upstream failures produce an explicit
   tool error, never invented or cached prices.
5. **Least privilege for public AI agents (Master Plan, MCP section).**
   Route allowlist, no redirects, hard caps on query length, page size, basket
   lines, store count, price-observation depth, inbound frame size and response
   size; unknown arguments are rejected instead of silently ignored.

## Deliverables

1. **`mcp_server/` package (Python 3.12, standard library only):**
   - `contract.py` — versioned (`MCP_TOOLS_VERSION = "v1"`) tool contract and all
     hard caps; single source of truth for schemas, docs and tests.
   - `api_client.py` — `CatalogApiClient`: route allowlist (regex, method-aware),
     no-redirect opener, timeout, response-size cap, URL-length cap, structured
     `UpstreamError`/`ReadOnlyViolation`.
   - `tools.py` — nine deterministic pass-through handlers plus argument
     validation and provenance summarisation.
   - `server.py` — JSON-RPC 2.0 dispatch (`initialize`, `ping`, `tools/list`,
     `tools/call`), notifications, batch frames, error codes (`-32700`,
     `-32600`, `-32601`, `-32602`) and in-band tool errors (`isError: true`).
   - `cli.py` — MCP stdio transport (`python -B -m mcp_server.cli`), `--list-tools`
     for inspecting the contract without any network call.
   - `mock_catalog_api.py` — in-process mock of the M3/M4 REST API (real
     Vero/Stokomak/Zito prices and provenance from the committed fixtures).
   - `tests.py` — 31 contract tests (protocol, schemas, bounds, determinism,
     provenance, identity labelling, read-only enforcement, failure modes,
     stdio round-trip).

2. **Tool surface (`v1`, read-only, bounded):**

   | Tool | Backing route | Hard cap |
   |---|---|---|
   | `search_products` | `GET /api/v1/offers/search` | `limit` ≤ 50, `q` ≤ 200 chars |
   | `get_product_details` | `GET /api/v1/products/{id}/history` + `GET /api/v1/offers/search` | 200 observations, 50 offers |
   | `compare_product_prices` | `GET /api/v1/products/compare` | `limit` ≤ 50, `minRetailers` ≤ 3 |
   | `get_price_history` | `GET /api/v1/products/{id}/history` | 200 observations |
   | `find_stores` | `GET /api/v1/stores` | `limit` ≤ 50 |
   | `find_current_discounts` | `GET /api/v1/offers/search?promoOnly=true` | 50 scan rows, `limit` ≤ 50 |
   | `suggest_product_substitutes` | `GET /api/v1/offers/search` | `limit` ≤ 50, category-scoped |
   | `optimize_shopping_basket` | `POST /api/v1/baskets/optimize` | 25 lines, `maxStores` ≤ 3, quantity ≤ 100000 |
   | `get_catalog_health` | `GET /api/v1/health` | — |

   `find_nearby_stores` from the master plan is deliberately **not** shipped as a
   radius search: the authoritative schema has no store geo-coordinates yet, so
   `find_stores` offers only a city text filter and says so
   (`geoScope: "city_text_filter_only"`).

3. **Documentation:** `docs/contracts/mcp-tools-contract.md` (protocol, tools,
   schemas, limits, error semantics, security boundaries, client configuration).

4. **Tests & CI:** `mcp_server/tests.py` runs without Docker/JVM/PostgreSQL
   against `mcp_server/mock_catalog_api.py`; `scripts/test-m5.ps1` re-runs the
   suite for the standard milestone script layout and verifies a live API when
   one is reachable. The three `.github/workflows/ci.yml` edits (doc check, MCP
   suite, M5 step) are specified in `docs/ci/m5-ci-steps.md` and are **pending
   owner application**: the agent's GitHub App token lacks the `workflows`
   permission, so the workflow file cannot be changed from an automation branch.

## Exit criterion (roadmap M5)

An MCP client can initialize the server, list the nine tools, search real
offers, compare verified identities across retailers, read price history, get
discounts, propose clearly-labelled substitutes, and optimize a basket — with
backend-identical totals and full provenance — while every mutation route is
unreachable.

## Non-goals (explicitly out of M5)

Natural-language interpretation / prompt orchestration (client responsibility),
embeddings or semantic retrieval, write operations of any kind (persisted lists,
alerts), authentication/multi-tenant accounts, delivery-fee modelling, and
unattended scheduling (M6).

## Local environment note

The MCP layer needs no Docker, JVM or database. Verification commands:

```bash
python3 -B mcp_server/tests.py
python3 -B -m mcp_server.cli --list-tools
AI_SHOPPING_API_BASE=http://localhost:8080 python3 -B -m mcp_server.cli   # stdio
```

