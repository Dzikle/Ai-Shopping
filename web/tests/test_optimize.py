"""Basket optimization relay: bounded, status-preserving, no client-side math."""

import json


def test_optimize_relays_server_totals(stub, client):
    payload = {
        "items": [{"canonicalProductId": 10, "quantity": 1, "unit": "pack", "itemLabel": "Млеко"}],
        "maxStores": 2,
        "allowSubstitutes": False,
        "inStockOnly": True,
    }
    res = client.post("/basket/optimize", json=payload)
    assert res.status_code == 200
    assert stub.optimize_payloads == [payload]
    body = res.json()
    assert body["bestSingleStore"]["totalMkd"] == 75.00
    assert body["bestSingleStore"]["storeName"] == "ВЕРО 1"
    assert body["singleStoreRankings"][1]["missingItems"][0]["reason"] == "no_offer_at_store"


def test_optimize_rejects_oversized_item_lists(stub, client):
    payload = {"items": [{"retailerProductId": i} for i in range(51)]}
    res = client.post("/basket/optimize", json=payload)
    assert res.status_code == 400
    assert res.json()["error"] == "too_many_items"
    assert stub.optimize_payloads == []


def test_optimize_rejects_non_list_items(client):
    res = client.post("/basket/optimize", json={"items": "nope"})
    assert res.status_code == 400


def test_optimize_relays_api_validation_errors(stub, client):
    stub.optimize_status = 400
    stub.optimize_body = {"timestamp": "t", "status": 400, "error": "Bad Request", "path": "/api/v1/baskets/optimize"}
    res = client.post("/basket/optimize", json={"items": []})
    assert res.status_code == 400
    assert res.json()["error"] == "Bad Request"
    assert len(stub.optimize_payloads) == 1


def test_optimize_api_outage_maps_to_503(offline_client):
    res = offline_client.post("/basket/optimize", json={"items": []})
    assert res.status_code == 503
    assert res.json()["error"] == "api_unreachable"


def test_optimize_rejects_oversized_body(stub, client):
    big = json.dumps({"items": [{"itemLabel": "x" * 70000}]})
    res = client.post(
        "/basket/optimize",
        content=big,
        headers={"Content-Type": "application/json"},
    )
    assert res.status_code == 413
    assert stub.optimize_payloads == []


def test_optimize_invalid_json_returns_validation_error(client):
    res = client.post(
        "/basket/optimize",
        content=b"{not json",
        headers={"Content-Type": "application/json"},
    )
    assert res.status_code == 422
