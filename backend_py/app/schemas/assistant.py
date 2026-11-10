"""Typed request/response schemas for the assistant turn API (M13).

Jackson-style camelCase with explicit nulls, mirroring existing DTO style.
Bounds are enforced here (schema validators) so the route never trusts raw
client input; ids/prices echoed back by clients are always revalidated
against a fresh catalog search before becoming basket proposals.
"""

from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

ALLOWED_UNITS = ("pack", "pcs", "g", "kg", "ml", "l")
AUDITED_LOCALES = ("mk", "en")


class ConversationEntry(BaseModel):
    model_config = ConfigDict(extra="ignore")

    role: str | None = Field(default=None, max_length=20)
    content: str | None = Field(default=None, max_length=400)

    @field_validator("content")
    @classmethod
    def content_not_empty(cls, value):
        if value is None:
            return None
        value = value.strip()
        return value or None


class BasketEchoItem(BaseModel):
    model_config = ConfigDict(extra="ignore")

    label: str = Field(..., min_length=1, max_length=120)
    canonicalProductId: int | None = Field(default=None, ge=0)
    retailerProductId: int | None = Field(default=None, ge=0)
    quantity: Decimal | None = Field(default=None, gt=0, le=100000)
    unit: str | None = Field(default=None, max_length=8)

    @field_validator("unit")
    @classmethod
    def unit_whitelist(cls, value):
        if value is None:
            return None
        if value not in ALLOWED_UNITS:
            return None
        return value


class AssistantPreferences(BaseModel):
    model_config = ConfigDict(extra="ignore")

    city: str | None = Field(default=None, max_length=60)
    maxStores: int | None = Field(default=None, ge=1, le=3)
    allowSubstitutes: bool | None = None


class CandidateSelection(BaseModel):
    model_config = ConfigDict(extra="ignore")

    itemLabel: str = Field(..., min_length=1, max_length=120)
    query: str | None = Field(default=None, max_length=120)
    candidateId: str = Field(..., min_length=1, max_length=80)
    quantity: Decimal | None = Field(default=None, gt=0, le=100000)
    unit: str | None = Field(default=None, max_length=8)

    @field_validator("unit")
    @classmethod
    def unit_whitelist(cls, value):
        if value is None:
            return None
        if value not in ALLOWED_UNITS:
            return None
        return value


class AssistantTurnRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    message: str | None = Field(default=None, max_length=500)
    locale: str | None = Field(default=None, max_length=8)
    conversationContext: list[ConversationEntry] | None = Field(default=None, max_length=6)
    currentBasket: list[BasketEchoItem] | None = Field(default=None, max_length=20)
    preferences: AssistantPreferences | None = None
    candidateSelections: list[CandidateSelection] | None = Field(default=None, max_length=8)

    @field_validator("message")
    @classmethod
    def message_not_blank(cls, value):
        if value is None:
            return None
        value = value.strip()
        if not value:
            return None
        return value

    @field_validator("locale")
    @classmethod
    def locale_whitelist(cls, value):
        if value is None:
            return None
        if value not in AUDITED_LOCALES:
            return None
        return value


AssistantStatus = Literal[
    "ok",
    "needs_clarification",
    "model_unavailable",
    "model_error",
    "assistant_error",
]

PROPOSAL_TYPES = ("add", "replace_quantity")
UNRESOLVED_REASONS = (
    "no_offers_found",
    "search_failed",
    "ambiguous_needs_clarification",
    "tool_budget_exhausted",
    "candidate_not_confirmed",
    "invalid_quantity",
)

ASSISTANT_LIMITS = {
    "messageMaxChars": 500,
    "conversationContextMaxEntries": 6,
    "conversationContextMaxCharsPerEntry": 400,
    "currentBasketMaxItems": 20,
    "maxItemsPerTurn": 8,
    "maxToolCallsPerTurn": 10,
    "candidateSelectionsMax": 8,
}
