"""Catalog search service - 1:1 port of CatalogSearchService.java.

OpenSearch is tried first wherever Java did so; any failure inside the OpenSearch
paths falls back to the same PostgreSQL repository call.
"""

import datetime as dt
from typing import Any

from app.repositories.catalog_repository import PostgresCatalogRepository
from app.services.opensearch_client import OpenSearchClient


class CatalogSearchService:
    def __init__(self, open_search_client: OpenSearchClient, postgres_repository: PostgresCatalogRepository):
        self._os = open_search_client
        self._pg = postgres_repository

    def get_health(self) -> dict[str, Any]:
        db_up = self._pg.is_database_healthy()
        counts: dict[str, int] = {}
        if db_up:
            counts.update(self._pg.get_table_counts())

        os_up = False
        try:
            os_stores = self._os.count_index("stores")
            os_offers = self._os.count_index("offers")
            os_products = self._os.count_index("products")
            if os_stores >= 0 and os_offers >= 0 and os_products >= 0:
                os_up = True
                counts["opensearch_stores"] = os_stores
                counts["opensearch_offers"] = os_offers
                counts["opensearch_products"] = os_products
        except Exception:
            os_up = False

        status = "UP" if db_up else "DOWN"
        db_status = "UP" if db_up else "DOWN"
        os_status = "UP" if os_up else "FALLBACK_POSTGRESQL"
        active_engine = "opensearch" if os_up else "postgresql_fallback"
        return {
            "status": status,
            "databaseStatus": db_status,
            "opensearchStatus": os_status,
            "activeSearchEngine": active_engine,
            "counts": counts,
        }

    def get_stores(self, retailer: str | None, city: str | None) -> dict[str, Any]:
        if self._os.is_healthy_and_populated():
            try:
                return self._os.search_stores(retailer, city)
            except Exception:
                pass
        return self._pg.find_stores(retailer, city)

    def search_offers(self, f: Any) -> dict[str, Any]:
        if self._os.is_healthy_and_populated():
            try:
                return self._os.search_offers(f)
            except Exception:
                pass
        return self._pg.search_offers(f)

    def compare_products(self, q: str | None, min_retailers: int, page: int, size: int) -> dict[str, Any]:
        if self._os.is_healthy_and_populated():
            try:
                return self._os.search_product_comparisons(q, min_retailers, page, size)
            except Exception:
                pass
        return self._pg.compare_products(q, min_retailers, page, size)

    def get_product_history(self, canonical_product_id: int) -> dict[str, Any] | None:
        return self._pg.get_product_history(canonical_product_id)

    def get_review_queue(self, limit: int) -> list[dict[str, Any]]:
        return self._pg.get_review_queue(limit)

    def get_freshness(self, retailer: str | None, stale_threshold_hours: int, quarantine_window_days: int) -> dict[str, Any]:
        return self._pg.get_freshness(retailer, stale_threshold_hours, quarantine_window_days)

    def approve_match(self, match_id: int, reviewed_by: str | None, review_notes: str | None) -> dict[str, Any]:
        return self._pg.approve_match(match_id, reviewed_by, review_notes)

    def reject_match(self, match_id: int, reviewed_by: str | None, review_notes: str | None) -> dict[str, Any]:
        return self._pg.reject_match(match_id, reviewed_by, review_notes)

    def get_metrics(self) -> dict[str, Any]:
        return self._pg.get_metrics()


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.UTC)
