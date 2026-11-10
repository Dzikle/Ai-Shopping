"""Catalog HTTP routes - port of CatalogController.java."""

from decimal import Decimal
from typing import Any, Optional

from fastapi import APIRouter, Query
from fastapi.responses import Response

from app.jsonx import RestJSONResponse
from app.schemas.requests import ReviewQueueActionRequest


class _OfferSearchFilter:
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


def make_catalog_router(search_service) -> APIRouter:
    router = APIRouter(prefix="/api/v1", default_response_class=RestJSONResponse)

    @router.get("/health", response_model=None)
    def health() -> dict[str, Any]:
        return search_service.get_health()

    @router.get("/stores", response_model=None)
    def stores(
        retailer: Optional[str] = Query(default=None),
        city: Optional[str] = Query(default=None),
    ) -> dict[str, Any]:
        return search_service.get_stores(retailer, city)

    @router.get("/offers/search", response_model=None)
    def search_offers(
        q: Optional[str] = Query(default=None),
        retailer: Optional[str] = Query(default=None),
        storeKey: Optional[str] = Query(default=None),
        category: Optional[str] = Query(default=None),
        inStockOnly: bool = Query(default=False),
        promoOnly: bool = Query(default=False),
        minPrice: Optional[Decimal] = Query(default=None),
        maxPrice: Optional[Decimal] = Query(default=None),
        sort: str = Query(default="price_asc"),
        page: int = Query(default=0),
        size: int = Query(default=20),
    ) -> dict[str, Any]:
        filter_obj = _OfferSearchFilter(
            q, retailer, storeKey, category, inStockOnly, promoOnly, minPrice, maxPrice, sort, page, size
        )
        return search_service.search_offers(filter_obj)

    @router.get("/products/compare", response_model=None)
    def compare_products(
        q: Optional[str] = Query(default=None),
        minRetailers: int = Query(default=2),
        page: int = Query(default=0),
        size: int = Query(default=20),
    ) -> dict[str, Any]:
        return search_service.compare_products(q, minRetailers, page, size)

    @router.get("/products/{canonical_id}/history", response_model=None)
    def product_history(canonical_id: int):
        history = search_service.get_product_history(canonical_id)
        if history is None:
            return Response(status_code=404)
        return history

    @router.get("/matches/review-queue", response_model=None)
    def review_queue(limit: int = Query(default=25)) -> list[dict[str, Any]]:
        return search_service.get_review_queue(limit)

    @router.post("/matches/review-queue/{match_id}/approve", response_model=None)
    def approve_match(match_id: int, request: ReviewQueueActionRequest) -> dict[str, Any]:
        return search_service.approve_match(match_id, request.reviewedBy, request.reviewNotes)

    @router.post("/matches/review-queue/{match_id}/reject", response_model=None)
    def reject_match(match_id: int, request: ReviewQueueActionRequest) -> dict[str, Any]:
        return search_service.reject_match(match_id, request.reviewedBy, request.reviewNotes)

    @router.get("/freshness", response_model=None)
    def freshness(
        retailer: Optional[str] = Query(default=None),
        staleThresholdHours: int = Query(default=48),
        quarantineWindowDays: int = Query(default=7),
    ) -> dict[str, Any]:
        return search_service.get_freshness(retailer, staleThresholdHours, quarantineWindowDays)

    @router.get("/metrics", response_model=None)
    def metrics() -> dict[str, Any]:
        return search_service.get_metrics()

    return router
