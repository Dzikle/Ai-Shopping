"""OpenSearch client - behavior-identical port of OpenSearchClient.java.

Same DSL bodies, same fallback decision points (any failure -> caller falls
back to PostgreSQL), same Decimal scale-2 shaping of numeric fields.
"""

import datetime as dt
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from opensearchpy import OpenSearch

INDEXES = ("stores", "offers", "products")


class OpenSearchUnavailable(Exception):
    pass


def scale2(value) -> Decimal | None:
    if value is None:
        return None
    return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


class OpenSearchClient:
    def __init__(self, base_url: str | None):
        self.base_url = (base_url or "http://localhost:9200").rstrip("/")
        self._client = OpenSearch(
            hosts=[self.base_url],
            http_compress=False,
            timeout=5,
            retry_on_timeout=False,
            max_retries=0,
        )

    def set_base_url(self, base_url: str | None) -> None:
        self.base_url = (base_url or "http://localhost:9200").rstrip("/")
        self._client = OpenSearch(
            hosts=[self.base_url],
            http_compress=False,
            timeout=5,
            retry_on_timeout=False,
            max_retries=0,
        )

    def get_base_url(self) -> str:
        return self.base_url

    def is_healthy_and_populated(self) -> bool:
        try:
            return self.count_index("offers") >= 0
        except Exception:
            return False

    def count_index(self, index_or_alias: str) -> int:
        response = self._client.count(index=index_or_alias)
        body = response.body if hasattr(response, "body") else response
        count = body.get("count")
        if not isinstance(count, int):
            raise OpenSearchUnavailable("OpenSearch count returned no count")
        return count

    def search_stores(self, retailer: str | None, city: str | None) -> dict[str, Any]:
        filters: list[dict[str, Any]] = []
        if retailer and retailer.strip():
            filters.append({"term": {"retailer_slug": retailer.strip().lower()}})
        if city and city.strip():
            filters.append({"term": {"city": city.strip()}})

        query: dict[str, Any] = (
            {"match_all": {}}
            if not filters
            else {"bool": {"filter": filters}}
        )
        body: dict[str, Any] = {
            "from": 0,
            "size": 500,
            "query": query,
            "sort": [{"store_id": {"order": "asc"}}],
        }
        root = self._post_search("stores", body)
        total = _hits_total(root)
        items = [_store_dto(hit["_source"]) for hit in root["hits"]["hits"]]
        return {"sourceEngine": "opensearch", "total": total, "page": 0, "size": len(items), "items": items}

    def search_offers(self, f) -> dict[str, Any]:
        must: list[dict[str, Any]] = []
        flt: list[dict[str, Any]] = []

        if f.q and f.q.strip():
            must.append({
                "multi_match": {
                    "query": f.q.strip(),
                    "fields": ["listing_name^2", "canonical_name^2", "category"],
                }
            })
        if f.retailer and f.retailer.strip():
            flt.append({"term": {"retailer_slug": f.retailer.strip().lower()}})
        if f.storeKey and f.storeKey.strip():
            flt.append({"term": {"store_external_key": f.storeKey.strip()}})
        if f.category and f.category.strip():
            flt.append({"term": {"category": f.category.strip()}})
        if f.inStockOnly:
            flt.append({"term": {"availability": "in_stock"}})
        if f.promoOnly:
            flt.append({"term": {"is_promo": True}})
        if f.minPrice is not None or f.maxPrice is not None:
            rng: dict[str, Any] = {}
            if f.minPrice is not None:
                rng["gte"] = f.minPrice
            if f.maxPrice is not None:
                rng["lte"] = f.maxPrice
            flt.append({"range": {"price_current": rng}})

        boolean: dict[str, Any] = {}
        if must:
            boolean["must"] = must
        if flt:
            boolean["filter"] = flt
        query = {"match_all": {}} if not boolean else {"bool": boolean}

        sort_order = "desc" if (f.sort and (f.sort.lower() == "desc" or f.sort.lower() == "price_desc")) else "asc"
        sort = [
            {"price_current": {"order": sort_order}},
            {"offer_id": {"order": "asc"}},
        ]

        from_ = max(0, f.page) * max(1, f.size)
        body: dict[str, Any] = {
            "from": from_,
            "size": max(1, f.size),
            "query": query,
            "sort": sort,
        }

        root = self._post_search("offers", body)
        total = _hits_total(root)
        items = [_offer_dto_from_doc(hit["_source"]) for hit in root["hits"]["hits"]]
        return {"sourceEngine": "opensearch", "total": total, "page": f.page, "size": f.size, "items": items}

    def search_product_comparisons(self, q: str | None, min_retailers: int, page: int, size: int, canonical_id: int | None = None) -> dict[str, Any]:
        must: list[dict[str, Any]] = []
        flt: list[dict[str, Any]] = []

        if q and q.strip():
            must.append({
                "multi_match": {
                    "query": q.strip(),
                    "fields": ["canonical_name^2", "normalized_tokens"],
                }
            })
        flt.append({"range": {"retailer_count": {"gte": max(1, min_retailers)}}})
        if canonical_id is not None:
            flt.append({"term": {"canonical_product_id": canonical_id}})

        boolean: dict[str, Any] = {"filter": flt}
        if must:
            boolean["must"] = must

        from_ = max(0, page) * max(1, size)
        body: dict[str, Any] = {
            "from": from_,
            "size": max(1, size),
            "query": {"bool": boolean},
            "sort": [{"canonical_name.keyword": {"order": "asc"}}],
        }

        root = self._post_search("products", body)
        total = _hits_total(root)
        items = []
        for hit in root["hits"]["hits"]:
            src = hit["_source"]
            offers = []
            for o in src.get("offers") or []:
                offers.append({
                    "retailerSlug": _text_or_none(o, "retailer_slug"),
                    "retailerProductId": o.get("retailer_product_id", 0) if isinstance(o.get("retailer_product_id"), int) else 0,
                    "listingName": _text_or_none(o, "listing_name"),
                    "minPrice": _decimal_or_none(o, "min_price"),
                    "maxPrice": _decimal_or_none(o, "max_price"),
                    "storeCount": o.get("store_count", 0) if isinstance(o.get("store_count"), int) else 0,
                    "latestPublishedTs": _instant_or_none(o, "latest_published_ts"),
                    "sourceUrl": _text_or_none(o, "source_url"),
                })
            items.append({
                "canonicalProductId": src.get("canonical_product_id", 0) if isinstance(src.get("canonical_product_id"), int) else 0,
                "canonicalKey": _text_or_none(src, "canonical_key"),
                "canonicalName": _text_or_none(src, "canonical_name"),
                "normalizedSize": _text_or_none(src, "normalized_size"),
                "retailerCount": src.get("retailer_count", 0) if isinstance(src.get("retailer_count"), int) else 0,
                "storeCount": src.get("store_count", 0) if isinstance(src.get("store_count"), int) else 0,
                "cheapestMkd": _decimal_or_none(src, "min_price"),
                "highestMkd": _decimal_or_none(src, "max_price"),
                "spreadMkd": _decimal_or_none(src, "spread_mkd"),
                "latestPublishedTs": _instant_or_none(src, "latest_published_ts"),
                "offers": offers,
            })
        return {"sourceEngine": "opensearch", "total": total, "page": page, "size": size, "items": items}

    def _post_search(self, index_or_alias: str, body: dict[str, Any]) -> dict[str, Any]:
        response = self._client.search(index=index_or_alias, body=body)
        return response.body if hasattr(response, "body") else response


