"""Deterministic, bounded tool implementations for the read-only MCP server.

Every handler is a *pass-through*: it validates and clamps client arguments,
forwards them to the authoritative REST API, and returns the backend payload
without altering prices, pack counts, unit conversions, totals or savings.
Only presentation concerns are added (provenance summary, truncation flags,
explicit identity/equivalence labelling).
"""

from __future__ import annotations

import math

from . import contract

# Fields we keep when re-shaping substitute/offer candidate lists.
_OFFER_SUMMARY_FIELDS = (
    "offerId",
    "retailerSlug",
    "retailerName",
    "storeId",
    "storeExternalKey",
    "storeName",
    "city",
    "retailerProductId",
    "listingName",
    "canonicalProductId",
    "canonicalName",
    "normalizedSize",
    "category",
    "currency",
    "priceCurrent",
    "unitPrice",
    "unitLabel",
    "isPromo",
    "discountPct",
    "availability",
    "publishedTs",
    "fetchedTs",
    "sourceUrl",
)


class ToolInputError(Exception):
    """Invalid tool arguments, reported to the agent as a structured tool error."""

    def __init__(self, reason: str, message: str):
        super().__init__(message)
        self.reason = reason
        self.message = message

    def as_dict(self) -> dict:
        return {"reason": self.reason, "message": self.message}


# -- argument validation ----------------------------------------------------
def _reject_unknown(args: dict, tool_name: str) -> None:
    allowed = set(contract.TOOLS_BY_NAME[tool_name]["inputSchema"].get("properties", {}))
    unknown = sorted(set(args) - allowed)
    if unknown:
        raise ToolInputError(
            "unknown_argument",
            f"unsupported argument(s) for {tool_name}: {', '.join(unknown)}; "
            f"allowed: {', '.join(sorted(allowed))}",
        )


def _opt_str(args: dict, name: str, max_len: int) -> str | None:
    value = args.get(name)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ToolInputError("invalid_argument", f"{name} must be a string")
    value = value.strip()
    if not value:
        return None
    if len(value) > max_len:
        raise ToolInputError("invalid_argument", f"{name} exceeds {max_len} characters")
    return value


def _opt_bool(args: dict, name: str, default: bool) -> bool:
    value = args.get(name)
    if value is None:
        return default
    if not isinstance(value, bool):
        raise ToolInputError("invalid_argument", f"{name} must be a boolean")
    return value


def _number(args: dict, name: str, *, default=None, required: bool = False, minimum=None, maximum=None):
    value = args.get(name)
    if value is None:
        if required:
            raise ToolInputError("missing_argument", f"{name} is required")
        return default
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ToolInputError("invalid_argument", f"{name} must be a number")
    if not math.isfinite(value):
        raise ToolInputError("invalid_argument", f"{name} must be finite")
    if minimum is not None and value < minimum:
        raise ToolInputError("invalid_argument", f"{name} must be >= {minimum}")
    if maximum is not None and value > maximum:
        raise ToolInputError("invalid_argument", f"{name} must be <= {maximum}")
    return value


def _integer(args: dict, name: str, *, default=None, required: bool = False, minimum=None, maximum=None):
    value = args.get(name)
    if value is None:
        if required:
            raise ToolInputError("missing_argument", f"{name} is required")
        return default
    if isinstance(value, bool) or not isinstance(value, int):
        raise ToolInputError("invalid_argument", f"{name} must be an integer")
    if minimum is not None and value < minimum:
        raise ToolInputError("invalid_argument", f"{name} must be >= {minimum}")
    if maximum is not None and value > maximum:
        raise ToolInputError("invalid_argument", f"{name} must be <= {maximum}")
    return value


def _enum(args: dict, name: str, allowed: tuple[str, ...], default=None):
    value = _opt_str(args, name, contract.MAX_IDENTIFIER_CHARS)
    if value is None:
        return default
    if value not in allowed:
        raise ToolInputError("invalid_argument", f"{name} must be one of: {', '.join(allowed)}")
    return value


def _limit(args: dict) -> int:
    return _integer(
        args, "limit", default=contract.DEFAULT_LIMIT, minimum=1, maximum=contract.MAX_LIMIT
    )


# -- presentation helpers (no arithmetic on money) ---------------------------
def _timestamp_of(item: dict) -> str | None:
    return item.get("publishedTs") or item.get("latestPublishedTs")


