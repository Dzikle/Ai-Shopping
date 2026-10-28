package mk.aishopping.service;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import mk.aishopping.model.ApiModels.OfferDto;
import mk.aishopping.model.ApiModels.OfferSearchFilter;
import mk.aishopping.model.ApiModels.ProductComparisonDto;
import mk.aishopping.model.ApiModels.RetailerOfferSummaryDto;
import mk.aishopping.model.ApiModels.SearchResponse;
import mk.aishopping.model.ApiModels.StoreDto;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

import java.math.BigDecimal;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.time.Instant;
import java.time.LocalDate;
import java.time.OffsetDateTime;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

@Component
public class OpenSearchClient {

    private final HttpClient httpClient;
    private final ObjectMapper objectMapper;
    private volatile String baseUrl;

    public OpenSearchClient(
            ObjectMapper objectMapper,
            @Value("${aishopping.opensearch.url:http://localhost:9200}") String baseUrl
    ) {
        this.objectMapper = objectMapper;
        this.baseUrl = trimSlash(baseUrl);
        this.httpClient = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(3))
                .build();
    }

    public void setBaseUrl(String baseUrl) {
        this.baseUrl = trimSlash(baseUrl);
    }

    public String getBaseUrl() {
        return baseUrl;
    }

    private static String trimSlash(String url) {
        if (url == null) {
            return "http://localhost:9200";
        }
        return url.endsWith("/") ? url.substring(0, url.length() - 1) : url;
    }

    public boolean isHealthyAndPopulated() {
        try {
            long offersCount = countIndex("offers");
            return offersCount >= 0;
        } catch (Exception e) {
            return false;
        }
    }

    public long countIndex(String indexOrAlias) throws Exception {
        HttpRequest req = HttpRequest.newBuilder()
                .uri(URI.create(baseUrl + "/" + indexOrAlias + "/_count"))
                .timeout(Duration.ofSeconds(3))
                .GET()
                .build();
        HttpResponse<String> resp = httpClient.send(req, HttpResponse.BodyHandlers.ofString());
        if (resp.statusCode() != 200) {
            throw new IllegalStateException("OpenSearch count returned HTTP " + resp.statusCode());
        }
        JsonNode root = objectMapper.readTree(resp.body());
        return root.path("count").asLong(-1);
    }

    public SearchResponse<StoreDto> searchStores(String retailer, String city) throws Exception {
        List<Map<String, Object>> filters = new ArrayList<>();
        if (retailer != null && !retailer.isBlank()) {
            filters.add(Map.of("term", Map.of("retailer_slug", retailer.trim().toLowerCase())));
        }
        if (city != null && !city.isBlank()) {
            filters.add(Map.of("term", Map.of("city", city.trim())));
        }
        Map<String, Object> query = filters.isEmpty()
                ? Map.of("match_all", Map.of())
                : Map.of("bool", Map.of("filter", filters));
        Map<String, Object> body = Map.of(
                "from", 0,
                "size", 500,
                "query", query,
                "sort", List.of(Map.of("store_id", Map.of("order", "asc")))
        );
        JsonNode root = postSearch("stores", body);
        long total = root.path("hits").path("total").path("value").asLong(0);
        List<StoreDto> items = new ArrayList<>();
        for (JsonNode hit : root.path("hits").path("hits")) {
            JsonNode src = hit.path("_source");
            items.add(new StoreDto(
                    src.path("store_id").asInt(),
                    textOrNull(src, "retailer_slug"),
                    textOrNull(src, "retailer_name"),
                    textOrNull(src, "external_key"),
                    textOrNull(src, "name"),
                    textOrNull(src, "address"),
                    textOrNull(src, "city"),
                    src.path("active_offers_count").asInt(0),
                    instantOrNull(src, "latest_published_ts")
            ));
        }
        return new SearchResponse<>("opensearch", total, 0, items.size(), items);
    }

    public SearchResponse<OfferDto> searchOffers(OfferSearchFilter f) throws Exception {
        List<Map<String, Object>> must = new ArrayList<>();
        List<Map<String, Object>> filter = new ArrayList<>();

        if (f.q() != null && !f.q().isBlank()) {
            must.add(Map.of("multi_match", Map.of(
                    "query", f.q().trim(),
                    "fields", List.of("listing_name^2", "canonical_name^2", "category")
            )));
        }
        if (f.retailer() != null && !f.retailer().isBlank()) {
            filter.add(Map.of("term", Map.of("retailer_slug", f.retailer().trim().toLowerCase())));
        }
        if (f.storeKey() != null && !f.storeKey().isBlank()) {
            filter.add(Map.of("term", Map.of("store_external_key", f.storeKey().trim())));
        }
        if (f.category() != null && !f.category().isBlank()) {
            filter.add(Map.of("term", Map.of("category", f.category().trim())));
        }
        if (f.inStockOnly()) {
            filter.add(Map.of("term", Map.of("availability", "in_stock")));
        }
        if (f.promoOnly()) {
            filter.add(Map.of("term", Map.of("is_promo", true)));
        }
        if (f.minPrice() != null || f.maxPrice() != null) {
            Map<String, Object> range = new LinkedHashMap<>();
            if (f.minPrice() != null) {
                range.put("gte", f.minPrice());
            }
            if (f.maxPrice() != null) {
                range.put("lte", f.maxPrice());
            }
            filter.add(Map.of("range", Map.of("price_current", range)));
        }

        Map<String, Object> bool = new LinkedHashMap<>();
        if (!must.isEmpty()) {
            bool.put("must", must);
        }
        if (!filter.isEmpty()) {
            bool.put("filter", filter);
        }
        Map<String, Object> query = bool.isEmpty()
                ? Map.of("match_all", Map.of())
                : Map.of("bool", bool);

        String sortOrder = "desc".equalsIgnoreCase(f.sort()) || "price_desc".equalsIgnoreCase(f.sort())
                ? "desc" : "asc";
        List<Map<String, Object>> sort = List.of(
                Map.of("price_current", Map.of("order", sortOrder)),
                Map.of("offer_id", Map.of("order", "asc"))
        );

        int from = Math.max(0, f.page()) * Math.max(1, f.size());
        Map<String, Object> body = Map.of(
                "from", from,
                "size", Math.max(1, f.size()),
                "query", query,
                "sort", sort
        );

        JsonNode root = postSearch("offers", body);
        long total = root.path("hits").path("total").path("value").asLong(0);
        List<OfferDto> items = new ArrayList<>();
        for (JsonNode hit : root.path("hits").path("hits")) {
            items.add(parseOfferDoc(hit.path("_source")));
        }
        return new SearchResponse<>("opensearch", total, f.page(), f.size(), items);
    }

    public SearchResponse<ProductComparisonDto> searchProductComparisons(String q, int minRetailers, int page, int size) throws Exception {
        List<Map<String, Object>> must = new ArrayList<>();
        List<Map<String, Object>> filter = new ArrayList<>();

        if (q != null && !q.isBlank()) {
            must.add(Map.of("multi_match", Map.of(
                    "query", q.trim(),
                    "fields", List.of("canonical_name^2", "normalized_tokens")
            )));
        }
        filter.add(Map.of("range", Map.of("retailer_count", Map.of("gte", Math.max(1, minRetailers)))));

        Map<String, Object> bool = new LinkedHashMap<>();
        if (!must.isEmpty()) {
            bool.put("must", must);
        }
        bool.put("filter", filter);

        int from = Math.max(0, page) * Math.max(1, size);
        Map<String, Object> body = Map.of(
                "from", from,
                "size", Math.max(1, size),
                "query", Map.of("bool", bool),
                "sort", List.of(Map.of("canonical_name.keyword", Map.of("order", "asc")))
        );

        JsonNode root = postSearch("products", body);
        long total = root.path("hits").path("total").path("value").asLong(0);
        List<ProductComparisonDto> items = new ArrayList<>();
        for (JsonNode hit : root.path("hits").path("hits")) {
            JsonNode src = hit.path("_source");
            List<RetailerOfferSummaryDto> offers = new ArrayList<>();
            for (JsonNode o : src.path("offers")) {
                offers.add(new RetailerOfferSummaryDto(
                        textOrNull(o, "retailer_slug"),
                        o.path("retailer_product_id").asInt(),
                        textOrNull(o, "listing_name"),
                        decimalOrNull(o, "min_price"),
                        decimalOrNull(o, "max_price"),
                        o.path("store_count").asInt(0),
                        instantOrNull(o, "latest_published_ts"),
                        textOrNull(o, "source_url")
                ));
            }
            items.add(new ProductComparisonDto(
                    src.path("canonical_product_id").asInt(),
                    textOrNull(src, "canonical_key"),
                    textOrNull(src, "canonical_name"),
                    textOrNull(src, "normalized_size"),
                    src.path("retailer_count").asInt(0),
                    src.path("store_count").asInt(0),
                    decimalOrNull(src, "min_price"),
                    decimalOrNull(src, "max_price"),
                    decimalOrNull(src, "spread_mkd"),
                    instantOrNull(src, "latest_published_ts"),
                    offers
            ));
        }
        return new SearchResponse<>("opensearch", total, page, size, items);
    }

    private JsonNode postSearch(String indexOrAlias, Map<String, Object> body) throws Exception {
        String payload = objectMapper.writeValueAsString(body);
        HttpRequest req = HttpRequest.newBuilder()
                .uri(URI.create(baseUrl + "/" + indexOrAlias + "/_search"))
                .timeout(Duration.ofSeconds(5))
                .header("Content-Type", "application/json")
                .POST(HttpRequest.BodyPublishers.ofString(payload))
                .build();
        HttpResponse<String> resp = httpClient.send(req, HttpResponse.BodyHandlers.ofString());
        if (resp.statusCode() != 200) {
            throw new IllegalStateException("OpenSearch _search returned HTTP " + resp.statusCode() + ": " + resp.body());
        }
        return objectMapper.readTree(resp.body());
    }

    private static OfferDto parseOfferDoc(JsonNode src) {
        Integer canonicalId = src.hasNonNull("canonical_product_id") ? src.get("canonical_product_id").asInt() : null;
        return new OfferDto(
                textOrNull(src, "offer_id"),
                src.path("store_id").asInt(),
                textOrNull(src, "store_external_key"),
                textOrNull(src, "store_name"),
                textOrNull(src, "city"),
                textOrNull(src, "retailer_slug"),
                textOrNull(src, "retailer_name"),
                src.path("retailer_product_id").asInt(),
                textOrNull(src, "sku_key"),
                textOrNull(src, "listing_name"),
                textOrNull(src, "category"),
                canonicalId,
                textOrNull(src, "canonical_key"),
                textOrNull(src, "canonical_name"),
                textOrNull(src, "normalized_size"),
                textOrNull(src, "currency"),
                decimalOrNull(src, "price_current"),
                decimalOrNull(src, "unit_price"),
                textOrNull(src, "unit_label"),
                decimalOrNull(src, "regular_price"),
                decimalOrNull(src, "discount_price"),
                decimalOrNull(src, "discount_pct"),
                textOrNull(src, "promo_type"),
                dateOrNull(src, "promo_starts_on"),
                dateOrNull(src, "promo_ends_on"),
                src.path("is_promo").asBoolean(false),
                textOrNull(src, "availability"),
                instantOrNull(src, "published_ts"),
                instantOrNull(src, "fetched_ts"),
                textOrNull(src, "source_url"),
                src.path("run_id").asInt()
        );
    }

    private static String textOrNull(JsonNode node, String field) {
        return node.hasNonNull(field) ? node.get(field).asText() : null;
    }

    private static BigDecimal decimalOrNull(JsonNode node, String field) {
        if (!node.hasNonNull(field)) {
            return null;
        }
        return new BigDecimal(node.get(field).asText()).setScale(2, java.math.RoundingMode.HALF_UP);
    }

    private static LocalDate dateOrNull(JsonNode node, String field) {
        if (!node.hasNonNull(field)) {
            return null;
        }
        String raw = node.get(field).asText();
        return raw.isBlank() ? null : LocalDate.parse(raw.substring(0, 10));
    }

    private static Instant instantOrNull(JsonNode node, String field) {
        if (!node.hasNonNull(field)) {
            return null;
        }
        String raw = node.get(field).asText();
        if (raw.isBlank()) {
            return null;
        }
        return OffsetDateTime.parse(raw).toInstant();
    }
}
