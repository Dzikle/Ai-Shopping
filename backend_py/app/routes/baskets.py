"""Basket HTTP routes - port of BasketController.java."""

from typing import Any, Optional

from fastapi import APIRouter, Body
from fastapi.responses import Response

from app.schemas.requests import BasketOptimizeRequest, CreateShoppingListRequest
from app.jsonx import RestJSONResponse


def make_baskets_router(basket_service) -> APIRouter:
    router = APIRouter(prefix="/api/v1/baskets", default_response_class=RestJSONResponse)

    @router.post("/optimize", response_model=None)
    def optimize_adhoc_basket(request: BasketOptimizeRequest):
        try:
            return basket_service.optimize_basket(request)
        except ValueError as exc:
            return RestJSONResponse(status_code=400, content={"error": str(exc)})

    @router.post("/lists", response_model=None)
    def create_shopping_list(request: CreateShoppingListRequest):
        try:
            created = basket_service.create_shopping_list(request)
            return RestJSONResponse(status_code=201, content=created)
        except ValueError as exc:
            return RestJSONResponse(status_code=400, content={"error": str(exc)})

    @router.get("/lists/{list_id}", response_model=None)
    def get_shopping_list(list_id: int):
        shopping_list = basket_service.get_shopping_list(list_id)
        if shopping_list is None:
            return Response(status_code=404)
        return shopping_list

    @router.post("/lists/{list_id}/optimize", response_model=None)
    def optimize_saved_shopping_list(list_id: int, overrides: Optional[BasketOptimizeRequest] = Body(default=None)):
        result = basket_service.optimize_saved_list(list_id, overrides)
        if result is None:
            return Response(status_code=404)
        return result

    return router
