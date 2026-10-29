package mk.aishopping.service;

import mk.aishopping.model.BasketModels.BasketItemRequest;
import mk.aishopping.model.BasketModels.BasketOptimizationResponse;
import mk.aishopping.model.BasketModels.BasketOptimizeRequest;
import mk.aishopping.model.BasketModels.CreateShoppingListRequest;
import mk.aishopping.model.BasketModels.MissingBasketItemDto;
import mk.aishopping.model.BasketModels.MultiStoreAllocationDto;
import mk.aishopping.model.BasketModels.MultiStorePlanDto;
import mk.aishopping.model.BasketModels.PricedBasketLineDto;
import mk.aishopping.model.BasketModels.ShoppingListDto;
import mk.aishopping.model.BasketModels.ShoppingListItemDto;
import mk.aishopping.model.BasketModels.SingleStoreBasketResultDto;
import mk.aishopping.repository.BasketRepository;
import mk.aishopping.repository.BasketRepository.CandidateStoreOffer;
import mk.aishopping.repository.BasketRepository.ProductTargetMeta;
import mk.aishopping.repository.BasketRepository.StoreHeader;
import org.springframework.stereotype.Service;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.Set;

@Service
public class BasketOptimizerService {

    private final BasketRepository basketRepository;

    public BasketOptimizerService(BasketRepository basketRepository) {
        this.basketRepository = basketRepository;
    }

    public ShoppingListDto createShoppingList(CreateShoppingListRequest req) {
        return basketRepository.createShoppingList(req);
    }

    public Optional<ShoppingListDto> getShoppingList(long listId) {
        return basketRepository.getShoppingList(listId);
    }

    public Optional<BasketOptimizationResponse> optimizeSavedList(long listId, BasketOptimizeRequest overrides) {
        Optional<ShoppingListDto> listOpt = basketRepository.getShoppingList(listId);
        if (listOpt.isEmpty()) {
            return Optional.empty();
        }
        ShoppingListDto list = listOpt.get();
        List<BasketItemRequest> items = new ArrayList<>();
        for (ShoppingListItemDto item : list.items()) {
            items.add(new BasketItemRequest(
                    item.canonicalProductId(),
                    item.retailerProductId(),
                    item.itemLabel() != null ? item.itemLabel() : item.resolvedName(),
                    item.quantity(),
                    item.unit()
            ));
        }

        String city = (overrides != null && overrides.city() != null && !overrides.city().isBlank())
                ? overrides.city() : list.cityFilter();
        List<String> retailers = overrides != null ? overrides.retailers() : null;
        Integer maxStores = overrides != null ? overrides.maxStores() : null;
        BigDecimal minSavings = overrides != null ? overrides.minSplitSavingsMkd() : null;
        Boolean allowSubstitutes = overrides != null ? overrides.allowSubstitutes() : null;
        Boolean inStockOnly = overrides != null ? overrides.inStockOnly() : null;

        return Optional.of(optimizeBasket(new BasketOptimizeRequest(
                items, city, retailers, maxStores, minSavings, allowSubstitutes, inStockOnly
        )));
    }

