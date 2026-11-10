"""M13 assistant route tests: grounding, choices, bounded fallbacks.

Fake services mirror tests/conftest.py seams but are tailored to assistant
resolution paths (verified/unverified/ambiguous/out-of-stock with substitute
candidate coverage).
"""

import json
import threading
from decimal import Decimal
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.assistant.providers import (
    InterpreterRequest,
    MockShoppingProvider,
    OpenAICompatibleProvider,
    ProviderInvalidResponse,
    ProviderUnavailable,
)
from app.main import create_app

URL = "https://pricelist.vero.com.mk/1_1.html"


class FakeAssistantCatalog:
    """search_offers seam keyed by trimmed query."""

    def __init__(self):
        self.queries = []

    def search_offers(self, f):
        self.queries.append(f.q)
        result = {
            "sourceEngine": "opensearch",
            "total": 1,
            "page": 0,
            "size": f.size,
            "items": [],
        }
        if f.q == "млеко":
            result["total"] = 1
            result["items"] = [_offer("1:101", 101, "МЛЕКО БИМИЛК 3.2% 1Л", 10, "МЛЕКО БИМИЛК 1Л", "75.00", "in_stock", "2026-10-28T08:00:00Z")]
        elif f.q == "каша":
            # two different canonical products -> ambiguous (needs choice)
            result["total"] = 2
            result["items"] = [
                _offer("1:201", 201, "КАША ЗРНА 500Г", 20, "КАША ЗРНА 500Г", "60.00", "in_stock", "2026-10-28T08:00:00Z"),
                _offer("2:202", 202, "КАША ВЕГЕТАЛИЈАНСКА 350Г", 22, "КАША ВЕГЕТАЛИЈАНСКА 350Г", "80.00", "in_stock", "2026-10-28T08:00:00Z"),
            ]
        elif f.q == "уникат":
            # group without verified identity -> single retailer product
            result["total"] = 1
            item = _offer("1:301", 301, "УНИКАТ ДЕЗЕРТ", None, None, "99.00", "in_stock", "2026-10-28T08:00:00Z")
            item["canonicalProductId"] = None
            item["canonicalKey"] = None
            item.pop("canonicalName", None)
            result["items"] = [item]
        elif f.q == "сирење":
            # verified canonical but out of stock everywhere
            result["total"] = 1
            result["items"] = [_offer("1:401", 401, "СИРЕњЕ СКМЈ 800Г", 30, "СИРЕњЕ 800Г", "150.00", "out_of_stock", "2026-10-28T08:00:00Z")]
        elif f.q == "БИТОЛСКИ ЈОГУРТ БИМИЛК 1Л":
            result["total"] = 1
            result["items"] = [_offer("1:501", 501, "БИТОЛСКИ ЈОГУРТ БИМИЛК 1Л", 22, "БИТОЛСКИ ЈОГУРТ 1Л", "55.00", "in_stock", "2026-10-28T07:00:00Z")]
        elif f.q == "СИРЕЊЕ КОЦКИ 800Г":
            # substitute-candidate probe (Stage-2 review queue name)
            result["total"] = 1
            result["items"] = [_offer("1:402", 402, "СИРЕЊЕ КОЦКИ 800Г", 30, "СИРЕЊЕ КОЦКИ 800Г", "145.00", "in_stock", "2026-10-29T06:00:00Z")]
        elif f.q == "старо":
            result["total"] = 1
            result["items"] = [_offer("1:601", 601, "СТАРО МЛЕКО 1Л", 10, "СТАРО МЛЕКО 1Л", "70.00", "in_stock", "2026-08-01T08:00:00Z")]
        return result

    def get_review_queue(self, limit):
        return [{
            "matchId": 78,
            "sourceRetailerSlug": "stokomak",
            "retailerProductId": 302,
            "sourceListingName": "СИРЕЊЕ СКМЈ 800Г",
            "candidateCanonicalId": 30,
            "candidateCanonicalName": "СИРЕЊЕ КОЦКИ 800Г",
            "normalizedSize": "1x800ml",
            "confidence": Decimal("0.61"),
            "reviewStatus": "pending_review",
            "evidence": {"shared_tokens": ["СИРЕЊЕ"]},
        }]


