"""Versioned and bounded MCP tool contract for the AI Shopping platform (M5).

Single source of truth shared by:

* the MCP server (`mcp_server.server`) that advertises and executes tools,
* the documentation (`docs/contracts/mcp-tools-contract.md`),
* the contract tests (`mcp_server/tests.py`).

Design rules enforced by this module (see ADR-0002, ADR-0004, ADR-0006):

1. Every tool is **read-only** (`readOnlyHint: True`, `destructiveHint: False`).
   The only non-GET route any tool may use is ``POST /api/v1/baskets/optimize``,
   which is a stateless, non-persisting deterministic computation.
2. Every tool is **bounded**: query length, page size, basket size, store count
   and price-observation depth all have hard caps that a client cannot raise.
3. Every tool is **deterministic**: it forwards parameters and returns the REST
   response unchanged. No tool performs arithmetic on prices, quantities,
   pack sizes, basket totals or savings. Identity/substitution flags are passed
   through from the backend, never inferred by the tool layer.
"""

from __future__ import annotations

MCP_PROTOCOL_VERSIONS = ("2025-06-18", "2025-03-26")
DEFAULT_PROTOCOL_VERSION = "2025-06-18"

# Hard caps. Clients can only request *lower* values.
DEFAULT_LIMIT = 20
MAX_LIMIT = 50
MAX_QUERY_CHARS = 200
MAX_IDENTIFIER_CHARS = 120
MAX_PRICE_OBSERVATIONS = 200
MAX_BASKET_ITEMS = 25
MAX_QUANTITY = 100000
MAX_STORES_ALLOWED = 3
MAX_RETAILER_FILTERS = 3
MIN_DISCOUNT_PCT = 0
MAX_DISCOUNT_PCT = 100

SUPPORTED_UNITS = ("pack", "pcs", "g", "kg", "ml", "l")
SUPPORTED_SORTS = ("price_asc", "price_desc")
KNOWN_RETAILER_SLUGS = ("vero", "stokomak", "zito")

READ_ONLY_NOTE = (
    "Read-only tool. Prices, pack counts, unit conversions, basket totals and "
    "savings are computed deterministically by the authoritative PostgreSQL/Java "
    "services; this tool only forwards parameters and returns the backend result "
    "with its original provenance (sourceUrl, publishedTs, fetchedTs)."
)

_PAGING_PROPERTIES = {
    "limit": {
        "type": "integer",
        "minimum": 1,
        "maximum": MAX_LIMIT,
        "default": DEFAULT_LIMIT,
        "description": f"Maximum number of items to return (hard cap {MAX_LIMIT}).",
    },
}

_RETAILER_PROPERTY = {
    "type": "string",
    "enum": list(KNOWN_RETAILER_SLUGS),
    "description": "Optional retailer slug filter.",
}