    public BasketOptimizationResponse optimizeBasket(BasketOptimizeRequest req) {
        if (req == null || req.items() == null || req.items().isEmpty()) {
            throw new IllegalArgumentException("Basket must contain at least one item");
        }

        boolean allowSubstitutes = Boolean.TRUE.equals(req.allowSubstitutes());
        boolean inStockOnly = req.inStockOnly() == null || Boolean.TRUE.equals(req.inStockOnly());
        int maxStores = req.maxStores() != null ? Math.max(1, Math.min(3, req.maxStores())) : 2;
        BigDecimal minSplitSavingsMkd = (req.minSplitSavingsMkd() != null && req.minSplitSavingsMkd().compareTo(BigDecimal.ZERO) >= 0)
                ? req.minSplitSavingsMkd().setScale(2, RoundingMode.HALF_UP)
                : BigDecimal.ZERO.setScale(2, RoundingMode.HALF_UP);

        List<StoreHeader> activeStores = basketRepository.findActiveStores(req.city(), req.retailers());
        Map<Integer, StoreHeader> storeById = new LinkedHashMap<>();
        for (StoreHeader s : activeStores) {
            storeById.put(s.storeId(), s);
        }

        int totalItems = req.items().size();
        List<ResolvedBasketItem> resolvedItems = new ArrayList<>(totalItems);

        // Per item: map storeId -> best PricedBasketLineDto in that store
        List<Map<Integer, PricedBasketLineDto>> perItemStoreLines = new ArrayList<>(totalItems);

        for (int idx = 0; idx < totalItems; idx++) {
            BasketItemRequest itemReq = req.items().get(idx);
            BigDecimal reqQty = (itemReq.quantity() == null || itemReq.quantity().compareTo(BigDecimal.ZERO) <= 0)
                    ? BigDecimal.ONE.setScale(3, RoundingMode.HALF_UP)
                    : itemReq.quantity().setScale(3, RoundingMode.HALF_UP);
            String reqUnit = UnitConversionUtil.normalizeUnit(itemReq.unit());

            Optional<ProductTargetMeta> metaOpt = basketRepository.resolveProductTarget(
                    itemReq.canonicalProductId(), itemReq.retailerProductId(), itemReq.itemLabel()
            );

            Integer effectiveCanonicalId = itemReq.canonicalProductId() != null
                    ? itemReq.canonicalProductId()
                    : metaOpt.map(ProductTargetMeta::canonicalProductId).orElse(null);

            String requestedName = metaOpt.map(ProductTargetMeta::displayName)
                    .orElse(itemReq.itemLabel() != null ? itemReq.itemLabel() : "Unknown product");

            ResolvedBasketItem resolved = new ResolvedBasketItem(
                    idx,
                    effectiveCanonicalId,
                    itemReq.retailerProductId(),
                    requestedName,
                    reqQty,
                    reqUnit,
                    metaOpt.isPresent()
            );
            resolvedItems.add(resolved);

            Map<Integer, PricedBasketLineDto> storeBestMap = new LinkedHashMap<>();
            if (metaOpt.isPresent()) {
                List<CandidateStoreOffer> candidates = basketRepository.findCandidateOffers(
                        effectiveCanonicalId,
                        itemReq.retailerProductId(),
                        allowSubstitutes,
                        inStockOnly,
                        req.city(),
                        req.retailers()
                );

                for (CandidateStoreOffer cand : candidates) {
                    int packsNeeded = UnitConversionUtil.computePacksNeeded(
                            reqQty,
                            reqUnit,
                            cand.skuQuantityValue(),
                            cand.skuQuantityUnit(),
                            cand.skuPackCount()
                    );
                    BigDecimal lineTotal = cand.priceCurrent()
                            .multiply(BigDecimal.valueOf(packsNeeded))
                            .setScale(2, RoundingMode.HALF_UP);

                    PricedBasketLineDto line = new PricedBasketLineDto(
                            idx,
                            effectiveCanonicalId,
                            itemReq.retailerProductId(),
                            requestedName,
                            reqQty,
                            reqUnit,
                            cand.storeId(),
                            cand.storeExternalKey(),
                            cand.storeName(),
                            cand.retailerSlug(),
                            cand.retailerProductId(),
                            cand.listingName(),
                            cand.normalizedSize(),
                            packsNeeded,
                            cand.priceCurrent(),
                            lineTotal,
                            cand.isSubstitute(),
                            cand.substituteReason(),
                            cand.confidence(),
                            cand.publishedTs(),
                            cand.fetchedTs(),
                            cand.sourceUrl()
                    );

                    PricedBasketLineDto existing = storeBestMap.get(cand.storeId());
                    if (existing == null || isBetterOfferForStore(line, existing)) {
                        storeBestMap.put(cand.storeId(), line);
                    }
                }
            }
            perItemStoreLines.add(storeBestMap);
        }

        // 1. Evaluate all single stores that cover at least 1 item (or all active stores if none cover any)
        List<SingleStoreBasketResultDto> rawSingleStores = new ArrayList<>();
        for (StoreHeader store : activeStores) {
            List<PricedBasketLineDto> covered = new ArrayList<>();
            List<MissingBasketItemDto> missing = new ArrayList<>();
            BigDecimal totalMkd = BigDecimal.ZERO.setScale(2, RoundingMode.HALF_UP);
            int exactCount = 0;
            int subCount = 0;

            for (int idx = 0; idx < totalItems; idx++) {
                ResolvedBasketItem item = resolvedItems.get(idx);
                PricedBasketLineDto line = perItemStoreLines.get(idx).get(store.storeId());
                if (line != null) {
                    covered.add(line);
                    totalMkd = totalMkd.add(line.lineTotalMkd());
                    if (line.isSubstitute()) {
                        subCount++;
                    } else {
                        exactCount++;
                    }
                } else {
                    String reason = !item.targetExists()
                            ? "product_not_found_in_catalog"
                            : "no_offer_at_store";
                    missing.add(new MissingBasketItemDto(
                            idx,
                            item.canonicalProductId(),
                            item.retailerProductId(),
                            item.requestedName(),
                            item.requestedQuantity(),
                            item.requestedUnit(),
                            reason
                    ));
                }
            }

            if (!covered.isEmpty()) {
                BigDecimal ratio = BigDecimal.valueOf(covered.size())
                        .divide(BigDecimal.valueOf(totalItems), 4, RoundingMode.HALF_UP);
                rawSingleStores.add(new SingleStoreBasketResultDto(
                        store.storeId(),
                        store.retailerSlug(),
                        store.retailerName(),
                        store.storeExternalKey(),
                        store.storeName(),
                        store.city(),
                        covered.size(),
                        totalItems,
                        ratio,
                        totalMkd,
                        BigDecimal.ZERO.setScale(2, RoundingMode.HALF_UP),
                        exactCount,
                        subCount,
                        covered,
                        missing
                ));
            }
        }

        Comparator<SingleStoreBasketResultDto> singleStoreComparator = Comparator
                .comparingInt(SingleStoreBasketResultDto::itemsCovered).reversed()
                .thenComparing(Comparator.comparingInt(SingleStoreBasketResultDto::exactMatchesCount).reversed())
                .thenComparing(SingleStoreBasketResultDto::totalMkd)
                .thenComparingInt(SingleStoreBasketResultDto::storeId);

        rawSingleStores.sort(singleStoreComparator);

        // Compute savingsVsHighestCoveredSingleStoreMkd among stores with maximum coverage
        int maxSingleCoverage = rawSingleStores.isEmpty() ? 0 : rawSingleStores.get(0).itemsCovered();
        BigDecimal highestTotalAtMaxCoverage = rawSingleStores.stream()
                .filter(s -> s.itemsCovered() == maxSingleCoverage)
                .map(SingleStoreBasketResultDto::totalMkd)
                .max(Comparator.naturalOrder())
                .orElse(BigDecimal.ZERO.setScale(2, RoundingMode.HALF_UP));

        List<SingleStoreBasketResultDto> rankedSingleStores = new ArrayList<>(rawSingleStores.size());
        for (SingleStoreBasketResultDto s : rawSingleStores) {
            BigDecimal savings = (s.itemsCovered() == maxSingleCoverage)
                    ? highestTotalAtMaxCoverage.subtract(s.totalMkd()).max(BigDecimal.ZERO).setScale(2, RoundingMode.HALF_UP)
                    : BigDecimal.ZERO.setScale(2, RoundingMode.HALF_UP);
            rankedSingleStores.add(new SingleStoreBasketResultDto(
                    s.storeId(),
                    s.retailerSlug(),
                    s.retailerName(),
                    s.storeExternalKey(),
                    s.storeName(),
                    s.city(),
                    s.itemsCovered(),
                    s.totalItemsRequested(),
                    s.coverageRatio(),
                    s.totalMkd(),
                    savings,
                    s.exactMatchesCount(),
                    s.substitutesCount(),
                    s.coveredItems(),
                    s.missingItems()
            ));
        }

        SingleStoreBasketResultDto bestSingleStore = rankedSingleStores.isEmpty()
                ? null
                : rankedSingleStores.get(0);

        // 2. Multi-store split optimization up to maxStores
        MultiStorePlanDto bestMultiStorePlan = computeBestMultiStorePlan(
                resolvedItems,
                perItemStoreLines,
                storeById,
                rankedSingleStores,
                bestSingleStore,
                maxStores,
                minSplitSavingsMkd
        );

        return new BasketOptimizationResponse(
                totalItems,
                allowSubstitutes,
                inStockOnly,
                maxStores,
                minSplitSavingsMkd,
                bestSingleStore,
                rankedSingleStores,
                bestMultiStorePlan
        );
    }

