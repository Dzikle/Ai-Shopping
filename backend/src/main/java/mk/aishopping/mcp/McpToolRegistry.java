package mk.aishopping.mcp;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import mk.aishopping.mcp.McpProtocolModels.McpContentBlock;
import mk.aishopping.mcp.McpProtocolModels.McpToolCallResult;
import mk.aishopping.mcp.McpProtocolModels.McpToolDefinition;
import mk.aishopping.model.ApiModels.OfferDto;
import mk.aishopping.model.ApiModels.OfferSearchFilter;
import mk.aishopping.model.ApiModels.ProductComparisonDto;
import mk.aishopping.model.ApiModels.ProductHistoryResponse;
import mk.aishopping.model.ApiModels.ReviewQueueItemDto;
import mk.aishopping.model.ApiModels.SearchResponse;
import mk.aishopping.model.ApiModels.StoreDto;
import mk.aishopping.model.BasketModels.BasketItemRequest;
import mk.aishopping.model.BasketModels.BasketOptimizationResponse;
import mk.aishopping.model.BasketModels.BasketOptimizeRequest;
import mk.aishopping.service.BasketOptimizerService;
import mk.aishopping.service.CatalogSearchService;
import org.springframework.stereotype.Service;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;

@Service
public class McpToolRegistry {

    private final CatalogSearchService catalogService;
    private final BasketOptimizerService basketService;
    private final ObjectMapper objectMapper;

    public McpToolRegistry(
            CatalogSearchService catalogService,
            BasketOptimizerService basketService,
            ObjectMapper objectMapper
    ) {
        this.catalogService = catalogService;
        this.basketService = basketService;
        this.objectMapper = objectMapper;
    }

    public List<McpToolDefinition> listTools() {
        return List.of(
                new McpToolDefinition(
                        "search_products",
                        "Search current grocery offers by product name, brand, or category across stores and retailers with pricing and provenance.",
                        Map.of(
                                "type", "object",
                                "properties", Map.of(
                                        "query", Map.of("type", "string", "description", "Search query (e.g. 'млеко', 'брашно', 'чоколадо')"),
                                        "retailer", Map.of("type", "string", "description", "Filter by retailer slug ('vero', 'stokomak', 'zito')"),
                                        "city", Map.of("type", "string", "description", "Store city filter"),
                                        "inStockOnly", Map.of("type", "boolean", "description", "Filter in-stock offers only (default true)"),
                                        "promoOnly", Map.of("type", "boolean", "description", "Filter active discounts only (default false)"),
                                        "minPrice", Map.of("type", "number", "description", "Minimum price in MKD"),
                                        "maxPrice", Map.of("type", "number", "description", "Maximum price in MKD"),
                                        "size", Map.of("type", "integer", "description", "Results count limit (default 10, max 25)")
                                ),
                                "required", List.of("query")
                        )
                ),
                new McpToolDefinition(
                        "compare_product_prices",
                        "Compare prices for canonical products across multiple supermarket chains (Vero, Stokomak, Zito). Returns cheapest/highest prices, spread, and store offers.",
                        Map.of(
                                "type", "object",
                                "properties", Map.of(
                                        "query", Map.of("type", "string", "description", "Product name query (e.g. 'кадаиф', 'супа')"),
                                        "minRetailers", Map.of("type", "integer", "description", "Minimum distinct supermarket chains offering the product (default 2)"),
                                        "size", Map.of("type", "integer", "description", "Results count limit (default 10, max 25)")
                                )
                        )
                ),
                new McpToolDefinition(
                        "get_price_history",
                        "Retrieve the immutable price observation timeline and promotional changes for a canonical product across stores and retailers.",
                        Map.of(
                                "type", "object",
                                "properties", Map.of(
                                        "canonicalProductId", Map.of("type", "integer", "description", "Canonical product ID")
                                ),
                                "required", List.of("canonicalProductId")
                        )
                ),
                new McpToolDefinition(
                        "list_stores",
                        "List supermarket store branches with location, active offer counts, and catalog freshness.",
                        Map.of(
                                "type", "object",
                                "properties", Map.of(
                                        "retailer", Map.of("type", "string", "description", "Filter by retailer slug ('vero', 'stokomak', 'zito')"),
                                        "city", Map.of("type", "string", "description", "City filter")
                                )
                        )
                ),
                new McpToolDefinition(
                        "find_current_discounts",
                        "Find top active promotional discounts and sales across stores and retailers sorted by discount percentage.",
                        Map.of(
                                "type", "object",
                                "properties", Map.of(
                                        "retailer", Map.of("type", "string", "description", "Filter by retailer slug ('vero', 'stokomak', 'zito')"),
                                        "category", Map.of("type", "string", "description", "Category filter"),
                                        "size", Map.of("type", "integer", "description", "Results count limit (default 10, max 25)")
                                )
                        )
                ),
                new McpToolDefinition(
                        "optimize_shopping_basket",
                        "Deterministically calculate and optimize total basket cost across single stores and multi-store splits with pack scaling and unit conversion.",
                        Map.of(
                                "type", "object",
                                "properties", Map.of(
                                        "items", Map.of(
                                                "type", "array",
                                                "description", "List of basket items to purchase (max 20)",
                                                "items", Map.of(
                                                        "type", "object",
                                                        "properties", Map.of(
                                                                "canonicalProductId", Map.of("type", "integer", "description", "Canonical product ID"),
                                                                "retailerProductId", Map.of("type", "integer", "description", "Retailer-specific product ID"),
                                                                "quantity", Map.of("type", "number", "description", "Requested quantity (default 1)"),
                                                                "unit", Map.of("type", "string", "description", "Requested unit ('pack', 'pcs', 'g', 'kg', 'ml', 'l')"),
                                                                "itemLabel", Map.of("type", "string", "description", "Optional label or product name")
                                                        )
                                                )
                                        ),
                                        "city", Map.of("type", "string", "description", "Store city constraint"),
                                        "retailers", Map.of("type", "array", "items", Map.of("type", "string"), "description", "Retailer slug whitelist"),
                                        "maxStores", Map.of("type", "integer", "description", "Max stores to split across (default 2, min 1, max 3)"),
                                        "minSplitSavingsMkd", Map.of("type", "number", "description", "Minimum MKD savings required to recommend splitting stores"),
                                        "allowSubstitutes", Map.of("type", "boolean", "description", "Allow Stage-2 candidate substitutes (default false)"),
                                        "inStockOnly", Map.of("type", "boolean", "description", "Require in-stock items (default true)")
                                ),
                                "required", List.of("items")
                        )
                ),
                new McpToolDefinition(
                        "suggest_product_substitutes",
                        "Retrieve potential product substitutes from Stage-2 high-overlap candidate matches for products that may be out of stock or missing in certain stores.",
                        Map.of(
                                "type", "object",
                                "properties", Map.of(
                                        "canonicalProductId", Map.of("type", "integer", "description", "Canonical product ID to find substitutes for"),
                                        "limit", Map.of("type", "integer", "description", "Results count limit (default 10, max 25)")
                                )
                        )
                )
        );
    }

