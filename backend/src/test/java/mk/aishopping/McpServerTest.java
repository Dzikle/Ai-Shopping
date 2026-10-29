package mk.aishopping;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.datatype.jsr310.JavaTimeModule;
import mk.aishopping.mcp.McpController;
import mk.aishopping.mcp.McpProtocolModels.McpRequest;
import mk.aishopping.mcp.McpProtocolModels.McpResponse;
import mk.aishopping.mcp.McpProtocolModels.McpToolCallResult;
import mk.aishopping.mcp.McpToolRegistry;
import mk.aishopping.model.ApiModels.OfferDto;
import mk.aishopping.model.ApiModels.ProductComparisonDto;
import mk.aishopping.model.ApiModels.ProductHistoryResponse;
import mk.aishopping.model.ApiModels.ReviewQueueItemDto;
import mk.aishopping.model.ApiModels.SearchResponse;
import mk.aishopping.model.ApiModels.StoreDto;
import mk.aishopping.model.BasketModels.BasketOptimizationResponse;
import mk.aishopping.model.BasketModels.MultiStorePlanDto;
import mk.aishopping.model.BasketModels.PricedBasketLineDto;
import mk.aishopping.model.BasketModels.SingleStoreBasketResultDto;
import mk.aishopping.service.BasketOptimizerService;
import mk.aishopping.service.CatalogSearchService;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.http.ResponseEntity;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;
import java.util.Map;
import java.util.Optional;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyInt;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class McpServerTest {

    private CatalogSearchService catalogService;
    private BasketOptimizerService basketService;
    private ObjectMapper objectMapper;
    private McpToolRegistry toolRegistry;
    private McpController mcpController;

    @BeforeEach
    void setUp() {
        catalogService = mock(CatalogSearchService.class);
        basketService = mock(BasketOptimizerService.class);
        objectMapper = new ObjectMapper();
        objectMapper.registerModule(new JavaTimeModule());

        toolRegistry = new McpToolRegistry(catalogService, basketService, objectMapper);
        mcpController = new McpController(toolRegistry);
    }

    @Test
    void testInitializeAndToolsList() throws Exception {
        McpRequest initReq = new McpRequest("2.0", 1, "initialize", Map.of(
                "protocolVersion", "2024-11-05",
                "clientInfo", Map.of("name", "test-client", "version", "1.0")
        ));
        ResponseEntity<?> initRespEntity = mcpController.handleJsonRpc(initReq);
        assertEquals(200, initRespEntity.getStatusCode().value());
        McpResponse initResp = (McpResponse) initRespEntity.getBody();
        assertNotNull(initResp);
        assertEquals(1, initResp.id());

        JsonNode initResult = objectMapper.valueToTree(initResp.result());
        assertEquals("2024-11-05", initResult.path("protocolVersion").asText());
        assertEquals("ai-shopping-mcp-server", initResult.path("serverInfo").path("name").asText());

        // Notifications/initialized returns 204 No Content
        McpRequest notifReq = new McpRequest("2.0", null, "notifications/initialized", Map.of());
        ResponseEntity<?> notifResp = mcpController.handleJsonRpc(notifReq);
        assertEquals(204, notifResp.getStatusCode().value());

        // tools/list returns all 7 tools
        McpRequest listReq = new McpRequest("2.0", 2, "tools/list", Map.of());
        ResponseEntity<?> listRespEntity = mcpController.handleJsonRpc(listReq);
        McpResponse listResp = (McpResponse) listRespEntity.getBody();
        assertNotNull(listResp);
        JsonNode listNode = objectMapper.valueToTree(listResp.result());
        JsonNode tools = listNode.path("tools");
        assertEquals(7, tools.size());

        List<String> toolNames = List.of(
                "search_products",
                "compare_product_prices",
                "get_price_history",
                "list_stores",
                "find_current_discounts",
                "optimize_shopping_basket",
                "suggest_product_substitutes"
        );
        for (String expectedName : toolNames) {
            boolean found = false;
            for (JsonNode t : tools) {
                if (expectedName.equals(t.path("name").asText())) {
                    found = true;
                    assertNotNull(t.path("description").asText());
                    assertTrue(t.path("inputSchema").has("properties"));
                    break;
                }
            }
            assertTrue(found, "Expected tool " + expectedName + " in tools/list");
        }
    }

    @Test
    void testSearchProductsToolCall() throws Exception {
        OfferDto sampleOffer = new OfferDto(
                "1:101", 1, "vero-1", "Веро Тафталиџе", "Скопје", "vero", "Vero", 101, "sku101",
                "МЛЕКО БИМИЛК 3.2% 1Л", "Млечни производи", 10, "1000.000:ml:1::БИМИЛК", "МЛЕКО БИМИЛК",
                "1x1000ml", "MKD", new BigDecimal("75.00"), new BigDecimal("75.00"), "1л",
                null, null, null, null, null, null, false, "in_stock",
                Instant.parse("2026-10-28T08:00:00Z"), Instant.parse("2026-10-28T09:00:00Z"),
                "https://pricelist.vero.com.mk/1_1.html", 1
        );
        when(catalogService.searchOffers(any())).thenReturn(
                new SearchResponse<>("opensearch", 1L, 0, 10, List.of(sampleOffer))
        );

        McpRequest callReq = new McpRequest("2.0", 3, "tools/call", Map.of(
                "name", "search_products",
                "arguments", Map.of("query", "млеко", "size", 10)
        ));
        ResponseEntity<?> respEntity = mcpController.handleJsonRpc(callReq);
        McpResponse resp = (McpResponse) respEntity.getBody();
        assertNotNull(resp);
        McpToolCallResult callResult = (McpToolCallResult) resp.result();
        assertFalse(callResult.isError());

        String jsonText = callResult.content().get(0).text();
        JsonNode resultJson = objectMapper.readTree(jsonText);
        assertEquals(1, resultJson.path("totalMatches").asInt());
        assertEquals("МЛЕКО БИМИЛК 3.2% 1Л", resultJson.path("items").get(0).path("listingName").asText());
        assertEquals("https://pricelist.vero.com.mk/1_1.html", resultJson.path("items").get(0).path("sourceUrl").asText());
        assertTrue(resultJson.has("dataFreshness"));
    }

    @Test
    void testOptimizeShoppingBasketToolCall() throws Exception {
        PricedBasketLineDto line = new PricedBasketLineDto(
                0, 101, null, "Кадаиф", new BigDecimal("800"), "g",
                1, "vero-1", "Веро Тафталиџе", "vero", 1001, "КАДАИФ 400ГР", "400g",
                2, new BigDecimal("180.00"), new BigDecimal("360.00"),
                false, null, new BigDecimal("1.00"),
                Instant.parse("2026-10-28T08:00:00Z"), Instant.parse("2026-10-28T09:00:00Z"),
                "https://pricelist.vero.com.mk/1_1.html"
        );
        SingleStoreBasketResultDto singleStore = new SingleStoreBasketResultDto(
                1, "vero", "Vero", "vero-1", "Веро Тафталиџе", "Скопје",
                1, 1, BigDecimal.ONE, new BigDecimal("360.00"), BigDecimal.ZERO,
                1, 0, List.of(line), List.of()
        );
        BasketOptimizationResponse optResp = new BasketOptimizationResponse(
                1, false, true, 2, BigDecimal.ZERO,
                singleStore, List.of(singleStore), null
        );
        when(basketService.optimizeBasket(any())).thenReturn(optResp);

        McpRequest callReq = new McpRequest("2.0", 4, "tools/call", Map.of(
                "name", "optimize_shopping_basket",
                "arguments", Map.of(
                        "items", List.of(Map.of("canonicalProductId", 101, "quantity", 800, "unit", "g")),
                        "maxStores", 2
                )
        ));
        ResponseEntity<?> respEntity = mcpController.handleJsonRpc(callReq);
        McpResponse resp = (McpResponse) respEntity.getBody();
        assertNotNull(resp);
        McpToolCallResult callResult = (McpToolCallResult) resp.result();
        assertFalse(callResult.isError());

        JsonNode resultJson = objectMapper.readTree(callResult.content().get(0).text());
        assertEquals(1, resultJson.path("totalItemsRequested").asInt());
        assertEquals(0, new BigDecimal("360.00").compareTo(new BigDecimal(resultJson.path("bestSingleStore").path("totalMkd").asText())));
        assertEquals(2, resultJson.path("bestSingleStore").path("coveredItems").get(0).path("packsNeeded").asInt());
        assertEquals("https://pricelist.vero.com.mk/1_1.html", resultJson.path("bestSingleStore").path("coveredItems").get(0).path("sourceUrl").asText());
    }

    @Test
    void testUnknownMethodAndToolErrors() throws Exception {
        McpRequest unknownMethod = new McpRequest("2.0", 5, "unknown/method", Map.of());
        ResponseEntity<?> respEntity = mcpController.handleJsonRpc(unknownMethod);
        McpResponse resp = (McpResponse) respEntity.getBody();
        assertNotNull(resp);
        assertNotNull(resp.error());
        assertEquals(-32601, resp.error().code());

        McpRequest unknownTool = new McpRequest("2.0", 6, "tools/call", Map.of("name", "non_existent_tool"));
        ResponseEntity<?> toolRespEntity = mcpController.handleJsonRpc(unknownTool);
        McpResponse toolResp = (McpResponse) toolRespEntity.getBody();
        assertNotNull(toolResp);
        McpToolCallResult result = (McpToolCallResult) toolResp.result();
        assertTrue(result.isError());
        assertTrue(result.content().get(0).text().contains("Unknown tool"));
    }

    @Test
    void testGetServerInfoEndpoint() {
        Map<String, Object> info = mcpController.serverInfo();
        assertEquals("ai-shopping-mcp-server", info.get("server"));
        assertEquals("2024-11-05", info.get("protocolVersion"));
        assertEquals("/mcp", info.get("endpoint"));
    }
}
