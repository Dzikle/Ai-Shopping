# Read-Only MCP Tool Contract (`v1`)

## Overview

`ai-shopping-mcp` is a bounded, strictly read-only MCP (Model Context Protocol)
server that exposes the M3/M4 Spring Boot REST API to AI agents. It is implemented
with the Python 3.12 standard library only (`mcp_server/`), holds no database
connection and no cache, and never performs price arithmetic.

### Key invariants (ADR-0001, ADR-0002, ADR-0003, ADR-0004)

1. **Deterministic money, server-side only.** Every price, unit price, pack count,
   unit conversion, basket total and saving is the value computed by
   PostgreSQL/Java and returned by the REST API. Tools only validate and forward
   arguments; they never recompute, round or aggregate.
2. **Read-only by construction.** `CatalogApiClient` has a method-aware route
   allowlist. Persisted shopping-list creation, match review writes and every
   other mutation route raise `ReadOnlyViolation` before a socket is opened.
   Redirects are refused so an upstream `3xx` cannot widen the allowlist.
3. **Identity ≠ equivalence.** `compare_product_prices` and
   `get_product_details` return `identityScope: "verified_identity_only"`.
   `suggest_product_substitutes` marks each candidate
   `equivalenceStatus: "not_verified_equivalent"` and never merges it into
   identity results.
4. **Provenance & freshness always attached.** Offer payloads keep `sourceUrl`,
   `publishedTs`, `fetchedTs`, `availability`; results add a `provenance`
   summary (`oldestPublishedTs`, `latestPublishedTs`, `latestFetchedTs`,
   `sourceUrlCount`, `sourceUrls`, `sourceEngine`).
5. **Explicit failure, never fabrication.** Upstream errors become
   `isError: true` tool results with a machine-readable `reason`; the server
   never returns cached, stale or synthesised prices.
6. **Bounded everything.** See the limits table below; clients can request lower
   values but cannot raise caps.

---

## Transport & lifecycle

* **Transport:** newline-delimited JSON-RPC 2.0 over stdin/stdout (MCP stdio).
  Diagnostics go to stderr only. Batch frames and notifications are supported.
* **Protocol versions:** `2025-06-18` (preferred) and `2025-03-26`; an
  unsupported requested version falls back to `2025-06-18`.
* **Capabilities:** `{"tools": {"listChanged": false}}` — no resources, prompts,
  sampling, logging or completion capabilities are advertised.
* **Methods:** `initialize`, `notifications/initialized`, `ping`, `tools/list`,
  `tools/call`. Anything else returns JSON-RPC `-32601`.

```json
{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"agent","version":"1"}}}
```

```json
{"jsonrpc":"2.0","id":1,"result":{"protocolVersion":"2025-06-18","capabilities":{"tools":{"listChanged":false}},"serverInfo":{"name":"ai-shopping-mcp","version":"1.0.0"},"instructions":"Read-only price-intelligence tools ..."}}
```

---

## Tool catalogue (`v1`)

| Tool | Purpose | Backing REST route |
|---|---|---|
| `search_products` | Search store offers by text/retailer/store/category/price/availability/promo | `GET /api/v1/offers/search` |
| `get_product_details` | Canonical product + history + current verified-identity offers | `GET /api/v1/products/{id}/history`, `GET /api/v1/offers/search` |
| `compare_product_prices` | Cross-retailer comparison for verified identities | `GET /api/v1/products/compare` |
| `get_price_history` | Immutable price observation timeline | `GET /api/v1/products/{id}/history` |
| `find_stores` | Store directory by retailer / city | `GET /api/v1/stores` |
| `find_current_discounts` | Active promotions above a discount threshold | `GET /api/v1/offers/search?promoOnly=true` |
| `suggest_product_substitutes` | Category-scoped alternatives, never claimed equivalent | `GET /api/v1/offers/search` |
| `optimize_shopping_basket` | Deterministic single/multi-store basket pricing | `POST /api/v1/baskets/optimize` |
| `get_catalog_health` | DB/projection health, active engine, row counts | `GET /api/v1/health` |

Every tool declares `annotations: {"readOnlyHint": true, "destructiveHint": false, "openWorldHint": false}`.

### Example call — `search_products`

