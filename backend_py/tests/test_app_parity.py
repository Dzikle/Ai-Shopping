"""App-routing parity checks (beyond the Java unit seams):

- Spring-shaped 404/400/500 error bodies and empty-body 404s.
- Body/query validation remapping (FastAPI 422 -> Spring Boot 400).
- In-basket actions throwing repository failures -> 400 {"error": ...}.
- MCP envelope edge cases (malformed JSON, missing method, notifications).
"""

import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture()
def client():
    from app.services.basket_optimizer_service import BasketOptimizerService
    from tests.conftest import FakeBasketRepository

    basket_service = BasketOptimizerService(FakeBasketRepository())

    class FakeCatalogService:
        def get_product_history(self, canonical_product_id):
            return None

        def get_review_queue(self, limit):
            return []

    return TestClient(
        create_app(catalog_service=FakeCatalogService(), basket_service=basket_service),
        raise_server_exceptions=False,
    )


def test_spring_error_shape_for_unknown_path(client):
    r = client.get("/nonexistent")
    assert r.status_code == 404
    body = r.json()
    assert body["status"] == 404
    assert body["error"] == "Not Found"
    assert body["path"] == "/nonexistent"
    assert "timestamp" in body


def test_query_type_mismatch_maps_to_400_spring_shape(client):
    r = client.get("/api/v1/offers/search?page=abc")
    assert r.status_code == 400
    assert r.json()["status"] == 400
    assert r.json()["error"] == "Bad Request"


def test_body_validation_maps_to_400_spring_shape(client):
    r = client.post("/api/v1/baskets/optimize", json={"items": "nope"})
    assert r.status_code == 400
    assert r.json()["error"] == "Bad Request"


def test_basket_empty_items_maps_to_400_error_payload(client):
    # Mirrors Java: IllegalArgumentException("Basket must contain at least one item") -> 400
    r = client.post("/api/v1/baskets/optimize", json={"items": []})
    assert r.status_code == 400
    assert list(r.json().keys()) == ["error"]


def test_history_404_empty_body_not_json(client):
    r = client.get("/api/v1/products/99999/history")
    assert r.status_code == 404
    assert r.headers.get("content-type") not in ("application/json",)


def test_mcp_malformed_json_maps_to_400(client):
    r = client.post("/mcp", content=b"not json", headers={"Content-Type": "application/json"})
    assert r.status_code == 400
    assert r.json()["status"] == 400


def test_mcp_empty_body_maps_to_invalid_request(client):
    r = client.post("/mcp", content=b"")
    assert r.status_code == 400
    assert r.json()["error"]["code"] == -32600


def test_mcp_missing_tool_name_maps_to_invalid_params(client):
    r = client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {}})
    assert r.json()["error"]["code"] == -32602


def test_mcp_notification_without_id_is_204(client):
    r = client.post("/mcp", json={"jsonrpc": "2.0", "method": "notifications/initialized"})
    assert r.status_code == 204
    assert r.content == b""


def test_mcp_notification_with_id_and_unknown_notifications_is_32601(client):
    r = client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "notifications/other"})
    assert r.status_code == 200
    assert r.json()["error"]["code"] == -32601
