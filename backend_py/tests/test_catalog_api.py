"""Port of CatalogApiTest.java (6 tests) at the HTTP layer via TestClient."""

from decimal import Decimal

from fastapi.testclient import TestClient

from app.main import create_app
from app.services.catalog_search_service import CatalogSearchService
from app.services.opensearch_client import OpenSearchClient
from tests.conftest import FakePostgresRepository, install_os_mock_counts


def _service(pg, open_search_url):
    return CatalogSearchService(OpenSearchClient(open_search_url), pg)


def _routes(mock_open_search):
    url, routes, calls = mock_open_search
    install_os_mock_counts(routes)
    return url


def test_open_search_primary_for_health_offers_and_comparison(mock_open_search):
    url = _routes(mock_open_search)
    pg = FakePostgresRepository()
    client = TestClient(create_app(catalog_service=_service(pg, url), basket_service=None))

    health = client.get("/api/v1/health").json()
    assert health["status"] == "UP"
    assert health["opensearchStatus"] == "UP"
    assert health["activeSearchEngine"] == "opensearch"
    assert health["counts"]["opensearch_offers"] == 1896

    offers = client.get(
        "/api/v1/offers/search?q=Ð¼Ð»ÐµÐºÐ¾&retailer=vero&inStockOnly=true&sort=price_asc&page=0&size=20"
    ).json()
    assert offers["sourceEngine"] == "opensearch"
    assert offers["total"] == 1
    assert Decimal(str(offers["items"][0]["priceCurrent"])) == Decimal("75.00")
    assert offers["items"][0]["isPromo"] is True
    assert offers["items"][0]["sourceUrl"] == "https://pricelist.vero.com.mk/1_1.html"

    comparisons = client.get("/api/v1/products/compare?q=Ð¼Ð»ÐµÐºÐ¾&minRetailers=2&page=0&size=20").json()
    assert comparisons["sourceEngine"] == "opensearch"
    assert comparisons["total"] == 1
    cmp = comparisons["items"][0]
    assert cmp["retailerCount"] == 2
    assert Decimal(str(cmp["cheapestMkd"])) == Decimal("85.00")
    assert Decimal(str(cmp["highestMkd"])) == Decimal("99.00")
    assert Decimal(str(cmp["spreadMkd"])) == Decimal("14.00")
    assert len(cmp["offers"]) == 2


def test_fallback_to_postgres_when_open_search_unavailable():
    pg = FakePostgresRepository()
    # Closed port so every OpenSearch call fails.
    url = "http://127.0.0.1:1"
    client = TestClient(create_app(catalog_service=_service(pg, url), basket_service=None))

    health = client.get("/api/v1/health").json()
    assert health["status"] == "UP"
    assert health["opensearchStatus"] == "FALLBACK_POSTGRESQL"
    assert health["activeSearchEngine"] == "postgresql_fallback"

    stores = client.get("/api/v1/stores?retailer=vero").json()
    assert stores["sourceEngine"] == "postgresql_fallback"
    assert len(stores["items"]) == 1

    cmp = client.get("/api/v1/products/compare?q=Ð¼Ð»ÐµÐºÐ¾&minRetailers=2&page=0&size=20").json()
    assert cmp["sourceEngine"] == "postgresql_fallback"
    assert cmp["total"] == 1
    assert pg.compare_calls == [("Ð¼Ð»ÐµÐºÐ¾", 2, 0, 20, None)]


def test_product_history_and_review_queue_endpoints(mock_open_search):
    url = _routes(mock_open_search)
    pg = FakePostgresRepository()
    client = TestClient(create_app(catalog_service=_service(pg, url), basket_service=None))

    found = client.get("/api/v1/products/10/history")
    assert found.status_code == 200
    assert len(found.json()["observations"]) == 1
    assert Decimal(str(found.json()["observations"][0]["priceCurrent"])) == Decimal("85.00")

    missing = client.get("/api/v1/products/99999/history")
    assert missing.status_code == 404
    assert missing.content == b""

    queue = client.get("/api/v1/matches/review-queue?limit=10").json()
    assert len(queue) == 1
    assert queue[0]["reviewStatus"] == "pending_review"
    assert Decimal(str(queue[0]["confidence"])) == Decimal("0.67")


