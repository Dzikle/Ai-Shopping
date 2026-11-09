"""Bounded read-only MCP tool registry - port of McpToolRegistry.java."""

import datetime as dt
from decimal import Decimal
from typing import Any

from app.services.basket_optimizer_service import BasketOptimizerService
from app.services.catalog_search_service import CatalogSearchService


class McpToolRegistry:
    def __init__(self, catalog_service: CatalogSearchService, basket_service: BasketOptimizerService):
        self._catalog = catalog_service
        self._basket = basket_service

    def list_tools(self) -> list[dict[str, Any]]:
        def tool(name: str, description: str, properties: dict[str, Any], required: list[str] | None = None):
            schema: dict[str, Any] = {"type": "object", "properties": properties}
            if required:
                schema["required"] = required
            return {"name": name, "description": description, "inputSchema": schema}

        return [
            tool(
                "search_products",
                "Search current grocery offers by product name, brand, or category across stores and retailers with pricing and provenance.",
                {
                    "query": {"type": "string", "description": "Search query (e.g. 'млеко', 'брашно', 'чоколадо')"},
                    "retailer": {"type": "string", "description": "Filter by retailer slug ('vero', 'stokomak', 'zito')"},
                    "city": {"type": "string", "description": "Store city filter"},
                    "inStockOnly": {"type": "boolean", "description": "Filter in-stock offers only (default true)"},
                    "promoOnly": {"type": "boolean", "description": "Filter active discounts only (default false)"},
                    "minPrice": {"type": "number", "description": "Minimum price in MKD"},
                    "maxPrice": {"type": "number", "description": "Maximum price in MKD"},
                    "size": {"type": "integer", "description": "Results count limit (default 10, max 25)"},
                },
                ["query"],
            ),
            tool(
                "compare_product_prices",
                "Compare prices for canonical products across multiple supermarket chains (Vero, Stokomak, Zito). Returns cheapest/highest prices, spread, and store offers.",
                {
                    "query": {"type": "string", "description": "Product name query (e.g. 'кадаиф', 'супа')"},
                    "minRetailers": {"type": "integer", "description": "Minimum distinct supermarket chains offering the product (default 2)"},
                    "size": {"type": "integer", "description": "Results count limit (default 10, max 25)"},
                },
            ),
            tool(
                "get_price_history",
                "Retrieve the immutable price observation timeline and promotional changes for a canonical product across stores and retailers.",
                {
                    "canonicalProductId": {"type": "integer", "description": "Canonical product ID"},
                },
                ["canonicalProductId"],
            ),
            tool(
                "list_stores",
                "List supermarket store branches with location, active offer counts, and catalog freshness.",
                {
                    "retailer": {"type": "string", "description": "Filter by retailer slug ('vero', 'stokomak', 'zito')"},
                    "city": {"type": "string", "description": "City filter"},
                },
            ),
            tool(
                "find_current_discounts",
                "Find top active promotional discounts and sales across stores and retailers sorted by discount percentage.",
                {
                    "retailer": {"type": "string", "description": "Filter by retailer slug ('vero', 'stokomak', 'zito')"},
                    "category": {"type": "string", "description": "Category filter"},
                    "size": {"type": "integer", "description": "Results count limit (default 10, max 25)"},
                },
            ),
            tool(
                "optimize_shopping_basket",
                "Deterministically calculate and optimize total basket cost across single stores and multi-store splits with pack scaling and unit conversion.",
                {
                    "items": {
                        "type": "array",
                        "description": "List of basket items to purchase (max 20)",
                        "items": {
                            "type": "object",
                            "properties": {
                                "canonicalProductId": {"type": "integer", "description": "Canonical product ID"},
                                "retailerProductId": {"type": "integer", "description": "Retailer-specific product ID"},
                                "quantity": {"type": "number", "description": "Requested quantity (default 1)"},
                                "unit": {"type": "string", "description": "Requested unit ('pack', 'pcs', 'g', 'kg', 'ml', 'l')"},
                                "itemLabel": {"type": "string", "description": "Optional label or product name"},
                            },
                        },
                    },
                    "city": {"type": "string", "description": "Store city constraint"},
                    "retailers": {"type": "array", "items": {"type": "string"}, "description": "Retailer slug whitelist"},
                    "maxStores": {"type": "integer", "description": "Max stores to split across (default 2, min 1, max 3)"},
                    "minSplitSavingsMkd": {"type": "number", "description": "Minimum MKD savings required to recommend splitting stores"},
                    "allowSubstitutes": {"type": "boolean", "description": "Allow Stage-2 candidate substitutes (default false)"},
                    "inStockOnly": {"type": "boolean", "description": "Require in-stock items (default true)"},
                },
                ["items"],
            ),
            tool(
                "suggest_product_substitutes",
                "Retrieve potential product substitutes from Stage-2 high-overlap candidate matches for products that may be out of stock or missing in certain stores.",
                {
                    "canonicalProductId": {"type": "integer", "description": "Canonical product ID to find substitutes for"},
                    "limit": {"type": "integer", "description": "Results count limit (default 10, max 25)"},
                },
            ),
        ]

    def call_tool(self, name: str, arguments: dict[str, Any] | None) -> dict[str, Any]:
        args: dict[str, Any] = arguments if arguments is not None else {}
        try:
            if name == "search_products":
                payload = self._search_products(args)
            elif name == "compare_product_prices":
                payload = self._compare_products(args)
            elif name == "get_price_history":
                payload = self._price_history(args)
            elif name == "list_stores":
                payload = self._list_stores(args)
            elif name == "find_current_discounts":
                payload = self._current_discounts(args)
            elif name == "optimize_shopping_basket":
                payload = self._optimize_basket(args)
            elif name == "suggest_product_substitutes":
                payload = self._suggest_substitutes(args)
            else:
                raise ValueError(f"Unknown tool: {name}")

            text = _pretty_json(payload)
            return {"content": [{"type": "text", "text": text}], "isError": False}
        except Exception as exc:
            message = str(exc) if str(exc) else repr(exc)
            text = _pretty_json({"error": message})
            return {"content": [{"type": "text", "text": text}], "isError": True}

    # ---- tool handlers ----

    def _search_products(self, args):
        query = _as_string(args.get("query"))
        if query is None or not query.strip():
            raise ValueError("'query' parameter is required for search_products")
        retailer = _as_string(args.get("retailer"))
        city = _as_string(args.get("city"))
        in_stock = _as_boolean(args.get("inStockOnly"), True)
        promo_only = _as_boolean(args.get("promoOnly"), False)
        min_price = _as_decimal(args.get("minPrice"))
        max_price = _as_decimal(args.get("maxPrice"))
        size = _bound_int(args.get("size"), 10, 1, 25)

        filter_obj = _Filter(
            query, retailer, None, None, in_stock, promo_only, min_price, max_price, "price_asc", 0, size
        )
        resp = self._catalog.search_offers(filter_obj)
        timestamps = [
            item["publishedTs"] for item in resp["items"] if item.get("publishedTs") is not None
        ]
        return {
            "totalMatches": resp["total"],
            "sourceEngine": resp["sourceEngine"],
            "items": resp["items"],
            "dataFreshness": _compute_freshness(timestamps),
        }

    def _compare_products(self, args):
        query = _as_string(args.get("query"))
        min_retailers = _bound_int(args.get("minRetailers"), 2, 1, 3)
        size = _bound_int(args.get("size"), 10, 1, 25)

        resp = self._catalog.compare_products(query, min_retailers, 0, size)
        timestamps = [
            item["latestPublishedTs"] for item in resp["items"] if item.get("latestPublishedTs") is not None
        ]
        return {
            "totalComparisons": resp["total"],
            "sourceEngine": resp["sourceEngine"],
            "comparisons": resp["items"],
            "dataFreshness": _compute_freshness(timestamps),
        }

    def _price_history(self, args):
        canonical_id = _as_integer(args.get("canonicalProductId"))
        if canonical_id is None:
            raise ValueError("'canonicalProductId' parameter is required for get_price_history")

        hist = self._catalog.get_product_history(canonical_id)
        if hist is None:
            return {"error": f"Canonical product not found: {canonical_id}"}

        timestamps = [
            obs["publishedTs"] for obs in hist["observations"] if obs.get("publishedTs") is not None
        ]
        return {
            "canonicalProductId": hist["canonicalProductId"],
            "canonicalName": hist["canonicalName"],
            "normalizedSize": hist["normalizedSize"],
            "totalObservations": len(hist["observations"]),
            "observations": hist["observations"],
            "dataFreshness": _compute_freshness(timestamps),
        }

    def _list_stores(self, args):
        retailer = _as_string(args.get("retailer"))
        city = _as_string(args.get("city"))
        resp = self._catalog.get_stores(retailer, city)
        timestamps = [
            item["latestPublishedTs"] for item in resp["items"] if item.get("latestPublishedTs") is not None
        ]
        return {
            "totalStores": resp["total"],
            "stores": resp["items"],
            "dataFreshness": _compute_freshness(timestamps),
        }

    def _current_discounts(self, args):
        retailer = _as_string(args.get("retailer"))
        category = _as_string(args.get("category"))
        size = _bound_int(args.get("size"), 10, 1, 25)

        filter_obj = _Filter(
            None, retailer, None, category, True, True, None, None, "price_asc", 0, size
        )
        resp = self._catalog.search_offers(filter_obj)
        timestamps = [
            item["publishedTs"] for item in resp["items"] if item.get("publishedTs") is not None
        ]
        return {
            "totalDiscounts": resp["total"],
            "discounts": resp["items"],
            "dataFreshness": _compute_freshness(timestamps),
        }

    def _optimize_basket(self, args):
        raw_items = args.get("items")
        if not isinstance(raw_items, list) or not raw_items:
            raise ValueError("'items' parameter must be a non-empty list of basket items")
        if len(raw_items) > 20:
            raise ValueError("Basket size cannot exceed 20 items per request")

        items = []
        for raw in raw_items:
            if isinstance(raw, dict):
                canon_id = _as_integer(raw.get("canonicalProductId"))
                ret_id = _as_integer(raw.get("retailerProductId"))
                qty = _as_decimal(raw.get("quantity"))
                unit = _as_string(raw.get("unit"))
                label = _as_string(raw.get("itemLabel"))
                from app.schemas.requests import BasketItemRequest

                items.append(BasketItemRequest(
                    canonicalProductId=canon_id,
                    retailerProductId=ret_id,
                    itemLabel=label,
                    quantity=qty if qty is not None else Decimal(1),
                    unit=unit if unit is not None else "pack",
                ))

        city = _as_string(args.get("city"))
        retailers = None
        if isinstance(args.get("retailers"), list):
            retailers = [str(r) for r in args["retailers"]]
        max_stores = _bound_int(args.get("maxStores"), 2, 1, 3)
        min_savings = _as_decimal(args.get("minSplitSavingsMkd"))
        allow_substitutes = _as_boolean(args.get("allowSubstitutes"), False)
        in_stock_only = _as_boolean(args.get("inStockOnly"), True)

        from app.schemas.requests import BasketOptimizeRequest

        req = BasketOptimizeRequest(
            items=items, city=city, retailers=retailers, maxStores=max_stores,
            minSplitSavingsMkd=min_savings, allowSubstitutes=allow_substitutes,
            inStockOnly=in_stock_only,
        )
        opt_resp = self._basket.optimize_basket(req)

        timestamps = []
        if opt_resp.get("bestSingleStore") is not None:
            for line in opt_resp["bestSingleStore"]["coveredItems"]:
                if line.get("publishedTs") is not None:
                    timestamps.append(line["publishedTs"])

        return {
            "totalItemsRequested": opt_resp["totalItemsRequested"],
            "allowSubstitutes": opt_resp["allowSubstitutes"],
            "inStockOnly": opt_resp["inStockOnly"],
            "bestSingleStore": opt_resp["bestSingleStore"],
            "bestMultiStorePlan": opt_resp["bestMultiStorePlan"],
            "allSingleStoreRankings": opt_resp["singleStoreRankings"],
            "dataFreshness": _compute_freshness(timestamps),
        }

    def _suggest_substitutes(self, args):
        canonical_id = _as_integer(args.get("canonicalProductId"))
        limit = _bound_int(args.get("limit"), 10, 1, 25)

        queue = self._catalog.get_review_queue(limit)
        if canonical_id is not None:
            queue = [item for item in queue if item["candidateCanonicalId"] == canonical_id]

        return {
            "note": "Substitutes are Stage-2 high-overlap unverified candidates per ADR-0003.",
            "substitutesCount": len(queue),
            "candidates": queue,
        }