def _offer(offer_id, retailer_product_id, listing_name, canonical_id, canonical_name,
           price, availability, published_ts):
    source = {
        "offerId": offer_id,
        "storeId": 1,
        "storeExternalKey": "vero-1",
        "storeName": "Веро Тафталиџе",
        "city": "Скопје",
        "retailerSlug": "vero",
        "retailerName": "Vero",
        "retailerProductId": retailer_product_id,
        "listingName": listing_name,
        "normalizedSize": "1x1000ml",
        "currency": "MKD",
        "priceCurrent": Decimal(price),
        "unitPrice": Decimal(price),
        "unitLabel": "1л",
        "isPromo": False,
        "availability": availability,
        "publishedTs": published_ts,
        "fetchedTs": published_ts,
        "sourceUrl": URL,
    }
    if canonical_id is not None:
        source["canonicalProductId"] = canonical_id
        source["canonicalKey"] = f"key-{canonical_id}"
        source["canonicalName"] = canonical_name
    return source


class RecordingBasketService:
    """optimize_basket seam that captures its request for assertions."""

    def __init__(self):
        self.requests = []

    def optimize_basket(self, req):
        self.requests.append(req)
        line = {
            "itemIndex": 0,
            "canonicalProductId": 10,
            "requestedRetailerProductId": None,
            "requestedName": "МЛЕКО",
            "requestedQuantity": Decimal("1"),
            "requestedUnit": "pack",
            "storeId": 1,
            "storeExternalKey": "vero-1",
            "storeName": "Веро Тафталиџе",
            "retailerSlug": "vero",
            "matchedRetailerProductId": 101,
            "matchedListingName": "МЛЕКО БИМИЛК 3.2% 1Л",
            "normalizedSize": "1x1000ml",
            "packsNeeded": 1,
            "unitPackPriceMkd": Decimal("75.00"),
            "lineTotalMkd": Decimal("75.00"),
            "isSubstitute": False,
            "substituteReason": None,
            "matchConfidence": Decimal("1.00"),
            "publishedTs": "2026-10-28T08:00:00Z",
            "fetchedTs": "2026-10-28T09:00:00Z",
            "sourceUrl": URL,
        }
        store = {
            "storeId": 1,
            "retailerSlug": "vero",
            "retailerName": "Vero",
            "storeExternalKey": "vero-1",
            "storeName": "Веро Тафталиџе",
            "city": "Скопје",
            "itemsCovered": 1,
            "totalItemsRequested": 1,
            "coverageRatio": Decimal("1.0000"),
            "totalMkd": Decimal("75.00"),
            "savingsVsHighestCoveredSingleStoreMkd": Decimal("0.00"),
            "exactMatchesCount": 1,
            "substitutesCount": 0,
            "coveredItems": [line],
            "missingItems": [],
        }
        return {
            "totalItemsRequested": 1,
            "allowSubstitutes": req.allowSubstitutes,
            "inStockOnly": req.inStockOnly,
            "maxStoresAllowed": req.maxStores,
            "minSplitSavingsMkd": Decimal("0.00"),
            "bestSingleStore": store,
            "singleStoreRankings": [store, store, store, store, store, store],
            "bestMultiStorePlan": None,
        }


class OutageProvider:
    id = "outage"
    is_mock = False

    def plan_turn(self, request: InterpreterRequest):
        raise ProviderUnavailable("provider_unreachable: OSError")


class InvalidProvider:
    id = "broken"
    is_mock = False

    def plan_turn(self, request: InterpreterRequest):
        raise ProviderInvalidResponse("invalid_json")


class _ChatHandler(BaseHTTPRequestHandler):
    reply_content: str = json.dumps({"items": [{"label": "млеко"}], "assistantMessage": "Пронајдов млеко."})

    def do_POST(self):  # noqa: N802
        self.rfile.read(int(self.headers.get("Content-Length", 0)))
        if self.path != "/v1/chat/completions":
            self.send_response(404)
            self.end_headers()
            return
        body = json.dumps({"choices": [{"message": {"content": self.reply_content}}]}).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):  # noqa: A002
        pass


