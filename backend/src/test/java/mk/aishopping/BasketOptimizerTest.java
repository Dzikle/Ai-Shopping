package mk.aishopping;

import mk.aishopping.controller.BasketController;
import mk.aishopping.model.BasketModels.BasketItemRequest;
import mk.aishopping.model.BasketModels.BasketOptimizationResponse;
import mk.aishopping.model.BasketModels.BasketOptimizeRequest;
import mk.aishopping.model.BasketModels.SingleStoreBasketResultDto;
import mk.aishopping.repository.BasketRepository;
import mk.aishopping.repository.BasketRepository.CandidateStoreOffer;
import mk.aishopping.repository.BasketRepository.ProductTargetMeta;
import mk.aishopping.repository.BasketRepository.StoreHeader;
import mk.aishopping.service.BasketOptimizerService;
import mk.aishopping.service.UnitConversionUtil;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.http.ResponseEntity;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;
import java.util.Optional;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyBoolean;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

class BasketOptimizerTest {

    private BasketRepository basketRepository;
    private BasketOptimizerService optimizerService;
    private BasketController basketController;

    private StoreHeader veroStore;
    private StoreHeader stokoStore;
    private StoreHeader zitoStore;

    @BeforeEach
    void setUp() {
        basketRepository = mock(BasketRepository.class);
        optimizerService = new BasketOptimizerService(basketRepository);
        basketController = new BasketController(optimizerService);

        veroStore = new StoreHeader(1, "vero", "Vero", "89", "Веро Тафталиџе", "Скопје");
        stokoStore = new StoreHeader(20, "stokomak", "Stokomak", "1", "КИСЕЛА ВОДА", "Скопје");
        zitoStore = new StoreHeader(100, "zito", "Zito", "8", "8 Бутел1 - Скопје", "Скопје");

        when(basketRepository.findActiveStores(any(), any())).thenReturn(List.of(veroStore, stokoStore, zitoStore));
    }

    @Test
    void testUnitConversionAndPackScaling() {
        // 1 kg (1000g) requested of a 400g product -> ceil(1000 / 400) = 3 packs
        assertEquals(3, UnitConversionUtil.computePacksNeeded(
                new BigDecimal("1"), "kg", new BigDecimal("400"), "g", 1
        ));
        // 800g requested of a 400g product -> 2 packs
        assertEquals(2, UnitConversionUtil.computePacksNeeded(
                new BigDecimal("800"), "g", new BigDecimal("400"), "g", 1
        ));
        // 1.5 l (1500ml) requested of a 1000ml milk carton -> 2 packs
        assertEquals(2, UnitConversionUtil.computePacksNeeded(
                new BigDecimal("1.5"), "l", new BigDecimal("1000"), "ml", 1
        ));
        // 2 packs requested -> 2 packs
        assertEquals(2, UnitConversionUtil.computePacksNeeded(
                new BigDecimal("2"), "pack", new BigDecimal("400"), "g", 1
        ));
    }

