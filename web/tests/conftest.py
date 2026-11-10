"""Shared fixtures: a stub AI Shopping API on a local HTTP server.

Matches the backend_py test seam style (ThreadingHTTPServer): the web app
under test talks real HTTP over a real socket, so URL construction, query
encoding, redirects and status handling are all exercised for real.
"""

import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.main import create_app  # noqa: E402

WEB_BASE = "http://web.test"

OFFER = {
    "offerId": "1:101",
    "storeId": 1,
    "storeExternalKey": "vero-1",
    "storeName": "ВЕРО 1",
    "city": "Скопје",
    "retailerSlug": "vero",
    "retailerName": "Vero",
    "retailerProductId": 101,
    "skuKey": "abc",
    "listingName": "Млеко Devin млеко 3.2% 1л",
    "category": "Млеко и млечни производи",
    "canonicalProductId": 10,
    "canonicalKey": "1000.000:ml:1::млеко",
    "canonicalName": "Млеко Devin 3.2% 1л",
    "normalizedSize": "1x1000ml",
    "currency": "MKD",
    "priceCurrent": 75.00,
    "unitPrice": 75.00,
    "unitLabel": "1л",
    "regularPrice": 79.00,
    "discountPrice": 75.00,
    "discountPct": 5.06,
    "promoType": "Каталошка акција",
    "promoStartsOn": "2026-04-01",
    "promoEndsOn": "2026-04-30",
    "isPromo": True,
    "availability": "in_stock",
    "publishedTs": "2026-04-17T10:00:00Z",
    "fetchedTs": "2026-04-17T12:00:00Z",
    "sourceUrl": "https://pricelist.vero.com.mk/1_1.html",
    "runId": 1,
}

COMPARE_GROUP = {
    "canonicalProductId": 10,
    "canonicalKey": "1000.000:ml:1::млеко",
    "canonicalName": "Млеко Devin 3.2% 1л",
    "normalizedSize": "1x1000ml",
    "retailerCount": 2,
    "storeCount": 6,
    "cheapestMkd": 85.00,
    "highestMkd": 99.00,
    "spreadMkd": 14.00,
    "latestPublishedTs": "2026-04-17T10:00:00Z",
    "offers": [
        {
            "retailerSlug": "vero",
            "retailerProductId": 101,
            "listingName": "Млеко Devin млеко 3.2% 1л",
            "minPrice": 85.00,
            "maxPrice": 85.00,
            "storeCount": 3,
            "latestPublishedTs": "2026-04-17T10:00:00Z",
            "sourceUrl": "https://pricelist.vero.com.mk/1_1.html",
        },
        {
            "retailerSlug": "stokomak",
            "retailerProductId": 202,
            "listingName": "Млеко Devin 3.2% 1л",
            "minPrice": 99.00,
            "maxPrice": 99.00,
            "storeCount": 3,
            "latestPublishedTs": "2026-04-16T09:00:00Z",
            "sourceUrl": "https://stokomak.proverkanaceni.mk/1_1.html",
        },
    ],
}

FRESHNESS = {
    "status": "FRESH",
    "checkedAt": "2026-11-10T07:30:00Z",
    "staleThresholdHours": 48,
    "quarantineWindowDays": 7,
    "totalOffers": 2,
    "totalPopulatedStores": 2,
    "totalStaleStores": 0,
    "totalQuarantinedRuns": 0,
    "retailers": [
        {
            "retailerSlug": "vero",
            "retailerName": "Vero",
            "seededStoresCount": 17,
            "populatedStoresCount": 1,
            "offerCount": 1,
            "latestPublishedTs": "2026-04-17T10:00:00Z",
            "oldestPublishedTs": "2026-04-17T10:00:00Z",
            "latestFetchedTs": "2026-04-17T12:00:00Z",
            "staleStoresCount": 0,
            "staleStores": [],
            "quarantinedRunsCount": 0,
            "lastCompletedRunKey": "r1",
            "lastCompletedAt": "2026-04-17T12:00:00Z",
        },
        {
            "retailerSlug": "stokomak",
            "retailerName": "Stokomak",
            "seededStoresCount": 81,
            "populatedStoresCount": 1,
            "offerCount": 1,
            "latestPublishedTs": "2026-04-16T09:00:00Z",
            "oldestPublishedTs": "2026-04-16T09:00:00Z",
            "latestFetchedTs": "2026-04-16T11:00:00Z",
            "staleStoresCount": 0,
            "staleStores": [],
            "quarantinedRunsCount": 0,
            "lastCompletedRunKey": "r2",
            "lastCompletedAt": "2026-04-16T11:00:00Z",
        },
    ],
    "quarantinedRuns": [],
}