```json
{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"search_products","arguments":{"q":"млеко","retailer":"zito","inStockOnly":true,"promoOnly":true,"limit":10}}}
```

Result envelope (abridged):

```json
{
  "jsonrpc": "2.0",
  "id": 2,
  "result": {
    "content": [{"type": "text", "text": "{ ...structuredContent as JSON... }"}],
    "structuredContent": {
      "sourceEngine": "opensearch",
      "total": 1,
      "returned": 1,
      "limit": 10,
      "truncated": false,
      "items": [{
        "offerId": "303:1",
        "retailerSlug": "zito",
        "storeName": "ЖИТО 2",
        "listingName": "МЛЕКО БИТОЛСКО 1Л",
        "priceCurrent": 62.00,
        "discountPct": 23.00,
        "isPromo": true,
        "availability": "in_stock",
        "publishedTs": "2026-10-29T06:10:00Z",
        "fetchedTs": "2026-10-29T06:30:00Z",
        "sourceUrl": "https://zito.proverkanaceni.mk/?org=2&perPage=100&page=1"
      }],
      "provenance": {
        "attributionPreserved": true,
        "sourceEngine": "opensearch",
        "oldestPublishedTs": "2026-10-29T06:10:00Z",
        "latestPublishedTs": "2026-10-29T06:10:00Z",
        "latestFetchedTs": "2026-10-29T06:30:00Z",
        "sourceUrlCount": 1,
        "sourceUrls": ["https://zito.proverkanaceni.mk/?org=2&perPage=100&page=1"]
      }
    },
    "isError": false
  }
}
```

### Input schemas

All schemas are `"type": "object"`, `"additionalProperties": false`. Unknown
arguments are rejected with `unknown_argument`.

**`search_products`**

| Field | Type | Notes |
|---|---|---|
| `q` | string ≤ 200 | matches listing name, canonical name, category |
| `retailer` | enum `vero`/`stokomak`/`zito` | |
| `storeKey` | string ≤ 120 | e.g. `vero-1`, `zito-2` |
| `category` | string ≤ 200 | |
| `inStockOnly`, `promoOnly` | boolean | default `false` |
| `minPrice`, `maxPrice` | number ≥ 0 | `minPrice <= maxPrice` |
| `sort` | enum `price_asc`/`price_desc` | default `price_asc` |
| `limit` | integer 1..50 | default 20 |

**`get_product_details`** — `canonicalProductId` (required, integer ≥ 1),
`historyLimit` (1..200, default 200), `offerLimit` (1..50, default 20).
Offers are found with the canonical name's head tokens (size/pack tokens
dropped, reported as `offerSearchSeed`) and then filtered to offers whose
`canonicalProductId` equals the request — verified identity, never fuzzy
matching.

**`compare_product_prices`** — `q` (string ≤ 200), `minRetailers` (1..3,
default 2), `limit` (1..50, default 20).

**`get_price_history`** — `canonicalProductId` (required), `limit` (1..200,
default 200).

**`find_stores`** — `retailer` (enum), `city` (string ≤ 120), `limit`
(1..50, default 20). Returns `geoScope: "city_text_filter_only"`; radius search
is unavailable until authoritative store coordinates exist.

**`find_current_discounts`** — `retailer`, `category`, `minDiscountPct`
(0..100, default 0), `limit` (1..50). Scans at most 50 promoted offers, filters
by `discountPct`, then orders by discount desc, price asc, `offerId` asc.

**`suggest_product_substitutes`** — `canonicalProductId` and/or `q` (one is
required), `category`, `retailer`, `limit` (1..50). The seed category is read
from the backend's own offer record (no string heuristics in the tool layer).

**`optimize_shopping_basket`**

| Field | Type | Notes |
|---|---|---|
| `items` | array 1..25 | required |
| `items[].canonicalProductId` / `items[].retailerProductId` | integer ≥ 1 | exactly one per line |
| `items[].itemLabel` | string ≤ 200 | |
| `items[].quantity` | number > 0, ≤ 100000 | default 1 (e.g. `800` with `unit: "g"`) |
| `items[].unit` | enum `pack`/`pcs`/`g`/`kg`/`ml`/`l` | default `pack` |
| `city` | string ≤ 120 | |
| `retailers` | array ≤ 3 of known slugs | |
| `maxStores` | integer 1..3 | default 2 |
| `minSplitSavingsMkd` | number ≥ 0 | forwarded to backend threshold |
| `allowSubstitutes` | boolean | default `false` (exact identity only) |
| `inStockOnly` | boolean | default `true` |

