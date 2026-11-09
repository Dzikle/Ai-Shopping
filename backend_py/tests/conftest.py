"""Shared test fixtures: mock OpenSearch HTTP server + fake repositories.

Ports the Java test seams: CatalogApiTest starts a local HTTP server answering
_count/_search requests and mocks PostgresCatalogRepository; BasketOptimizerTest
and McpServerTest mock repository/service objects directly.
"""

import threading
from decimal import Decimal
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest


class _MockOpenSearchHandler(BaseHTTPRequestHandler):
    routes: dict = {}
    calls: list = []

    def _handle(self):
        path = self.path.split("?")[0]
        self.calls.append(path)
        route = self.routes.get(path)
        if route is None:
            self.send_response(404)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        status, body = route
        data = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    do_GET = _handle
    do_POST = _handle
    do_HEAD = _handle

    def log_message(self, format, *args):  # noqa: A002
        pass


@pytest.fixture()
def mock_open_search():
    handler_cls = type("Handler", (_MockOpenSearchHandler,), {"routes": {}, "calls": []})
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler_cls)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}", handler_cls.routes, handler_cls.calls
    finally:
        server.shutdown()
        server.server_close()


def install_os_mock_counts(routes):
    routes["/stores/_count"] = (200, '{"count":192}')
    routes["/offers/_count"] = (200, '{"count":1896}')
    routes["/products/_count"] = (200, '{"count":1372}')
    routes["/offers/_search"] = (200, r"""
        {
          "hits": {
            "total": { "value": 1, "relation": "eq" },
            "hits": [
              {
                "_source": {
                  "offer_id": "1:101",
                  "store_id": 1,
                  "store_external_key": "vero-1",
                  "store_name": "Веро 1",
                  "city": "Скопје",
                  "retailer_slug": "vero",
                  "retailer_name": "Vero",
                  "retailer_product_id": 101,
                  "sku_key": "8600103021011",
                  "listing_name": "МЛЕКО БИМИЛК 3.2% 1Л",
                  "category": "Млечни производи",
                  "canonical_product_id": 10,
                  "canonical_key": "1000.000:ml:1::БИМИЛК МЛЕКО",
                  "canonical_name": "МЛЕКО БИМИЛК 3.2% 1Л",
                  "normalized_size": "1x1000ml",
                  "currency": "MKD",
                  "price_current": 75.00,
                  "unit_price": 75.00,
                  "unit_label": "1л",
                  "regular_price": 79.00,
                  "discount_price": 75.00,
                  "discount_pct": 5.06,
                  "promo_type": "Рамазанска акција",
                  "promo_starts_on": "2026-04-01",
                  "promo_ends_on": "2026-04-30",
                  "is_promo": true,
                  "availability": "in_stock",
                  "published_ts": "2026-04-17T10:00:00Z",
                  "fetched_ts": "2026-04-17T12:00:00Z",
                  "source_url": "https://pricelist.vero.com.mk/1_1.html",
                  "run_id": 1
                }
              }
            ]
          }
        }
        """)
    routes["/products/_search"] = (200, r"""
        {
          "hits": {
            "total": { "value": 1, "relation": "eq" },
            "hits": [
              {
                "_source": {
                  "canonical_product_id": 10,
                  "canonical_key": "1000.000:ml:1::БИМИЛК МЛЕКО",
                  "canonical_name": "БИО МЛЕКО БИМИЛК 1Л",
                  "normalized_size": "1x1000ml",
                  "retailer_count": 2,
                  "store_count": 6,
                  "min_price": 85.00,
                  "max_price": 99.00,
                  "spread_mkd": 14.00,
                  "latest_published_ts": "2026-04-17T10:00:00Z",
                  "offers": [
                    {
                      "retailer_slug": "zito",
                      "retailer_product_id": 201,
                      "listing_name": "БИО МЛЕКО БИМИЛК 1Л",
                      "min_price": 85.00,
                      "max_price": 85.00,
                      "store_count": 3,
                      "latest_published_ts": "2026-04-17T10:00:00Z",
                      "source_url": "https://zito.proverkanaceni.mk/2_1.html"
                    },
                    {
                      "retailer_slug": "vero",
                      "retailer_product_id": 102,
                      "listing_name": "БИО МЛЕКО БИМИЛК 1Л",
                      "min_price": 99.00,
                      "max_price": 99.00,
                      "store_count": 3,
                      "latest_published_ts": "2026-04-17T09:00:00Z",
                      "source_url": "https://pricelist.vero.com.mk/1_1.html"
                    }
                  ]
                }
              }
            ]
          }
        }
        """)
    return routes


def vero_store():
    return {"store_id": 1, "retailer_slug": "vero", "retailer_name": "Vero",
            "store_external_key": "89", "store_name": "Веро Тафталиџе", "city": "Скопје"}


