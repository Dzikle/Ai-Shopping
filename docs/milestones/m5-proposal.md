# M5 proposal — bounded read-only MCP server over the catalog & basket optimizer

**Status:** Design approved (2026-10-29) — implementation not started.
**Depends on:** M3 (search/comparison services, PostgreSQL fallback) + M4 (deterministic basket optimizer).

## Owner decisions (2026-10-29)

1. **Order:** M5 (MCP over existing fixture data) next; M6 live daily ingestion after.
2. **Transport:** HTTP at `/mcp` inside the existing Spring Boot backend (no separate STDIO jar).
3. **No backend LLM calls:** the MCP client's model does the language interpretation; no provider abstraction or paid API in M5.

## Goal

Let an AI agent (Claude Desktop, Antigravity, any MCP client) answer shopping questions using **actual offer data and deterministic totals**, via a small set of bounded, read-only MCP tools that call the same Java services the REST API uses. The LLM interprets the user's request and chooses tools; it never computes prices, pack counts, totals or savings itself.

Roadmap exit criterion: *agent uses actual offer data and deterministic totals.*

## Reuse-first decision

| Option | Verdict |
|---|---|
| **Spring AI MCP server starter** (`spring-ai-starter-mcp-server-webmvc`, Spring AI BOM `2.0.2` GA on Maven Central, targets Spring Boot 4.x) | **Preferred.** Annotated `@Tool` methods on existing Spring beans; no new process or language. Compatibility with our Boot `4.1.2` to be verified as the first implementation step. |
| Official MCP Java SDK used directly | Fallback if the Spring AI starter conflicts with Boot 4.1.2 / Jackson setup. More wiring, same protocol. |
| Separate Python/TypeScript MCP server calling the REST API | Rejected: second runtime, duplicate DTOs, extra hop; no benefit over in-process tools. |

## Architectural alignment

1. **Read-only, bounded (Master Plan "MCP"):** no tool writes to PostgreSQL. `optimize_shopping_basket` uses the stateless optimizer path (no `shopping_lists` writes). Every tool enforces hard caps (e.g. ≤ 25 results, ≤ 20 basket items, `maxStores` ≤ 3). No raw SQL/index access tools.
2. **Same capabilities as REST:** tools delegate to `CatalogSearchService` and `BasketOptimizerService`; no parallel query logic.
3. **Deterministic math (ADR-0001/Master Plan):** totals, `packsNeeded`, savings and rankings come from the M4 engine, returned verbatim.
4. **Identity vs substitution (ADR-0003):** `allowSubstitutes` defaults to `false`; substitutes stay flagged (`isSubstitute`, `substituteReason`, `matchConfidence`). `suggest_product_substitutes` returns only Stage-2 candidates, labelled as unverified.
5. **Evidence-backed answers:** every tool response carries `sourceUrl`, `publishedTs`, `fetchedTs`, store attribution, and a `dataFreshness` block (oldest/newest `published_ts` in the result) so the agent can state how current the data is.

## Proposed tool set

| Tool | Backed by | Notes |
|---|---|---|
| `search_products` | offers search | query, retailer, inStockOnly, promoOnly, price range; capped results |
| `compare_product_prices` | products compare | verified cross-retailer comparisons only |
| `get_price_history` | product history | by `canonicalProductId` |
| `list_stores` | stores | by retailer/city (no geo yet — see limitations) |
| `find_current_discounts` | offers search `promoOnly=true` | sorted by `discount_pct` |
| `optimize_shopping_basket` | M4 stateless optimizer | items by canonical/retailer ID + qty/unit |
| `suggest_product_substitutes` | review queue / Stage-2 candidates | explicitly unverified |

A resolving step is required because users speak in names, not IDs: the agent calls `search_products` / `compare_product_prices` to obtain IDs, then `optimize_shopping_basket`. This is documented in the tool descriptions.

## Deliverables

1. `backend/.../mcp/ShoppingMcpTools.java` (tool definitions + input validation/caps) and MCP server config (`/mcp` endpoint on the existing backend).
2. `docs/contracts/mcp-tools-contract.md` — tool names, schemas, caps, error semantics.
3. JUnit tests: each tool delegates correctly, caps enforced, read-only guarantee (no write paths reachable), substitute flags preserved.
4. `scripts/test-m5.ps1`: boots backend on the M2 fixture DB, performs MCP `initialize` → `tools/list` → `tools/call` over HTTP for each tool, and asserts that basket totals returned via MCP are **identical** to `POST /api/v1/baskets/optimize` for the same input.
5. Docs/CI updates (`current-status.md`, README, `ci.yml`).

## Non-goals (out of M5)

In-app chat UI, backend-side LLM calls / provider abstraction (the MCP client's model does the language work; no paid API needed), vector embeddings, authentication/multi-tenant access, write tools (creating shopping lists, approving matches), scheduled live ingestion (M6).

## Known limitations going in

- **Data is fixture-replay only** (Vero 1 store, Stokomak 3, Zito 3; captured 2026-10-28). An agent will answer correctly *about that data*, which will be stale. Live daily ingestion is M6.
- **No geolocation:** `stores.city` is often NULL for Stokomak/Zito; a true `find_nearby_stores` needs coordinates (deferred).