def _provenance(items: list[dict], source_engine: str | None) -> dict:
    published = sorted({ts for ts in (_timestamp_of(i) for i in items) if ts})
    fetched = sorted({i.get("fetchedTs") for i in items if i.get("fetchedTs")})
    urls = sorted({i.get("sourceUrl") for i in items if i.get("sourceUrl")})
    return {
        "attributionPreserved": True,
        "sourceEngine": source_engine,
        "oldestPublishedTs": published[0] if published else None,
        "latestPublishedTs": published[-1] if published else None,
        "latestFetchedTs": fetched[-1] if fetched else None,
        "sourceUrlCount": len(urls),
        "sourceUrls": urls[:5],
    }


def _paged_envelope(response: dict, limit: int) -> dict:
    raw_items = response.get("items")
    items = list(raw_items) if isinstance(raw_items, list) else []
    returned = items[:limit]
    total = response.get("total")
    truncated = bool(isinstance(total, int) and total > len(returned))
    return {
        "sourceEngine": response.get("sourceEngine"),
        "total": total,
        "returned": len(returned),
        "limit": limit,
        "truncated": truncated,
        "items": returned,
        "provenance": _provenance(returned, response.get("sourceEngine")),
    }


def _offer_summary(item: dict) -> dict:
    return {field: item.get(field) for field in _OFFER_SUMMARY_FIELDS if field in item}


# -- handlers ---------------------------------------------------------------
def search_products(client, args: dict) -> dict:
    _reject_unknown(args, "search_products")
    limit = _limit(args)
    query = {
        "q": _opt_str(args, "q", contract.MAX_QUERY_CHARS),
        "retailer": _enum(args, "retailer", contract.KNOWN_RETAILER_SLUGS),
        "storeKey": _opt_str(args, "storeKey", contract.MAX_IDENTIFIER_CHARS),
        "category": _opt_str(args, "category", contract.MAX_QUERY_CHARS),
        "inStockOnly": _opt_bool(args, "inStockOnly", False),
        "promoOnly": _opt_bool(args, "promoOnly", False),
        "minPrice": _number(args, "minPrice", minimum=0),
        "maxPrice": _number(args, "maxPrice", minimum=0),
        "sort": _enum(args, "sort", contract.SUPPORTED_SORTS, default="price_asc"),
        "page": 0,
        "size": limit,
    }
    min_price, max_price = query["minPrice"], query["maxPrice"]
    if min_price is not None and max_price is not None and min_price > max_price:
        raise ToolInputError("invalid_argument", "minPrice must be <= maxPrice")
    response = client.get("/api/v1/offers/search", query)
    envelope = _paged_envelope(response, limit)
    envelope["request"] = {
        "q": query["q"],
        "retailer": query["retailer"],
        "storeKey": query["storeKey"],
        "inStockOnly": query["inStockOnly"],
        "promoOnly": query["promoOnly"],
        "sort": query["sort"],
    }
    return envelope


def compare_product_prices(client, args: dict) -> dict:
    _reject_unknown(args, "compare_product_prices")
    limit = _limit(args)
    min_retailers = _integer(
        args, "minRetailers", default=2, minimum=1, maximum=len(contract.KNOWN_RETAILER_SLUGS)
    )
    response = client.get(
        "/api/v1/products/compare",
        {
            "q": _opt_str(args, "q", contract.MAX_QUERY_CHARS),
            "minRetailers": min_retailers,
            "page": 0,
            "size": limit,
        },
    )
    envelope = _paged_envelope(response, limit)
    envelope["identityScope"] = "verified_identity_only"
    envelope["identityNote"] = (
        "Stage-2 pending_review candidates are excluded by the backend; cross-retailer "
        "equality here means verified identity, not merely a similar name."
    )
    return envelope


def get_price_history(client, args: dict) -> dict:
    _reject_unknown(args, "get_price_history")
    canonical_id = _integer(args, "canonicalProductId", required=True, minimum=1)
    limit = _integer(
        args,
        "limit",
        default=contract.MAX_PRICE_OBSERVATIONS,
        minimum=1,
        maximum=contract.MAX_PRICE_OBSERVATIONS,
    )
    history = client.get(f"/api/v1/products/{canonical_id}/history")
    observations = history.get("observations")
    observations = list(observations) if isinstance(observations, list) else []
    returned = observations[:limit]
    return {
        "canonicalProductId": history.get("canonicalProductId", canonical_id),
        "canonicalName": history.get("canonicalName"),
        "normalizedSize": history.get("normalizedSize"),
        "observationCount": len(observations),
        "returned": len(returned),
        "limit": limit,
        "truncated": len(observations) > len(returned),
        "observations": returned,
        "provenance": _provenance(returned, None),
    }


