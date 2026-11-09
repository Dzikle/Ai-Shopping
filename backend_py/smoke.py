"""Smoke test - exercise routes with in-memory fakes before infra wiring."""

import sys

from fastapi.testclient import TestClient

from app.main import create_app, _build_default_stack
from app.schemas.requests import BasketOptimizeRequest, CreateShoppingListRequest, BasketItemRequest
from app.jsonx import RestJSONResponse


class FakeCatalog:
    def get_health(self):
        return {"status": "UP", "counts": {}}

    def get_stores(self, retailer, city):
        return {"total": 1, "items": [{"key": "vero-skar"}]}

    def search_offers(self, f):
        return {"total": 2, "page": f.page if hasattr(f, "page") else 0, "items": [
            {"canonicalProductId": 1, "displayPrice": 49.99},
        ]}

    def compare_products(self, q, min_ret, page, size):
        return {"total": 1, "items": []}

    def get_product_history(self, canonical_id):
        if canonical_id == 99:
            return None
        return {"canonicalProductId": canonical_id, "observations": []}

    def get_review_queue(self, limit):
        return [{"candidateCanonicalId": 5}]

    def get_freshness(self, retailer, stale_hours, window_days):
        return {"summary": [{"retailer": "vero", "staleCount": 0}]}

    def approve_match(self, match_id, reviewed_by, review_notes):
        raise ValueError("Match not found: " + str(match_id))

    def reject_match(self, match_id, reviewed_by, review_notes):
        return {"matchId": match_id, "status": "REJECTED"}

    def get_metrics(self):
        return {"grossMarginPct": {"value": 12.5}}


class FakeBasket:
    def optimize_basket(self, req: BasketOptimizeRequest):
        if req.items and req.items[0].canonicalProductId == 77:
            raise ValueError("x")
        from decimal import Decimal
        return {
            "totalItemsRequested": len(req.items),
            "singleStoreRankings": [{"storeId": "s", "totalMkd": Decimal("12.30")}],
            "bestSingleStore": {"storeId": "s", "coveredItems": []},
            "bestMultiStorePlan": None,
            "allowSubstitutes": req.allowSubstitutes,
            "inStockOnly": req.inStockOnly,
        }

    def create_shopping_list(self, req: CreateShoppingListRequest):
        import datetime as dt
        return {"id": 1, "name": req.name, "createdAt": dt.datetime(2026, 1, 1, 12, 0, 0, tzinfo=dt.UTC),
                "items": [{"requestedItemId": 1, "quantity": req.items[0].quantity}]}

    def get_shopping_list(self, list_id):
        if list_id == 99:
            return None
        return {"id": list_id, "status": "ACTIVE"}

    def optimize_saved_list(self, list_id, overrides):
        if list_id == 99:
            return None
        return {"listId": list_id, "totalItemsRequested": 1}


app = create_app(catalog_service=FakeCatalog(), basket_service=FakeBasket())


def expect(name, cond):
    print(f"{'OK  ' if cond else 'FAIL'} {name}")
    if not cond:
        sys.exit(1)


c = TestClient(app, raise_server_exceptions=False)

r = c.get("/api/v1/health")
expect("health 200", r.status_code == 200 and r.json()["status"] == "UP")

r = c.get("/api/v1/stores?retailer=vero&city=Skopje")
expect("stores query params", r.status_code == 200 and r.json()["total"] == 1)

r = c.get("/api/v1/offers/search?q=млеко&minPrice=9.50&size=5&page=1")
expect("offers decimal parse", r.status_code == 200 and r.json()["total"] == 2)

r = c.get("/api/v1/offers/search?page=abc")
expect("bad param -> 400", r.status_code == 400 and r.json()["status"] == 400)

r = c.get("/api/v1/products/42/history")
expect("history found", r.status_code == 200 and r.json()["canonicalProductId"] == 42)

r = c.get("/api/v1/products/99/history")
expect("history 404 empty body", r.status_code == 404 and r.content == b"")

r = c.get("/api/v1/matches/review-queue?limit=10")
expect("review queue", r.json()[0]["candidateCanonicalId"] == 5)

r = c.post("/api/v1/matches/review-queue/7/approve", json={"reviewedBy": "me"})
expect("approve uncaught -> 500 spring", r.status_code == 500 and r.json()["error"] == "Internal Server Error")

r = c.post("/api/v1/matches/review-queue/7/reject", json={"reviewedBy": "me"})
expect("reject ok", r.status_code == 200 and r.json()["status"] == "REJECTED")