    @Test
    void testCoverageFirstRankingMissingItemsAndMultiStoreSplitSavings() {
        // Item 1: Кадаиф 400г (canonicalId=101), user requests 800g -> 2 packs needed
        when(basketRepository.resolveProductTarget(eq(101), any(), any())).thenReturn(Optional.of(
                new ProductTargetMeta(101, null, "КАДАИФ 400ГР ХАСТЕЛ", "400g", new BigDecimal("400"), "g", 1)
        ));
        // Item 2: Кроасан Милка 50г (canonicalId=102), user requests 2 packs
        when(basketRepository.resolveProductTarget(eq(102), any(), any())).thenReturn(Optional.of(
                new ProductTargetMeta(102, null, "КРОАСАН МИЛКА 50гр ЧОКО", "50g", new BigDecimal("50"), "g", 1)
        ));
        // Item 3: Стоби Флипс 150г (canonicalId=103), user requests 1 pack
        when(basketRepository.resolveProductTarget(eq(103), any(), any())).thenReturn(Optional.of(
                new ProductTargetMeta(103, null, "СТОБИ ФЛИПС 150ГР ВИТАМИНКА", "150g", new BigDecimal("150"), "g", 1)
        ));

        Instant pubTs = Instant.parse("2026-10-28T08:00:00Z");
        Instant fetchTs = Instant.parse("2026-10-28T09:00:00Z");

        // Item 1 offers (2 packs needed):
        // Vero: 180 * 2 = 360 MKD; Zito: 170 * 2 = 340 MKD; Stokomak: 159 * 2 = 318 MKD
        when(basketRepository.findCandidateOffers(eq(101), any(), anyBoolean(), anyBoolean(), any(), any())).thenReturn(List.of(
                offer(veroStore, 1001, "КАДАИФ 400ГР ХАСТЕЛ", "400g", 400, "g", "180.00", false, null, "1.00", pubTs, fetchTs, "https://pricelist.vero.com.mk/89_1.html"),
                offer(zitoStore, 3001, "КАДАИФ 400ГР ХАСТЕЛ", "400g", 400, "g", "170.00", false, null, "1.00", pubTs, fetchTs, "https://zito.proverkanaceni.mk/8_1.html"),
                offer(stokoStore, 2001, "КАДАИФ 400ГР ХАСТЕЛ", "400g", 400, "g", "159.00", false, null, "1.00", pubTs, fetchTs, "https://stokomak.proverkanaceni.mk/1_1.html")
        ));

        // Item 2 offers (2 packs needed):
        // Vero: 45 * 2 = 90 MKD; Zito: 43 * 2 = 86 MKD; Stokomak: 32 * 2 = 64 MKD
        when(basketRepository.findCandidateOffers(eq(102), any(), anyBoolean(), anyBoolean(), any(), any())).thenReturn(List.of(
                offer(veroStore, 1002, "КРОАСАН МИЛКА 50гр ЧОКО", "50g", 50, "g", "45.00", false, null, "1.00", pubTs, fetchTs, "https://pricelist.vero.com.mk/89_1.html"),
                offer(zitoStore, 3002, "КРОАСАН МИЛКА 50гр ЧОКО", "50g", 50, "g", "43.00", false, null, "1.00", pubTs, fetchTs, "https://zito.proverkanaceni.mk/8_1.html"),
                offer(stokoStore, 2002, "КРОАСАН МИЛКА 50гр ЧОКО", "50g", 50, "g", "32.00", false, null, "1.00", pubTs, fetchTs, "https://stokomak.proverkanaceni.mk/1_1.html")
        ));

        // Item 3 offers (1 pack needed):
        // Available at Vero (50 MKD) and Zito (43 MKD), MISSING at Stokomak!
        when(basketRepository.findCandidateOffers(eq(103), any(), anyBoolean(), anyBoolean(), any(), any())).thenReturn(List.of(
                offer(veroStore, 1003, "СТОБИ ФЛИПС 150ГР ВИТАМИНКА", "150g", 150, "g", "50.00", false, null, "1.00", pubTs, fetchTs, "https://pricelist.vero.com.mk/89_1.html"),
                offer(zitoStore, 3003, "СТОБИ ФЛИПС 150ГР ВИТАМИНКА", "150g", 150, "g", "43.00", false, null, "1.00", pubTs, fetchTs, "https://zito.proverkanaceni.mk/8_1.html")
        ));

        BasketOptimizeRequest req = new BasketOptimizeRequest(
                List.of(
                        new BasketItemRequest(101, null, "Кадаиф", new BigDecimal("800"), "g"),
                        new BasketItemRequest(102, null, "Кроасан", new BigDecimal("2"), "pack"),
                        new BasketItemRequest(103, null, "Стоби Флипс", new BigDecimal("1"), "pack")
                ),
                null,
                null,
                2,
                new BigDecimal("20.00"),
                false,
                true
        );

        ResponseEntity<?> responseEntity = basketController.optimizeAdHocBasket(req);
        assertEquals(200, responseEntity.getStatusCode().value());
        BasketOptimizationResponse resp = (BasketOptimizationResponse) responseEntity.getBody();
        assertNotNull(resp);

        // Single-store rankings:
        // 1st: Zito (3/3 items covered, total = 340 + 86 + 43 = 469.00 MKD, savings vs Vero = 500 - 469 = 31.00 MKD)
        // 2nd: Vero (3/3 items covered, total = 360 + 90 + 50 = 500.00 MKD)
        // 3rd: Stokomak (2/3 items covered, total = 318 + 64 = 382.00 MKD, missing item 103)
        assertEquals(3, resp.singleStoreRankings().size());
        SingleStoreBasketResultDto first = resp.singleStoreRankings().get(0);
        SingleStoreBasketResultDto second = resp.singleStoreRankings().get(1);
        SingleStoreBasketResultDto third = resp.singleStoreRankings().get(2);

        assertEquals("zito", first.retailerSlug());
        assertEquals(3, first.itemsCovered());
        assertEquals(new BigDecimal("469.00"), first.totalMkd());
        assertEquals(new BigDecimal("31.00"), first.savingsVsHighestCoveredSingleStoreMkd());
        assertEquals(2, first.coveredItems().get(0).packsNeeded());

        assertEquals("vero", second.retailerSlug());
        assertEquals(3, second.itemsCovered());
        assertEquals(new BigDecimal("500.00"), second.totalMkd());

        assertEquals("stokomak", third.retailerSlug());
        assertEquals(2, third.itemsCovered());
        assertEquals(new BigDecimal("382.00"), third.totalMkd());
        assertEquals(1, third.missingItems().size());
        assertEquals(103, third.missingItems().get(0).canonicalProductId());

        // Multi-store split: Stokomak (items 1 & 2 = 382.00 MKD) + Zito (item 3 = 43.00 MKD) = 425.00 MKD!
        // Savings vs best single store (Zito 469.00 MKD) = 44.00 MKD >= 20.00 MKD threshold!
        assertNotNull(resp.bestMultiStorePlan());
        assertEquals(2, resp.bestMultiStorePlan().storesUsed());
        assertEquals(3, resp.bestMultiStorePlan().itemsCovered());
        assertEquals(new BigDecimal("425.00"), resp.bestMultiStorePlan().totalMkd());
        assertEquals(new BigDecimal("44.00"), resp.bestMultiStorePlan().savingsVsBestSingleStoreMkd());
        assertTrue(resp.bestMultiStorePlan().meetsMinSavingsThreshold());
        assertEquals("multi_store_saves_mkd_above_threshold", resp.bestMultiStorePlan().recommendationReason());

        // Now test with a high minSplitSavingsMkd threshold (100.00 MKD) -> meetsMinSavingsThreshold becomes false
        BasketOptimizeRequest highThresholdReq = new BasketOptimizeRequest(
                req.items(), null, null, 2, new BigDecimal("100.00"), false, true
        );
        BasketOptimizationResponse highResp = optimizerService.optimizeBasket(highThresholdReq);
        assertFalse(highResp.bestMultiStorePlan().meetsMinSavingsThreshold());
        assertEquals("single_store_recommended_split_savings_below_threshold", highResp.bestMultiStorePlan().recommendationReason());
    }

