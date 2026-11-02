"""In-process mock of the M3/M4 Spring Boot REST API for MCP contract tests.

Serves the exact JSON shapes documented in `docs/contracts/search-api-contract.md`
and `docs/contracts/basket-api-contract.md` so the MCP layer can be verified
without Docker, PostgreSQL, OpenSearch or a JVM. Values mirror the committed
Vero/Stokomak/Zito fixtures (prices, provenance, canonical ids) used by the
M2–M4 integration tests.
"""

from __future__ import annotations

import json
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

OFFERS = [
    {
        "offerId": "101:1",
        "storeId": 101,
        "storeExternalKey": "1",
        "storeName": "ВЕРО 1",
        "city": "Скопје",
        "retailerSlug": "vero",
        "retailerName": "Vero",
        "retailerProductId": 1,
        "skuKey": "vero-sku-1",
        "listingName": "ФЛИПС СТОБИ ФЛИПС 150Г ВИТАМИНКА",
        "category": "ГРИЦКИ",
        "canonicalProductId": 897,
        "canonicalKey": "canon-897",
        "canonicalName": "СТОБИ ФЛИПС 150ГР ВИТАМИНКА",
        "normalizedSize": "150g",
        "currency": "MKD",
        "priceCurrent": 43.00,
        "unitPrice": None,
        "unitLabel": None,
        "regularPrice": 43.00,
        "discountPrice": None,
        "discountPct": None,
        "promoType": None,
        "promoStartsOn": None,
        "promoEndsOn": None,
        "isPromo": False,
        "availability": "in_stock",
        "publishedTs": "2026-10-28T07:02:00Z",
        "fetchedTs": "2026-10-28T08:00:00Z",
        "sourceUrl": "https://pricelist.vero.com.mk/89_1.html",
        "runId": 1,
    },
    {
        "offerId": "202:1",
        "storeId": 202,
        "storeExternalKey": "1",
        "storeName": "КИСЕЛА ВОДА",
        "city": "Скопје",
        "retailerSlug": "stokomak",
        "retailerName": "Stokomak",
        "retailerProductId": 1,
        "skuKey": "stokomak-sku-1",
        "listingName": "СТОБИ ФЛИПС 150ГР ВИТАМИНКА",
        "category": "ГРИЦКИ",
        "canonicalProductId": 897,
        "canonicalKey": "canon-897",
        "canonicalName": "СТОБИ ФЛИПС 150ГР ВИТАМИНКА",
        "normalizedSize": "150g",
        "currency": "MKD",
        "priceCurrent": 41.50,
        "unitPrice": 276.67,
        "unitLabel": "MKD/кг",
        "regularPrice": 48.80,
        "discountPrice": 41.50,
        "discountPct": 15.00,
        "promoType": "percent_discount",
        "promoStartsOn": "2026-10-23",
        "promoEndsOn": "2026-10-29",
        "isPromo": True,
        "availability": "in_stock",
        "publishedTs": "2026-10-28T19:55:00Z",
        "fetchedTs": "2026-10-28T20:10:00Z",
        "sourceUrl": "https://stokomak.proverkanaceni.mk/?org=1&perPage=100&page=1",
        "runId": 2,
    },
]