def _hits_total(root: dict[str, Any]) -> int:
    hits = root.get("hits") or {}
    total_obj = hits.get("total")
    if isinstance(total_obj, dict):
        value = total_obj.get("value")
        return value if isinstance(value, int) else 0
    if isinstance(total_obj, int):
        return total_obj
    return 0


def _text_or_none(node: dict[str, Any], field: str) -> str | None:
    value = node.get(field)
    if value is None:
        return None
    return str(value)


def _decimal_or_none(node: dict[str, Any], field: str) -> Decimal | None:
    value = node.get(field)
    if value is None:
        return None
    return scale2(value)


def _date_or_none(node: dict[str, Any], field: str):
    raw = node.get(field)
    if raw is None:
        return None
    text = str(raw)
    if not text.strip():
        return None
    return dt.date.fromisoformat(text[:10])


def _instant_or_none(node: dict[str, Any], field: str):
    raw = node.get(field)
    if raw is None:
        return None
    text = str(raw)
    if not text.strip():
        return None
    parsed = dt.datetime.fromisoformat(text.replace("Z", "+00:00"))
    return parsed.astimezone(dt.timezone.utc)


def _store_dto(src: dict[str, Any]) -> dict[str, Any]:
    return {
        "storeId": src.get("store_id", 0) if isinstance(src.get("store_id"), int) else 0,
        "retailerSlug": _text_or_none(src, "retailer_slug"),
        "retailerName": _text_or_none(src, "retailer_name"),
        "externalKey": _text_or_none(src, "external_key"),
        "name": _text_or_none(src, "name"),
        "address": _text_or_none(src, "address"),
        "city": _text_or_none(src, "city"),
        "activeOffersCount": src.get("active_offers_count", 0) if isinstance(src.get("active_offers_count"), int) else 0,
        "latestPublishedTs": _instant_or_none(src, "latest_published_ts"),
    }