    public McpToolCallResult callTool(String name, Map<String, Object> arguments) {
        Map<String, Object> args = arguments != null ? arguments : Map.of();
        try {
            Object payload = switch (name) {
                case "search_products" -> handleSearchProducts(args);
                case "compare_product_prices" -> handleCompareProducts(args);
                case "get_price_history" -> handlePriceHistory(args);
                case "list_stores" -> handleListStores(args);
                case "find_current_discounts" -> handleCurrentDiscounts(args);
                case "optimize_shopping_basket" -> handleOptimizeBasket(args);
                case "suggest_product_substitutes" -> handleSuggestSubstitutes(args);
                default -> throw new IllegalArgumentException("Unknown tool: " + name);
            };

            String jsonText = objectMapper.writerWithDefaultPrettyPrinter().writeValueAsString(payload);
            return new McpToolCallResult(List.of(new McpContentBlock("text", jsonText)), false);
        } catch (Exception e) {
            String errJson = "{\"error\": \"" + escapeJson(e.getMessage() != null ? e.getMessage() : e.toString()) + "\"}";
            return new McpToolCallResult(List.of(new McpContentBlock("text", errJson)), true);
        }
    }

    private Object handleSearchProducts(Map<String, Object> args) {
        String query = asString(args.get("query"));
        if (query == null || query.isBlank()) {
            throw new IllegalArgumentException("'query' parameter is required for search_products");
        }
        String retailer = asString(args.get("retailer"));
        String city = asString(args.get("city"));
        boolean inStock = asBoolean(args.get("inStockOnly"), true);
        boolean promoOnly = asBoolean(args.get("promoOnly"), false);
        BigDecimal minPrice = asBigDecimal(args.get("minPrice"));
        BigDecimal maxPrice = asBigDecimal(args.get("maxPrice"));
        int size = boundInt(args.get("size"), 10, 1, 25);

        OfferSearchFilter filter = new OfferSearchFilter(
                query, retailer, null, null, inStock, promoOnly, minPrice, maxPrice, "price_asc", 0, size
        );
        SearchResponse<OfferDto> resp = catalogService.searchOffers(filter);

        List<Instant> timestamps = resp.items().stream()
                .map(OfferDto::publishedTs)
                .filter(java.util.Objects::nonNull)
                .toList();

        Map<String, Object> out = new LinkedHashMap<>();
        out.put("totalMatches", resp.total());
        out.put("sourceEngine", resp.sourceEngine());
        out.put("items", resp.items());
        out.put("dataFreshness", computeFreshness(timestamps));
        return out;
    }