def get_product_details(client, args: dict) -> dict:
    _reject_unknown(args, "get_product_details")
    canonical_id = _integer(args, "canonicalProductId", required=True, minimum=1)
    history_limit = _integer(
        args,
        "historyLimit",
        default=contract.MAX_PRICE_OBSERVATIONS,
        minimum=1,
        maximum=contract.MAX_PRICE_OBSERVATIONS,
    )
    offer_limit = _integer(
        args, "offerLimit", default=contract.DEFAULT_LIMIT, minimum=1, maximum=contract.MAX_LIMIT
    )

    history = client.get(f"/api/v1/products/{canonical_id}/history")
    observations = history.get("observations")
    observations = list(observations) if isinstance(observations, list) else []
    canonical_name = history.get("canonicalName")

    offers: list[dict] = []
    source_engine = None
    if canonical_name:
        response = client.get(
            "/api/v1/offers/search",
            {"q": canonical_name, "page": 0, "size": contract.MAX_LIMIT},
        )
        source_engine = response.get("sourceEngine")
        items = response.get("items")
        if isinstance(items, list):
            offers = [item for item in items if item.get("canonicalProductId") == canonical_id]
    offered = offers[:offer_limit]
    return {
        "canonicalProductId": canonical_id,
        "canonicalName": canonical_name,
        "normalizedSize": history.get("normalizedSize"),
        "identityScope": "verified_identity_only",
        "observationCount": len(observations),
        "observations": observations[:history_limit],
        "observationsTruncated": len(observations) > history_limit,
        "currentOfferCount": len(offers),
        "currentOffers": offered,
        "offersTruncated": len(offers) > len(offered),
        "provenance": _provenance(offered or observations, source_engine),
    }


def find_stores(client, args: dict) -> dict:
    _reject_unknown(args, "find_stores")
    limit = _limit(args)
    response = client.get(
        "/api/v1/stores",
        {
            "retailer": _enum(args, "retailer", contract.KNOWN_RETAILER_SLUGS),
            "city": _opt_str(args, "city", contract.MAX_IDENTIFIER_CHARS),
        },
    )
    envelope = _paged_envelope(response, limit)
    envelope["geoScope"] = "city_text_filter_only"
    return envelope


def _discount_value(item: dict) -> float:
    value = item.get("discountPct")
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return 0.0
    return float(value)


def _price_value(item: dict) -> float:
    value = item.get("priceCurrent")
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return math.inf
    return float(value)


def find_current_discounts(client, args: dict) -> dict:
    _reject_unknown(args, "find_current_discounts")
    limit = _limit(args)
    min_discount = _number(
        args,
        "minDiscountPct",
        default=contract.MIN_DISCOUNT_PCT,
        minimum=contract.MIN_DISCOUNT_PCT,
        maximum=contract.MAX_DISCOUNT_PCT,
    )
    response = client.get(
        "/api/v1/offers/search",
        {
            "retailer": _enum(args, "retailer", contract.KNOWN_RETAILER_SLUGS),
            "category": _opt_str(args, "category", contract.MAX_QUERY_CHARS),
            "promoOnly": True,
            "sort": "price_asc",
            "page": 0,
            "size": contract.MAX_LIMIT,
        },
    )
    items = response.get("items")
    items = list(items) if isinstance(items, list) else []
    promoted = [
        item
        for item in items
        if item.get("isPromo") is not False and _discount_value(item) >= float(min_discount)
    ]
    promoted.sort(key=lambda item: (-_discount_value(item), _price_value(item), str(item.get("offerId") or "")))
    returned = promoted[:limit]
    return {
        "sourceEngine": response.get("sourceEngine"),
        "totalPromotionsMatched": len(promoted),
        "returned": len(returned),
        "limit": limit,
        "minDiscountPct": min_discount,
        "truncated": len(promoted) > len(returned),
        "note": (
            "Only active promotions as flagged by the source are returned. Discount percentages "
            "and prices are the source/backend values, not recalculated here."
        ),
        "discounts": returned,
        "provenance": _provenance(returned, response.get("sourceEngine")),
    }


