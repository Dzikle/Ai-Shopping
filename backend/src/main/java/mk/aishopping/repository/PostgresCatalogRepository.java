package mk.aishopping.repository;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import mk.aishopping.model.ApiModels.OfferDto;
import mk.aishopping.model.ApiModels.OfferSearchFilter;
import mk.aishopping.model.ApiModels.PriceObservationDto;
import mk.aishopping.model.ApiModels.ProductComparisonDto;
import mk.aishopping.model.ApiModels.ProductHistoryResponse;
import mk.aishopping.model.ApiModels.RetailerOfferSummaryDto;
import mk.aishopping.model.ApiModels.ReviewQueueItemDto;
import mk.aishopping.model.ApiModels.SearchResponse;
import mk.aishopping.model.ApiModels.StoreDto;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.sql.Date;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Timestamp;
import java.time.Instant;
import java.time.LocalDate;
import java.time.OffsetDateTime;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;

@Repository
public class PostgresCatalogRepository {

    private final JdbcTemplate jdbcTemplate;
    private final ObjectMapper objectMapper;

    public PostgresCatalogRepository(JdbcTemplate jdbcTemplate, ObjectMapper objectMapper) {
        this.jdbcTemplate = jdbcTemplate;
        this.objectMapper = objectMapper;
    }

    public boolean isDatabaseHealthy() {
        try {
            Integer one = jdbcTemplate.queryForObject("SELECT 1", Integer.class);
            return one != null && one == 1;
        } catch (Exception e) {
            return false;
        }
    }

    public Map<String, Long> getTableCounts() {
        Map<String, Long> counts = new LinkedHashMap<>();
        counts.put("stores", countTable("stores"));
        counts.put("retailer_products", countTable("retailer_products"));
        counts.put("offers_current", countTable("offers_current"));
        counts.put("price_observations", countTable("price_observations"));
        counts.put("canonical_products", countTable("canonical_products"));
        counts.put("product_matches", countTable("product_matches"));
        return counts;
    }

    private long countTable(String table) {
        Long count = jdbcTemplate.queryForObject("SELECT COUNT(*) FROM " + table, Long.class);
        return count != null ? count : 0L;
    }

    public SearchResponse<StoreDto> findStores(String retailer, String city) {
        StringBuilder where = new StringBuilder(" WHERE 1=1 ");
        List<Object> params = new ArrayList<>();
        if (retailer != null && !retailer.isBlank()) {
            where.append(" AND LOWER(r.slug) = ? ");
            params.add(retailer.trim().toLowerCase());
        }
        if (city != null && !city.isBlank()) {
            where.append(" AND LOWER(s.city) = ? ");
            params.add(city.trim().toLowerCase());
        }

        String sql = """
                SELECT s.id AS store_id,
                       r.slug AS retailer_slug,
                       r.name AS retailer_name,
                       s.external_key,
                       s.name,
                       s.address,
                       s.city,
                       COUNT(oc.retailer_product_id)::int AS active_offers_count,
                       MAX(oc.published_ts) AS latest_published_ts
                FROM stores s
                JOIN retailers r ON r.id = s.retailer_id
                LEFT JOIN offers_current oc ON oc.store_id = s.id
                """ + where + """
                GROUP BY s.id, r.slug, r.name, s.external_key, s.name, s.address, s.city
                ORDER BY s.id ASC
                """;

        List<StoreDto> items = jdbcTemplate.query(sql, (rs, rowNum) -> new StoreDto(
                rs.getInt("store_id"),
                rs.getString("retailer_slug"),
                rs.getString("retailer_name"),
                rs.getString("external_key"),
                rs.getString("name"),
                rs.getString("address"),
                rs.getString("city"),
                rs.getInt("active_offers_count"),
                toInstant(rs.getTimestamp("latest_published_ts"))
        ), params.toArray());

        return new SearchResponse<>("postgresql_fallback", items.size(), 0, items.size(), items);
    }