    private MultiStorePlanDto computeBestMultiStorePlan(
            List<ResolvedBasketItem> resolvedItems,
            List<Map<Integer, PricedBasketLineDto>> perItemStoreLines,
            Map<Integer, StoreHeader> storeById,
            List<SingleStoreBasketResultDto> rankedSingleStores,
            SingleStoreBasketResultDto bestSingleStore,
            int maxStores,
            BigDecimal minSplitSavingsMkd
    ) {
        int totalItems = resolvedItems.size();
        if (rankedSingleStores.isEmpty()) {
            List<MissingBasketItemDto> allMissing = resolvedItems.stream()
                    .map(item -> new MissingBasketItemDto(
                            item.itemIndex(),
                            item.canonicalProductId(),
                            item.retailerProductId(),
                            item.requestedName(),
                            item.requestedQuantity(),
                            item.requestedUnit(),
                            !item.targetExists() ? "product_not_found_in_catalog" : "no_offer_at_any_store"
                    ))
                    .toList();
            return new MultiStorePlanDto(
                    0, 0, totalItems, BigDecimal.ZERO.setScale(4, RoundingMode.HALF_UP),
                    BigDecimal.ZERO.setScale(2, RoundingMode.HALF_UP),
                    BigDecimal.ZERO.setScale(2, RoundingMode.HALF_UP),
                    false, "no_stores_cover_requested_items", List.of(), allMissing
            );
        }

        // Collect candidate store IDs: top single stores + top 5 cheapest stores per item
        Set<Integer> candidateStoreIds = new LinkedHashSet<>();
        for (int i = 0; i < Math.min(10, rankedSingleStores.size()); i++) {
            candidateStoreIds.add(rankedSingleStores.get(i).storeId());
        }
        for (Map<Integer, PricedBasketLineDto> itemMap : perItemStoreLines) {
            itemMap.values().stream()
                    .sorted(Comparator
                            .comparing(PricedBasketLineDto::isSubstitute)
                            .thenComparing(PricedBasketLineDto::lineTotalMkd)
                            .thenComparingInt(PricedBasketLineDto::storeId))
                    .limit(5)
                    .forEach(line -> candidateStoreIds.add(line.storeId()));
        }

        List<Integer> storePool = new ArrayList<>(candidateStoreIds);
        List<List<Integer>> subsets = new ArrayList<>();
        generateSubsets(storePool, maxStores, 0, new ArrayList<>(), subsets);

        EvaluatedSubset bestEval = null;
        for (List<Integer> subset : subsets) {
            EvaluatedSubset eval = evaluateSubset(subset, resolvedItems, perItemStoreLines, storeById);
            if (eval.itemsCovered() == 0) {
                continue;
            }
            if (bestEval == null || compareEvaluatedSubsets(eval, bestEval) < 0) {
                bestEval = eval;
            }
        }

        if (bestEval == null) {
            return null;
        }

        BigDecimal savingsVsSingle = BigDecimal.ZERO.setScale(2, RoundingMode.HALF_UP);
        boolean meetsThreshold = false;
        String reason;

        if (bestSingleStore == null) {
            meetsThreshold = true;
            reason = "multi_store_plan_found";
        } else if (bestEval.itemsCovered() > bestSingleStore.itemsCovered()) {
            // Multi-store covers strictly more items than any single store!
            savingsVsSingle = BigDecimal.ZERO.setScale(2, RoundingMode.HALF_UP);
            meetsThreshold = true;
            reason = "higher_item_coverage_across_stores";
        } else {
            savingsVsSingle = bestSingleStore.totalMkd()
                    .subtract(bestEval.totalMkd())
                    .max(BigDecimal.ZERO)
                    .setScale(2, RoundingMode.HALF_UP);
            if (bestEval.allocations().size() == 1) {
                meetsThreshold = true;
                reason = "single_store_is_already_optimal";
            } else if (savingsVsSingle.compareTo(minSplitSavingsMkd) >= 0 && savingsVsSingle.compareTo(BigDecimal.ZERO) > 0) {
                meetsThreshold = true;
                reason = "multi_store_saves_mkd_above_threshold";
            } else {
                meetsThreshold = false;
                reason = "single_store_recommended_split_savings_below_threshold";
            }
        }

        BigDecimal ratio = BigDecimal.valueOf(bestEval.itemsCovered())
                .divide(BigDecimal.valueOf(totalItems), 4, RoundingMode.HALF_UP);

        return new MultiStorePlanDto(
                bestEval.allocations().size(),
                bestEval.itemsCovered(),
                totalItems,
                ratio,
                bestEval.totalMkd(),
                savingsVsSingle,
                meetsThreshold,
                reason,
                bestEval.allocations(),
                bestEval.missingItems()
        );
    }

