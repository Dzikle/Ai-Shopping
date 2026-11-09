"""Port of McpServerTest.java (5 tests)."""

import datetime as dt
from decimal import Decimal

from fastapi.testclient import TestClient

from app.main import create_app


class FakeCatalogForMcp:
    def search_offers(self, f):
        return {
            "sourceEngine": "opensearch",
            "total": 1,
            "page": 0,
            "size": 10,
            "items": [{
                "offerId": "1:101",
                "storeId": 1,
                "storeExternalKey": "vero-1",
                "storeName": "Веро Тафталиџе",
                "city": "Скопје",
                "retailerSlug": "vero",
                "retailerName": "Vero",
                "retailerProductId": 101,
                "skuKey": "sku101",
                "listingName": "МЛЕКО БИМИЛК 3.2% 1Л",
                "category": "Млечни производи",
                "canonicalProductId": 10,
                "canonicalKey": "1000.000:ml:1::БИМИЛК",
                "canonicalName": "МЛЕКО БИМИЛК",
                "normalizedSize": "1x1000ml",
                "currency": "MKD",
                "priceCurrent": Decimal("75.00"),
                "unitPrice": Decimal("75.00"),
                "unitLabel": "1л",
                "isPromo": False,
                "availability": "in_stock",
                "publishedTs": "2026-10-28T08:00:00Z",
                "fetchedTs": "2026-10-28T09:00:00Z",
                "sourceUrl": "https://pricelist.vero.com.mk/1_1.html",
            }],
        }


class FakeBasketForMcp:
    def optimize_basket(self, req):
        line = {
            "itemIndex": 0,
            "canonicalProductId": 101,
            "requestedRetailerProductId": None,
            "requestedName": "Кадаиф",
            "requestedQuantity": Decimal("800"),
            "requestedUnit": "g",
            "storeId": 1,
            "storeExternalKey": "vero-1",
            "storeName": "Веро Тафталиџе",
            "retailerSlug": "vero",
            "matchedRetailerProductId": 1001,
            "matchedListingName": "КАДАИФ 400ГР",
            "normalizedSize": "400g",
            "packsNeeded": 2,
            "unitPackPriceMkd": Decimal("180.00"),
            "lineTotalMkd": Decimal("360.00"),
            "isSubstitute": False,
            "substituteReason": None,
            "matchConfidence": Decimal("1.00"),
            "publishedTs": "2026-10-28T08:00:00Z",
            "fetchedTs": "2026-10-28T09:00:00Z",
            "sourceUrl": "https://pricelist.vero.com.mk/1_1.html",
        }
        single_store = {
            "storeId": 1,
            "retailerSlug": "vero",
            "retailerName": "Vero",
            "storeExternalKey": "vero-1",
            "storeName": "Веро Тафталиџе",
            "city": "Скопје",
            "itemsCovered": 1,
            "totalItemsRequested": 1,
            "coverageRatio": Decimal("1.0000"),
            "totalMkd": Decimal("360.00"),
            "savingsVsHighestCoveredSingleStoreMkd": Decimal("0.00"),
            "exactMatchesCount": 1,
            "substitutesCount": 0,
            "coveredItems": [line],
            "missingItems": [],
        }
        return {
            "totalItemsRequested": 1,
            "allowSubstitutes": False,
            "inStockOnly": True,
            "maxStoresAllowed": 2,
            "minSplitSavingsMkd": Decimal("0.00"),
            "bestSingleStore": single_store,
            "singleStoreRankings": [single_store],
            "bestMultiStorePlan": None,
        }


def _client():
    return TestClient(create_app(catalog_service=FakeCatalogForMcp(), basket_service=FakeBasketForMcp()))


def test_initialize_and_tools_list():
    c = _client()

    init = c.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
        "protocolVersion": "2024-11-05",
        "clientInfo": {"name": "test-client", "version": "1.0"},
    }})
    assert init.status_code == 200
    init_result = init.json()
    assert init_result["id"] == 1
    assert init_result["result"]["protocolVersion"] == "2024-11-05"
    assert init_result["result"]["serverInfo"]["name"] == "ai-shopping-mcp-server"

    # Notifications/initialized returns 204 No Content
    notif = c.post("/mcp", json={"jsonrpc": "2.0", "method": "notifications/initialized"})
    assert notif.status_code == 204
    assert notif.content == b""

    # tools/list returns all 7 tools
    list_resp = c.post("/mcp", json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    tools = list_resp.json()["result"]["tools"]
    assert len(tools) == 7

    expected_names = [
        "search_products",
        "compare_product_prices",
        "get_price_history",
        "list_stores",
        "find_current_discounts",
        "optimize_shopping_basket",
        "suggest_product_substitutes",
    ]
    for name in expected_names:
        matches = [t for t in tools if t["name"] == name]
        assert len(matches) == 1, f"Expected tool {name} in tools/list"
        assert matches[0]["description"]
        assert "properties" in matches[0]["inputSchema"]


def test_search_products_tool_call():
    c = _client()
    resp = c.post("/mcp", json={
        "jsonrpc": "2.0", "id": 3, "method": "tools/call",
        "params": {"name": "search_products", "arguments": {"query": "млеко", "size": 10}},
    })
    assert resp.status_code == 200
    result = resp.json()["result"]
    assert result["isError"] is False

    payload = __import__("json").loads(result["content"][0]["text"])
    assert payload["totalMatches"] == 1
    assert payload["items"][0]["listingName"] == "МЛЕКО БИМИЛК 3.2% 1Л"
    assert payload["items"][0]["sourceUrl"] == "https://pricelist.vero.com.mk/1_1.html"
    assert "dataFreshness" in payload


def test_optimize_shopping_basket_tool_call():
    c = _client()
    resp = c.post("/mcp", json={
        "jsonrpc": "2.0", "id": 4, "method": "tools/call",
        "params": {"name": "optimize_shopping_basket", "arguments": {
            "items": [{"canonicalProductId": 101, "quantity": 800, "unit": "g"}],
            "maxStores": 2,
        }},
    })
    assert resp.status_code == 200
    result = resp.json()["result"]
    assert result["isError"] is False

    payload = __import__("json").loads(result["content"][0]["text"])
    assert payload["totalItemsRequested"] == 1
    assert Decimal(str(payload["bestSingleStore"]["totalMkd"])) == Decimal("360.00")
    assert payload["bestSingleStore"]["coveredItems"][0]["packsNeeded"] == 2
    assert payload["bestSingleStore"]["coveredItems"][0]["sourceUrl"] == "https://pricelist.vero.com.mk/1_1.html"


def test_unknown_method_and_tool_errors():
    c = _client()
    resp = c.post("/mcp", json={"jsonrpc": "2.0", "id": 5, "method": "unknown/method"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["error"]["code"] == -32601

    tool_resp = c.post("/mcp", json={
        "jsonrpc": "2.0", "id": 6, "method": "tools/call",
        "params": {"name": "non_existent_tool"},
    })
    result = tool_resp.json()["result"]
    assert result["isError"] is True
    assert "Unknown tool" in result["content"][0]["text"]


def test_get_server_info_endpoint():
    c = _client()
    info = c.get("/mcp").json()
    assert info["server"] == "ai-shopping-mcp-server"
    assert info["protocolVersion"] == "2024-11-05"
    assert info["endpoint"] == "/mcp"