class _Filter:
    def __init__(self, q, retailer, storeKey, category, inStockOnly, promoOnly,
                 minPrice, maxPrice, sort, page, size):
        self.q = q
        self.retailer = retailer
        self.storeKey = storeKey
        self.category = category
        self.inStockOnly = inStockOnly
        self.promoOnly = promoOnly
        self.minPrice = minPrice
        self.maxPrice = maxPrice
        self.sort = sort
        self.page = page
        self.size = size


def _pretty_json(payload) -> str:
    import json

    def default(obj):
        if isinstance(obj, Decimal):
            return float(obj)
        if isinstance(obj, dt.datetime):
            if obj.tzinfo is None:
                obj = obj.replace(tzinfo=dt.UTC)
            iso = obj.isoformat()
            return iso[:-6] + "Z" if iso.endswith("+00:00") else iso
        if isinstance(obj, dt.date):
            return obj.isoformat()
        raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")

    return json.dumps(payload, ensure_ascii=False, indent=2, default=default)


def _compute_freshness(timestamps) -> dict[str, Any]:
    instants = [_as_instant(t) for t in timestamps]
    instants = [t for t in instants if t is not None]
    if not instants:
        return {"status": "no_timestamps_available"}
    minimum = min(instants)
    maximum = max(instants)
    return {
        "oldestOfferPublishedTs": minimum,
        "latestOfferPublishedTs": maximum,
        "sampleCount": len(instants),
    }