OFFERS += [
    {
        "offerId": "303:1",
        "storeId": 303,
        "storeExternalKey": "2",
        "storeName": "ЖИТО 2",
        "city": "Битола",
        "retailerSlug": "zito",
        "retailerName": "Zito",
        "retailerProductId": 5,
        "skuKey": "zito-sku-5",
        "listingName": "МЛЕКО БИТОЛСКО 1Л",
        "category": "МЛЕЧНИ ПРОИЗВОДИ",
        "canonicalProductId": 1116,
        "canonicalKey": "canon-1116",
        "canonicalName": "МЛЕКО БИТОЛСКО 1ЛР",
        "normalizedSize": "1l",
        "currency": "MKD",
        "priceCurrent": 62.00,
        "unitPrice": 62.00,
        "unitLabel": "MKD/л",
        "regularPrice": 80.52,
        "discountPrice": 62.00,
        "discountPct": 23.00,
        "promoType": "percent_discount",
        "promoStartsOn": "2026-10-23",
        "promoEndsOn": "2026-10-29",
        "isPromo": True,
        "availability": "in_stock",
        "publishedTs": "2026-10-29T06:10:00Z",
        "fetchedTs": "2026-10-29T06:30:00Z",
        "sourceUrl": "https://zito.proverkanaceni.mk/?org=2&perPage=100&page=1",
        "runId": 3,
    },
    {
        "offerId": "101:2",
        "storeId": 101,
        "storeExternalKey": "1",
        "storeName": "ВЕРО 1",
        "city": "Скопје",
        "retailerSlug": "vero",
        "retailerName": "Vero",
        "retailerProductId": 2,
        "skuKey": "vero-sku-2",
        "listingName": "МЛЕКО БИТОЛСКО 1Л",
        "category": "МЛЕЧНИ ПРОИЗВОДИ",
        "canonicalProductId": 1116,
        "canonicalKey": "canon-1116",
        "canonicalName": "МЛЕКО БИТОЛСКО 1ЛР",
        "normalizedSize": "1l",
        "currency": "MKD",
        "priceCurrent": 66.00,
        "unitPrice": 66.00,
        "unitLabel": "MKD/л",
        "regularPrice": 66.00,
        "discountPrice": None,
        "discountPct": None,
        "promoType": None,
        "promoStartsOn": None,
        "promoEndsOn": None,
        "isPromo": False,
        "availability": "in_stock",
        "publishedTs": "2026-10-28T07:02:00Z",
        "fetchedTs": "2026-10-28T08:00:00Z",
        "sourceUrl": "https://pricelist.vero.com.mk/89_1.html",
        "runId": 1,
    },
    {
        "offerId": "202:2",
        "storeId": 202,
        "storeExternalKey": "1",
        "storeName": "КИСЕЛА ВОДА",
        "city": "Скопје",
        "retailerSlug": "stokomak",
        "retailerName": "Stokomak",
        "retailerProductId": 2,
        "skuKey": "stokomak-sku-2",
        "listingName": "ЈОГУРТ 400Г",
        "category": "МЛЕЧНИ ПРОИЗВОДИ",
        "canonicalProductId": None,
        "canonicalKey": None,
        "canonicalName": None,
        "normalizedSize": "400g",
        "currency": "MKD",
        "priceCurrent": 39.00,
        "unitPrice": 97.50,
        "unitLabel": "MKD/кг",
        "regularPrice": 39.00,
        "discountPrice": None,
        "discountPct": None,
        "promoType": None,
        "promoStartsOn": None,
        "promoEndsOn": None,
        "isPromo": False,
        "availability": "in_stock",
        "publishedTs": "2026-10-28T19:55:00Z",
        "fetchedTs": "2026-10-28T20:10:00Z",
        "sourceUrl": "https://stokomak.proverkanaceni.mk/?org=1&perPage=100&page=1",
        "runId": 2,
    },
]



OFFERS.append(
    {
        "offerId": "101:3",
        "storeId": 101,
        "storeExternalKey": "1",
        "storeName": "ВЕРО 1",
        "city": "Скопје",
        "retailerSlug": "vero",
        "retailerName": "Vero",
        "retailerProductId": 3,
        "skuKey": "vero-sku-3",
        "listingName": "СТОБИ ФЛИПС 200Г ЛЕШНИК",
        "category": "ГРИЦКИ",
        "canonicalProductId": 898,
        "canonicalKey": "canon-898",
        "canonicalName": "СТОБИ ФЛИПС 200ГР ЛЕШНИК",
        "normalizedSize": "200g",
        "currency": "MKD",
        "priceCurrent": 58.00,
        "unitPrice": 290.00,
        "unitLabel": "MKD/кг",
        "regularPrice": 58.00,
        "discountPrice": None,
        "discountPct": None,
        "promoType": None,
        "promoStartsOn": None,
        "promoEndsOn": None,
        "isPromo": False,
        "availability": "in_stock",
        "publishedTs": "2026-10-28T07:02:00Z",
        "fetchedTs": "2026-10-28T08:00:00Z",
        "sourceUrl": "https://pricelist.vero.com.mk/89_1.html",
        "runId": 1,
    }
)

STORES = [
    {
        "storeId": 101,
        "retailerSlug": "vero",
        "retailerName": "Vero",
        "externalKey": "1",
        "name": "ВЕРО 1",
        "address": "Бул. Јане Сандански бр.111",
        "city": "Скопје",
        "activeOffersCount": 3,
        "latestPublishedTs": "2026-10-28T07:02:00Z",
    },
    {
        "storeId": 202,
        "retailerSlug": "stokomak",
        "retailerName": "Stokomak",
        "externalKey": "1",
        "name": "КИСЕЛА ВОДА",
        "address": "Бул. Партизански одреди 44",
        "city": "Скопје",
        "activeOffersCount": 2,
        "latestPublishedTs": "2026-10-28T19:55:00Z",
    },
    {
        "storeId": 303,
        "retailerSlug": "zito",
        "retailerName": "Zito",
        "externalKey": "2",
        "name": "ЖИТО 2",
        "address": "Климент Охридски 12",
        "city": "Битола",
        "activeOffersCount": 1,
        "latestPublishedTs": "2026-10-29T06:10:00Z",
    },
]