    public SearchResponse<OfferDto> searchOffers(OfferSearchFilter f) {
        StringBuilder where = new StringBuilder(" WHERE 1=1 ");
        List<Object> params = new ArrayList<>();

        if (f.q() != null && !f.q().isBlank()) {
            String pattern = "%" + f.q().trim() + "%";
            where.append(" AND (rp.listing_name ILIKE ? OR COALESCE(cp.canonical_name, '') ILIKE ? OR COALESCE(rp.category, '') ILIKE ?) ");
            params.add(pattern);
            params.add(pattern);
            params.add(pattern);
        }
        if (f.retailer() != null && !f.retailer().isBlank()) {
            where.append(" AND LOWER(r.slug) = ? ");
            params.add(f.retailer().trim().toLowerCase());
        }
        if (f.storeKey() != null && !f.storeKey().isBlank()) {
            where.append(" AND s.external_key = ? ");
            params.add(f.storeKey().trim());
        }
        if (f.category() != null && !f.category().isBlank()) {
            where.append(" AND rp.category = ? ");
            params.add(f.category().trim());
        }
        if (f.inStockOnly()) {
            where.append(" AND oc.availability = 'in_stock' ");
        }
        if (f.promoOnly()) {
            where.append(" AND oc.promo_type IS NOT NULL AND oc.promo_type <> '' ");
        }
        if (f.minPrice() != null) {
            where.append(" AND oc.price_current >= ? ");
            params.add(f.minPrice());
        }
        if (f.maxPrice() != null) {
            where.append(" AND oc.price_current <= ? ");
            params.add(f.maxPrice());
        }

        String fromJoins = """
                FROM offers_current oc
                JOIN stores s ON s.id = oc.store_id
                JOIN retailers r ON r.id = s.retailer_id
                JOIN retailer_products rp ON rp.id = oc.retailer_product_id
                LEFT JOIN product_matches pm
                  ON pm.retailer_product_id = rp.id
                 AND pm.review_status IN ('auto_accepted', 'approved')
                LEFT JOIN canonical_products cp ON cp.id = pm.canonical_product_id
                """;

        Long totalObj = jdbcTemplate.queryForObject(
                "SELECT COUNT(*) " + fromJoins + where,
                Long.class,
                params.toArray()
        );
        long total = totalObj != null ? totalObj : 0L;

        String sortDir = ("desc".equalsIgnoreCase(f.sort()) || "price_desc".equalsIgnoreCase(f.sort()))
                ? "DESC" : "ASC";
        int safeSize = Math.max(1, f.size());
        int safePage = Math.max(0, f.page());
        int offset = safePage * safeSize;

        List<Object> pageParams = new ArrayList<>(params);
        pageParams.add(safeSize);
        pageParams.add(offset);

        String selectSql = """
                SELECT (oc.store_id::text || ':' || oc.retailer_product_id::text) AS offer_id,
                       oc.store_id,
                       s.external_key AS store_external_key,
                       s.name AS store_name,
                       s.city,
                       r.slug AS retailer_slug,
                       r.name AS retailer_name,
                       oc.retailer_product_id,
                       rp.sku_key,
                       rp.listing_name,
                       rp.category,
                       cp.id AS canonical_product_id,
                       cp.canonical_key,
                       cp.canonical_name,
                       cp.normalized_size,
                       trim(oc.currency) AS currency,
                       oc.price_current,
                       oc.unit_price,
                       oc.unit_label,
                       oc.regular_price,
                       oc.discount_price,
                       oc.discount_pct,
                       oc.promo_type,
                       oc.promo_starts_on,
                       oc.promo_ends_on,
                       (oc.promo_type IS NOT NULL AND oc.promo_type <> '') AS is_promo,
                       oc.availability,
                       oc.published_ts,
                       oc.fetched_ts,
                       oc.source_url,
                       oc.run_id
                """ + fromJoins + where +
                " ORDER BY oc.price_current " + sortDir + ", oc.store_id ASC, oc.retailer_product_id ASC LIMIT ? OFFSET ?";

        List<OfferDto> items = jdbcTemplate.query(selectSql, (rs, rowNum) -> mapOfferRow(rs), pageParams.toArray());
        return new SearchResponse<>("postgresql_fallback", total, safePage, safeSize, items);
    }