def _offer_dto_from_doc(src: dict[str, Any]) -> dict[str, Any]:
    canonical_id = src.get("canonical_product_id")
    canonical_id = canonical_id if isinstance(canonical_id, int) else None
    return {
        "offerId": _text_or_none(src, "offer_id"),
        "storeId": src.get("store_id", 0) if isinstance(src.get("store_id"), int) else 0,
        "storeExternalKey": _text_or_none(src, "store_external_key"),
        "storeName": _text_or_none(src, "store_name"),
        "city": _text_or_none(src, "city"),
        "retailerSlug": _text_or_none(src, "retailer_slug"),
        "retailerName": _text_or_none(src, "retailer_name"),
        "retailerProductId": src.get("retailer_product_id", 0) if isinstance(src.get("retailer_product_id"), int) else 0,
        "skuKey": _text_or_none(src, "sku_key"),
        "listingName": _text_or_none(src, "listing_name"),
        "category": _text_or_none(src, "category"),
        "canonicalProductId": canonical_id,
        "canonicalKey": _text_or_none(src, "canonical_key"),
        "canonicalName": _text_or_none(src, "canonical_name"),
        "normalizedSize": _text_or_none(src, "normalized_size"),
        "currency": _text_or_none(src, "currency"),
        "priceCurrent": _decimal_or_none(src, "price_current"),
        "unitPrice": _decimal_or_none(src, "unit_price"),
        "unitLabel": _text_or_none(src, "unit_label"),
        "regularPrice": _decimal_or_none(src, "regular_price"),
        "discountPrice": _decimal_or_none(src, "discount_price"),
        "discountPct": _decimal_or_none(src, "discount_pct"),
        "promoType": _text_or_none(src, "promo_type"),
        "promoStartsOn": _date_or_none(src, "promo_starts_on"),
        "promoEndsOn": _date_or_none(src, "promo_ends_on"),
        "isPromo": bool(src.get("is_promo", False)),
        "availability": _text_or_none(src, "availability"),
        "publishedTs": _instant_or_none(src, "published_ts"),
        "fetchedTs": _instant_or_none(src, "fetched_ts"),
        "sourceUrl": _text_or_none(src, "source_url"),
        "runId": src.get("run_id", 0) if isinstance(src.get("run_id"), int) else 0,
    }