COMPARISONS = [
    {
        "canonicalProductId": 897,
        "canonicalKey": "canon-897",
        "canonicalName": "СТОБИ ФЛИПС 150ГР ВИТАМИНКА",
        "normalizedSize": "150g",
        "retailerCount": 2,
        "storeCount": 2,
        "cheapestMkd": 41.50,
        "highestMkd": 43.00,
        "spreadMkd": 1.50,
        "latestPublishedTs": "2026-10-28T19:55:00Z",
        "offers": [
            {
                "retailerSlug": "stokomak",
                "retailerProductId": 1,
                "listingName": "СТОБИ ФЛИПС 150ГР ВИТАМИНКА",
                "minPrice": 41.50,
                "maxPrice": 41.50,
                "storeCount": 1,
                "latestPublishedTs": "2026-10-28T19:55:00Z",
                "sourceUrl": "https://stokomak.proverkanaceni.mk/?org=1&perPage=100&page=1",
            },
            {
                "retailerSlug": "vero",
                "retailerProductId": 1,
                "listingName": "ФЛИПС СТОБИ ФЛИПС 150Г ВИТАМИНКА",
                "minPrice": 43.00,
                "maxPrice": 43.00,
                "storeCount": 1,
                "latestPublishedTs": "2026-10-28T07:02:00Z",
                "sourceUrl": "https://pricelist.vero.com.mk/89_1.html",
            },
        ],
    },
    {
        "canonicalProductId": 1116,
        "canonicalKey": "canon-1116",
        "canonicalName": "МЛЕКО БИТОЛСКО 1ЛР",
        "normalizedSize": "1l",
        "retailerCount": 2,
        "storeCount": 2,
        "cheapestMkd": 62.00,
        "highestMkd": 66.00,
        "spreadMkd": 4.00,
        "latestPublishedTs": "2026-10-29T06:10:00Z",
        "offers": [
            {
                "retailerSlug": "vero",
                "retailerProductId": 2,
                "listingName": "МЛЕКО БИТОЛСКО 1Л",
                "minPrice": 66.00,
                "maxPrice": 66.00,
                "storeCount": 1,
                "latestPublishedTs": "2026-10-28T07:02:00Z",
                "sourceUrl": "https://pricelist.vero.com.mk/89_1.html",
            },
            {
                "retailerSlug": "zito",
                "retailerProductId": 5,
                "listingName": "МЛЕКО БИТОЛСКО 1Л",
                "minPrice": 62.00,
                "maxPrice": 62.00,
                "storeCount": 1,
                "latestPublishedTs": "2026-10-29T06:10:00Z",
                "sourceUrl": "https://zito.proverkanaceni.mk/?org=2&perPage=100&page=1",
            },
        ],
    },
]