TOOLS: list[dict] = [
    {
        "name": "search_products",
        "title": "Search products and store offers",
        "description": (
            "Search store-level offers by free text, retailer, store, category, "
            "price range, availability and active promotions. Returns exact "
            "store offers with price, unit price, promotion metadata, normalized "
            "size, availability, publishedTs, fetchedTs and sourceUrl. "
            + READ_ONLY_NOTE
        ),
        "inputSchema": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "q": {
                    "type": "string",
                    "maxLength": MAX_QUERY_CHARS,
                    "description": "Free-text query on listing name, canonical name or category.",
                },
                "retailer": _RETAILER_PROPERTY,
                "storeKey": {
                    "type": "string",
                    "maxLength": MAX_IDENTIFIER_CHARS,
                    "description": "Optional store key such as 'vero-1' or 'zito-2'.",
                },
                "category": {
                    "type": "string",
                    "maxLength": MAX_QUERY_CHARS,
                    "description": "Optional retailer category filter.",
                },
                "inStockOnly": {"type": "boolean", "default": False},
                "promoOnly": {"type": "boolean", "default": False},
                "minPrice": {"type": "number", "minimum": 0},
                "maxPrice": {"type": "number", "minimum": 0},
                "sort": {"type": "string", "enum": list(SUPPORTED_SORTS), "default": "price_asc"},
                **_PAGING_PROPERTIES,
            },
        },
        "annotations": {"readOnlyHint": True, "destructiveHint": False, "openWorldHint": False},
    },
    {
        "name": "get_product_details",
        "title": "Get canonical product details",
        "description": (
            "Return one canonical product with its immutable price-observation "
            "history and the current verified-identity store offers for it. "
            "Only verified identity matches are used for the offer list. "
            + READ_ONLY_NOTE
        ),
        "inputSchema": {
            "type": "object",
            "additionalProperties": False,
            "required": ["canonicalProductId"],
            "properties": {
                "canonicalProductId": {"type": "integer", "minimum": 1},
                "historyLimit": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": MAX_PRICE_OBSERVATIONS,
                    "default": MAX_PRICE_OBSERVATIONS,
                },
                "offerLimit": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": MAX_LIMIT,
                    "default": DEFAULT_LIMIT,
                },
            },
        },
        "annotations": {"readOnlyHint": True, "destructiveHint": False, "openWorldHint": False},
    },

    {
        "name": "compare_product_prices",
        "title": "Compare product prices across retailers",
        "description": (
            "Return canonical products matched across at least `minRetailers` "
            "retailers with cheapest/highest price, spread, per-retailer offer "
            "summaries and the latest published timestamp. Stage-2 pending "
            "candidates are never included (ADR-0004). " + READ_ONLY_NOTE
        ),
        "inputSchema": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "q": {"type": "string", "maxLength": MAX_QUERY_CHARS},
                "minRetailers": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": len(KNOWN_RETAILER_SLUGS),
                    "default": 2,
                },
                **_PAGING_PROPERTIES,
            },
        },
        "annotations": {"readOnlyHint": True, "destructiveHint": False, "openWorldHint": False},
    },
    {
        "name": "get_price_history",
        "title": "Get product price history",
        "description": (
            "Return the ordered, immutable price_observations timeline for a "
            "canonical product across all matched retailers and stores. "
            "Timestamps are returned exactly as stored (publishedTs, fetchedTs). "
            + READ_ONLY_NOTE
        ),
        "inputSchema": {
            "type": "object",
            "additionalProperties": False,
            "required": ["canonicalProductId"],
            "properties": {
                "canonicalProductId": {"type": "integer", "minimum": 1},
                "limit": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": MAX_PRICE_OBSERVATIONS,
                    "default": MAX_PRICE_OBSERVATIONS,
                },
            },
        },
        "annotations": {"readOnlyHint": True, "destructiveHint": False, "openWorldHint": False},
    },
    {
        "name": "find_stores",
        "title": "Find stores",
        "description": (
            "List retailer stores with active offer counts and latest published "
            "timestamp, optionally filtered by retailer and city. Radius search "
            "is intentionally not offered until store geo-coordinates exist in "
            "the authoritative schema. " + READ_ONLY_NOTE
        ),
        "inputSchema": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "retailer": _RETAILER_PROPERTY,
                "city": {"type": "string", "maxLength": MAX_IDENTIFIER_CHARS},
                **_PAGING_PROPERTIES,
            },
        },
        "annotations": {"readOnlyHint": True, "destructiveHint": False, "openWorldHint": False},
    },
    {
        "name": "find_current_discounts",
        "title": "Find current discounts",
        "description": (
            "Return currently promoted store offers, optionally filtered by "
            "retailer, category and a minimum discount percentage. Results are "
            "sorted by discount percentage (descending), then price (ascending), "
            "then offer id for deterministic ordering. Prices are not modified. "
            + READ_ONLY_NOTE
        ),
        "inputSchema": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "retailer": _RETAILER_PROPERTY,
                "category": {"type": "string", "maxLength": MAX_QUERY_CHARS},
                "minDiscountPct": {
                    "type": "number",
                    "minimum": MIN_DISCOUNT_PCT,
                    "maximum": MAX_DISCOUNT_PCT,
                    "default": MIN_DISCOUNT_PCT,
                },
                **_PAGING_PROPERTIES,
            },
        },
        "annotations": {"readOnlyHint": True, "destructiveHint": False, "openWorldHint": False},
    },
    {
        "name": "suggest_product_substitutes",
        "title": "Suggest product substitutes",
        "description": (
            "Suggest candidate alternatives from current store offers for a "
            "product. Every candidate is explicitly flagged with "
            "equivalenceStatus='not_verified_equivalent': these are substitution "
            "candidates, never verified identities (ADR-0004). Exact identity "
            "questions must use compare_product_prices. " + READ_ONLY_NOTE
        ),
        "inputSchema": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "canonicalProductId": {
                    "type": "integer",
                    "minimum": 1,
                    "description": "Product to exclude from the candidate list.",
                },
                "q": {
                    "type": "string",
                    "maxLength": MAX_QUERY_CHARS,
                    "description": "Seed query, e.g. 'млеко 1л'.",
                },
                "category": {"type": "string", "maxLength": MAX_QUERY_CHARS},
                "retailer": _RETAILER_PROPERTY,
                **_PAGING_PROPERTIES,
            },
        },
        "annotations": {"readOnlyHint": True, "destructiveHint": False, "openWorldHint": False},
    },
    {
        "name": "optimize_shopping_basket",
        "title": "Optimize a shopping basket",
        "description": (
            "Price a shopping basket and return deterministic single-store "
            "rankings plus the best multi-store split plan. Coverage-first "
            "ranking, unit/pack scaling, missing-item reasons and substitute "
            "flags are computed by the backend exactly as in the M4 contract. "
            + READ_ONLY_NOTE
        ),
        "inputSchema": {
            "type": "object",
            "additionalProperties": False,
            "required": ["items"],
            "properties": {
                "items": {
                    "type": "array",
                    "minItems": 1,
                    "maxItems": MAX_BASKET_ITEMS,
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "canonicalProductId": {"type": "integer", "minimum": 1},
                            "retailerProductId": {"type": "integer", "minimum": 1},
                            "itemLabel": {"type": "string", "maxLength": MAX_QUERY_CHARS},
                            "quantity": {
                                "type": "number",
                                "exclusiveMinimum": 0,
                                "maximum": MAX_QUANTITY,
                                "default": 1,
                            },
                            "unit": {"type": "string", "enum": list(SUPPORTED_UNITS), "default": "pack"},
                        },
                    },
                },
                "city": {"type": "string", "maxLength": MAX_IDENTIFIER_CHARS},
                "retailers": {
                    "type": "array",
                    "maxItems": MAX_RETAILER_FILTERS,
                    "items": {"type": "string", "enum": list(KNOWN_RETAILER_SLUGS)},
                },
                "maxStores": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": MAX_STORES_ALLOWED,
                    "default": 2,
                },
                "minSplitSavingsMkd": {"type": "number", "minimum": 0},
                "allowSubstitutes": {"type": "boolean", "default": False},
                "inStockOnly": {"type": "boolean", "default": True},
            },
        },
        "annotations": {"readOnlyHint": True, "destructiveHint": False, "openWorldHint": False},
    },
    {
        "name": "get_catalog_health",
        "title": "Get catalog health",
        "description": (
            "Report database/projection health, the active search engine "
            "(opensearch or postgresql_fallback) and authoritative row counts, "
            "so an agent can state how fresh and complete the catalog is. "
            + READ_ONLY_NOTE
        ),
        "inputSchema": {"type": "object", "additionalProperties": False, "properties": {}},
        "annotations": {"readOnlyHint": True, "destructiveHint": False, "openWorldHint": False},
    },
]

TOOL_NAMES = tuple(tool["name"] for tool in TOOLS)
TOOLS_BY_NAME = {tool["name"]: tool for tool in TOOLS}