def stoko_store():
    return {"store_id": 20, "retailer_slug": "stokomak", "retailer_name": "Stokomak",
            "store_external_key": "1", "store_name": "КИСЕЛА ВОДА", "city": "Скопје"}


def zito_store():
    return {"store_id": 100, "retailer_slug": "zito", "retailer_name": "Zito",
            "store_external_key": "8", "store_name": "8 Бутел1 - Скопје", "city": "Скопје"}


def offer_row(store: dict, retailer_product_id, listing_name, normalized_size,
              qty_value, qty_unit, price, is_sub, sub_reason, confidence,
              pub_ts, fetch_ts, url) -> dict:
    return {
        "store_id": store["store_id"],
        "store_external_key": store["store_external_key"],
        "store_name": store["store_name"],
        "city": store["city"],
        "retailer_slug": store["retailer_slug"],
        "retailer_name": store["retailer_name"],
        "retailer_product_id": retailer_product_id,
        "listing_name": listing_name,
        "normalized_size": normalized_size,
        "quantity_value": Decimal(str(qty_value)),
        "quantity_unit": qty_unit,
        "pack_count": 1,
        "price_current": Decimal(price),
        "is_substitute": is_sub,
        "substitute_reason": sub_reason,
        "confidence": Decimal(confidence),
        "published_ts": pub_ts,
        "fetched_ts": fetch_ts,
        "source_url": url,
    }


class FakeBasketRepository:
    """Port of BasketOptimizerTest's Mockito seeding."""

    def __init__(self):
        self.targets = {}
        self.offers = {}

    def find_active_stores(self, city, retailers):
        return [vero_store(), stoko_store(), zito_store()]

    def resolve_product_target(self, canonical_product_id, retailer_product_id, fallback_label):
        if canonical_product_id is None or canonical_product_id in self.targets:
            return self.targets.get(canonical_product_id)
        return None

    def find_candidate_offers(self, canonical_product_id, retailer_product_id,
                              allow_substitutes, in_stock_only, city, retailers):
        provider = self.offers.get(canonical_product_id)
        return provider(allow_substitutes) if provider else []


