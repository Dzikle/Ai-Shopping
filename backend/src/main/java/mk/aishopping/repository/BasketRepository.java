package mk.aishopping.repository;

import mk.aishopping.model.BasketModels.BasketItemRequest;
import mk.aishopping.model.BasketModels.CreateShoppingListRequest;
import mk.aishopping.model.BasketModels.ShoppingListDto;
import mk.aishopping.model.BasketModels.ShoppingListItemDto;
import mk.aishopping.service.UnitConversionUtil;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;
import org.springframework.transaction.annotation.Transactional;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Timestamp;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Optional;

@Repository
public class BasketRepository {

    public record StoreHeader(
            int storeId,
            String retailerSlug,
            String retailerName,
            String storeExternalKey,
            String storeName,
            String city
    ) {}

    public record ProductTargetMeta(
            Integer canonicalProductId,
            Integer retailerProductId,
            String displayName,
            String normalizedSize,
            BigDecimal quantityValue,
            String quantityUnit,
            int packCount
    ) {}

    public record CandidateStoreOffer(
            int storeId,
            String storeExternalKey,
            String storeName,
            String city,
            String retailerSlug,
            String retailerName,
            int retailerProductId,
            String listingName,
            String normalizedSize,
            BigDecimal skuQuantityValue,
            String skuQuantityUnit,
            int skuPackCount,
            BigDecimal priceCurrent,
            boolean isSubstitute,
            String substituteReason,
            BigDecimal confidence,
            Instant publishedTs,
            Instant fetchedTs,
            String sourceUrl
    ) {}

    private final JdbcTemplate jdbcTemplate;