    public SearchResponse<ProductComparisonDto> compareProducts(String q, int minRetailers, int page, int size) {
        StringBuilder filterClause = new StringBuilder(" WHERE retailer_count >= ? ");
        List<Object> params = new ArrayList<>();
        params.add(Math.max(1, minRetailers));

        if (q != null && !q.isBlank()) {
            String pattern = "%" + q.trim() + "%";
            filterClause.append(" AND (canonical_name ILIKE ? OR normalized_tokens ILIKE ?) ");
            params.add(pattern);
            params.add(pattern);
        }

        String cte = """
                WITH per_retailer AS (
                    SELECT cp.id AS canonical_product_id,
                           r.slug AS retailer_slug,
                           rp.id AS retailer_product_id,
                           rp.listing_name,
                           MIN(oc.price_current) AS min_price,
                           MAX(oc.price_current) AS max_price,
                           COUNT(DISTINCT oc.store_id)::int AS store_count,
                           MAX(oc.published_ts) AS latest_published_ts,
                           MIN(oc.source_url) AS source_url
                    FROM canonical_products cp
                    JOIN product_matches pm
                      ON pm.canonical_product_id = cp.id
                     AND pm.review_status IN ('auto_accepted', 'approved')
                    JOIN retailer_products rp ON rp.id = pm.retailer_product_id
                    JOIN retailers r ON r.id = rp.retailer_id
                    JOIN offers_current oc ON oc.retailer_product_id = rp.id
                    GROUP BY cp.id, r.slug, rp.id, rp.listing_name
                ),
                aggregated AS (
                    SELECT cp.id AS canonical_product_id,
                           cp.canonical_key,
                           cp.canonical_name,
                           cp.normalized_tokens,
                           cp.normalized_size,
                           COUNT(DISTINCT pr.retailer_slug)::int AS retailer_count,
                           COALESCE(SUM(pr.store_count), 0)::int AS store_count,
                           MIN(pr.min_price) AS min_price,
                           MAX(pr.max_price) AS max_price,
                           (MAX(pr.max_price) - MIN(pr.min_price)) AS spread_mkd,
                           MAX(pr.latest_published_ts) AS latest_published_ts,
                           COALESCE(
                               JSON_AGG(
                                   JSON_BUILD_OBJECT(
                                       'retailer_slug', pr.retailer_slug,
                                       'retailer_product_id', pr.retailer_product_id,
                                       'listing_name', pr.listing_name,
                                       'min_price', pr.min_price,
                                       'max_price', pr.max_price,
                                       'store_count', pr.store_count,
                                       'latest_published_ts', pr.latest_published_ts,
                                       'source_url', pr.source_url
                                   )
                                   ORDER BY pr.min_price, pr.retailer_slug
                               ) FILTER (WHERE pr.retailer_slug IS NOT NULL),
                               '[]'::json
                           )::text AS offers_json
                    FROM canonical_products cp
                    LEFT JOIN per_retailer pr ON pr.canonical_product_id = cp.id
                    GROUP BY cp.id, cp.canonical_key, cp.canonical_name, cp.normalized_tokens, cp.normalized_size
                )
                """;

        Long totalObj = jdbcTemplate.queryForObject(
                cte + " SELECT COUNT(*) FROM aggregated " + filterClause,
                Long.class,
                params.toArray()
        );
        long total = totalObj != null ? totalObj : 0L;

        int safeSize = Math.max(1, size);
        int safePage = Math.max(0, page);
        int offset = safePage * safeSize;

        List<Object> pageParams = new ArrayList<>(params);
        pageParams.add(safeSize);
        pageParams.add(offset);

        String selectSql = cte + """
                SELECT canonical_product_id,
                       canonical_key,
                       canonical_name,
                       normalized_size,
                       retailer_count,
                       store_count,
                       min_price,
                       max_price,
                       spread_mkd,
                       latest_published_ts,
                       offers_json
                FROM aggregated
                """ + filterClause + " ORDER BY canonical_name ASC LIMIT ? OFFSET ?";

        List<ProductComparisonDto> items = jdbcTemplate.query(selectSql, (rs, rowNum) -> {
            List<RetailerOfferSummaryDto> offers = parseOffersJson(rs.getString("offers_json"));
            return new ProductComparisonDto(
                    rs.getInt("canonical_product_id"),
                    rs.getString("canonical_key"),
                    rs.getString("canonical_name"),
                    rs.getString("normalized_size"),
                    rs.getInt("retailer_count"),
                    rs.getInt("store_count"),
                    scale2(rs.getBigDecimal("min_price")),
                    scale2(rs.getBigDecimal("max_price")),
                    scale2(rs.getBigDecimal("spread_mkd")),
                    toInstant(rs.getTimestamp("latest_published_ts")),
                    offers
            );
        }, pageParams.toArray());

        return new SearchResponse<>("postgresql_fallback", total, safePage, safeSize, items);
    }

