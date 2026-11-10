"""Basket persistence - 1:1 port of BasketRepository.java."""

from decimal import Decimal
from typing import Any

import psycopg
from psycopg import Connection

from app.schemas.requests import BasketOptimizeRequest, CreateShoppingListRequest
from app.services.unit_conversion import normalize_unit, scale

class ProductTargetMeta:
    __slots__ = ("canonical_product_id", "retailer_product_id", "display_name",
                 "normalized_size", "quantity_value", "quantity_unit", "pack_count")

    def __init__(self, canonical_product_id, retailer_product_id, display_name,
                 normalized_size, quantity_value, quantity_unit, pack_count):
        self.canonical_product_id = canonical_product_id
        self.retailer_product_id = retailer_product_id
        self.display_name = display_name
        self.normalized_size = normalized_size
        self.quantity_value = quantity_value
        self.quantity_unit = quantity_unit
        self.pack_count = pack_count


class CandidateStoreOffer:
    __slots__ = ("store_id", "store_external_key", "store_name", "city", "retailer_slug",
                 "retailer_name", "retailer_product_id", "listing_name", "normalized_size",
                 "sku_quantity_value", "sku_quantity_unit", "sku_pack_count", "price_current",
                 "is_substitute", "substitute_reason", "confidence", "published_ts",
                 "fetched_ts", "source_url")

    def __init__(self, row):
        self.store_id = row["store_id"]
        self.store_external_key = row["store_external_key"]
        self.store_name = row["store_name"]
        self.city = row["city"]
        self.retailer_slug = row["retailer_slug"]
        self.retailer_name = row["retailer_name"]
        self.retailer_product_id = row["retailer_product_id"]
        self.listing_name = row["listing_name"]
        self.normalized_size = row["normalized_size"]
        self.sku_quantity_value = row["quantity_value"]
        self.sku_quantity_unit = row["quantity_unit"]
        self.sku_pack_count = _jdbc_int(row["pack_count"])
        self.price_current = scale(row["price_current"], 2)
        self.is_substitute = bool(row["is_substitute"])
        self.substitute_reason = row["substitute_reason"]
        conf = row["confidence"]
        self.confidence = scale(conf, 2) if conf is not None else Decimal("1.00")
        self.published_ts = row["published_ts"]
        self.fetched_ts = row["fetched_ts"]
        self.source_url = row["source_url"]


def _jdbc_int(value) -> int:
    """Java rs.getInt() semantics: SQL NULL -> 0."""
    if value is None:
        return 0
    return int(value)