    private EvaluatedSubset evaluateSubset(
            List<Integer> subset,
            List<ResolvedBasketItem> resolvedItems,
            List<Map<Integer, PricedBasketLineDto>> perItemStoreLines,
            Map<Integer, StoreHeader> storeById
    ) {
        Map<Integer, List<PricedBasketLineDto>> byStore = new LinkedHashMap<>();
        List<MissingBasketItemDto> missing = new ArrayList<>();
        BigDecimal totalMkd = BigDecimal.ZERO.setScale(2, RoundingMode.HALF_UP);
        int coveredCount = 0;
        int exactCount = 0;

        for (int idx = 0; idx < resolvedItems.size(); idx++) {
            ResolvedBasketItem item = resolvedItems.get(idx);
            Map<Integer, PricedBasketLineDto> storeOffers = perItemStoreLines.get(idx);

            PricedBasketLineDto bestLine = null;
            for (int storeId : subset) {
                PricedBasketLineDto candidate = storeOffers.get(storeId);
                if (candidate != null) {
                    if (bestLine == null || isBetterOfferForStore(candidate, bestLine)) {
                        bestLine = candidate;
                    }
                }
            }

            if (bestLine != null) {
                coveredCount++;
                if (!bestLine.isSubstitute()) {
                    exactCount++;
                }
                totalMkd = totalMkd.add(bestLine.lineTotalMkd());
                byStore.computeIfAbsent(bestLine.storeId(), k -> new ArrayList<>()).add(bestLine);
            } else {
                missing.add(new MissingBasketItemDto(
                        idx,
                        item.canonicalProductId(),
                        item.retailerProductId(),
                        item.requestedName(),
                        item.requestedQuantity(),
                        item.requestedUnit(),
                        !item.targetExists() ? "product_not_found_in_catalog" : "no_offer_in_selected_stores"
                ));
            }
        }

        List<MultiStoreAllocationDto> allocations = new ArrayList<>();
        for (Map.Entry<Integer, List<PricedBasketLineDto>> entry : byStore.entrySet()) {
            StoreHeader sh = storeById.get(entry.getKey());
            BigDecimal subTotal = entry.getValue().stream()
                    .map(PricedBasketLineDto::lineTotalMkd)
                    .reduce(BigDecimal.ZERO.setScale(2, RoundingMode.HALF_UP), BigDecimal::add);
            allocations.add(new MultiStoreAllocationDto(
                    sh.storeId(),
                    sh.retailerSlug(),
                    sh.retailerName(),
                    sh.storeExternalKey(),
                    sh.storeName(),
                    sh.city(),
                    subTotal,
                    entry.getValue()
            ));
        }

        allocations.sort(Comparator.comparingInt(MultiStoreAllocationDto::storeId));
        return new EvaluatedSubset(coveredCount, exactCount, totalMkd, allocations, missing);
    }

