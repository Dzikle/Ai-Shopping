"""Port of BasketOptimizerTest.java (3 tests)."""

import datetime as dt
from decimal import Decimal

import pytest

from app.repositories.basket_repository import CandidateStoreOffer, ProductTargetMeta
from app.schemas.requests import BasketItemRequest, BasketOptimizeRequest
from app.services.basket_optimizer_service import BasketOptimizerService
from app.services.unit_conversion import compute_packs_needed
from tests.conftest import FakeBasketRepository, offer_row

PUB_TS = dt.datetime(2026, 10, 28, 8, 0, 0, tzinfo=dt.UTC)
FETCH_TS = dt.datetime(2026, 10, 28, 9, 0, 0, tzinfo=dt.UTC)


def _cand(row) -> CandidateStoreOffer:
    return CandidateStoreOffer(row)


def test_unit_conversion_and_pack_scaling():
    # 1 kg (1000g) requested of a 400g product -> ceil(1000 / 400) = 3 packs
    assert compute_packs_needed(Decimal("1"), "kg", Decimal("400"), "g", 1) == 3
    # 800g requested of a 400g product -> 2 packs
    assert compute_packs_needed(Decimal("800"), "g", Decimal("400"), "g", 1) == 2
    # 1.5 l (1500ml) requested of a 1000ml milk carton -> 2 packs
    assert compute_packs_needed(Decimal("1.5"), "l", Decimal("1000"), "ml", 1) == 2
    # 2 packs requested -> 2 packs
    assert compute_packs_needed(Decimal("2"), "pack", Decimal("400"), "g", 1) == 2


def _seed(repo: FakeBasketRepository):
    repo.targets[101] = ProductTargetMeta(101, None, "КАДАИФ 400ГР ХАСТЕЛ", "400g", Decimal("400"), "g", 1)
    repo.targets[102] = ProductTargetMeta(102, None, "КРОАСАН МИЛКА 50гр ЧОКО", "50g", Decimal("50"), "g", 1)
    repo.targets[103] = ProductTargetMeta(103, None, "СТОБИ ФЛИПС 150ГР ВИТАМИНКА", "150g", Decimal("150"), "g", 1)

    stores = {s["retailer_slug"]: s for s in repo.find_active_stores(None, None)}
    vero, stoko, zito = stores["vero"], stores["stokomak"], stores["zito"]

    repo.offers[101] = lambda allow: [
        _cand(offer_row(vero, 1001, "КАДАИФ 400ГР ХАСТЕЛ", "400g", 400, "g", "180.00", False, None, "1.00", PUB_TS, FETCH_TS, "https://pricelist.vero.com.mk/89_1.html")),
        _cand(offer_row(zito, 3001, "КАДАИФ 400ГР ХАСТЕЛ", "400g", 400, "g", "170.00", False, None, "1.00", PUB_TS, FETCH_TS, "https://zito.proverkanaceni.mk/8_1.html")),
        _cand(offer_row(stoko, 2001, "КАДАИФ 400ГР ХАСТЕЛ", "400g", 400, "g", "159.00", False, None, "1.00", PUB_TS, FETCH_TS, "https://stokomak.proverkanaceni.mk/1_1.html")),
    ]
    repo.offers[102] = lambda allow: [
        _cand(offer_row(vero, 1002, "КРОАСАН МИЛКА 50гр ЧОКО", "50g", 50, "g", "45.00", False, None, "1.00", PUB_TS, FETCH_TS, "https://pricelist.vero.com.mk/89_1.html")),
        _cand(offer_row(zito, 3002, "КРОАСАН МИЛКА 50гр ЧОКО", "50g", 50, "g", "43.00", False, None, "1.00", PUB_TS, FETCH_TS, "https://zito.proverkanaceni.mk/8_1.html")),
        _cand(offer_row(stoko, 2002, "КРОАСАН МИЛКА 50гр ЧОКО", "50g", 50, "g", "32.00", False, None, "1.00", PUB_TS, FETCH_TS, "https://stokomak.proverkanaceni.mk/1_1.html")),
    ]
    repo.offers[103] = lambda allow: [
        _cand(offer_row(vero, 1003, "СТОБИ ФЛИПС 150ГР ВИТАМИНКА", "150g", 150, "g", "50.00", False, None, "1.00", PUB_TS, FETCH_TS, "https://pricelist.vero.com.mk/89_1.html")),
        _cand(offer_row(zito, 3003, "СТОБИ ФЛИПС 150ГР ВИТАМИНКА", "150g", 150, "g", "43.00", False, None, "1.00", PUB_TS, FETCH_TS, "https://zito.proverkanaceni.mk/8_1.html")),
    ]