def test_freshness_endpoint_reports_stale_stores_and_quarantined_runs(mock_open_search):
    url = _routes(mock_open_search)
    pg = FakePostgresRepository()
    client = TestClient(create_app(catalog_service=_service(pg, url), basket_service=None))

    res = client.get("/api/v1/freshness?staleThresholdHours=48&quarantineWindowDays=7").json()
    assert res["status"] == "DEGRADED"
    assert res["staleThresholdHours"] == 48
    assert res["quarantineWindowDays"] == 7
    assert res["totalOffers"] == 1896
    assert res["totalStaleStores"] == 1
    assert res["totalQuarantinedRuns"] == 1
    assert res["retailers"][0]["retailerSlug"] == "vero"
    assert res["retailers"][0]["staleStores"][0]["externalKey"] == "89"
    assert res["quarantinedRuns"][0]["runKey"] == "m6-zito-empty"


def test_review_queue_approve_and_reject_endpoints(mock_open_search):
    url = _routes(mock_open_search)
    pg = FakePostgresRepository()
    client = TestClient(create_app(catalog_service=_service(pg, url), basket_service=None))

    approved = client.post(
        "/api/v1/matches/review-queue/7/approve",
        json={"reviewedBy": "operator@example.com", "reviewNotes": "Confirmed same product"},
    ).json()
    assert approved["reviewStatus"] == "approved"
    assert approved["matchId"] == 7
    assert approved["reviewedBy"] == "operator@example.com"
    assert approved["reviewNotes"] == "Confirmed same product"
    assert pg.approve_calls == [(7, "operator@example.com", "Confirmed same product")]

    rejected = client.post(
        "/api/v1/matches/review-queue/7/reject",
        json={"reviewedBy": "operator@example.com", "reviewNotes": "Different pack size"},
    ).json()
    assert rejected["reviewStatus"] == "rejected"
    assert rejected["matchId"] == 7
    assert pg.reject_calls == [(7, "operator@example.com", "Different pack size")]


def test_metrics_endpoint_reports_runs_and_review_queue(mock_open_search):
    url = _routes(mock_open_search)
    pg = FakePostgresRepository()
    client = TestClient(create_app(catalog_service=_service(pg, url), basket_service=None))

    res = client.get("/api/v1/metrics").json()
    assert res["totalOffers"] == 1896
    assert res["totalCanonicalProducts"] == 1372
    assert res["totalObservations"] == 1896
    assert res["totalPopulatedStores"] == 7
    assert res["totalStaleStores"] == 7
    assert res["totalQuarantinedRuns"] == 1
    assert res["totalPendingReview"] == 3400
    assert len(res["recentRuns"]) == 1
    assert res["recentRuns"][0]["runKey"] == "m6-zito-empty"
    assert res["recentRuns"][0]["status"] == "quarantined"
    assert res["recentRuns"][0]["quarantined"] is True
    assert res["reviewQueue"]["totalPending"] == 3400
    assert res["reviewQueue"]["totalAutoAccepted"] == 322
    assert res["reviewQueue"]["oldestPendingDays"] == 2


def test_compare_by_canonical_id_backward_compatible(mock_open_search):
    # OpenSearch path: canonicalId becomes an extra term filter, q stays optional.
    url = _routes(mock_open_search)
    pg = FakePostgresRepository()
    client = TestClient(create_app(catalog_service=_service(pg, url), basket_service=None))

    res = client.get("/api/v1/products/compare?canonicalId=10&minRetailers=2&page=0&size=20").json()
    assert res["sourceEngine"] == "opensearch"
    assert res["total"] == 1
    assert res["items"][0]["canonicalProductId"] == 10

    # PostgreSQL fallback path: the filter is forwarded to the repository.
    pg2 = FakePostgresRepository()
    client2 = TestClient(create_app(catalog_service=_service(pg2, "http://127.0.0.1:1"), basket_service=None))
    res2 = client2.get("/api/v1/products/compare?canonicalId=10").json()
    assert res2["sourceEngine"] == "postgresql_fallback"
    assert res2["total"] == 1
    assert pg2.compare_calls == [(None, 2, 0, 20, 10)]

    # Omitting the parameter keeps the original behavior (backward compatible).
    pg3 = FakePostgresRepository()
    client3 = TestClient(create_app(catalog_service=_service(pg3, "http://127.0.0.1:1"), basket_service=None))
    client3.get("/api/v1/products/compare?minRetailers=3")
    assert pg3.compare_calls == [(None, 3, 0, 20, None)]