    private static int compareEvaluatedSubsets(EvaluatedSubset a, EvaluatedSubset b) {
        if (a.itemsCovered() != b.itemsCovered()) {
            return Integer.compare(b.itemsCovered(), a.itemsCovered()); // higher coverage first
        }
        if (a.exactMatchesCount() != b.exactMatchesCount()) {
            return Integer.compare(b.exactMatchesCount(), a.exactMatchesCount()); // more exact matches first
        }
        int priceCmp = a.totalMkd().compareTo(b.totalMkd());
        if (priceCmp != 0) {
            return priceCmp; // lower total MKD first
        }
        int storesCmp = Integer.compare(a.allocations().size(), b.allocations().size());
        if (storesCmp != 0) {
            return storesCmp; // fewer stores preferred on exact price tie
        }
        for (int i = 0; i < Math.min(a.allocations().size(), b.allocations().size()); i++) {
            int idCmp = Integer.compare(a.allocations().get(i).storeId(), b.allocations().get(i).storeId());
            if (idCmp != 0) {
                return idCmp;
            }
        }
        return 0;
    }

    private static void generateSubsets(
            List<Integer> pool,
            int maxLen,
            int startIdx,
            List<Integer> current,
            List<List<Integer>> out
    ) {
        if (!current.isEmpty()) {
            out.add(new ArrayList<>(current));
        }
        if (current.size() >= maxLen) {
            return;
        }
        for (int i = startIdx; i < pool.size(); i++) {
            current.add(pool.get(i));
            generateSubsets(pool, maxLen, i + 1, current, out);
            current.remove(current.size() - 1);
        }
    }