OPTIMIZATION = {
    "totalItemsRequested": 1,
    "allowSubstitutes": False,
    "inStockOnly": True,
    "maxStoresAllowed": 2,
    "minSplitSavingsMkd": 15.00,
    "bestSingleStore": {
        "storeId": 1,
        "retailerSlug": "vero",
        "retailerName": "Vero",
        "storeExternalKey": "vero-1",
        "storeName": "ВЕРО 1",
        "city": "Скопје",
        "itemsCovered": 1,
        "totalItemsRequested": 1,
        "coverageRatio": 1.0,
        "totalMkd": 75.00,
        "savingsVsHighestCoveredSingleStoreMkd": 0,
        "exactMatchesCount": 1,
        "substitutesCount": 0,
        "coveredItems": [{
            "itemIndex": 0,
            "canonicalProductId": 10,
            "requestedName": "Млеко Devin 3.2% 1л",
            "storeId": 1,
            "matchedListingName": "Млеко Devin млеко 3.2% 1л",
            "packsNeeded": 1,
            "lineTotalMkd": 75.00,
            "isSubstitute": False,
        }],
        "missingItems": [],
    },
    "singleStoreRankings": [
        {
            "storeId": 1, "retailerSlug": "vero", "retailerName": "Vero",
            "storeName": "ВЕРО 1", "city": "Скопје",
            "itemsCovered": 1, "totalItemsRequested": 1,
            "coverageRatio": 1.0, "totalMkd": 75.00,
            "savingsVsHighestCoveredSingleStoreMkd": 0,
            "exactMatchesCount": 1, "substitutesCount": 0,
            "coveredItems": [], "missingItems": [],
        },
        {
            "storeId": 2, "retailerSlug": "stokomak", "retailerName": "Stokomak",
            "storeName": "СТОКОМАК 1", "city": "Скопје",
            "itemsCovered": 0, "totalItemsRequested": 1,
            "coverageRatio": 0.0, "totalMkd": 0,
            "savingsVsHighestCoveredSingleStoreMkd": 0,
            "exactMatchesCount": 0, "substitutesCount": 0,
            "coveredItems": [],
            "missingItems": [{
                "itemIndex": 0, "canonicalProductId": 10, "retailerProductId": None,
                "requestedName": "Млеко Devin 3.2% 1л", "requestedQuantity": 1,
                "requestedUnit": "pack", "reason": "no_offer_at_store",
            }],
        },
    ],
    "bestMultiStorePlan": {
        "storeIds": [1],
        "storeCount": 1,
        "itemsCovered": 1,
        "coverageRatio": 1.0,
        "totalMkd": 75.00,
        "savingsVsBestSingleStoreMkd": 0,
        "meetsMinSavingsThreshold": False,
        "recommendationReason": "split_not_worth_vs_best_single",
        "storeAllocations": [],
        "missingItems": [],
    },
}


class StubApi:
    """Records requests and serves deterministic canned responses."""

    def __init__(self, port: int = 0):
        self.search_calls: list[dict] = []
        self.compare_calls: list[dict] = []
        self.optimize_payloads: list[dict] = []
        self.offers = [dict(OFFER)]
        self.offers_total = 1
        self.compare_groups = [dict(COMPARE_GROUP)]
        self.optimize_status = 200
        self.optimize_body = OPTIMIZATION

        outer = self

        class Handler(BaseHTTPRequestHandler):
            def _send(self, status: int, body: dict | list):
                data = json.dumps(body).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self):
                parsed = urlparse(self.path)
                params = {k: v[-1] for k, v in parse_qs(parsed.query).items()}
                path = parsed.path
                if path == "/api/v1/freshness":
                    self._send(200, FRESHNESS)
                elif path == "/api/v1/offers/search":
                    outer.search_calls.append({
                        "q": params.get("q"),
                        "retailer": params.get("retailer"),
                        "inStockOnly": params.get("inStockOnly") == "true",
                        "promoOnly": params.get("promoOnly") == "true",
                        "sort": params.get("sort", "price_asc"),
                        "page": int(params.get("page", "0")),
                        "size": int(params.get("size", "20")),
                    })
                    page = int(params.get("page", "0"))
                    self._send(200, {
                        "sourceEngine": "postgresql_fallback",
                        "total": outer.offers_total,
                        "page": page,
                        "size": int(params.get("size", "20")),
                        "items": outer.offers if page == 0 else [],
                    })
                elif path == "/api/v1/products/compare":
                    call = {
                        "q": params.get("q"),
                        "minRetailers": int(params.get("minRetailers", "2")),
                        "page": int(params.get("page", "0")),
                        "size": int(params.get("size", "20")),
                        "canonicalId": int(params["canonicalId"]) if "canonicalId" in params else None,
                    }
                    outer.compare_calls.append(call)
                    if call["canonicalId"] is not None:
                        groups = [g for g in outer.compare_groups
                                  if g["canonicalProductId"] == call["canonicalId"]]
                    else:
                        groups = outer.compare_groups
                    self._send(200, {
                        "sourceEngine": "postgresql_fallback",
                        "total": len(groups),
                        "page": call["page"],
                        "size": call["size"],
                        "items": groups if call["page"] == 0 else [],
                    })
                else:
                    self.send_response(404)
                    self.send_header("Content-Length", "0")
                    self.end_headers()

            def do_POST(self):
                length = int(self.headers.get("Content-Length") or 0)
                raw = self.rfile.read(length) if length else b"{}"
                payload = json.loads(raw.decode("utf-8"))
                outer.optimize_payloads.append(payload)
                self._send(outer.optimize_status, outer.optimize_body)

            def log_message(self, format, *args):  # noqa: A002
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
        self._thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self._thread.start()

    @property
    def url(self) -> str:
        host, port = self.server.server_address[:2]
        return f"http://{host}:{port}"

    def stop(self) -> None:
        self.server.shutdown()
        self.server.server_close()


def _make_client(stub: StubApi | None):
    if stub is None:
        class _FailingTransport(httpx.BaseTransport):
            def handle_request(self, request):
                raise httpx.ConnectError("connection refused", request=request)
        transport = _FailingTransport()
    else:
        transport = None
    app = create_app(
        api_base_url=stub.url if stub else "http://api.test",
        web_base_url=WEB_BASE,
        transport=transport,
    )
    from fastapi.testclient import TestClient
    return TestClient(app)


@pytest.fixture()
def stub():
    instance = StubApi()
    yield instance
    instance.stop()


@pytest.fixture()
def client(stub):
    return _make_client(stub)


@pytest.fixture()
def offline_client():
    return _make_client(None)