r = c.get("/api/v1/freshness?retailer=vero&staleThresholdHours=24&quarantineWindowDays=6")
expect("freshness", r.status_code == 200)

r = c.post("/api/v1/baskets/optimize", json={
    "items": [{"canonicalProductId": 1, "quantity": 2, "unit": "kg"}],
})
j = r.json()
expect("optimize decimal rendering", r.status_code == 200 and isinstance(j["singleStoreRankings"][0]["totalMkd"], (int, float)) and abs(j["singleStoreRankings"][0]["totalMkd"] - 12.3) < 1e-9)

r = c.post("/api/v1/baskets/optimize", json={"items": [{"canonicalProductId": 77, "quantity": 1}]})
expect("optimize 400 error shape", r.status_code == 400 and r.json() == {"error": "x"})

r = c.post("/api/v1/baskets/lists", json={"name": "Pazar", "items": [{"canonicalProductId": 3, "quantity": 1.5}]})
expect("create list 201", r.status_code == 201 and r.json()["createdAt"] == "2026-01-01T12:00:00Z")

r = c.get("/api/v1/baskets/lists/99")
expect("list 404", r.status_code == 404 and r.content == b"")

r = c.post("/api/v1/baskets/lists/5/optimize")
expect("saved optimize no body ok", r.status_code == 200 and r.json()["listId"] == 5)

r = c.get("/mcp")
expect("mcp info", r.json()["server"] == "ai-shopping-mcp-server" and r.json()["version"] == "0.5.0")

r = c.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "initialize"})
expect("initialize", r.json()["result"]["protocolVersion"] == "2024-11-05" and r.json()["result"]["serverInfo"]["name"] == "ai-shopping-mcp-server")

r = c.post("/mcp", json={"jsonrpc": "2.0", "id": 2, "method": "ping"})
expect("ping", r.json()["result"] == {})

r = c.post("/mcp", json={"jsonrpc": "2.0", "id": 3, "method": "tools/list"})
expect("tools/list 7 tools", len(r.json()["result"]["tools"]) == 7 and r.json()["result"]["tools"][0]["name"] == "search_products")

r = c.post("/mcp", json={"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "search_products"}})
j = r.json()["result"]
expect("tools/call validation error flag", j["isError"] is True and "'query'" in j["content"][0]["text"])

r = c.post("/mcp", json={"jsonrpc": "2.0", "id": 5, "method": "tools/call", "params": {"name": "zzz"}})
j = r.json()["result"]
expect("unknown tool error", j["isError"] is True and "Unknown tool" in j["content"][0]["text"])

r = c.post("/mcp", json={"jsonrpc": "2.0", "id": 6, "method": "nope"})
expect("unknown method -32601", r.json()["error"]["code"] == -32601)

r = c.post("/mcp", json={"jsonrpc": "2.0", "method": "notifications/initialized"})
expect("notification 204", r.status_code == 204 and r.content == b"")

r = c.post("/mcp", json={"jsonrpc": "2.0", "id": 7, "method": "notifications/initialized"})
expect("initialized w/ id -> 204", r.status_code == 204)

r = c.post("/mcp", json={"jsonrpc": "2.0", "id": 8, "method": "notifications/other"})
expect("other notification w/ id -> -32601", r.status_code == 200 and r.json()["error"]["code"] == -32601)

r = c.post("/mcp", content=b"not json", headers={"Content-Type": "application/json"})
expect("malformed json -> 400 spring", r.status_code == 400 and r.json()["status"] == 400 and r.json()["error"] == "Bad Request")

r = c.post("/mcp", content=b"")
expect("empty json -> 400 -32600", r.status_code == 400 and r.json()["error"]["code"] == -32600)

r = c.post("/mcp", json={"jsonrpc": "2.0", "id": 9, "method": "tools/call", "params": {}})
expect("tools/call no name -> -32602", r.json()["error"]["code"] == -32602 and "name" in r.json()["error"]["message"])

r = c.get("/nonexistent")
expect("404 spring shape", r.status_code == 404 and r.json()["error"] == "Not Found" and r.json()["path"] == "/nonexistent")

r = c.post("/api/v1/baskets/optimize", json={"items": "nope", "maxStores": 9})
expect("body validation -> 400 spring", r.status_code == 400 and r.json()["error"] == "Bad Request")

print("ALL SMOKE OK")