class BasketRepository:
    def __init__(self, db):
        self._db = db

    # ---- list CRUD ----

    def create_shopping_list(self, req: CreateShoppingListRequest) -> dict[str, Any]:
        if req is None or req.name is None or not req.name.strip():
            raise ValueError("Shopping list name is required")
        city_filter = req.cityFilter.strip() if (req.cityFilter and req.cityFilter.strip()) else None

        with self._db.transaction() as conn:
            cur = conn.execute(
                "INSERT INTO shopping_lists (name, city_filter) VALUES (%s, %s) RETURNING id",
                (req.name.strip(), city_filter),
            )
            row = cur.fetchone()
            if not row or row["id"] is None:
                raise RuntimeError("Failed to insert shopping_list")
            list_id = row["id"]

            items = req.items or []
            for i, item in enumerate(items):
                if item.canonicalProductId is None and item.retailerProductId is None:
                    raise ValueError(
                        "Each basket item must specify canonicalProductId or retailerProductId"
                    )
                qty = item.quantity if (item.quantity is not None and item.quantity > 0) else Decimal(1)
                qty = scale(qty, 3)
                unit = normalize_unit(item.unit)
                conn.execute(
                    """
                    INSERT INTO shopping_list_items
                        (shopping_list_id, canonical_product_id, retailer_product_id, item_label, quantity, unit, position)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """,
                    (list_id, item.canonicalProductId, item.retailerProductId,
                     item.itemLabel, qty, unit, i),
                )

        created = self.get_shopping_list(list_id)
        if created is None:
            raise RuntimeError(f"Created shopping list not found: {list_id}")
        return created

    def get_shopping_list(self, list_id: int) -> dict[str, Any] | None:
        header = self._db.query_one(
            "SELECT id, name, city_filter, created_at, updated_at FROM shopping_lists WHERE id = %s",
            (list_id,),
        )
        if header is None:
            return None

        item_sql = """
                SELECT sli.id,
                       sli.canonical_product_id,
                       sli.retailer_product_id,
                       sli.item_label,
                       sli.quantity,
                       sli.unit,
                       sli.position,
                       COALESCE(cp.canonical_name, rp.listing_name, sli.item_label) AS resolved_name,
                       cp.normalized_size
                FROM shopping_list_items sli
                LEFT JOIN canonical_products cp ON cp.id = sli.canonical_product_id
                LEFT JOIN retailer_products rp ON rp.id = sli.retailer_product_id
                WHERE sli.shopping_list_id = %s
                ORDER BY sli.position ASC, sli.id ASC
                """
        items = []
        for row in self._db.query(item_sql, (list_id,)):
            items.append({
                "id": row["id"],
                "canonicalProductId": row["canonical_product_id"],
                "retailerProductId": row["retailer_product_id"],
                "resolvedName": row["resolved_name"],
                "normalizedSize": row["normalized_size"],
                "itemLabel": row["item_label"],
                "quantity": scale(row["quantity"], 3) if row["quantity"] is not None else None,
                "unit": row["unit"],
                "position": row["position"],
            })
        return {
            "id": header["id"],
            "name": header["name"],
            "cityFilter": header["city_filter"],
            "createdAt": header["created_at"],
            "updatedAt": header["updated_at"],
            "items": items,
        }

    # ---- candidate store/offer loading ----

    def find_active_stores(self, city: str | None, retailers: list[str] | None) -> list[dict[str, Any]]:
        where = " WHERE EXISTS (SELECT 1 FROM offers_current oc WHERE oc.store_id = s.id) "
        params: list[Any] = []

        if city and city.strip():
            where += " AND LOWER(s.city) = %s "
            params.append(city.strip().lower())
        if retailers:
            clean = [r.strip().lower() for r in retailers if r and r.strip()]
            if clean:
                where += " AND LOWER(r.slug) IN (" + ",".join("%s" for _ in clean) + ") "
                params.extend(clean)

        sql = f"""
                SELECT s.id AS store_id,
                       r.slug AS retailer_slug,
                       r.name AS retailer_name,
                       s.external_key AS store_external_key,
                       s.name AS store_name,
                       s.city
                FROM stores s
                JOIN retailers r ON r.id = s.retailer_id
                {where} ORDER BY s.id ASC
                """
        return [
            {
                "store_id": row["store_id"],
                "retailer_slug": row["retailer_slug"],
                "retailer_name": row["retailer_name"],
                "store_external_key": row["store_external_key"],
                "store_name": row["store_name"],
                "city": row["city"],
            }
            for row in self._db.query(sql, tuple(params))
        ]

    def resolve_product_target(self, canonical_product_id: int | None,
                               retailer_product_id: int | None,
                               fallback_label: str | None) -> ProductTargetMeta | None:
        if canonical_product_id is not None:
            sql = """
                    SELECT id, canonical_name, normalized_size, quantity_value, quantity_unit, pack_count
                    FROM canonical_products
                    WHERE id = %s
                    """
            rows = self._db.query(sql, (canonical_product_id,))
            if rows:
                row = rows[0]
                return ProductTargetMeta(
                    canonical_product_id=row["id"],
                    retailer_product_id=retailer_product_id,
                    display_name=row["canonical_name"],
                    normalized_size=row["normalized_size"],
                    quantity_value=row["quantity_value"],
                    quantity_unit=row["quantity_unit"],
                    pack_count=_jdbc_int(row["pack_count"]),
                )

        if retailer_product_id is not None:
            sql = """
                    SELECT rp.id AS retailer_product_id,
                           rp.listing_name,
                           cp.id AS canonical_product_id,
                           cp.normalized_size,
                           cp.quantity_value,
                           cp.quantity_unit,
                           COALESCE(cp.pack_count, 1) AS pack_count
                    FROM retailer_products rp
                    LEFT JOIN product_matches pm
                      ON pm.retailer_product_id = rp.id
                     AND pm.review_status IN ('auto_accepted', 'approved')
                    LEFT JOIN canonical_products cp ON cp.id = pm.canonical_product_id
                    WHERE rp.id = %s
                    """
            rows = self._db.query(sql, (retailer_product_id,))
            if rows:
                row = rows[0]
                return ProductTargetMeta(
                    canonical_product_id=row["canonical_product_id"],
                    retailer_product_id=row["retailer_product_id"],
                    display_name=row["listing_name"],
                    normalized_size=row["normalized_size"],
                    quantity_value=row["quantity_value"],
                    quantity_unit=row["quantity_unit"],
                    pack_count=_jdbc_int(row["pack_count"]),
                )
        return None

    def find_candidate_offers(self, canonical_product_id: int | None,
                              retailer_product_id: int | None,
                              allow_substitutes: bool, in_stock_only: bool,
                              city: str | None, retailers: list[str] | None) -> list[CandidateStoreOffer]:
        filter_where = ""
        filter_params: list[Any] = []

        if in_stock_only:
            filter_where += " AND oc.availability = 'in_stock' "
        if city and city.strip():
            filter_where += " AND LOWER(s.city) = %s "
            filter_params.append(city.strip().lower())
        if retailers:
            clean = [r.strip().lower() for r in retailers if r and r.strip()]
            if clean:
                filter_where += " AND LOWER(r.slug) IN (" + ",".join("%s" for _ in clean) + ") "
                filter_params.extend(clean)

        if canonical_product_id is not None:
            status_clause = (
                "pm.review_status IN ('auto_accepted', 'approved', 'pending_review')"
                if allow_substitutes
                else "pm.review_status IN ('auto_accepted', 'approved')"
            )
            sql = f"""
                    SELECT s.id AS store_id,
                           s.external_key AS store_external_key,
                           s.name AS store_name,
                           s.city,
                           r.slug AS retailer_slug,
                           r.name AS retailer_name,
                           rp.id AS retailer_product_id,
                           rp.listing_name,
                           cp.normalized_size,
                           cp.quantity_value,
                           cp.quantity_unit,
                           cp.pack_count,
                           oc.price_current,
                           (pm.review_status = 'pending_review') AS is_substitute,
                           CASE WHEN pm.review_status = 'pending_review'
                                THEN 'stage2_pending_review_candidate'
                                ELSE NULL
                           END AS substitute_reason,
                           pm.confidence,
                           oc.published_ts,
                           oc.fetched_ts,
                           oc.source_url
                    FROM product_matches pm
                    JOIN canonical_products cp ON cp.id = pm.canonical_product_id
                    JOIN retailer_products rp ON rp.id = pm.retailer_product_id
                    JOIN offers_current oc ON oc.retailer_product_id = rp.id
                    JOIN stores s ON s.id = oc.store_id
                    JOIN retailers r ON r.id = s.retailer_id
                    WHERE pm.canonical_product_id = %s
                     AND {status_clause}
                    {filter_where}
                    ORDER BY is_substitute ASC, pm.confidence DESC, oc.price_current ASC, s.id ASC
                    """
            params = [canonical_product_id] + filter_params
            return [CandidateStoreOffer(row) for row in self._db.query(sql, tuple(params))]

        if retailer_product_id is not None:
            sql = f"""
                    SELECT s.id AS store_id,
                           s.external_key AS store_external_key,
                           s.name AS store_name,
                           s.city,
                           r.slug AS retailer_slug,
                           r.name AS retailer_name,
                           rp.id AS retailer_product_id,
                           rp.listing_name,
                           cp.normalized_size,
                           cp.quantity_value,
                           cp.quantity_unit,
                           COALESCE(cp.pack_count, 1) AS pack_count,
                           oc.price_current,
                           false AS is_substitute,
                           NULL::text AS substitute_reason,
                           1.000::numeric AS confidence,
                           oc.published_ts,
                           oc.fetched_ts,
                           oc.source_url
                    FROM offers_current oc
                    JOIN retailer_products rp ON rp.id = oc.retailer_product_id
                    JOIN stores s ON s.id = oc.store_id
                    JOIN retailers r ON r.id = s.retailer_id
                    LEFT JOIN product_matches pm
                      ON pm.retailer_product_id = rp.id
                     AND pm.review_status IN ('auto_accepted', 'approved')
                    LEFT JOIN canonical_products cp ON cp.id = pm.canonical_product_id
                    WHERE oc.retailer_product_id = %s
                    {filter_where}
                    ORDER BY oc.price_current ASC, s.id ASC
                    """
            params = [retailer_product_id] + filter_params
            return [CandidateStoreOffer(row) for row in self._db.query(sql, tuple(params))]

        return []