def _as_instant(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.astimezone(dt.timezone.utc).isoformat().replace("+00:00", "Z")
    if isinstance(value, dt.datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=dt.UTC)
        iso = value.astimezone(dt.timezone.utc).isoformat()
        return iso.replace("+00:00", "Z")
    return None


def _as_string(obj) -> str | None:
    if obj is None:
        return None
    return str(obj).strip()


def _as_integer(obj) -> int | None:
    if isinstance(obj, bool):
        return None
    if isinstance(obj, (int, float)):
        return int(obj)
    if isinstance(obj, Decimal):
        return int(obj)
    if isinstance(obj, str) and obj.strip():
        try:
            return int(obj.strip())
        except ValueError:
            return None
    return None


def _as_decimal(obj) -> Decimal | None:
    if obj is None:
        return None
    if isinstance(obj, bool):
        return None
    if isinstance(obj, (int, float)):
        return Decimal(str(obj))
    if isinstance(obj, Decimal):
        return obj
    if isinstance(obj, str) and obj.strip():
        try:
            return Decimal(obj.strip())
        except Exception:
            return None
    return None


def _as_boolean(obj, default_val: bool) -> bool:
    if obj is None:
        return default_val
    if isinstance(obj, bool):
        return obj
    if isinstance(obj, str) and obj.strip():
        s = obj.strip().lower()
        if s == "true":
            return True
        if s == "false":
            return False
        return default_val
    return default_val


def _bound_int(obj, default_val: int, minimum: int, maximum: int) -> int:
    value = _as_integer(obj)
    if value is None:
        return default_val
    return max(minimum, min(maximum, value))