    public Optional<ProductHistoryResponse> getProductHistory(int canonicalProductId) {
        String productSql = """
                SELECT id, canonical_name, normalized_size
                FROM canonical_products
                WHERE id = ?
                """;
        List<Map<String, Object>> rows = jdbcTemplate.queryForList(productSql, canonicalProductId);
        if (rows.isEmpty()) {
            return Optional.empty();
        }
        Map<String, Object> header = rows.get(0);
        String canonicalName = (String) header.get("canonical_name");
        String normalizedSize = (String) header.get("normalized_size");

        String obsSql = """
                SELECT po.id AS observation_id,
                       r.slug AS retailer_slug,
                       s.external_key AS store_external_key,
                       s.name AS store_name,
                       rp.listing_name,
                       po.price_current,
                       po.regular_price,
                       po.discount_price,
                       po.discount_pct,
                       po.promo_type,
                       po.availability,
                       po.published_ts,
                       po.fetched_ts,
                       po.source_url
                FROM product_matches pm
                JOIN retailer_products rp ON rp.id = pm.retailer_product_id
                JOIN retailers r ON r.id = rp.retailer_id
                JOIN price_observations po ON po.retailer_product_id = rp.id
                JOIN stores s ON s.id = po.store_id
                WHERE pm.canonical_product_id = ?
                  AND pm.review_status IN ('auto_accepted', 'approved')
                ORDER BY po.published_ts DESC NULLS LAST, r.slug ASC, s.external_key ASC
                """;

        List<PriceObservationDto> observations = jdbcTemplate.query(obsSql, (rs, rowNum) -> new PriceObservationDto(
                rs.getLong("observation_id"),
                rs.getString("retailer_slug"),
                rs.getString("store_external_key"),
                rs.getString("store_name"),
                rs.getString("listing_name"),
                scale2(rs.getBigDecimal("price_current")),
                scale2(rs.getBigDecimal("regular_price")),
                scale2(rs.getBigDecimal("discount_price")),
                scale2(rs.getBigDecimal("discount_pct")),
                rs.getString("promo_type"),
                rs.getString("availability"),
                toInstant(rs.getTimestamp("published_ts")),
                toInstant(rs.getTimestamp("fetched_ts")),
                rs.getString("source_url")
        ), canonicalProductId);

        return Optional.of(new ProductHistoryResponse(
                canonicalProductId,
                canonicalName,
                normalizedSize,
                observations
        ));
    }

    public List<ReviewQueueItemDto> getReviewQueue(int limit) {
        int safeLimit = Math.max(1, Math.min(200, limit));
        String sql = """
                SELECT pm.id AS match_id,
                       r.slug AS source_retailer_slug,
                       rp.id AS retailer_product_id,
                       rp.listing_name AS source_listing_name,
                       cp.id AS candidate_canonical_id,
                       cp.canonical_name AS candidate_canonical_name,
                       cp.normalized_size,
                       pm.confidence,
                       pm.review_status,
                       pm.evidence::text AS evidence_json
                FROM product_matches pm
                JOIN retailer_products rp ON rp.id = pm.retailer_product_id
                JOIN retailers r ON r.id = rp.retailer_id
                JOIN canonical_products cp ON cp.id = pm.canonical_product_id
                WHERE pm.review_status = 'pending_review'
                ORDER BY pm.confidence DESC, rp.listing_name ASC
                LIMIT ?
                """;

        return jdbcTemplate.query(sql, (rs, rowNum) -> new ReviewQueueItemDto(
                rs.getLong("match_id"),
                rs.getString("source_retailer_slug"),
                rs.getInt("retailer_product_id"),
                rs.getString("source_listing_name"),
                rs.getInt("candidate_canonical_id"),
                rs.getString("candidate_canonical_name"),
                rs.getString("normalized_size"),
                scale2(rs.getBigDecimal("confidence")),
                rs.getString("review_status"),
                parseEvidence(rs.getString("evidence_json"))
        ), safeLimit);
    }

