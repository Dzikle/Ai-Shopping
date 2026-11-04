package mk.aishopping;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.datatype.jsr310.JavaTimeModule;
import com.sun.net.httpserver.HttpServer;
import mk.aishopping.controller.CatalogController;
import mk.aishopping.model.ApiModels.FreshnessResponse;
import mk.aishopping.model.ApiModels.HealthResponse;
import mk.aishopping.model.ApiModels.OfferDto;
import mk.aishopping.model.ApiModels.PriceObservationDto;
import mk.aishopping.model.ApiModels.ProductComparisonDto;
import mk.aishopping.model.ApiModels.ProductHistoryResponse;
import mk.aishopping.model.ApiModels.QuarantinedRunDto;
import mk.aishopping.model.ApiModels.RetailerFreshnessDto;
import mk.aishopping.model.ApiModels.RetailerOfferSummaryDto;
import mk.aishopping.model.ApiModels.ReviewQueueDecisionDto;
import mk.aishopping.model.ApiModels.ReviewQueueItemDto;
import mk.aishopping.model.ApiModels.SearchResponse;
import mk.aishopping.model.ApiModels.StoreDto;
import mk.aishopping.model.ApiModels.StoreFreshnessDto;
import mk.aishopping.repository.PostgresCatalogRepository;
import mk.aishopping.service.CatalogSearchService;
import mk.aishopping.service.OpenSearchClient;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.http.ResponseEntity;

