package mk.aishopping.model;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;

public final class BasketModels {

    private BasketModels() {}

    public record BasketItemRequest(
            Integer canonicalProductId,
            Integer retailerProductId,
            String itemLabel,
            BigDecimal quantity,
            String unit
    ) {}

    public record CreateShoppingListRequest(
            String name,
            String cityFilter,
            List<BasketItemRequest> items
    ) {}

    public record ShoppingListItemDto(
            long id,
            Integer canonicalProductId,
            Integer retailerProductId,
            String resolvedName,
            String normalizedSize,
            String itemLabel,
            BigDecimal quantity,
            String unit,
            int position
    ) {}

    public record ShoppingListDto(
            long id,
            String name,
            String cityFilter,
            Instant createdAt,
            Instant updatedAt,
            List<ShoppingListItemDto> items
    ) {}

    public record BasketOptimizeRequest(
            List<BasketItemRequest> items,
            String city,
            List<String> retailers,
            Integer maxStores,
            BigDecimal minSplitSavingsMkd,
            Boolean allowSubstitutes,
            Boolean inStockOnly
    ) {}

    public record PricedBasketLineDto(
            int itemIndex,
            Integer canonicalProductId,
            Integer requestedRetailerProductId,
            String requestedName,
            BigDecimal requestedQuantity,
            String requestedUnit,
            int storeId,
            String storeExternalKey,
            String storeName,
            String retailerSlug,
            int matchedRetailerProductId,
            String matchedListingName,
            String normalizedSize,
            int packsNeeded,
            BigDecimal unitPackPriceMkd,
            BigDecimal lineTotalMkd,
            boolean isSubstitute,
            String substituteReason,
            BigDecimal matchConfidence,
            Instant publishedTs,
            Instant fetchedTs,
            String sourceUrl
    ) {}

    public record MissingBasketItemDto(
            int itemIndex,
            Integer canonicalProductId,
            Integer retailerProductId,
            String requestedName,
            BigDecimal requestedQuantity,
            String requestedUnit,
            String reason
    ) {}

    public record SingleStoreBasketResultDto(
            int storeId,
            String retailerSlug,
            String retailerName,
            String storeExternalKey,
            String storeName,
            String city,
            int itemsCovered,
            int totalItemsRequested,
            BigDecimal coverageRatio,
            BigDecimal totalMkd,
            BigDecimal savingsVsHighestCoveredSingleStoreMkd,
            int exactMatchesCount,
            int substitutesCount,
            List<PricedBasketLineDto> coveredItems,
            List<MissingBasketItemDto> missingItems
    ) {}

    public record MultiStoreAllocationDto(
            int storeId,
            String retailerSlug,
            String retailerName,
            String storeExternalKey,
            String storeName,
            String city,
            BigDecimal subtotalMkd,
            List<PricedBasketLineDto> items
    ) {}

    public record MultiStorePlanDto(
            int storesUsed,
            int itemsCovered,
            int totalItemsRequested,
            BigDecimal coverageRatio,
            BigDecimal totalMkd,
            BigDecimal savingsVsBestSingleStoreMkd,
            boolean meetsMinSavingsThreshold,
            String recommendationReason,
            List<MultiStoreAllocationDto> storeAllocations,
            List<MissingBasketItemDto> missingItems
    ) {}

    public record BasketOptimizationResponse(
            int totalItemsRequested,
            boolean allowSubstitutes,
            boolean inStockOnly,
            int maxStoresAllowed,
            BigDecimal minSplitSavingsMkd,
            SingleStoreBasketResultDto bestSingleStore,
            List<SingleStoreBasketResultDto> singleStoreRankings,
            MultiStorePlanDto bestMultiStorePlan
    ) {}
}