Response = the M4 `BasketOptimizationResponse` **unchanged**, plus
`computation: "server_side_deterministic_bigdecimal"`, `identityPolicy`,
`request` (echo) and `note`. `isSubstitute` is whatever the backend computed.

**`get_catalog_health`** — no arguments.

---

## Results, errors & limits

### Tool result envelope

* Success: `{"content":[{"type":"text","text":"<json>"}], "structuredContent": {...}, "isError": false}`.
  The `text` block always deserialises to exactly `structuredContent`.
* Failure: `{"content":[{"type":"text","text":"{\"error\": ...}"}], "structuredContent":{"error":{...}}, "isError": true}`.
  Protocol errors (bad frame, unknown tool/method) use JSON-RPC `error` instead.

### Machine-readable error reasons

| Reason | Meaning |
|---|---|
| `missing_argument` | required argument absent |
| `invalid_argument` | wrong type/range/enum, or `minPrice > maxPrice` |
| `unknown_argument` | argument not defined by the tool schema |
| `seed_product_not_found` | substitute seed has no canonical name |
| `product_not_found` | upstream `404` for the canonical product |
| `upstream_rejected_request` | upstream `400` |
| `upstream_rate_limited` | upstream `429` |
| `upstream_timeout` | no response within the configured timeout |
| `upstream_unavailable` | backend unreachable (no prices are invented) |
| `upstream_redirect_not_allowed` | upstream attempted a redirect |
| `upstream_response_too_large` | response exceeded the byte cap |
| `upstream_invalid_json` | non-JSON / unexpected document type |
| `upstream_error` | upstream `5xx` or other failure (`upstreamStatus` included) |
| `read_only_violation` | attempted route outside the allowlist |
| `result_too_large` | tool payload exceeded the outbound cap |
| `internal_error` | unexpected failure (logged to stderr only) |

### Hard limits

| Limit | Value |
|---|---|
| Page size (`limit`) | 50 |
| Query length (`q`, `category`, `itemLabel`) | 200 chars |
| Store key / city | 120 chars |
| Price observations per call | 200 |
| Basket lines | 25 |
| Quantity per line | 100000 |
| `maxStores` | 3 |
| Retailer filters | 3 |
| Upstream timeout | 10 s default (max 30 s) |
| Upstream response | 2 MB |
| Inbound JSON-RPC frame | 256 KB |
| Tool result payload | 1 MB |
| Request URL | 1024 chars |

### Read-only route allowlist

```
GET  /api/v1/health
GET  /api/v1/stores
GET  /api/v1/offers/search
GET  /api/v1/products/compare
GET  /api/v1/products/{id}/history      (numeric id only)
POST /api/v1/baskets/optimize           (stateless computation)
```

Not reachable, by design: `POST /api/v1/baskets/lists`,
`GET /api/v1/matches/review-queue` (internal review surface), any future write
endpoint, any path containing traversal segments.

---

## Client configuration

```json
{
  "mcpServers": {
    "ai-shopping": {
      "command": "python3",
      "args": ["-B", "-m", "mcp_server.cli"],
      "cwd": "/path/to/Ai-Shopping",
      "env": {
        "AI_SHOPPING_API_BASE": "http://localhost:8080",
        "AI_SHOPPING_API_TIMEOUT": "10"
      }
    }
  }
}
```

Environment variables: `AI_SHOPPING_API_BASE` (default `http://localhost:8080`),
`AI_SHOPPING_API_TIMEOUT`, `AI_SHOPPING_MAX_RESPONSE_BYTES`.

## Verification

```bash
python3 -B mcp_server/tests.py                       # 31 contract tests, no Docker/JVM
python3 -B -m mcp_server.cli --list-tools            # print this contract as JSON
./scripts/test-m5.ps1 -ApiBase http://localhost:8080 # milestone script (+ live API if up)
```

