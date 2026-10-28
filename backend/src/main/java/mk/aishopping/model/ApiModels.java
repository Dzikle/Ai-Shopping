package mk.aishopping.model;

import java.math.BigDecimal;
import java.time.Instant;
import java.time.LocalDate;
import java.util.List;
import java.util.Map;

public final class ApiModels {

    private ApiModels() {}

    public record HealthResponse(
            String status,
            String databaseStatus,
            String opensearchStatus,
            String activeSearchEngine,
            Map<String, Long> counts
    ) {}

    public record StoreDto(
            int storeId,
            String retailerSlug,
            String retailerName,
            String externalKey,
            String name,
            String address,
            String city,
            int activeOffersCount,
            Instant latestPublishedTs
    ) {}

    public record OfferDto(
            String offerId,
            int storeId,
            String storeExternalKey,
            String storeName,
            String city,
            String retailerSlug,
            String retailerName,
            int retailerProductId,
            String skuKey,
            String listingName,
            String category,
            Integer canonicalProductId,
            String canonicalKey,
            String canonicalName,
            String normalizedSize,
            String currency,
            BigDecimal priceCurrent,
            BigDecimal unitPrice,
            String unitLabel,
            BigDecimal regularPrice,
            BigDecimal discountPrice,
            BigDecimal discountPct,
            String promoType,
            LocalDate promoStartsOn,
            LocalDate promoEndsOn,
            boolean isPromo,
            String availability,
            Instant publishedTs,
            Instant fetchedTs,
            String sourceUrl,
            int runId
    ) {}

    public record SearchResponse<T>(
            String sourceEngine,
            long total,
            int page,
            int size,
            List<T> items
    ) {}

    public record RetailerOfferSummaryDto(
            String retailerSlug,
            int retailerProductId,
            String listingName,
            BigDecimal minPrice,
            BigDecimal maxPrice,
            int storeCount,
            Instant latestPublishedTs,
            String sourceUrl
    ) {}

    public record ProductComparisonDto(
            int canonicalProductId,
            String canonicalKey,
            String canonicalName,
            String normalizedSize,
            int retailerCount,
            int storeCount,
            BigDecimal cheapestMkd,
            BigDecimal highestMkd,
            BigDecimal spreadMkd,
            Instant latestPublishedTs,
            List<RetailerOfferSummaryDto> offers
    ) {}

    public record PriceObservationDto(
            long observationId,
            String retailerSlug,
            String storeExternalKey,
            String storeName,
            String listingName,
            BigDecimal priceCurrent,
            BigDecimal regularPrice,
            BigDecimal discountPrice,
            BigDecimal discountPct,
            String promoType,
            String availability,
            Instant publishedTs,
            Instant fetchedTs,
            String sourceUrl
    ) {}

    public record ProductHistoryResponse(
            int canonicalProductId,
            String canonicalName,
            String normalizedSize,
            List<PriceObservationDto> observations
    ) {}

    public record ReviewQueueItemDto(
            long matchId,
            String sourceRetailerSlug,
            int retailerProductId,
            String sourceListingName,
            int candidateCanonicalId,
            String candidateCanonicalName,
            String normalizedSize,
            BigDecimal confidence,
            String reviewStatus,
            Map<String, Object> evidence
    ) {}

    public record OfferSearchFilter(
            String q,
            String retailer,
            String storeKey,
            String category,
            boolean inStockOnly,
            boolean promoOnly,
            BigDecimal minPrice,
            BigDecimal maxPrice,
            String sort,
            int page,
            int size
    ) {}
}