def chat_server(reply_content: str = _ChatHandler.reply_content):
    handler_cls = type("Handler", (_ChatHandler,), {"reply_content": reply_content})
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler_cls)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, f"http://127.0.0.1:{server.server_address[1]}/v1"


def live_provider(base_url: str) -> OpenAICompatibleProvider:
    return OpenAICompatibleProvider(
        model="test-model",
        base_url=base_url,
        api_key="test-key",
        max_tokens=256,
        timeout_seconds=5,
    )


def app_with(catalog=None, basket=None, provider=None, settings=None):
    catalog = catalog if catalog is not None else FakeAssistantCatalog()
    basket = basket if basket is not None else RecordingBasketService()
    return create_app(
        settings=settings,
        catalog_service=catalog,
        basket_service=basket,
        assistant_provider=provider,
    )


# --------------------------------------------------------------------- tests

def test_no_provider_reports_honest_unavailability():
    client = TestClient(app_with(provider=None))
    resp = client.post("/api/v1/assistant/turn", json={"message": "млеко"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "model_unavailable"
    assert "model_not_configured" in body["warnings"]
    assert body["provider"]["configured"] is False
    assert body["provider"]["id"] == "none"
    assert body["toolCalls"] == []
    assert body["proposedBasketChanges"] == []


def test_blank_message_rejected():
    client = TestClient(app_with(provider=MockShoppingProvider()))
    resp = client.post("/api/v1/assistant/turn", json={"message": "   "})
    assert resp.status_code == 400


def test_mock_turn_proposes_verified_product_with_preview():
    catalog, basket = FakeAssistantCatalog(), RecordingBasketService()
    client = TestClient(app_with(catalog, basket, provider=MockShoppingProvider()))
    resp = client.post("/api/v1/assistant/turn", json={"message": "млеко"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["provider"]["isMock"] is True
    assert "mock_provider_demo_only" in body["warnings"]
    assert len(body["proposedBasketChanges"]) == 1
    proposal = body["proposedBasketChanges"][0]
    assert proposal["changeType"] == "add"
    assert proposal["canonicalProductId"] == 10
    assert proposal["retailerProductId"] == 101
    assert proposal["verifiedIdentity"] is True
    assert Decimal(str(proposal["priceCurrentMkd"])) == Decimal("75.00")
    assert proposal["sourceUrl"] == URL
    assert proposal["publishedTs"].endswith("Z")
    tools = [c["tool"] for c in body["toolCalls"]]
    assert tools == ["search_products", "optimize_shopping_basket"]
    preview = body["optimizationPreview"]
    assert preview["previewOnly"] is True
    assert Decimal(str(preview["bestSingleStore"]["totalMkd"])) == Decimal("75.00")
    assert len(basket.requests) == 1
    assert basket.requests[0].inStockOnly is True
    assert len(preview["singleStoreRankings"]) == 5  # trimmed from 6


def test_mock_turn_ambiguous_asks_for_choice():
    client = TestClient(app_with(provider=MockShoppingProvider()))
    resp = client.post("/api/v1/assistant/turn", json={"message": "каша"})
    body = resp.json()
    assert body["status"] == "needs_clarification"
    assert body["proposedBasketChanges"] == []
    assert len(body["candidateChoices"]) == 1
    choice = body["candidateChoices"][0]
    assert choice["reason"] == "multiple_products"
    options = choice["options"]
    assert 2 <= len(options) <= 3
    canonical_ids = {o["canonicalProductId"] for o in options}
    assert canonical_ids == {20, 22}
    assert all(o["candidateId"].startswith("c:") for o in options)
    assert " примена " not in body["assistantMessage"]
    assert body["optimizationPreview"] is None


def test_mock_unverified_single_listing_proposal_without_canonical():
    client = TestClient(app_with(provider=MockShoppingProvider()))
    resp = client.post("/api/v1/assistant/turn", json={"message": "уникат"})
    body = resp.json()
    assert body["status"] == "ok"
    assert len(body["proposedBasketChanges"]) == 1
    proposal = body["proposedBasketChanges"][0]
    assert proposal["canonicalProductId"] is None
    assert proposal["verifiedIdentity"] is False
    assert proposal["retailerProductId"] == 301


def test_selection_turn_honors_explicit_candidate():
    client = TestClient(app_with(provider=MockShoppingProvider()))
    resp = client.post("/api/v1/assistant/turn", json={
        "message": None,
        "candidateSelections": [{
            "itemLabel": "КАША",
            "query": "каша",
            "candidateId": "c:20:201",
            "quantity": 2,
            "unit": "pack",
        }],
    })
    body = resp.json()
    assert body["status"] == "ok"
    assert len(body["proposedBasketChanges"]) == 1
    proposal = body["proposedBasketChanges"][0]
    assert proposal["canonicalProductId"] == 20
    assert proposal["quantity"] == 2.0
    assert Decimal(str(proposal["priceCurrentMkd"])) == Decimal("60.00")


def test_selection_turn_with_disappeared_candidate_unresolved():
    client = TestClient(app_with(provider=MockShoppingProvider()))
    resp = client.post("/api/v1/assistant/turn", json={
        "message": None,
        "candidateSelections": [{
            "itemLabel": "ДОНЕСОНО",
            "query": "каша",
            "candidateId": "c:999:123",
            "quantity": 1,
            "unit": "pack",
        }],
    })
    body = resp.json()
    assert body["status"] == "ok"
    assert body["proposedBasketChanges"] == []
    assert body["unresolvedItems"] == [{"label": "ДОНЕСОНО", "reason": "candidate_not_confirmed"}]
    assert body["optimizationPreview"] is None


def test_missing_picks_offer_out_of_stock_substitute():
    client = TestClient(app_with(provider=MockShoppingProvider()))
    resp = client.post("/api/v1/assistant/turn", json={"message": "сирење"})
    body = resp.json()
    assert body["status"] == "needs_clarification"
    choice = body["candidateChoices"][0]
    assert choice["reason"] == "no_in_stock_offers"
    options = choice["options"]
    assert options[0]["canonicalProductId"] == 30
    assert options[0]["retailerProductId"] == 402
    assert options[0]["isSubstituteCandidate"] is True
    assert "substitute_candidates_unverified" in body["warnings"]
    assert body["proposedBasketChanges"] == []


def test_stale_offers_flagged():
    client = TestClient(app_with(provider=MockShoppingProvider()))
    resp = client.post("/api/v1/assistant/turn", json={"message": "старо"})
    body = resp.json()
    assert "stale_offers" in body["warnings"]


def test_basket_echo_replaces_quantity():
    basket = RecordingBasketService()
    client = TestClient(app_with(basket=basket, provider=MockShoppingProvider()))
    resp = client.post("/api/v1/assistant/turn", json={
        "message": "2 литра млеко",
        "currentBasket": [{
            "label": "МЛЕКО БИМИЛК 1Л",
            "canonicalProductId": 10,
            "retailerProductId": 101,
            "quantity": 1,
            "unit": "pack",
        }],
    })
    body = resp.json()
    proposal = body["proposedBasketChanges"][0]
    assert proposal["changeType"] == "replace_quantity"
    assert proposal["quantity"] == 2.0
    assert proposal["unit"] == "l"
    assert proposal["oldQuantity"] == 1.0
    assert proposal["oldUnit"] == "pack"


def test_basket_echo_same_quantity_is_no_change():
    client = TestClient(app_with(provider=MockShoppingProvider()))
    resp = client.post("/api/v1/assistant/turn", json={
        "message": "млеко",
        "currentBasket": [{
            "label": "МЛЕКО БИМИЛК 1Л",
            "canonicalProductId": 10,
            "retailerProductId": 101,
            "quantity": 1,
            "unit": "pack",
        }],
        # mock extractor: no quantity -> default 1.0 package
    })
    body = resp.json()
    assert body["proposedBasketChanges"] == []
    assert body["itemsConsidered"][0]["outcome"] == "already_in_basket"


def test_provider_outage_is_model_unavailable():
    client = TestClient(app_with(provider=OutageProvider()))
    resp = client.post("/api/v1/assistant/turn", json={"message": "млеко"})
    body = resp.json()
    assert body["status"] == "model_unavailable"
    assert "provider_outage" in body["warnings"]
    assert body["proposedBasketChanges"] == []
    assert body["toolCalls"] == []


def test_invalid_model_output_is_model_error():
    client = TestClient(app_with(provider=InvalidProvider()))
    resp = client.post("/api/v1/assistant/turn", json={"message": "млеко"})
    body = resp.json()
    assert body["status"] == "model_error"
    assert "model_invalid_response" in body["warnings"]
    assert body["proposedBasketChanges"] == []


def test_openai_compatible_provider_end_to_end():
    server, base = chat_server()
    try:
        client = TestClient(app_with(provider=live_provider(base)))
        resp = client.post("/api/v1/assistant/turn", json={"message": "треба ми млеко"})
        body = resp.json()
        assert body["status"] == "ok"
        assert body["provider"]["id"] == "openai_compatible"
        assert body["provider"]["isMock"] is False
        assert body["assistantMessage"] == "Пронајдов млеко."
        proposal = body["proposedBasketChanges"][0]
        assert proposal["canonicalProductId"] == 10
    finally:
        server.shutdown()
        server.server_close()


def test_openai_compatible_provider_rejects_money_like_fields():
    handler_content = json.dumps({"items": [], "assistantMessage": "hi", "estimatedTotalMkd": 5})
    server, base = chat_server(reply_content=handler_content)
    try:
        client = TestClient(app_with(provider=live_provider(base)))
        resp = client.post("/api/v1/assistant/turn", json={"message": "млеко"})
        body = resp.json()
        assert body["status"] == "model_error"
        assert "model_invalid_response" in body["warnings"]
    finally:
        server.shutdown()
        server.server_close()


LIMITED_SETTINGS = SimpleNamespace(
    assistant_rate_limit_requests=1,
    assistant_rate_limit_window_seconds=600,
    assistant_max_concurrency=1,
)


def test_rate_limit_429_after_burst():
    client = TestClient(app_with(provider=MockShoppingProvider(), settings=LIMITED_SETTINGS))
    first = client.post("/api/v1/assistant/turn", json={"message": "млеко"})
    second = client.post("/api/v1/assistant/turn", json={"message": "каша"})
    assert first.status_code == 200
    assert second.status_code == 429
    error_body = second.json()
    assert error_body["status"] == 429


def test_tools_endpoint_lists_allowlist_only():
    client = TestClient(app_with(provider=MockShoppingProvider()))
    resp = client.get("/api/v1/assistant/tools")
    body = resp.json()
    assert set(body["allowlistedTools"]) == {
        "search_products", "compare_product_prices", "get_price_history",
        "list_stores", "find_current_discounts", "optimize_shopping_basket",
        "suggest_product_substitutes",
    }
    assert body["dispatchedTools"] == ["search_products", "suggest_product_substitutes", "optimize_shopping_basket"]


def test_tool_budget_bounds_runaway_requests():
    catalog = FakeAssistantCatalog()
    client = TestClient(app_with(catalog=catalog, provider=MockShoppingProvider()))
    message = ", ".join("млеко" for _ in range(12))
    resp = client.post("/api/v1/assistant/turn", json={"message": message})
    body = resp.json()
    # The mock provider clamps to MAX_ITEMS_PER_TURN=8 items; the coordinator
    # then issues 8 bounded searches plus 1 optimizer call.
    assert len(body["itemsConsidered"]) == 8
    ok_calls = [c for c in body["toolCalls"] if c["status"] == "ok"]
    assert len(ok_calls) <= 10
    assert len(body["proposedBasketChanges"]) == 8