    @Test
    void testSubstituteFlaggingPerAdr0003() {
        when(basketRepository.resolveProductTarget(eq(201), any(), any())).thenReturn(Optional.of(
                new ProductTargetMeta(201, null, "БИТОЛСКИ ЈОГУРТ БИМИЛК 1Л", "1000ml", new BigDecimal("1000"), "ml", 1)
        ));
        Instant pubTs = Instant.parse("2026-10-28T08:00:00Z");

        // When allowSubstitutes = true, Stokomak has a Stage-2 pending_review substitute (isSubstitute=true, confidence=0.67)
        when(basketRepository.findCandidateOffers(eq(201), any(), eq(true), anyBoolean(), any(), any())).thenReturn(List.of(
                offer(veroStore, 1101, "БИТОЛСКИ ЈОГУРТ БИМИЛК 1Л", "1000ml", 1000, "ml", "79.00", false, null, "1.00", pubTs, pubTs, "https://pricelist.vero.com.mk/89_1.html"),
                offer(stokoStore, 2101, "ЈОГУРТ БИМИЛК 1Л", "1000ml", 1000, "ml", "65.00", true, "stage2_pending_review_candidate", "0.67", pubTs, pubTs, "https://stokomak.proverkanaceni.mk/1_1.html")
        ));

        BasketOptimizationResponse subResp = optimizerService.optimizeBasket(new BasketOptimizeRequest(
                List.of(new BasketItemRequest(201, null, "Јогурт", BigDecimal.ONE, "pack")),
                null, null, 2, BigDecimal.ZERO, true, true
        ));

        assertEquals(2, subResp.singleStoreRankings().size());
        // Exact match store (Vero) ranks above substitute-only store (Stokomak) at equal item coverage
        assertEquals("vero", subResp.singleStoreRankings().get(0).retailerSlug());
        assertEquals(1, subResp.singleStoreRankings().get(0).exactMatchesCount());
        assertEquals(0, subResp.singleStoreRankings().get(0).substitutesCount());

        SingleStoreBasketResultDto stokoRes = subResp.singleStoreRankings().get(1);
        assertEquals("stokomak", stokoRes.retailerSlug());
        assertEquals(0, stokoRes.exactMatchesCount());
        assertEquals(1, stokoRes.substitutesCount());
        assertTrue(stokoRes.coveredItems().get(0).isSubstitute());
        assertEquals("stage2_pending_review_candidate", stokoRes.coveredItems().get(0).substituteReason());
        assertEquals(new BigDecimal("0.67"), stokoRes.coveredItems().get(0).matchConfidence());
    }

    private static CandidateStoreOffer offer(
            StoreHeader store,
            int retailerProductId,
            String listingName,
            String normSize,
            int qtyVal,
            String qtyUnit,
            String price,
            boolean isSub,
            String subReason,
            String confidence,
            Instant pubTs,
            Instant fetchTs,
            String url
    ) {
        return new CandidateStoreOffer(
                store.storeId(),
                store.storeExternalKey(),
                store.storeName(),
                store.city(),
                store.retailerSlug(),
                store.retailerName(),
                retailerProductId,
                listingName,
                normSize,
                BigDecimal.valueOf(qtyVal),
                qtyUnit,
                1,
                new BigDecimal(price),
                isSub,
                subReason,
                new BigDecimal(confidence),
                pubTs,
                fetchTs,
                url
        );
    }
}