HISTORIES = {
    897: {
        "canonicalProductId": 897,
        "canonicalName": "СТОБИ ФЛИПС 150ГР ВИТАМИНКА",
        "normalizedSize": "150g",
        "observations": [
            {
                "observationId": 1,
                "retailerSlug": "vero",
                "storeExternalKey": "1",
                "storeName": "ВЕРО 1",
                "listingName": "ФЛИПС СТОБИ ФЛИПС 150Г ВИТАМИНКА",
                "priceCurrent": 43.00,
                "regularPrice": 43.00,
                "discountPrice": None,
                "discountPct": None,
                "promoType": None,
                "availability": "in_stock",
                "publishedTs": "2026-10-28T07:02:00Z",
                "fetchedTs": "2026-10-28T08:00:00Z",
                "sourceUrl": "https://pricelist.vero.com.mk/89_1.html",
            },
            {
                "observationId": 2,
                "retailerSlug": "stokomak",
                "storeExternalKey": "1",
                "storeName": "КИСЕЛА ВОДА",
                "listingName": "СТОБИ ФЛИПС 150ГР ВИТАМИНКА",
                "priceCurrent": 41.50,
                "regularPrice": 48.80,
                "discountPrice": 41.50,
                "discountPct": 15.00,
                "promoType": "percent_discount",
                "availability": "in_stock",
                "publishedTs": "2026-10-28T19:55:00Z",
                "fetchedTs": "2026-10-28T20:10:00Z",
                "sourceUrl": "https://stokomak.proverkanaceni.mk/?org=1&perPage=100&page=1",
            },
        ],
    },
    1116: {
        "canonicalProductId": 1116,
        "canonicalName": "МЛЕКО БИТОЛСКО 1ЛР",
        "normalizedSize": "1l",
        "observations": [
            {
                "observationId": 3,
                "retailerSlug": "vero",
                "storeExternalKey": "1",
                "storeName": "ВЕРО 1",
                "listingName": "МЛЕКО БИТОЛСКО 1Л",
                "priceCurrent": 66.00,
                "regularPrice": 66.00,
                "discountPrice": None,
                "discountPct": None,
                "promoType": None,
                "availability": "in_stock",
                "publishedTs": "2026-10-28T07:02:00Z",
                "fetchedTs": "2026-10-28T08:00:00Z",
                "sourceUrl": "https://pricelist.vero.com.mk/89_1.html",
            },
            {
                "observationId": 4,
                "retailerSlug": "zito",
                "storeExternalKey": "2",
                "storeName": "ЖИТО 2",
                "listingName": "МЛЕКО БИТОЛСКО 1Л",
                "priceCurrent": 62.00,
                "regularPrice": 80.52,
                "discountPrice": 62.00,
                "discountPct": 23.00,
                "promoType": "percent_discount",
                "availability": "in_stock",
                "publishedTs": "2026-10-29T06:10:00Z",
                "fetchedTs": "2026-10-29T06:30:00Z",
                "sourceUrl": "https://zito.proverkanaceni.mk/?org=2&perPage=100&page=1",
            },
        ],
    },
}


BASKET_TOTALS = {
    "bestSingleStore": {
        "storeId": 303,
        "retailerSlug": "zito",
        "retailerName": "Zito",
        "storeExternalKey": "2",
        "storeName": "ЖИТО 2",
        "city": "Битола",
        "itemsCovered": 2,
        "totalItemsRequested": 2,
        "coverageRatio": 1.000,
        "totalMkd": 498.00,
        "savingsVsHighestCoveredSingleStoreMkd": 21.00,
        "exactMatchesCount": 2,
        "substitutesCount": 0,
        "coveredItems": [
            {
                "itemIndex": 0,
                "canonicalProductId": 1116,
                "requestedName": "МЛЕКО БИТОЛСКО 1ЛР",
                "requestedQuantity": 2,
                "requestedUnit": "pack",
                "storeId": 303,
                "storeExternalKey": "2",
                "storeName": "ЖИТО 2",
                "retailerSlug": "zito",
                "matchedRetailerProductId": 5,
                "matchedListingName": "МЛЕКО БИТОЛСКО 1Л",
                "normalizedSize": "1l",
                "packsNeeded": 2,
                "unitPackPriceMkd": 62.00,
                "lineTotalMkd": 124.00,
                "isSubstitute": False,
                "substituteReason": None,
                "matchConfidence": 1.000,
                "publishedTs": "2026-10-29T06:10:00Z",
                "fetchedTs": "2026-10-29T06:30:00Z",
                "sourceUrl": "https://zito.proverkanaceni.mk/?org=2&perPage=100&page=1",
            },
            {
                "itemIndex": 1,
                "canonicalProductId": 897,
                "requestedName": "СТОБИ ФЛИПС 150ГР ВИТАМИНКА",
                "requestedQuantity": 6,
                "requestedUnit": "pack",
                "storeId": 303,
                "storeExternalKey": "2",
                "storeName": "ЖИТО 2",
                "retailerSlug": "zito",
                "matchedRetailerProductId": 6,
                "matchedListingName": "СТОБИ ФЛИПС 150ГР ВИТАМИНКА",
                "normalizedSize": "150g",
                "packsNeeded": 6,
                "unitPackPriceMkd": 62.3333,
                "lineTotalMkd": 374.00,
                "isSubstitute": False,
                "substituteReason": None,
                "matchConfidence": 1.000,
                "publishedTs": "2026-10-29T06:10:00Z",
                "fetchedTs": "2026-10-29T06:30:00Z",
                "sourceUrl": "https://zito.proverkanaceni.mk/?org=2&perPage=100&page=1",
            },
        ],
        "missingItems": [],
    },
    "bestMultiStorePlan": {
        "storesUsed": 2,
        "itemsCovered": 2,
        "totalItemsRequested": 2,
        "coverageRatio": 1.000,
        "totalMkd": 483.50,
        "savingsVsBestSingleStoreMkd": 14.50,
        "meetsMinSavingsThreshold": True,
        "recommendationReason": "split_saves_above_threshold",
        "storeAllocations": [
            {
                "storeId": 303,
                "retailerSlug": "zito",
                "retailerName": "Zito",
                "storeExternalKey": "2",
                "storeName": "ЖИТО 2",
                "city": "Битола",
                "subtotalMkd": 124.00,
                "items": [],
            },
            {
                "storeId": 202,
                "retailerSlug": "stokomak",
                "retailerName": "Stokomak",
                "storeExternalKey": "1",
                "storeName": "КИСЕЛА ВОДА",
                "city": "Скопје",
                "subtotalMkd": 359.50,
                "items": [],
            },
        ],
        "missingItems": [],
    },
}