import java.io.OutputStream;
import java.math.BigDecimal;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.util.List;
import java.util.Map;
import java.util.Optional;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyInt;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class CatalogApiTest {

    private ObjectMapper objectMapper;
    private HttpServer mockOpenSearch;
    private String openSearchUrl;
    private PostgresCatalogRepository postgresRepository;

    @BeforeEach
    void setUp() throws Exception {
        objectMapper = new ObjectMapper();
        objectMapper.registerModule(new JavaTimeModule());
        postgresRepository = mock(PostgresCatalogRepository.class);

        mockOpenSearch = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        int port = mockOpenSearch.getAddress().getPort();
        openSearchUrl = "http://127.0.0.1:" + port;

        mockOpenSearch.createContext("/stores/_count", exchange -> respondJson(exchange, 200, "{\"count\":192}"));
        mockOpenSearch.createContext("/offers/_count", exchange -> respondJson(exchange, 200, "{\"count\":1896}"));
        mockOpenSearch.createContext("/products/_count", exchange -> respondJson(exchange, 200, "{\"count\":1372}"));

        mockOpenSearch.createContext("/offers/_search", exchange -> {
            String body = """
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
                    """;
            respondJson(exchange, 200, body);
        });

        mockOpenSearch.createContext("/products/_search", exchange -> {
            String body = """
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
                    """;
            respondJson(exchange, 200, body);
        });

        mockOpenSearch.start();
    }

    @AfterEach
    void tearDown() {
        if (mockOpenSearch != null) {
            mockOpenSearch.stop(0);
        }
    }

    @Test
    void testOpenSearchPrimaryForHealthOffersAndComparison() {
        when(postgresRepository.isDatabaseHealthy()).thenReturn(true);
        when(postgresRepository.getTableCounts()).thenReturn(Map.of(
                "stores", 192L,
                "offers_current", 1896L,
                "canonical_products", 1372L
        ));

        OpenSearchClient osClient = new OpenSearchClient(objectMapper, openSearchUrl);
        CatalogSearchService service = new CatalogSearchService(osClient, postgresRepository);
        CatalogController controller = new CatalogController(service);

        HealthResponse health = controller.health();
        assertEquals("UP", health.status());
        assertEquals("UP", health.opensearchStatus());
        assertEquals("opensearch", health.activeSearchEngine());
        assertEquals(1896L, health.counts().get("opensearch_offers"));

        SearchResponse<OfferDto> offers = controller.searchOffers(
                "млеко", "vero", null, null, true, false, null, null, "price_asc", 0, 20
        );
        assertEquals("opensearch", offers.sourceEngine());
        assertEquals(1L, offers.total());
        assertEquals(new BigDecimal("75.00"), offers.items().get(0).priceCurrent());
        assertTrue(offers.items().get(0).isPromo());
        assertEquals("https://pricelist.vero.com.mk/1_1.html", offers.items().get(0).sourceUrl());

        SearchResponse<ProductComparisonDto> comparisons = controller.compareProducts("млеко", 2, 0, 20);
        assertEquals("opensearch", comparisons.sourceEngine());
        assertEquals(1L, comparisons.total());
        ProductComparisonDto cmp = comparisons.items().get(0);
        assertEquals(2, cmp.retailerCount());
        assertEquals(new BigDecimal("85.00"), cmp.cheapestMkd());
        assertEquals(new BigDecimal("99.00"), cmp.highestMkd());
        assertEquals(new BigDecimal("14.00"), cmp.spreadMkd());
        assertEquals(2, cmp.offers().size());
    }

    @Test
    void testFallbackToPostgresWhenOpenSearchUnavailable() {
        when(postgresRepository.isDatabaseHealthy()).thenReturn(true);
        when(postgresRepository.getTableCounts()).thenReturn(Map.of("offers_current", 1896L));

        StoreDto storeDto = new StoreDto(1, "vero", "Vero", "vero-1", "Веро 1", "Скопје", "Скопје", 162, Instant.parse("2026-04-17T10:00:00Z"));
        when(postgresRepository.findStores(any(), any())).thenReturn(
                new SearchResponse<>("postgresql_fallback", 1L, 0, 1, List.of(storeDto))
        );

        ProductComparisonDto fallbackCmp = new ProductComparisonDto(
                10,
                "1000.000:ml:1::БИМИЛК МЛЕКО",
                "БИО МЛЕКО БИМИЛК 1Л",
                "1x1000ml",
                2,
                6,
                new BigDecimal("85.00"),
                new BigDecimal("99.00"),
                new BigDecimal("14.00"),
                Instant.parse("2026-04-17T10:00:00Z"),
                List.of(new RetailerOfferSummaryDto(
                        "zito", 201, "БИО МЛЕКО БИМИЛК 1Л",
                        new BigDecimal("85.00"), new BigDecimal("85.00"), 3,
                        Instant.parse("2026-04-17T10:00:00Z"), "https://zito.proverkanaceni.mk/2_1.html"
                ))
        );
        when(postgresRepository.compareProducts(anyString(), anyInt(), anyInt(), anyInt())).thenReturn(
                new SearchResponse<>("postgresql_fallback", 1L, 0, 20, List.of(fallbackCmp))
        );

        // Point OpenSearchClient to an closed port so OpenSearch is unreachable
        OpenSearchClient unreachableOs = new OpenSearchClient(objectMapper, "http://127.0.0.1:1");
        CatalogSearchService service = new CatalogSearchService(unreachableOs, postgresRepository);
        CatalogController controller = new CatalogController(service);

        HealthResponse health = controller.health();
        assertEquals("UP", health.status());
        assertEquals("FALLBACK_POSTGRESQL", health.opensearchStatus());
        assertEquals("postgresql_fallback", health.activeSearchEngine());

        SearchResponse<StoreDto> stores = controller.stores("vero", null);
        assertEquals("postgresql_fallback", stores.sourceEngine());
        assertEquals(1, stores.items().size());

        SearchResponse<ProductComparisonDto> cmp = controller.compareProducts("млеко", 2, 0, 20);
        assertEquals("postgresql_fallback", cmp.sourceEngine());
        assertEquals(1L, cmp.total());
        verify(postgresRepository).compareProducts("млеко", 2, 0, 20);
    }

    @Test
    void testProductHistoryAndReviewQueueEndpoints() {
        PriceObservationDto obs = new PriceObservationDto(
                500L, "zito", "zito-2", "Жито 2", "БИО МЛЕКО БИМИЛК 1Л",
                new BigDecimal("85.00"), null, null, null, null, "in_stock",
                Instant.parse("2026-04-17T10:00:00Z"), Instant.parse("2026-04-17T12:00:00Z"),
                "https://zito.proverkanaceni.mk/2_1.html"
        );
        when(postgresRepository.getProductHistory(10)).thenReturn(Optional.of(
                new ProductHistoryResponse(10, "БИО МЛЕКО БИМИЛК 1Л", "1x1000ml", List.of(obs))
        ));
        when(postgresRepository.getProductHistory(99999)).thenReturn(Optional.empty());

        ReviewQueueItemDto queueItem = new ReviewQueueItemDto(
                77L, "stokomak", 301, "ЈОГУРТ БИМИЛК 1Л", 22, "БИТОЛСКИ ЈОГУРТ БИМИЛК 1Л",
                "1x1000ml", new BigDecimal("0.67"), "pending_review", Map.of("shared_tokens", List.of("БИМИЛК", "ЈОГУРТ"))
        );
        when(postgresRepository.getReviewQueue(10)).thenReturn(List.of(queueItem));

        OpenSearchClient osClient = new OpenSearchClient(objectMapper, openSearchUrl);
        CatalogSearchService service = new CatalogSearchService(osClient, postgresRepository);
        CatalogController controller = new CatalogController(service);

        ResponseEntity<ProductHistoryResponse> found = controller.productHistory(10);
        assertEquals(200, found.getStatusCode().value());
        assertNotNull(found.getBody());
        assertEquals(1, found.getBody().observations().size());
        assertEquals(new BigDecimal("85.00"), found.getBody().observations().get(0).priceCurrent());

        ResponseEntity<ProductHistoryResponse> missing = controller.productHistory(99999);
        assertEquals(404, missing.getStatusCode().value());

        List<ReviewQueueItemDto> queue = controller.reviewQueue(10);
        assertEquals(1, queue.size());
        assertEquals("pending_review", queue.get(0).reviewStatus());
        assertEquals(new BigDecimal("0.67"), queue.get(0).confidence());
    }

    @Test
    void testFreshnessEndpointReportsStaleStoresAndQuarantinedRuns() {
        StoreFreshnessDto staleStore = new StoreFreshnessDto(
                89, "89", "ВЕРО 1", "Аеродром", 1000,
                Instant.parse("2026-10-28T07:02:00Z"),
                Instant.parse("2026-10-28T10:00:00Z"),
                new BigDecimal("72.50")
        );
        RetailerFreshnessDto veroFreshness = new RetailerFreshnessDto(
                "vero", "Vero", 17, 1, 1000L,
                Instant.parse("2026-10-28T07:02:00Z"),
                Instant.parse("2026-10-28T07:02:00Z"),
                Instant.parse("2026-10-28T10:00:00Z"),
                1, List.of(staleStore), 0,
                "m6-vero-1", Instant.parse("2026-10-28T10:01:00Z")
        );
        QuarantinedRunDto quarantinedZito = new QuarantinedRunDto(
                42, "m6-zito-empty", "zito", "quarantined",
                Instant.parse("2026-10-29T08:35:00Z"),
                Instant.parse("2026-10-29T08:35:05Z"),
                1, 0, "pages with header but zero product rows: https://zito.proverkanaceni.mk/?org=1&perPage=2000&page=1",
                "scheduler-host:1234"
        );
        FreshnessResponse mockResponse = new FreshnessResponse(
                "DEGRADED",
                Instant.parse("2026-10-31T08:30:00Z"),
                48,
                7,
                1896L,
                7,
                1,
                1,
                List.of(veroFreshness),
                List.of(quarantinedZito)
        );

        when(postgresRepository.getFreshness(null, 48, 7)).thenReturn(mockResponse);

        OpenSearchClient osClient = new OpenSearchClient(objectMapper, openSearchUrl);
        CatalogSearchService service = new CatalogSearchService(osClient, postgresRepository);
        CatalogController controller = new CatalogController(service);

        FreshnessResponse res = controller.freshness(null, 48, 7);
        assertEquals("DEGRADED", res.status());
        assertEquals(48, res.staleThresholdHours());
        assertEquals(7, res.quarantineWindowDays());
        assertEquals(1896L, res.totalOffers());
        assertEquals(1, res.totalStaleStores());
        assertEquals(1, res.totalQuarantinedRuns());
        assertEquals("vero", res.retailers().get(0).retailerSlug());
        assertEquals("89", res.retailers().get(0).staleStores().get(0).externalKey());
        assertEquals("m6-zito-empty", res.quarantinedRuns().get(0).runKey());
    }

    @Test
    void testReviewQueueApproveAndRejectEndpoints() {
        long matchId = 7L;
        ReviewQueueDecisionDto approved = new ReviewQueueDecisionDto(matchId, "approved", "operator@example.com", "Confirmed same product");
        ReviewQueueDecisionDto rejected = new ReviewQueueDecisionDto(matchId, "rejected", "operator@example.com", "Different pack size");

        when(postgresRepository.approveMatch(matchId, "operator@example.com", "Confirmed same product"))
                .thenReturn(approved);
        when(postgresRepository.rejectMatch(matchId, "operator@example.com", "Different pack size"))
                .thenReturn(rejected);

        OpenSearchClient osClient = new OpenSearchClient(objectMapper, openSearchUrl);
        CatalogSearchService service = new CatalogSearchService(osClient, postgresRepository);
        CatalogController controller = new CatalogController(service);

        // Approve
        CatalogController.ReviewQueueActionRequest approveReq =
                new CatalogController.ReviewQueueActionRequest("operator@example.com", "Confirmed same product");
        ReviewQueueDecisionDto approveRes = controller.approveMatch(matchId, approveReq);
        assertEquals("approved", approveRes.reviewStatus());
        assertEquals(matchId, approveRes.matchId());
        assertEquals("operator@example.com", approveRes.reviewedBy());
        assertEquals("Confirmed same product", approveRes.reviewNotes());
        verify(postgresRepository).approveMatch(matchId, "operator@example.com", "Confirmed same product");

        // Reject
        CatalogController.ReviewQueueActionRequest rejectReq =
                new CatalogController.ReviewQueueActionRequest("operator@example.com", "Different pack size");
        ReviewQueueDecisionDto rejectRes = controller.rejectMatch(matchId, rejectReq);
        assertEquals("rejected", rejectRes.reviewStatus());
        assertEquals(matchId, rejectRes.matchId());
        assertEquals("operator@example.com", rejectRes.reviewedBy());
        assertEquals("Different pack size", rejectRes.reviewNotes());
        verify(postgresRepository).rejectMatch(matchId, "operator@example.com", "Different pack size");
    }

    private static void respondJson(com.sun.net.httpserver.HttpExchange exchange, int status, String json) throws java.io.IOException {
        byte[] bytes = json.getBytes(StandardCharsets.UTF_8);
        exchange.getResponseHeaders().set("Content-Type", "application/json; charset=utf-8");
        exchange.sendResponseHeaders(status, bytes.length);
        try (OutputStream os = exchange.getResponseBody()) {
            os.write(bytes);
        }
    }
}