    private Object handleCompareProducts(Map<String, Object> args) {
        String query = asString(args.get("query"));
        int minRetailers = boundInt(args.get("minRetailers"), 2, 1, 3);
        int size = boundInt(args.get("size"), 10, 1, 25);

        SearchResponse<ProductComparisonDto> resp = catalogService.compareProducts(query, minRetailers, 0, size);

        List<Instant> timestamps = resp.items().stream()
                .map(ProductComparisonDto::latestPublishedTs)
                .filter(java.util.Objects::nonNull)
                .toList();

        Map<String, Object> out = new LinkedHashMap<>();
        out.put("totalComparisons", resp.total());
        out.put("sourceEngine", resp.sourceEngine());
        out.put("comparisons", resp.items());
        out.put("dataFreshness", computeFreshness(timestamps));
        return out;
    }

    private Object handlePriceHistory(Map<String, Object> args) {
        Integer canonicalId = asInteger(args.get("canonicalProductId"));
        if (canonicalId == null) {
            throw new IllegalArgumentException("'canonicalProductId' parameter is required for get_price_history");
        }

        Optional<ProductHistoryResponse> histOpt = catalogService.getProductHistory(canonicalId);
        if (histOpt.isEmpty()) {
            return Map.of("error", "Canonical product not found: " + canonicalId);
        }
        ProductHistoryResponse hist = histOpt.get();

        List<Instant> timestamps = hist.observations().stream()
                .map(mk.aishopping.model.ApiModels.PriceObservationDto::publishedTs)
                .filter(java.util.Objects::nonNull)
                .toList();

        Map<String, Object> out = new LinkedHashMap<>();
        out.put("canonicalProductId", hist.canonicalProductId());
        out.put("canonicalName", hist.canonicalName());
        out.put("normalizedSize", hist.normalizedSize());
        out.put("totalObservations", hist.observations().size());
        out.put("observations", hist.observations());
        out.put("dataFreshness", computeFreshness(timestamps));
        return out;
    }

    private Object handleListStores(Map<String, Object> args) {
        String retailer = asString(args.get("retailer"));
        String city = asString(args.get("city"));

        SearchResponse<StoreDto> resp = catalogService.getStores(retailer, city);

        List<Instant> timestamps = resp.items().stream()
                .map(StoreDto::latestPublishedTs)
                .filter(java.util.Objects::nonNull)
                .toList();

        Map<String, Object> out = new LinkedHashMap<>();
        out.put("totalStores", resp.total());
        out.put("stores", resp.items());
        out.put("dataFreshness", computeFreshness(timestamps));
        return out;
    }

    private Object handleCurrentDiscounts(Map<String, Object> args) {
        String retailer = asString(args.get("retailer"));
        String category = asString(args.get("category"));
        int size = boundInt(args.get("size"), 10, 1, 25);

        OfferSearchFilter filter = new OfferSearchFilter(
                null, retailer, null, category, true, true, null, null, "price_asc", 0, size
        );
        SearchResponse<OfferDto> resp = catalogService.searchOffers(filter);

        List<Instant> timestamps = resp.items().stream()
                .map(OfferDto::publishedTs)
                .filter(java.util.Objects::nonNull)
                .toList();

        Map<String, Object> out = new LinkedHashMap<>();
        out.put("totalDiscounts", resp.total());
        out.put("discounts", resp.items());
        out.put("dataFreshness", computeFreshness(timestamps));
        return out;
    }