class CatalogApiState:
    """Recorded requests plus optional forced-failure switch for negative tests."""

    def __init__(self):
        self.requests: list[dict] = []
        self.forced_status: int | None = None

    def last_request(self) -> dict | None:
        return self.requests[-1] if self.requests else None


def _first(query: dict, key: str) -> str | None:
    values = query.get(key)
    if not values:
        return None
    return values[0]


def _bool_param(query: dict, key: str, default: bool) -> bool:
    value = _first(query, key)
    if value is None:
        return default
    return value.strip().lower() in ("1", "true", "yes")


def _int_param(query: dict, key: str, default: int) -> int:
    value = _first(query, key)
    try:
        return int(value) if value is not None else default
    except ValueError:
        return default


def _float_param(query: dict, key: str):
    value = _first(query, key)
    if value is None:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _matches_text(offer: dict, needle: str) -> bool:
    needle = needle.casefold()
    haystack = " ".join(
        str(offer.get(field) or "") for field in ("listingName", "canonicalName", "category")
    ).casefold()
    return needle in haystack


def filter_offers(query: dict) -> dict:
    items = list(OFFERS)
    q = _first(query, "q")
    if q:
        items = [item for item in items if _matches_text(item, q)]
    retailer = _first(query, "retailer")
    if retailer:
        items = [item for item in items if item.get("retailerSlug") == retailer]
    store_key = _first(query, "storeKey")
    if store_key:
        items = [
            item for item in items if f"{item.get('retailerSlug')}-{item.get('storeExternalKey')}" == store_key
        ]
    category = _first(query, "category")
    if category:
        items = [item for item in items if item.get("category") == category]
    if _bool_param(query, "inStockOnly", False):
        items = [item for item in items if item.get("availability") == "in_stock"]
    if _bool_param(query, "promoOnly", False):
        items = [item for item in items if item.get("isPromo")]
    min_price = _float_param(query, "minPrice")
    if min_price is not None:
        items = [item for item in items if float(item.get("priceCurrent") or 0) >= min_price]
    max_price = _float_param(query, "maxPrice")
    if max_price is not None:
        items = [item for item in items if float(item.get("priceCurrent") or 0) <= max_price]

    descending = _first(query, "sort") == "price_desc"
    items.sort(key=lambda item: (float(item.get("priceCurrent") or 0), str(item.get("offerId"))), reverse=descending)

    total = len(items)
    page = max(0, _int_param(query, "page", 0))
    size = max(1, _int_param(query, "size", 20))
    window = items[page * size : page * size + size]
    return {
        "sourceEngine": "opensearch",
        "total": total,
        "page": page,
        "size": size,
        "items": window,
    }


def filter_comparisons(query: dict) -> dict:
    items = list(COMPARISONS)
    q = _first(query, "q")
    if q:
        needle = q.casefold()
        items = [item for item in items if needle in str(item.get("canonicalName") or "").casefold()]
    min_retailers = _int_param(query, "minRetailers", 2)
    items = [item for item in items if int(item.get("retailerCount") or 0) >= min_retailers]
    total = len(items)
    size = max(1, _int_param(query, "size", 20))
    return {"sourceEngine": "opensearch", "total": total, "page": 0, "size": size, "items": items[:size]}