def test_coverage_first_ranking_missing_items_and_multi_store_split_savings():
    repo = FakeBasketRepository()
    _seed(repo)
    service = BasketOptimizerService(repo)

    req = BasketOptimizeRequest(
        items=[
            BasketItemRequest(canonicalProductId=101, retailerProductId=None, itemLabel="Кадаиф", quantity=Decimal("800"), unit="g"),
            BasketItemRequest(canonicalProductId=102, retailerProductId=None, itemLabel="Кроасан", quantity=Decimal("2"), unit="pack"),
            BasketItemRequest(canonicalProductId=103, retailerProductId=None, itemLabel="Стоби Флипс", quantity=Decimal("1"), unit="pack"),
        ],
        city=None,
        retailers=None,
        maxStores=2,
        minSplitSavingsMkd=Decimal("20.00"),
        allowSubstitutes=False,
        inStockOnly=True,
    )

    resp = service.optimize_basket(req)

    # Single-store rankings:
    # 1st Zito: 3/3 items, 340 + 86 + 43 = 469.00 MKD, savings vs Vero = 31.00
    # 2nd Vero: 3/3 items, 360 + 90 + 50 = 500.00 MKD
    # 3rd Stokomak: 2/3 items, 318 + 64 = 382.00 MKD, missing item 103
    assert len(resp["singleStoreRankings"]) == 3
    first, second, third = resp["singleStoreRankings"]

    assert first["retailerSlug"] == "zito"
    assert first["itemsCovered"] == 3
    assert first["totalMkd"] == Decimal("469.00")
    assert first["savingsVsHighestCoveredSingleStoreMkd"] == Decimal("31.00")
    assert first["coveredItems"][0]["packsNeeded"] == 2

    assert second["retailerSlug"] == "vero"
    assert second["itemsCovered"] == 3
    assert second["totalMkd"] == Decimal("500.00")

    assert third["retailerSlug"] == "stokomak"
    assert third["itemsCovered"] == 2
    assert third["totalMkd"] == Decimal("382.00")
    assert len(third["missingItems"]) == 1
    assert third["missingItems"][0]["canonicalProductId"] == 103

    # Multi-store split: Stokomak (items 1&2 = 382.00) + Zito (item 3 = 43.00) = 425.00
    # Savings vs best single store (469.00) = 44.00 >= 20.00 threshold
    plan = resp["bestMultiStorePlan"]
    assert plan is not None
    assert plan["storesUsed"] == 2
    assert plan["itemsCovered"] == 3
    assert plan["totalMkd"] == Decimal("425.00")
    assert plan["savingsVsBestSingleStoreMkd"] == Decimal("44.00")
    assert plan["meetsMinSavingsThreshold"] is True
    assert plan["recommendationReason"] == "multi_store_saves_mkd_above_threshold"

    # High threshold (100.00 MKD) -> below threshold
    high_req = BasketOptimizeRequest(
        items=req.items, city=None, retailers=None, maxStores=2,
        minSplitSavingsMkd=Decimal("100.00"), allowSubstitutes=False, inStockOnly=True,
    )
    high_resp = service.optimize_basket(high_req)
    assert high_resp["bestMultiStorePlan"]["meetsMinSavingsThreshold"] is False
    assert high_resp["bestMultiStorePlan"]["recommendationReason"] == "single_store_recommended_split_savings_below_threshold"


def test_substitute_flagging_per_adr0003():
    repo = FakeBasketRepository()
    vero = [s for s in repo.find_active_stores(None, None) if s["retailer_slug"] == "vero"][0]
    stoko = [s for s in repo.find_active_stores(None, None) if s["retailer_slug"] == "stokomak"][0]
    repo.targets[201] = ProductTargetMeta(201, None, "БИТОЛСКИ ЈОГУРТ БИМИЛК 1Л", "1000ml", Decimal("1000"), "ml", 1)

    def provider(allow_substitutes):
        if allow_substitutes:
            return [
                _cand(offer_row(vero, 1101, "БИТОЛСКИ ЈОГУРТ БИМИЛК 1Л", "1000ml", 1000, "ml", "79.00", False, None, "1.00", PUB_TS, PUB_TS, "https://pricelist.vero.com.mk/89_1.html")),
                _cand(offer_row(stoko, 2101, "ЈОГУРТ БИМИЛК 1Л", "1000ml", 1000, "ml", "65.00", True, "stage2_pending_review_candidate", "0.67", PUB_TS, PUB_TS, "https://stokomak.proverkanaceni.mk/1_1.html")),
            ]
        return []

    repo.offers[201] = provider
    service = BasketOptimizerService(repo)

    resp = service.optimize_basket(BasketOptimizeRequest(
        items=[BasketItemRequest(canonicalProductId=201, retailerProductId=None, itemLabel="Јогурт", quantity=Decimal(1), unit="pack")],
        city=None, retailers=None, maxStores=2, minSplitSavingsMkd=Decimal(0), allowSubstitutes=True, inStockOnly=True,
    ))

    assert len(resp["singleStoreRankings"]) == 2
    # Exact-match store (Vero) ranks above substitute-only store (Stokomak)
    first = resp["singleStoreRankings"][0]
    assert first["retailerSlug"] == "vero"
    assert first["exactMatchesCount"] == 1
    assert first["substitutesCount"] == 0

    stoko_res = resp["singleStoreRankings"][1]
    assert stoko_res["retailerSlug"] == "stokomak"
    assert stoko_res["exactMatchesCount"] == 0
    assert stoko_res["substitutesCount"] == 1
    assert stoko_res["coveredItems"][0]["isSubstitute"] is True
    assert stoko_res["coveredItems"][0]["substituteReason"] == "stage2_pending_review_candidate"
    assert stoko_res["coveredItems"][0]["matchConfidence"] == Decimal("0.67")
