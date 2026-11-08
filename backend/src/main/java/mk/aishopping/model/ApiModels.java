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

    public record ReviewQueueDecisionDto(
            long matchId,
            String reviewStatus,
            String reviewedBy,
            String reviewNotes
    ) {}

    public record PipelineRunMetricDto(
            int runId,
            String runKey,
            String sourceSlug,
            String status,
            Instant startedAt,
            Instant finishedAt,
            Integer pagesSeen,
            Integer rowsSeen,
            Integer rowsStored,
            Integer rowsSkipped,
            boolean quarantined,
            String quarantineReason,
            String workerId,
            Double durationSeconds
    ) {}

    public record ReviewQueueMetricDto(
            int totalPending,
            int totalApproved,
            int totalRejected,
            int totalAutoAccepted,
            int oldestPendingDays
    ) {}

    public record MetricsResponse(
            Instant checkedAt,
            long totalOffers,
            long totalObservations,
            long totalCanonicalProducts,
            long totalProductMatches,
            long totalPendingReview,
            int totalPopulatedStores,
            int totalStaleStores,
            int totalQuarantinedRuns,
            List<PipelineRunMetricDto> recentRuns,
            ReviewQueueMetricDto reviewQueue
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

    public record StoreFreshnessDto(
            int storeId,
            String externalKey,
            String storeName,
            String city,
            int offerCount,
            Instant latestPublishedTs,
            Instant latestFetchedTs,
            BigDecimal ageHours
    ) {}

    public record QuarantinedRunDto(
            int runId,
            String runKey,
            String sourceSlug,
            String status,
            Instant startedAt,
            Instant finishedAt,
            Integer pagesSeen,
            Integer rowsSeen,
            String quarantineReason,
            String workerId
    ) {}

    public record RetailerFreshnessDto(
            String retailerSlug,
            String retailerName,
            int seededStoresCount,
            int populatedStoresCount,
            long offerCount,
            Instant latestPublishedTs,
            Instant oldestPublishedTs,
            Instant latestFetchedTs,
            int staleStoresCount,
            List<StoreFreshnessDto> staleStores,
            int quarantinedRunsCount,
            String lastCompletedRunKey,
            Instant lastCompletedAt
    ) {}

    public record FreshnessResponse(
            String status,
            Instant checkedAt,
            int staleThresholdHours,
            int quarantineWindowDays,
            long totalOffers,
            int totalPopulatedStores,
            int totalStaleStores,
            int totalQuarantinedRuns,
            List<RetailerFreshnessDto> retailers,
            List<QuarantinedRunDto> quarantinedRuns
    ) {}
}