    public BasketRepository(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    @Transactional
    public ShoppingListDto createShoppingList(CreateShoppingListRequest req) {
        if (req == null || req.name() == null || req.name().isBlank()) {
            throw new IllegalArgumentException("Shopping list name is required");
        }
        String cityFilter = (req.cityFilter() != null && !req.cityFilter().isBlank())
                ? req.cityFilter().trim() : null;

        Long listId = jdbcTemplate.queryForObject(
                "INSERT INTO shopping_lists (name, city_filter) VALUES (?, ?) RETURNING id",
                Long.class,
                req.name().trim(),
                cityFilter
        );
        if (listId == null) {
            throw new IllegalStateException("Failed to insert shopping_list");
        }

        List<BasketItemRequest> items = req.items() != null ? req.items() : List.of();
        for (int i = 0; i < items.size(); i++) {
            BasketItemRequest item = items.get(i);
            if (item.canonicalProductId() == null && item.retailerProductId() == null) {
                throw new IllegalArgumentException("Each basket item must specify canonicalProductId or retailerProductId");
            }
            BigDecimal qty = (item.quantity() == null || item.quantity().compareTo(BigDecimal.ZERO) <= 0)
                    ? BigDecimal.ONE
                    : item.quantity().setScale(3, RoundingMode.HALF_UP);
            String unit = UnitConversionUtil.normalizeUnit(item.unit());
            jdbcTemplate.update(
                    """
                    INSERT INTO shopping_list_items
                        (shopping_list_id, canonical_product_id, retailer_product_id, item_label, quantity, unit, position)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    listId,
                    item.canonicalProductId(),
                    item.retailerProductId(),
                    item.itemLabel(),
                    qty,
                    unit,
                    i
            );
        }

        return getShoppingList(listId)
                .orElseThrow(() -> new IllegalStateException("Created shopping list not found: " + listId));
    }

    public Optional<ShoppingListDto> getShoppingList(long listId) {
        List<Map<String, Object>> headerRows = jdbcTemplate.queryForList(
                "SELECT id, name, city_filter, created_at, updated_at FROM shopping_lists WHERE id = ?",
                listId
        );
        if (headerRows.isEmpty()) {
            return Optional.empty();
        }
        Map<String, Object> h = headerRows.get(0);

        String itemSql = """
                SELECT sli.id,
                       sli.canonical_product_id,
                       sli.retailer_product_id,
                       sli.item_label,
                       sli.quantity,
                       sli.unit,
                       sli.position,
                       COALESCE(cp.canonical_name, rp.listing_name, sli.item_label) AS resolved_name,
                       cp.normalized_size
                FROM shopping_list_items sli
                LEFT JOIN canonical_products cp ON cp.id = sli.canonical_product_id
                LEFT JOIN retailer_products rp ON rp.id = sli.retailer_product_id
                WHERE sli.shopping_list_id = ?
                ORDER BY sli.position ASC, sli.id ASC
                """;

        List<ShoppingListItemDto> items = jdbcTemplate.query(itemSql, (rs, rowNum) -> new ShoppingListItemDto(
                rs.getLong("id"),
                rs.getObject("canonical_product_id") != null ? rs.getInt("canonical_product_id") : null,
                rs.getObject("retailer_product_id") != null ? rs.getInt("retailer_product_id") : null,
                rs.getString("resolved_name"),
                rs.getString("normalized_size"),
                rs.getString("item_label"),
                rs.getBigDecimal("quantity").setScale(3, RoundingMode.HALF_UP),
                rs.getString("unit"),
                rs.getInt("position")
        ), listId);

        return Optional.of(new ShoppingListDto(
                ((Number) h.get("id")).longValue(),
                (String) h.get("name"),
                (String) h.get("city_filter"),
                toInstant((Timestamp) h.get("created_at")),
                toInstant((Timestamp) h.get("updated_at")),
                items
        ));
    }

    public List<StoreHeader> findActiveStores(String city, List<String> retailers) {
        StringBuilder where = new StringBuilder(" WHERE EXISTS (SELECT 1 FROM offers_current oc WHERE oc.store_id = s.id) ");
        List<Object> params = new ArrayList<>();

        if (city != null && !city.isBlank()) {
            where.append(" AND LOWER(s.city) = ? ");
            params.add(city.trim().toLowerCase());
        }
        if (retailers != null && !retailers.isEmpty()) {
            List<String> clean = retailers.stream()
                    .filter(r -> r != null && !r.isBlank())
                    .map(r -> r.trim().toLowerCase())
                    .toList();
            if (!clean.isEmpty()) {
                where.append(" AND LOWER(r.slug) IN (")
                        .append(String.join(",", clean.stream().map(x -> "?").toList()))
                        .append(") ");
                params.addAll(clean);
            }
        }

        String sql = """
                SELECT s.id AS store_id,
                       r.slug AS retailer_slug,
                       r.name AS retailer_name,
                       s.external_key AS store_external_key,
                       s.name AS store_name,
                       s.city
                FROM stores s
                JOIN retailers r ON r.id = s.retailer_id
                """ + where + " ORDER BY s.id ASC";

        return jdbcTemplate.query(sql, (rs, rowNum) -> new StoreHeader(
                rs.getInt("store_id"),
                rs.getString("retailer_slug"),
                rs.getString("retailer_name"),
                rs.getString("store_external_key"),
                rs.getString("store_name"),
                rs.getString("city")
        ), params.toArray());
    }

    public Optional<ProductTargetMeta> resolveProductTarget(Integer canonicalProductId, Integer retailerProductId, String fallbackLabel) {
        if (canonicalProductId != null) {
            String sql = """
                    SELECT id, canonical_name, normalized_size, quantity_value, quantity_unit, pack_count
                    FROM canonical_products
                    WHERE id = ?
                    """;
            List<ProductTargetMeta> list = jdbcTemplate.query(sql, (rs, rowNum) -> new ProductTargetMeta(
                    rs.getInt("id"),
                    retailerProductId,
                    rs.getString("canonical_name"),
                    rs.getString("normalized_size"),
                    rs.getBigDecimal("quantity_value"),
                    rs.getString("quantity_unit"),
                    rs.getInt("pack_count")
            ), canonicalProductId);
            if (!list.isEmpty()) {
                return Optional.of(list.get(0));
            }
        }

        if (retailerProductId != null) {
            String sql = """
                    SELECT rp.id AS retailer_product_id,
                           rp.listing_name,
                           cp.id AS canonical_product_id,
                           cp.normalized_size,
                           cp.quantity_value,
                           cp.quantity_unit,
                           COALESCE(cp.pack_count, 1) AS pack_count
                    FROM retailer_products rp
                    LEFT JOIN product_matches pm
                      ON pm.retailer_product_id = rp.id
                     AND pm.review_status IN ('auto_accepted', 'approved')
                    LEFT JOIN canonical_products cp ON cp.id = pm.canonical_product_id
                    WHERE rp.id = ?
                    """;
            List<ProductTargetMeta> list = jdbcTemplate.query(sql, (rs, rowNum) -> new ProductTargetMeta(
                    rs.getObject("canonical_product_id") != null ? rs.getInt("canonical_product_id") : null,
                    rs.getInt("retailer_product_id"),
                    rs.getString("listing_name"),
                    rs.getString("normalized_size"),
                    rs.getBigDecimal("quantity_value"),
                    rs.getString("quantity_unit"),
                    rs.getInt("pack_count")
            ), retailerProductId);
            if (!list.isEmpty()) {
                return Optional.of(list.get(0));
            }
        }

        return Optional.empty();
    }

    public List<CandidateStoreOffer> findCandidateOffers(
            Integer canonicalProductId,
            Integer retailerProductId,
            boolean allowSubstitutes,
            boolean inStockOnly,
            String city,
            List<String> retailers
    ) {
        StringBuilder filterWhere = new StringBuilder();
        List<Object> filterParams = new ArrayList<>();

        if (inStockOnly) {
            filterWhere.append(" AND oc.availability = 'in_stock' ");
        }
        if (city != null && !city.isBlank()) {
            filterWhere.append(" AND LOWER(s.city) = ? ");
            filterParams.add(city.trim().toLowerCase());
        }
        if (retailers != null && !retailers.isEmpty()) {
            List<String> clean = retailers.stream()
                    .filter(r -> r != null && !r.isBlank())
                    .map(r -> r.trim().toLowerCase())
                    .toList();
            if (!clean.isEmpty()) {
                filterWhere.append(" AND LOWER(r.slug) IN (")
                        .append(String.join(",", clean.stream().map(x -> "?").toList()))
                        .append(") ");
                filterParams.addAll(clean);
            }
        }

        if (canonicalProductId != null) {
            String statusClause = allowSubstitutes
                    ? "pm.review_status IN ('auto_accepted', 'approved', 'pending_review')"
                    : "pm.review_status IN ('auto_accepted', 'approved')";

            String sql = """
                    SELECT s.id AS store_id,
                           s.external_key AS store_external_key,
                           s.name AS store_name,
                           s.city,
                           r.slug AS retailer_slug,
                           r.name AS retailer_name,
                           rp.id AS retailer_product_id,
                           rp.listing_name,
                           cp.normalized_size,
                           cp.quantity_value,
                           cp.quantity_unit,
                           cp.pack_count,
                           oc.price_current,
                           (pm.review_status = 'pending_review') AS is_substitute,
                           CASE WHEN pm.review_status = 'pending_review'
                                THEN 'stage2_pending_review_candidate'
                                ELSE NULL
                           END AS substitute_reason,
                           pm.confidence,
                           oc.published_ts,
                           oc.fetched_ts,
                           oc.source_url
                    FROM product_matches pm
                    JOIN canonical_products cp ON cp.id = pm.canonical_product_id
                    JOIN retailer_products rp ON rp.id = pm.retailer_product_id
                    JOIN offers_current oc ON oc.retailer_product_id = rp.id
                    JOIN stores s ON s.id = oc.store_id
                    JOIN retailers r ON r.id = s.retailer_id
                    WHERE pm.canonical_product_id = ?
                    """ + " AND " + statusClause + " " + filterWhere + "\n" + """
                    ORDER BY is_substitute ASC, pm.confidence DESC, oc.price_current ASC, s.id ASC
                    """;

            List<Object> params = new ArrayList<>();
            params.add(canonicalProductId);
            params.addAll(filterParams);
            return jdbcTemplate.query(sql, (rs, rowNum) -> mapCandidateOffer(rs), params.toArray());
        }

        if (retailerProductId != null) {
            String sql = """
                    SELECT s.id AS store_id,
                           s.external_key AS store_external_key,
                           s.name AS store_name,
                           s.city,
                           r.slug AS retailer_slug,
                           r.name AS retailer_name,
                           rp.id AS retailer_product_id,
                           rp.listing_name,
                           cp.normalized_size,
                           cp.quantity_value,
                           cp.quantity_unit,
                           COALESCE(cp.pack_count, 1) AS pack_count,
                           oc.price_current,
                           false AS is_substitute,
                           NULL::text AS substitute_reason,
                           1.000::numeric AS confidence,
                           oc.published_ts,
                           oc.fetched_ts,
                           oc.source_url
                    FROM offers_current oc
                    JOIN retailer_products rp ON rp.id = oc.retailer_product_id
                    JOIN stores s ON s.id = oc.store_id
                    JOIN retailers r ON r.id = s.retailer_id
                    LEFT JOIN product_matches pm
                      ON pm.retailer_product_id = rp.id
                     AND pm.review_status IN ('auto_accepted', 'approved')
                    LEFT JOIN canonical_products cp ON cp.id = pm.canonical_product_id
                    WHERE oc.retailer_product_id = ?
                    """ + " " + filterWhere + "\n" + """
                    ORDER BY oc.price_current ASC, s.id ASC
                    """;
            List<Object> params = new ArrayList<>();
            params.add(retailerProductId);
            params.addAll(filterParams);
            return jdbcTemplate.query(sql, (rs, rowNum) -> mapCandidateOffer(rs), params.toArray());
        }

        return List.of();
    }

    private static CandidateStoreOffer mapCandidateOffer(ResultSet rs) throws SQLException {
        return new CandidateStoreOffer(
                rs.getInt("store_id"),
                rs.getString("store_external_key"),
                rs.getString("store_name"),
                rs.getString("city"),
                rs.getString("retailer_slug"),
                rs.getString("retailer_name"),
                rs.getInt("retailer_product_id"),
                rs.getString("listing_name"),
                rs.getString("normalized_size"),
                rs.getBigDecimal("quantity_value"),
                rs.getString("quantity_unit"),
                rs.getInt("pack_count"),
                rs.getBigDecimal("price_current").setScale(2, RoundingMode.HALF_UP),
                rs.getBoolean("is_substitute"),
                rs.getString("substitute_reason"),
                rs.getBigDecimal("confidence") != null
                        ? rs.getBigDecimal("confidence").setScale(2, RoundingMode.HALF_UP)
                        : new BigDecimal("1.00"),
                toInstant(rs.getTimestamp("published_ts")),
                toInstant(rs.getTimestamp("fetched_ts")),
                rs.getString("source_url")
        );
    }

    private static Instant toInstant(Timestamp ts) {
        return ts != null ? ts.toInstant() : null;
    }
}