def _seed_context(client, args: dict) -> dict:
    """Resolve the seed product (id/query/category) from backend data only."""
    canonical_id = _integer(args, "canonicalProductId", minimum=1)
    explicit_query = _opt_str(args, "q", contract.MAX_QUERY_CHARS)
    explicit_category = _opt_str(args, "category", contract.MAX_QUERY_CHARS)

    seed_offer = None
    source_engine = None
    name = explicit_query
    if canonical_id is not None:
        history = client.get(f"/api/v1/products/{canonical_id}/history")
        history_name = history.get("canonicalName")
        if not history_name and not name:
            raise ToolInputError(
                "seed_product_not_found",
                f"canonicalProductId {canonical_id} exists but has no canonical name to search with",
            )
        name = name or history_name
        seed_search = client.get(
            "/api/v1/offers/search",
            {"q": history_name or name, "page": 0, "size": contract.MAX_LIMIT},
        )
        source_engine = seed_search.get("sourceEngine")
        items = seed_search.get("items")
        for item in items if isinstance(items, list) else []:
            if item.get("canonicalProductId") == canonical_id:
                seed_offer = item
                break
    if not name:
        raise ToolInputError("missing_argument", "provide canonicalProductId or q to seed the substitute search")
    category = explicit_category or (seed_offer or {}).get("category")
    return {
        "canonicalProductId": canonical_id,
        "name": name,
        "category": category,
        "seedOffer": seed_offer,
        "sourceEngine": source_engine,
    }


def suggest_product_substitutes(client, args: dict) -> dict:
    _reject_unknown(args, "suggest_product_substitutes")
    limit = _limit(args)
    seed = _seed_context(client, args)

    # Widen the candidate search to the seed's own retailer category when the
    # backend knows it; this keeps substitution candidates in the same shelf
    # category instead of doing string heuristics in the tool layer.
    query = {
        "q": seed["name"] if seed["category"] is None else _opt_str(args, "q", contract.MAX_QUERY_CHARS),
        "retailer": _enum(args, "retailer", contract.KNOWN_RETAILER_SLUGS),
        "category": seed["category"],
        "page": 0,
        "size": contract.MAX_LIMIT,
    }
    response = client.get("/api/v1/offers/search", query)
    items = response.get("items")
    items = list(items) if isinstance(items, list) else []

    candidates: list[dict] = []
    seen: set[tuple] = set()
    for item in items:
        if seed["canonicalProductId"] is not None and item.get("canonicalProductId") == seed["canonicalProductId"]:
            continue
        if seed["seedOffer"] is not None and item.get("offerId") == seed["seedOffer"].get("offerId"):
            continue
        key = (item.get("retailerSlug"), item.get("canonicalProductId"), item.get("listingName"))
        if key in seen:
            continue
        seen.add(key)
        candidate = _offer_summary(item)
        candidate["equivalenceStatus"] = "not_verified_equivalent"
        candidates.append(candidate)

    candidates.sort(
        key=lambda item: (
            str(item.get("listingName") or ""),
            str(item.get("retailerSlug") or ""),
            str(item.get("offerId") or ""),
        )
    )
    returned = candidates[:limit]
    return {
        "seed": {
            "canonicalProductId": seed["canonicalProductId"],
            "query": seed["name"],
            "category": seed["category"],
            "seedOfferId": (seed["seedOffer"] or {}).get("offerId"),
        },
        "sourceEngine": response.get("sourceEngine") or seed["sourceEngine"],
        "equivalenceStatus": "not_verified_equivalent",
        "equivalenceNote": (
            "These are substitution candidates only. They are not verified equal products; "
            "use compare_product_prices for verified identity comparisons, and never present "
            "a candidate as the same product."
        ),
        "candidateCount": len(candidates),
        "returned": len(returned),
        "limit": limit,
        "truncated": len(candidates) > len(returned),
        "candidates": returned,
        "provenance": _provenance(returned, response.get("sourceEngine")),
    }


_BASKET_ITEM_KEYS = ("canonicalProductId", "retailerProductId", "itemLabel", "quantity", "unit")


