"""Request DTOs (Jackson-shaped camelCase; unknown fields ignored)."""

from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class BasketItemRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    canonicalProductId: int | None = None
    retailerProductId: int | None = None
    itemLabel: str | None = None
    quantity: Decimal | None = None
    unit: str | None = None


class BasketOptimizeRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    items: list[BasketItemRequest] | None = None
    city: str | None = None
    retailers: list[str] | None = None
    maxStores: int | None = None
    minSplitSavingsMkd: Decimal | None = None
    allowSubstitutes: bool | None = None
    inStockOnly: bool | None = None


class CreateShoppingListRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str | None = None
    cityFilter: str | None = None
    items: list[BasketItemRequest] | None = None


class ReviewQueueActionRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    reviewedBy: str | None = None
    reviewNotes: str | None = None


def plain_item(item: BasketItemRequest) -> dict[str, Any]:
    """Snake-free dict view used by repositories/services."""
    return {
        "canonicalProductId": item.canonicalProductId,
        "retailerProductId": item.retailerProductId,
        "itemLabel": item.itemLabel,
        "quantity": item.quantity,
        "unit": item.unit,
    }