class FakePostgresRepository:
    """Port of CatalogApiTest's Mockito seeding."""

    def __init__(self):
        self.compare_calls = []
        self.approve_calls = []
        self.reject_calls = []

    def is_database_healthy(self):
        return True

    def get_table_counts(self):
        return {"stores": 192, "offers_current": 1896, "canonical_products": 1372}

    def find_stores(self, retailer, city):
        return {
            "sourceEngine": "postgresql_fallback",
            "total": 1,
            "page": 0,
            "size": 1,
            "items": [{
                "storeId": 1,
                "retailerSlug": "vero",
                "retailerName": "Vero",
                "externalKey": "vero-1",
                "name": "Веро 1",
                "address": "Скопје",
                "city": "Скопје",
                "activeOffersCount": 162,
                "latestPublishedTs": "2026-04-17T10:00:00Z",
            }],
        }

    def search_offers(self, f):
        return {"sourceEngine": "postgresql_fallback", "total": 0, "page": f.page, "size": f.size, "items": []}

    def compare_products(self, q, min_retailers, page, size):
        self.compare_calls.append((q, min_retailers, page, size))
        return {
            "sourceEngine": "postgresql_fallback",
            "total": 1,
            "page": 0,
            "size": 20,
            "items": [{
                "canonicalProductId": 10,
                "canonicalKey": "1000.000:ml:1::БИМИЛК МЛЕКО",
                "canonicalName": "БИО МЛЕКО БИМИЛК 1Л",
                "normalizedSize": "1x1000ml",
                "retailerCount": 2,
                "storeCount": 6,
                "cheapestMkd": Decimal("85.00"),
                "highestMkd": Decimal("99.00"),
                "spreadMkd": Decimal("14.00"),
                "latestPublishedTs": "2026-04-17T10:00:00Z",
                "offers": [{
                    "retailerSlug": "zito",
                    "retailerProductId": 201,
                    "listingName": "БИО МЛЕКО БИМИЛК 1Л",
                    "minPrice": Decimal("85.00"),
                    "maxPrice": Decimal("85.00"),
                    "storeCount": 3,
                    "latestPublishedTs": "2026-04-17T10:00:00Z",
                    "sourceUrl": "https://zito.proverkanaceni.mk/2_1.html",
                }],
            }],
        }

    def get_product_history(self, canonical_product_id):
        if canonical_product_id == 10:
            return {
                "canonicalProductId": 10,
                "canonicalName": "БИО МЛЕКО БИМИЛК 1Л",
                "normalizedSize": "1x1000ml",
                "observations": [{
                    "observationId": 500,
                    "retailerSlug": "zito",
                    "storeExternalKey": "zito-2",
                    "storeName": "Жито 2",
                    "listingName": "БИО МЛЕКО БИМИЛК 1Л",
                    "priceCurrent": Decimal("85.00"),
                    "regularPrice": None,
                    "discountPrice": None,
                    "discountPct": None,
                    "promoType": None,
                    "availability": "in_stock",
                    "publishedTs": "2026-04-17T10:00:00Z",
                    "fetchedTs": "2026-04-17T12:00:00Z",
                    "sourceUrl": "https://zito.proverkanaceni.mk/2_1.html",
                }],
            }
        return None

    def get_review_queue(self, limit):
        return [{
            "matchId": 77,
            "sourceRetailerSlug": "stokomak",
            "retailerProductId": 301,
            "sourceListingName": "ЈОГУРТ БИМИЛК 1Л",
            "candidateCanonicalId": 22,
            "candidateCanonicalName": "БИТОЛСКИ ЈОГУРТ БИМИЛК 1Л",
            "normalizedSize": "1x1000ml",
            "confidence": Decimal("0.67"),
            "reviewStatus": "pending_review",
            "evidence": {"shared_tokens": ["БИМИЛК", "ЈОГУРТ"]},
        }]

    def approve_match(self, match_id, reviewed_by, review_notes):
        self.approve_calls.append((match_id, reviewed_by, review_notes))
        return {"matchId": match_id, "reviewStatus": "approved",
                "reviewedBy": reviewed_by, "reviewNotes": review_notes}

    def reject_match(self, match_id, reviewed_by, review_notes):
        self.reject_calls.append((match_id, reviewed_by, review_notes))
        return {"matchId": match_id, "reviewStatus": "rejected",
                "reviewedBy": reviewed_by, "reviewNotes": review_notes}

    def get_freshness(self, retailer, stale_threshold_hours, quarantine_window_days):
        return {
            "status": "DEGRADED",
            "checkedAt": "2026-10-31T08:30:00Z",
            "staleThresholdHours": stale_threshold_hours,
            "quarantineWindowDays": quarantine_window_days,
            "totalOffers": 1896,
            "totalPopulatedStores": 7,
            "totalStaleStores": 1,
            "totalQuarantinedRuns": 1,
            "retailers": [{
                "retailerSlug": "vero",
                "retailerName": "Vero",
                "seededStoresCount": 17,
                "populatedStoresCount": 1,
                "offerCount": 1000,
                "latestPublishedTs": "2026-10-28T07:02:00Z",
                "oldestPublishedTs": "2026-10-28T07:02:00Z",
                "latestFetchedTs": "2026-10-28T10:00:00Z",
                "staleStoresCount": 1,
                "staleStores": [{
                    "storeId": 89,
                    "externalKey": "89",
                    "storeName": "ВЕРО 1",
                    "city": "Аеродром",
                    "offerCount": 1000,
                    "latestPublishedTs": "2026-10-28T07:02:00Z",
                    "latestFetchedTs": "2026-10-28T10:00:00Z",
                    "ageHours": Decimal("72.50"),
                }],
                "quarantinedRunsCount": 0,
                "lastCompletedRunKey": "m6-vero-1",
                "lastCompletedAt": "2026-10-28T10:01:00Z",
            }],
            "quarantinedRuns": [{
                "runId": 42,
                "runKey": "m6-zito-empty",
                "sourceSlug": "zito",
                "status": "quarantined",
                "startedAt": "2026-10-29T08:35:00Z",
                "finishedAt": "2026-10-29T08:35:05Z",
                "pagesSeen": 1,
                "rowsSeen": 0,
                "quarantineReason": "pages with header but zero product rows: https://zito.proverkanaceni.mk/?org=1&perPage=2000&page=1",
                "workerId": "scheduler-host:1234",
            }],
        }

    def get_metrics(self):
        return {
            "checkedAt": "2026-10-31T08:30:00Z",
            "totalOffers": 1896,
            "totalObservations": 1896,
            "totalCanonicalProducts": 1372,
            "totalProductMatches": 3722,
            "totalPendingReview": 3400,
            "totalPopulatedStores": 7,
            "totalStaleStores": 7,
            "totalQuarantinedRuns": 1,
            "recentRuns": [{
                "runId": 42,
                "runKey": "m6-zito-empty",
                "sourceSlug": "zito",
                "status": "quarantined",
                "startedAt": "2026-10-29T08:35:00Z",
                "finishedAt": "2026-10-29T08:35:05Z",
                "pagesSeen": 1,
                "rowsSeen": 0,
                "rowsStored": 0,
                "rowsSkipped": 0,
                "quarantined": True,
                "quarantineReason": "pages with header but zero product rows",
                "workerId": "scheduler-host:1234",
                "durationSeconds": 5.0,
            }],
            "reviewQueue": {
                "totalPending": 3400,
                "totalApproved": 0,
                "totalRejected": 0,
                "totalAutoAccepted": 322,
                "oldestPendingDays": 2,
            },
        }