def _basket_items(args: dict) -> list[dict]:
    raw = args.get("items")
    if not isinstance(raw, list) or not raw:
        raise ToolInputError("missing_argument", "items must be a non-empty array")
    if len(raw) > contract.MAX_BASKET_ITEMS:
        raise ToolInputError(
            "invalid_argument", f"items exceeds the hard cap of {contract.MAX_BASKET_ITEMS} basket lines"
        )
    validated: list[dict] = []
    for index, item in enumerate(raw):
        if not isinstance(item, dict):
            raise ToolInputError("invalid_argument", f"items[{index}] must be an object")
        unknown = sorted(set(item) - set(_BASKET_ITEM_KEYS))
        if unknown:
            raise ToolInputError(
                "unknown_argument",
                f"items[{index}] has unsupported field(s): {', '.join(unknown)}",
            )
        canonical_id = _integer(item, "canonicalProductId", minimum=1)
        retailer_id = _integer(item, "retailerProductId", minimum=1)
        if (canonical_id is None) == (retailer_id is None):
            raise ToolInputError(
                "invalid_argument",
                f"items[{index}] must set exactly one of canonicalProductId or retailerProductId",
            )
        quantity = _number(item, "quantity", default=1)
        if quantity is None or quantity <= 0 or quantity > contract.MAX_QUANTITY:
            raise ToolInputError(
                "invalid_argument",
                f"items[{index}].quantity must be > 0 and <= {contract.MAX_QUANTITY}",
            )
        validated.append(
            {
                "canonicalProductId": canonical_id,
                "retailerProductId": retailer_id,
                "itemLabel": _opt_str(item, "itemLabel", contract.MAX_QUERY_CHARS),
                "quantity": quantity,
                "unit": _enum(item, "unit", contract.SUPPORTED_UNITS, default="pack"),
            }
        )
    return validated


def _retailers(args: dict) -> list[str] | None:
    raw = args.get("retailers")
    if raw is None:
        return None
    if not isinstance(raw, list) or not raw:
        raise ToolInputError("invalid_argument", "retailers must be a non-empty array when provided")
    if len(raw) > contract.MAX_RETAILER_FILTERS:
        raise ToolInputError(
            "invalid_argument", f"retailers exceeds the hard cap of {contract.MAX_RETAILER_FILTERS}"
        )
    result: list[str] = []
    for slug in raw:
        if not isinstance(slug, str) or slug not in contract.KNOWN_RETAILER_SLUGS:
            raise ToolInputError(
                "invalid_argument", f"retailers entries must be one of: {', '.join(contract.KNOWN_RETAILER_SLUGS)}"
            )
        if slug not in result:
            result.append(slug)
    return result


def optimize_shopping_basket(client, args: dict) -> dict:
    _reject_unknown(args, "optimize_shopping_basket")
    payload = {
        "items": _basket_items(args),
        "city": _opt_str(args, "city", contract.MAX_IDENTIFIER_CHARS),
        "retailers": _retailers(args),
        "maxStores": _integer(
            args, "maxStores", default=2, minimum=1, maximum=contract.MAX_STORES_ALLOWED
        ),
        "minSplitSavingsMkd": _number(args, "minSplitSavingsMkd", minimum=0),
        "allowSubstitutes": _opt_bool(args, "allowSubstitutes", False),
        "inStockOnly": _opt_bool(args, "inStockOnly", True),
    }
    response = client.post("/api/v1/baskets/optimize", payload)
    response = dict(response)
    response["computation"] = "server_side_deterministic_bigdecimal"
    response["identityPolicy"] = (
        "exact_identity_only" if not payload["allowSubstitutes"] else "exact_identity_with_flagged_substitutes"
    )
    response["request"] = payload
    response["note"] = (
        "Totals, pack counts, unit conversions and savings are the backend's deterministic "
        "values and are returned unchanged. Missing items are explicitly listed; a partial "
        "basket is never presented as complete."
    )
    return response


def get_catalog_health(client, args: dict) -> dict:
    _reject_unknown(args, "get_catalog_health")
    response = client.get("/api/v1/health")
    response = dict(response)
    response["note"] = (
        "sourceEngine=postgresql_fallback means OpenSearch was unavailable; data is still "
        "authoritative but search ranking may differ. Counts are authoritative row counts."
    )
    return response


HANDLERS = {
    "search_products": search_products,
    "get_product_details": get_product_details,
    "compare_product_prices": compare_product_prices,
    "get_price_history": get_price_history,
    "find_stores": find_stores,
    "find_current_discounts": find_current_discounts,
    "suggest_product_substitutes": suggest_product_substitutes,
    "optimize_shopping_basket": optimize_shopping_basket,
    "get_catalog_health": get_catalog_health,
}