    @SuppressWarnings("unchecked")
    private Object handleOptimizeBasket(Map<String, Object> args) {
        Object rawItems = args.get("items");
        if (!(rawItems instanceof List<?> rawList) || rawList.isEmpty()) {
            throw new IllegalArgumentException("'items' parameter must be a non-empty list of basket items");
        }
        if (rawList.size() > 20) {
            throw new IllegalArgumentException("Basket size cannot exceed 20 items per request");
        }

        List<BasketItemRequest> items = new ArrayList<>();
        for (Object o : rawList) {
            if (o instanceof Map<?, ?> m) {
                Integer canonId = asInteger(m.get("canonicalProductId"));
                Integer retId = asInteger(m.get("retailerProductId"));
                BigDecimal qty = asBigDecimal(m.get("quantity"));
                String unit = asString(m.get("unit"));
                String label = asString(m.get("itemLabel"));
                items.add(new BasketItemRequest(canonId, retId, label, qty != null ? qty : BigDecimal.ONE, unit != null ? unit : "pack"));
            }
        }

        String city = asString(args.get("city"));
        List<String> retailers = null;
        if (args.get("retailers") instanceof List<?> rList) {
            retailers = rList.stream().map(Object::toString).toList();
        }
        int maxStores = boundInt(args.get("maxStores"), 2, 1, 3);
        BigDecimal minSavings = asBigDecimal(args.get("minSplitSavingsMkd"));
        boolean allowSubstitutes = asBoolean(args.get("allowSubstitutes"), false);
        boolean inStockOnly = asBoolean(args.get("inStockOnly"), true);

        BasketOptimizeRequest req = new BasketOptimizeRequest(
                items, city, retailers, maxStores, minSavings, allowSubstitutes, inStockOnly
        );
        BasketOptimizationResponse optResp = basketService.optimizeBasket(req);

        List<Instant> timestamps = new ArrayList<>();
        if (optResp.bestSingleStore() != null) {
            optResp.bestSingleStore().coveredItems().forEach(line -> {
                if (line.publishedTs() != null) timestamps.add(line.publishedTs());
            });
        }

        Map<String, Object> out = new LinkedHashMap<>();
        out.put("totalItemsRequested", optResp.totalItemsRequested());
        out.put("allowSubstitutes", optResp.allowSubstitutes());
        out.put("inStockOnly", optResp.inStockOnly());
        out.put("bestSingleStore", optResp.bestSingleStore());
        out.put("bestMultiStorePlan", optResp.bestMultiStorePlan());
        out.put("allSingleStoreRankings", optResp.singleStoreRankings());
        out.put("dataFreshness", computeFreshness(timestamps));
        return out;
    }

    private Object handleSuggestSubstitutes(Map<String, Object> args) {
        Integer canonicalId = asInteger(args.get("canonicalProductId"));
        int limit = boundInt(args.get("limit"), 10, 1, 25);

        List<ReviewQueueItemDto> queue = catalogService.getReviewQueue(limit);
        if (canonicalId != null) {
            queue = queue.stream()
                    .filter(item -> item.candidateCanonicalId() == canonicalId)
                    .toList();
        }

        Map<String, Object> out = new LinkedHashMap<>();
        out.put("note", "Substitutes are Stage-2 high-overlap unverified candidates per ADR-0003.");
        out.put("substitutesCount", queue.size());
        out.put("candidates", queue);
        return out;
    }

    private static Map<String, Object> computeFreshness(List<Instant> timestamps) {
        if (timestamps == null || timestamps.isEmpty()) {
            return Map.of("status", "no_timestamps_available");
        }
        Instant min = timestamps.stream().min(Instant::compareTo).orElse(null);
        Instant max = timestamps.stream().max(Instant::compareTo).orElse(null);
        Map<String, Object> f = new LinkedHashMap<>();
        f.put("oldestOfferPublishedTs", min != null ? min.toString() : null);
        f.put("latestOfferPublishedTs", max != null ? max.toString() : null);
        f.put("sampleCount", timestamps.size());
        return f;
    }

    private static String asString(Object o) {
        return o != null ? o.toString().trim() : null;
    }

    private static Integer asInteger(Object o) {
        if (o instanceof Number n) {
            return n.intValue();
        }
        if (o instanceof String s && !s.isBlank()) {
            try { return Integer.parseInt(s.trim()); } catch (NumberFormatException ignored) {}
        }
        return null;
    }

    private static BigDecimal asBigDecimal(Object o) {
        if (o instanceof Number n) {
            return BigDecimal.valueOf(n.doubleValue());
        }
        if (o instanceof String s && !s.isBlank()) {
            try { return new BigDecimal(s.trim()); } catch (Exception ignored) {}
        }
        return null;
    }

    private static boolean asBoolean(Object o, boolean defaultVal) {
        if (o instanceof Boolean b) {
            return b;
        }
        if (o instanceof String s && !s.isBlank()) {
            return Boolean.parseBoolean(s.trim());
        }
        return defaultVal;
    }

    private static int boundInt(Object o, int defaultVal, int min, int max) {
        Integer val = asInteger(o);
        if (val == null) {
            return defaultVal;
        }
        return Math.max(min, Math.min(max, val));
    }

    private static String escapeJson(String s) {
        return s.replace("\"", "\\\"").replace("\n", " ");
    }
}