    private static boolean isBetterOfferForStore(PricedBasketLineDto candidate, PricedBasketLineDto existing) {
        // Exact identity match always takes precedence over a substitute (ADR-0003)
        if (candidate.isSubstitute() != existing.isSubstitute()) {
            return !candidate.isSubstitute();
        }
        // Higher confidence preferred for substitutes
        if (candidate.isSubstitute()) {
            int confCmp = candidate.matchConfidence().compareTo(existing.matchConfidence());
            if (confCmp != 0) {
                return confCmp > 0;
            }
        }
        // Lower total MKD preferred
        int totalCmp = candidate.lineTotalMkd().compareTo(existing.lineTotalMkd());
        if (totalCmp != 0) {
            return totalCmp < 0;
        }
        return candidate.storeId() < existing.storeId();
    }

    private record ResolvedBasketItem(
            int itemIndex,
            Integer canonicalProductId,
            Integer retailerProductId,
            String requestedName,
            BigDecimal requestedQuantity,
            String requestedUnit,
            boolean targetExists
    ) {}

    private record EvaluatedSubset(
            int itemsCovered,
            int exactMatchesCount,
            BigDecimal totalMkd,
            List<MultiStoreAllocationDto> allocations,
            List<MissingBasketItemDto> missingItems
    ) {}
}