    private OfferDto mapOfferRow(ResultSet rs) throws SQLException {
        Integer canonicalId = rs.getObject("canonical_product_id") != null
                ? rs.getInt("canonical_product_id") : null;
        return new OfferDto(
                rs.getString("offer_id"),
                rs.getInt("store_id"),
                rs.getString("store_external_key"),
                rs.getString("store_name"),
                rs.getString("city"),
                rs.getString("retailer_slug"),
                rs.getString("retailer_name"),
                rs.getInt("retailer_product_id"),
                rs.getString("sku_key"),
                rs.getString("listing_name"),
                rs.getString("category"),
                canonicalId,
                rs.getString("canonical_key"),
                rs.getString("canonical_name"),
                rs.getString("normalized_size"),
                rs.getString("currency"),
                scale2(rs.getBigDecimal("price_current")),
                scale2(rs.getBigDecimal("unit_price")),
                rs.getString("unit_label"),
                scale2(rs.getBigDecimal("regular_price")),
                scale2(rs.getBigDecimal("discount_price")),
                scale2(rs.getBigDecimal("discount_pct")),
                rs.getString("promo_type"),
                toLocalDate(rs.getDate("promo_starts_on")),
                toLocalDate(rs.getDate("promo_ends_on")),
                rs.getBoolean("is_promo"),
                rs.getString("availability"),
                toInstant(rs.getTimestamp("published_ts")),
                toInstant(rs.getTimestamp("fetched_ts")),
                rs.getString("source_url"),
                rs.getInt("run_id")
        );
    }

    private List<RetailerOfferSummaryDto> parseOffersJson(String json) {
        if (json == null || json.isBlank()) {
            return List.of();
        }
        try {
            JsonNode arr = objectMapper.readTree(json);
            List<RetailerOfferSummaryDto> result = new ArrayList<>();
            for (JsonNode o : arr) {
                Instant ts = null;
                if (o.hasNonNull("latest_published_ts") && !o.get("latest_published_ts").asText().isBlank()) {
                    ts = OffsetDateTime.parse(o.get("latest_published_ts").asText()).toInstant();
                }
                result.add(new RetailerOfferSummaryDto(
                        o.path("retailer_slug").asText(null),
                        o.path("retailer_product_id").asInt(),
                        o.path("listing_name").asText(null),
                        o.hasNonNull("min_price") ? scale2(new BigDecimal(o.get("min_price").asText())) : null,
                        o.hasNonNull("max_price") ? scale2(new BigDecimal(o.get("max_price").asText())) : null,
                        o.path("store_count").asInt(0),
                        ts,
                        o.path("source_url").asText(null)
                ));
            }
            return result;
        } catch (Exception e) {
            return List.of();
        }
    }

    private Map<String, Object> parseEvidence(String json) {
        if (json == null || json.isBlank()) {
            return Map.of();
        }
        try {
            return objectMapper.readValue(json, new TypeReference<>() {});
        } catch (Exception e) {
            return Map.of();
        }
    }

    private static BigDecimal scale2(BigDecimal val) {
        return val != null ? val.setScale(2, RoundingMode.HALF_UP) : null;
    }

    private static Instant toInstant(Timestamp ts) {
        return ts != null ? ts.toInstant() : null;
    }

    private static LocalDate toLocalDate(Date d) {
        return d != null ? d.toLocalDate() : null;
    }
}
