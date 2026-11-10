"""Assistant HTTP route - bounded guest endpoint `POST /api/v1/assistant/turn` (M13).

Rules (m13 task doc):
- never mutates a server or client basket: the response only proposes changes;
- only the explicit allowlist of read-only shopping tools is reachable;
- bounded unauthenticated controls: payload bounds (schemas), per-client rate
  limit, global concurrency cap, provider timeout;
- secrets, stack traces and internal prompts are never reflected to clients;
- response bodies keep the same numeric rendering as the rest of the API.
"""

import time

from fastapi import APIRouter, Request

from app.assistant.rate_limit import ConcurrencyGate, RateLimiter, rate_limit_response
from app.jsonx import RestJSONResponse
from app.schemas.assistant import AssistantTurnRequest

# Allowlist ceiling (task doc): the only operations an assistant turn may ever
# touch - all read-only shopping tools. Privileged surfaces (match review,
# metrics, direct SQL, arbitrary MCP registration) are structurally excluded
# because the coordinator only dispatches by fixed name against the registry.
ASSISTANT_ALLOWLISTED_TOOLS = (
    "search_products",
    "compare_product_prices",
    "get_price_history",
    "list_stores",
    "find_current_discounts",
    "optimize_shopping_basket",
    "suggest_product_substitutes",
)

# Narrower set actually dispatched by the current coordinator.
ASSISTANT_DISPATCHED_TOOLS = (
    "search_products",
    "suggest_product_substitutes",
    "optimize_shopping_basket",
)


def make_assistant_router(coordinator, settings) -> APIRouter:
    router = APIRouter(prefix="/api/v1/assistant", default_response_class=RestJSONResponse)

    rate_limiter = RateLimiter(
        max_requests=settings.assistant_rate_limit_requests,
        window_seconds=settings.assistant_rate_limit_window_seconds,
    )
    concurrency = ConcurrencyGate(settings.assistant_max_concurrency)

    @router.post("/turn", response_model=None)
    def assistant_turn(turn_request: AssistantTurnRequest, request: Request):
        if not (turn_request.message or "").strip() and not turn_request.candidateSelections:
            return RestJSONResponse(
                status_code=400,
                content={"error": "'message' is required (or repeat the previous message with 'candidateSelections')"},
            )

        client_key = request.client.host if (request.client is not None and request.client.host) else "unknown"
        path = request.url.path
        if not rate_limiter.allow(client_key):
            return rate_limit_response(settings.assistant_rate_limit_requests, path)
        if not concurrency.acquire():
            return RestJSONResponse(
                status_code=503,
                content={"error": "Assistant is busy; try again shortly."},
            )
        started = time.monotonic()
        try:
            return coordinator.run_turn(turn_request)
        except Exception:
            # Never leak stack traces; degrade to a typed recoverable error.
            return RestJSONResponse(
                status_code=200,
                content={
                    "requestId": f"asst-{int(started * 1000)}",
                    "status": "assistant_error",
                    "assistantMessage": "Асистентот наиде на неочекувана грешка; обидете се повторно.",
                    "provider": {"id": "unknown", "model": None, "isMock": False, "configured": False},
                    "itemsConsidered": [],
                    "candidateChoices": [],
                    "proposedBasketChanges": [],
                    "unresolvedItems": [],
                    "toolCalls": [],
                    "optimizationPreview": None,
                    "warnings": ["internal_error"],
                    "limits": {},
                },
            )
        finally:
            concurrency.release()

    @router.get("/tools", response_model=None)
    def assistant_tools():
        """Read-only tool surface for the assistant: the allowlist ceiling and
        the subset currently dispatched. No admin tools, no registration."""
        return {
            "allowlistedTools": list(ASSISTANT_ALLOWLISTED_TOOLS),
            "dispatchedTools": list(ASSISTANT_DISPATCHED_TOOLS),
            "note": "Read-only shopping tools only; no administrative surface.",
        }

    return router
