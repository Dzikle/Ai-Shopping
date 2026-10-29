# Model Context Protocol (MCP) Tools Contract (`v1`)

## Overview

The AI Shopping MCP Server exposes bounded, read-only tools over the authoritative catalog, search projections, and deterministic basket optimization engine to external AI agents (e.g. Claude Desktop, Antigravity, or any standard MCP client).

In accordance with **ADR-0001, ADR-0002, ADR-0003, and the Master Implementation Plan**:
1. **Bounded & Read-Only**: No tool mutates canonical state, creates persisted shopping lists, or accesses raw database connections.
2. **Deterministic Calculations**: The MCP server never asks an LLM to compute totals, convert units, scale packs, or calculate savings. All arithmetic is performed deterministically by the underlying Java/PostgreSQL services and returned verbatim.
3. **Identity vs. Equivalence (ADR-0003)**: Exact identity matches (`auto_accepted` / `approved`) are strictly separated from ambiguous candidates. The `suggest_product_substitutes` tool returns unverified Stage-2 candidates explicitly labeled with `isSubstitute: true` and their `matchConfidence`.
4. **Data Provenance & Freshness**: Every product offer carries `sourceUrl`, `publishedTs`, `fetchedTs`, store attribution, and a `dataFreshness` envelope.
5. **Transport**: Streamable HTTP / JSON-RPC 2.0 at `POST /mcp` and `GET /mcp` (SSE / Streamable HTTP endpoint discovery).

---

## Protocol Specification

- **Protocol Version:** `2024-11-05`
- **Endpoint:** `POST /mcp` (Content-Type: `application/json`)
- **JSON-RPC Methods Supported:**
  - `initialize`: Returns server capabilities and metadata (`name: "ai-shopping-mcp-server"`, `version: "0.5.0"`).
  - `notifications/initialized`: Notification acknowledging initialization.
  - `ping`: Health ping returning `{}`.
  - `tools/list`: Returns JSON schemas for all available tools.
  - `tools/call`: Executes the requested tool with input arguments and returns `{ "content": [{"type": "text", "text": "..."}], "isError": false }`.

---

## Tool Definitions

### 1. `search_products`
Full-text search for current grocery offers across retailers and stores with pricing, promo info, and provenance.

**Parameters:**
- `query` (string, required): Search query (e.g. "млеко", "брашно", "чоколадо").
- `retailer` (string, optional): Filter by retailer slug (`vero`, `stokomak`, `zito`).
- `city` (string, optional): Store city filter.
- `inStockOnly` (boolean, optional, default `true`): Only in-stock offers.
- `promoOnly` (boolean, optional, default `false`): Only active promotions.
- `minPrice` / `maxPrice` (number, optional): Price bounds in MKD.
- `size` (integer, optional, default `10`, max `25`): Number of offers to return.

### 2. `compare_product_prices`
Compare verified canonical products across supermarket chains (Vero, Stokomak, Zito).

**Parameters:**
- `query` (string, optional): Product name query.
- `minRetailers` (integer, optional, default `2`, min `1`): Minimum distinct chains selling the product.
- `size` (integer, optional, default `10`, max `25`): Results count limit.

### 3. `get_price_history`
Retrieve the immutable price observation timeline and promotional changes for a canonical product.

**Parameters:**
- `canonicalProductId` (integer, required): The ID of the canonical product.

### 4. `list_stores`
List supermarket store branches with active offer counts and latest published timestamp.

**Parameters:**
- `retailer` (string, optional): Filter by retailer slug (`vero`, `stokomak`, `zito`).
- `city` (string, optional): City filter.

### 5. `find_current_discounts`
Find top active promotional discounts across stores and retailers sorted by discount percentage.

**Parameters:**
- `retailer` (string, optional): Filter by retailer slug (`vero`, `stokomak`, `zito`).
- `category` (string, optional): Category filter.
- `size` (integer, optional, default `10`, max `25`): Maximum results to return.

### 6. `optimize_shopping_basket`
Stateless deterministic basket calculation and optimization across single stores and multi-store splits.

**Parameters:**
- `items` (array of objects, required, max 20 items):
  - `canonicalProductId` (integer, optional)
  - `retailerProductId` (integer, optional)
  - `quantity` (number, default `1`)
  - `unit` (string: `pack`, `pcs`, `g`, `kg`, `ml`, `l`)
  - `itemLabel` (string, optional)
- `city` (string, optional): Store city constraint.
- `retailers` (array of strings, optional): Retailer slug whitelist.
- `maxStores` (integer, optional, default `2`, min `1`, max `3`): Max store split.
- `minSplitSavingsMkd` (number, optional, default `0.0`): Minimum split savings threshold.
- `allowSubstitutes` (boolean, optional, default `false`): Allow Stage-2 candidate substitutes.
- `inStockOnly` (boolean, optional, default `true`): Require items to be currently in stock.

### 7. `suggest_product_substitutes`
Retrieve unverified Stage-2 substitute candidate pairs for items missing or out of stock.

**Parameters:**
- `canonicalProductId` (integer, optional): Canonical product ID to find candidates for.
- `limit` (integer, optional, default `10`, max `25`): Max candidates to return.