def basket_response(body: dict) -> dict:
    payload = json.loads(json.dumps(BASKET_TOTALS))
    return {
        "totalItemsRequested": len(body.get("items") or []),
        "allowSubstitutes": bool(body.get("allowSubstitutes", False)),
        "inStockOnly": bool(body.get("inStockOnly", True)),
        "maxStoresAllowed": body.get("maxStores", 2),
        "minSplitSavingsMkd": body.get("minSplitSavingsMkd") if body.get("minSplitSavingsMkd") is not None else 0.0,
        "bestSingleStore": payload["bestSingleStore"],
        "singleStoreRankings": [payload["bestSingleStore"]],
        "bestMultiStorePlan": payload["bestMultiStorePlan"],
    }


HEALTH = {
    "status": "UP",
    "databaseStatus": "UP",
    "opensearchStatus": "UP",
    "activeSearchEngine": "opensearch",
    "counts": {
        "stores": 192,
        "retailer_products": 1463,
        "offers_current": 1896,
        "price_observations": 1896,
        "canonical_products": 1372,
        "product_matches": 1483,
        "opensearch_stores": 192,
        "opensearch_offers": 1896,
        "opensearch_products": 1372,
    },
}



HISTORY_PATH = re.compile(r"^/api/v1/products/([0-9]+)/history$")


def make_handler(state: CatalogApiState):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, format, *args):  # noqa: A002 - stdlib signature
            return

        def _send_json(self, status: int, payload) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _record(self, method: str, path: str, query: dict, body) -> None:
            state.requests.append({"method": method, "path": path, "query": query, "body": body})

        def _forced(self) -> bool:
            if state.forced_status is None:
                return False
            self._send_json(state.forced_status, {"error": "forced_failure"})
            return True

        def do_GET(self):  # noqa: N802 - stdlib hook
            parsed = urlparse(self.path)
            query = parse_qs(parsed.query, keep_blank_values=False)
            self._record("GET", parsed.path, query, None)
            if self._forced():
                return
            if parsed.path == "/api/v1/health":
                return self._send_json(200, HEALTH)
            if parsed.path == "/api/v1/stores":
                items = list(STORES)
                retailer = _first(query, "retailer")
                if retailer:
                    items = [store for store in items if store.get("retailerSlug") == retailer]
                city = _first(query, "city")
                if city:
                    items = [store for store in items if store.get("city") == city]
                return self._send_json(
                    200,
                    {"sourceEngine": "opensearch", "total": len(items), "page": 0, "size": len(items), "items": items},
                )
            if parsed.path == "/api/v1/offers/search":
                return self._send_json(200, filter_offers(query))
            if parsed.path == "/api/v1/products/compare":
                return self._send_json(200, filter_comparisons(query))
            match = HISTORY_PATH.match(parsed.path)
            if match:
                canonical_id = int(match.group(1))
                history = HISTORIES.get(canonical_id)
                if history is None:
                    return self._send_json(404, {"error": "canonical product not found"})
                return self._send_json(200, history)
            if parsed.path == "/api/v1/matches/review-queue":
                return self._send_json(200, [])
            return self._send_json(404, {"error": "not_found"})

        def do_POST(self):  # noqa: N802 - stdlib hook
            parsed = urlparse(self.path)
            query = parse_qs(parsed.query, keep_blank_values=False)
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length) if length else b""
            try:
                body = json.loads(raw.decode("utf-8")) if raw else None
            except (UnicodeDecodeError, json.JSONDecodeError):
                body = None
            self._record("POST", parsed.path, query, body)
            if self._forced():
                return
            if parsed.path == "/api/v1/baskets/optimize":
                if not isinstance(body, dict):
                    return self._send_json(400, {"error": "invalid basket payload"})
                return self._send_json(200, basket_response(body))
            return self._send_json(404, {"error": "not_found"})

    return Handler


def start_background_server(host: str = "127.0.0.1", port: int = 0) -> tuple[ThreadingHTTPServer, str, CatalogApiState]:
    import threading

    state = CatalogApiState()
    server = ThreadingHTTPServer((host, port), make_handler(state))
    actual_port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, f"http://{host}:{actual_port}", state


def main(argv=None):
    import argparse

    parser = argparse.ArgumentParser(description="Mock M3/M4 catalog REST API for MCP tests")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8080)
    args = parser.parse_args(argv)
    server, base_url, _state = start_background_server(args.host, args.port)
    print(f"Mock catalog API listening on {base_url}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:  # pragma: no cover - interactive convenience
        pass
    finally:
        server.shutdown()


if __name__ == "__main__":
    main()

