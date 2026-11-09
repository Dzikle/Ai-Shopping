"""Basket optimization service - 1:1 port of BasketOptimizerService.java.

Deterministic money math (Decimal, scale 2), coverage-first single-store
ranking, subset-based multi-store split; no redesign.
"""

from decimal import Decimal
from typing import Any

from app.repositories.basket_repository import BasketRepository, CandidateStoreOffer, ProductTargetMeta
from app.services.unit_conversion import compute_packs_needed, normalize_unit, scale
from app.schemas.requests import BasketItemRequest, BasketOptimizeRequest, CreateShoppingListRequest

ZERO = Decimal("0.00")


class _ResolvedBasketItem:
    __slots__ = ("item_index", "canonical_product_id", "retailer_product_id",
                 "requested_name", "requested_quantity", "requested_unit", "target_exists")

    def __init__(self, item_index, canonical_product_id, retailer_product_id,
                 requested_name, requested_quantity, requested_unit, target_exists):
        self.item_index = item_index
        self.canonical_product_id = canonical_product_id
        self.retailer_product_id = retailer_product_id
        self.requested_name = requested_name
        self.requested_quantity = requested_quantity
        self.requested_unit = requested_unit
        self.target_exists = target_exists


class _EvaluatedSubset:
    __slots__ = ("items_covered", "exact_matches_count", "total_mkd", "allocations", "missing_items")

    def __init__(self, items_covered, exact_matches_count, total_mkd, allocations, missing_items):
        self.items_covered = items_covered
        self.exact_matches_count = exact_matches_count
        self.total_mkd = total_mkd
        self.allocations = allocations
        self.missing_items = missing_items


class BasketOptimizerService:
    def __init__(self, basket_repository: BasketRepository):
        self._repo = basket_repository

    def create_shopping_list(self, req: CreateShoppingListRequest) -> dict[str, Any]:
        return self._repo.create_shopping_list(req)

    def get_shopping_list(self, list_id: int) -> dict[str, Any] | None:
        return self._repo.get_shopping_list(list_id)

    def optimize_saved_list(self, list_id: int, overrides: BasketOptimizeRequest | None):
        list_view = self._repo.get_shopping_list(list_id)
        if list_view is None:
            return None
        items = []
        for item in list_view["items"]:
            items.append(BasketItemRequest(
                canonicalProductId=item["canonicalProductId"],
                retailerProductId=item["retailerProductId"],
                itemLabel=item["itemLabel"] if item["itemLabel"] is not None else item["resolvedName"],
                quantity=item["quantity"],
                unit=item["unit"],
            ))
        city = (
            overrides.city
            if (overrides is not None and overrides.city is not None and overrides.city.strip())
            else list_view["cityFilter"]
        )
        req = BasketOptimizeRequest(
            items=items,
            city=city,
            retailers=overrides.retailers if overrides is not None else None,
            maxStores=overrides.maxStores if overrides is not None else None,
            minSplitSavingsMkd=overrides.minSplitSavingsMkd if overrides is not None else None,
            allowSubstitutes=overrides.allowSubstitutes if overrides is not None else None,
            inStockOnly=overrides.inStockOnly if overrides is not None else None,
        )
        return self.optimize_basket(req)

    def optimize_basket(self, req: BasketOptimizeRequest | None) -> dict[str, Any]:
        if req is None or req.items is None or not req.items:
            raise ValueError("Basket must contain at least one item")

        allow_substitutes = req.allowSubstitutes is True
        in_stock_only = req.inStockOnly is None or req.inStockOnly is True
        max_stores = max(1, min(3, req.maxStores)) if req.maxStores is not None else 2
        if req.minSplitSavingsMkd is not None and req.minSplitSavingsMkd >= 0:
            min_split_savings = scale(req.minSplitSavingsMkd, 2)
        else:
            min_split_savings = ZERO

        active_stores = self._repo.find_active_stores(req.city, req.retailers)
        store_by_id = {s["store_id"]: s for s in active_stores}

        total_items = len(req.items)
        resolved_items: list[_ResolvedBasketItem] = []
        per_item_store_lines: list[dict[int, dict[str, Any]]] = []

        for idx, item_req in enumerate(req.items):
            req_qty = (
                item_req.quantity
                if (item_req.quantity is not None and item_req.quantity > 0)
                else Decimal("1")
            ).quantize(Decimal("0.001"))
            req_unit = normalize_unit(item_req.unit)

            meta = self._repo.resolve_product_target(
                item_req.canonicalProductId, item_req.retailerProductId, item_req.itemLabel
            )

            effective_canonical_id = (
                item_req.canonicalProductId
                if item_req.canonicalProductId is not None
                else (meta.canonical_product_id if meta is not None else None)
            )
            requested_name = (
                meta.display_name if meta is not None
                else (item_req.itemLabel if item_req.itemLabel is not None else "Unknown product")
            )

            resolved = _ResolvedBasketItem(
                idx,
                effective_canonical_id,
                item_req.retailerProductId,
                requested_name,
                req_qty,
                req_unit,
                meta is not None,
            )
            resolved_items.append(resolved)

            store_best_map: dict[int, dict[str, Any]] = {}
            if meta is not None:
                candidates = self._repo.find_candidate_offers(
                    effective_canonical_id,
                    item_req.retailerProductId,
                    allow_substitutes,
                    in_stock_only,
                    req.city,
                    req.retailers,
                )
                for cand in candidates:
                    packs_needed = compute_packs_needed(
                        req_qty, req_unit,
                        cand.sku_quantity_value, cand.sku_quantity_unit, cand.sku_pack_count,
                    )
                    line_total = scale(cand.price_current * packs_needed, 2)
                    line = _priced_basket_line(
                        idx, effective_canonical_id, item_req.retailerProductId,
                        requested_name, req_qty, req_unit, cand, packs_needed, line_total,
                    )
                    existing = store_best_map.get(cand.store_id)
                    if existing is None or _is_better_offer_for_store(line, existing):
                        store_best_map[cand.store_id] = line
            per_item_store_lines.append(store_best_map)

        # 1. Evaluate all single stores that cover at least 1 item
        raw_single_stores = []
        for store in active_stores:
            covered = []
            missing = []
            total_mkd = ZERO
            exact_count = 0
            sub_count = 0
            for idx in range(total_items):
                item = resolved_items[idx]
                line = per_item_store_lines[idx].get(store["store_id"])
                if line is not None:
                    covered.append(line)
                    total_mkd = total_mkd + line["lineTotalMkd"]
                    if line["isSubstitute"]:
                        sub_count += 1
                    else:
                        exact_count += 1
                else:
                    reason = (
                        "product_not_found_in_catalog"
                        if not item.target_exists
                        else "no_offer_at_store"
                    )
                    missing.append(_missing_item(item, reason))

            if covered:
                ratio = scale(Decimal(len(covered)) / total_items, 4)
                raw_single_stores.append({
                    "storeId": store["store_id"],
                    "retailerSlug": store["retailer_slug"],
                    "retailerName": store["retailer_name"],
                    "storeExternalKey": store["store_external_key"],
                    "storeName": store["store_name"],
                    "city": store["city"],
                    "itemsCovered": len(covered),
                    "totalItemsRequested": total_items,
                    "coverageRatio": ratio,
                    "totalMkd": total_mkd,
                    "savingsVsHighestCoveredSingleStoreMkd": ZERO,
                    "exactMatchesCount": exact_count,
                    "substitutesCount": sub_count,
                    "coveredItems": covered,
                    "missingItems": missing,
                })

        raw_single_stores.sort(key=_single_store_sort_key)

        max_single_coverage = raw_single_stores[0]["itemsCovered"] if raw_single_stores else 0
        at_max = [s["totalMkd"] for s in raw_single_stores if s["itemsCovered"] == max_single_coverage]
        highest_total_at_max_coverage = max(at_max) if at_max else ZERO

        ranked_single_stores = []
        for s in raw_single_stores:
            if s["itemsCovered"] == max_single_coverage:
                savings = scale(max(
                    highest_total_at_max_coverage - s["totalMkd"], ZERO), 2)
            else:
                savings = ZERO
            ranked_single_stores.append({**s, "savingsVsHighestCoveredSingleStoreMkd": savings})

        best_single_store = ranked_single_stores[0] if ranked_single_stores else None

        best_multi_store_plan = self._compute_best_multi_store_plan(
            resolved_items, per_item_store_lines, store_by_id,
            ranked_single_stores, best_single_store, max_stores, min_split_savings,
        )

        return {
            "totalItemsRequested": total_items,
            "allowSubstitutes": allow_substitutes,
            "inStockOnly": in_stock_only,
            "maxStoresAllowed": max_stores,
            "minSplitSavingsMkd": min_split_savings,
            "bestSingleStore": best_single_store,
            "singleStoreRankings": ranked_single_stores,
            "bestMultiStorePlan": best_multi_store_plan,
        }

    def _compute_best_multi_store_plan(
        self, resolved_items, per_item_store_lines, store_by_id,
        ranked_single_stores, best_single_store, max_stores, min_split_savings,
    ):
        total_items = len(resolved_items)
        if not ranked_single_stores:
            all_missing = [
                _missing_item(
                    item,
                    "product_not_found_in_catalog" if not item.target_exists
                    else "no_offer_at_any_store",
                )
                for item in resolved_items
            ]
            return {
                "storesUsed": 0,
                "itemsCovered": 0,
                "totalItemsRequested": total_items,
                "coverageRatio": Decimal("0.0000"),
                "totalMkd": ZERO,
                "savingsVsBestSingleStoreMkd": ZERO,
                "meetsMinSavingsThreshold": False,
                "recommendationReason": "no_stores_cover_requested_items",
                "storeAllocations": [],
                "missingItems": all_missing,
            }

        candidate_store_ids: list[int] = []
        for s in ranked_single_stores[:10]:
            if s["storeId"] not in candidate_store_ids:
                candidate_store_ids.append(s["storeId"])
        for item_map in per_item_store_lines:
            line_values = sorted(item_map.values(), key=_candidate_order_key)[:5]
            for line in line_values:
                if line["storeId"] not in candidate_store_ids:
                    candidate_store_ids.append(line["storeId"])

        store_pool = candidate_store_ids
        subsets: list[list[int]] = []
        _generate_subsets(store_pool, max_stores, 0, [], subsets)

        best_eval: _EvaluatedSubset | None = None
        for subset in subsets:
            eval_subset = self._evaluate_subset(subset, resolved_items, per_item_store_lines, store_by_id)
            if eval_subset.items_covered == 0:
                continue
            if best_eval is None or _compare_evaluated_subsets(eval_subset, best_eval) < 0:
                best_eval = eval_subset

        if best_eval is None:
            return None

        savings_vs_single = ZERO
        meets_threshold = False
        if best_single_store is None:
            meets_threshold = True
            reason = "multi_store_plan_found"
        elif best_eval.items_covered > best_single_store["itemsCovered"]:
            savings_vs_single = ZERO
            meets_threshold = True
            reason = "higher_item_coverage_across_stores"
        else:
            savings_vs_single = scale(max(
                best_single_store["totalMkd"] - best_eval.total_mkd, ZERO), 2)
            if len(best_eval.allocations) == 1:
                meets_threshold = True
                reason = "single_store_is_already_optimal"
            elif savings_vs_single >= min_split_savings and savings_vs_single > 0:
                meets_threshold = True
                reason = "multi_store_saves_mkd_above_threshold"
            else:
                meets_threshold = False
                reason = "single_store_recommended_split_savings_below_threshold"

        ratio = scale(Decimal(best_eval.items_covered) / total_items, 4)

        return {
            "storesUsed": len(best_eval.allocations),
            "itemsCovered": best_eval.items_covered,
            "totalItemsRequested": total_items,
            "coverageRatio": ratio,
            "totalMkd": best_eval.total_mkd,
            "savingsVsBestSingleStoreMkd": savings_vs_single,
            "meetsMinSavingsThreshold": meets_threshold,
            "recommendationReason": reason,
            "storeAllocations": best_eval.allocations,
            "missingItems": best_eval.missing_items,
        }

    def _evaluate_subset(self, subset, resolved_items, per_item_store_lines, store_by_id):
        by_store: dict[int, list[dict[str, Any]]] = {}
        missing = []
        total_mkd = ZERO
        covered_count = 0
        exact_count = 0

        for idx, item in enumerate(resolved_items):
            store_offers = per_item_store_lines[idx]

            best_line = None
            for store_id in subset:
                candidate = store_offers.get(store_id)
                if candidate is not None:
                    if best_line is None or _is_better_offer_for_store(candidate, best_line):
                        best_line = candidate

            if best_line is not None:
                covered_count += 1
                if not best_line["isSubstitute"]:
                    exact_count += 1
                total_mkd = total_mkd + best_line["lineTotalMkd"]
                by_store.setdefault(best_line["storeId"], []).append(best_line)
            else:
                missing.append(_missing_item(
                    item,
                    "product_not_found_in_catalog" if not item.target_exists
                    else "no_offer_in_selected_stores",
                ))

        allocations = []
        for store_id, lines in by_store.items():
            sh = store_by_id[store_id]
            sub_total = ZERO
            for line in lines:
                sub_total = sub_total + line["lineTotalMkd"]
            allocations.append({
                "storeId": sh["store_id"],
                "retailerSlug": sh["retailer_slug"],
                "retailerName": sh["retailer_name"],
                "storeExternalKey": sh["store_external_key"],
                "storeName": sh["store_name"],
                "city": sh["city"],
                "subtotalMkd": sub_total,
                "items": lines,
            })

        allocations.sort(key=lambda a: a["storeId"])
        return _EvaluatedSubset(covered_count, exact_count, total_mkd, allocations, missing)


def _priced_basket_line(idx, effective_canonical_id, requested_retailer_product_id,
                        requested_name, req_qty, req_unit, cand: CandidateStoreOffer,
                        packs_needed, line_total) -> dict[str, Any]:
    return {
        "itemIndex": idx,
        "canonicalProductId": effective_canonical_id,
        "requestedRetailerProductId": requested_retailer_product_id,
        "requestedName": requested_name,
        "requestedQuantity": req_qty,
        "requestedUnit": req_unit,
        "storeId": cand.store_id,
        "storeExternalKey": cand.store_external_key,
        "storeName": cand.store_name,
        "retailerSlug": cand.retailer_slug,
        "matchedRetailerProductId": cand.retailer_product_id,
        "matchedListingName": cand.listing_name,
        "normalizedSize": cand.normalized_size,
        "packsNeeded": packs_needed,
        "unitPackPriceMkd": cand.price_current,
        "lineTotalMkd": line_total,
        "isSubstitute": cand.is_substitute,
        "substituteReason": cand.substitute_reason,
        "matchConfidence": cand.confidence,
        "publishedTs": cand.published_ts,
        "fetchedTs": cand.fetched_ts,
        "sourceUrl": cand.source_url,
    }


def _missing_item(item: _ResolvedBasketItem, reason: str) -> dict[str, Any]:
    return {
        "itemIndex": item.item_index,
        "canonicalProductId": item.canonical_product_id,
        "retailerProductId": item.retailer_product_id,
        "requestedName": item.requested_name,
        "requestedQuantity": item.requested_quantity,
        "requestedUnit": item.requested_unit,
        "reason": reason,
    }


def _single_store_sort_key(s: dict[str, Any]):
    return (
        -s["itemsCovered"],
        -s["exactMatchesCount"],
        s["totalMkd"],
        s["storeId"],
    )


def _candidate_order_key(line: dict[str, Any]):
    return (line["isSubstitute"], line["lineTotalMkd"], line["storeId"])


def _compare_evaluated_subsets(a: _EvaluatedSubset, b: _EvaluatedSubset) -> int:
    if a.items_covered != b.items_covered:
        return -1 if b.items_covered < a.items_covered else 1  # higher coverage first
    if a.exact_matches_count != b.exact_matches_count:
        return -1 if b.exact_matches_count < a.exact_matches_count else 1  # more exact matches first
    if a.total_mkd != b.total_mkd:
        return -1 if a.total_mkd < b.total_mkd else 1  # lower total MKD first
    if len(a.allocations) != len(b.allocations):
        return -1 if len(a.allocations) < len(b.allocations) else 1  # fewer stores preferred
    for ai, bi in zip(a.allocations, b.allocations):
        if ai["storeId"] != bi["storeId"]:
            return -1 if ai["storeId"] < bi["storeId"] else 1  # lexicographic store ids
    return 0


def _generate_subsets(pool, max_len, start_idx, current, out):
    if current:
        out.append(list(current))
    if len(current) >= max_len:
        return
    for i in range(start_idx, len(pool)):
        current.append(pool[i])
        _generate_subsets(pool, max_len, i + 1, current, out)
        current.pop()


def _is_better_offer_for_store(candidate, existing) -> bool:
    # Exact identity match always takes precedence over a substitute (ADR-0003)
    if candidate["isSubstitute"] != existing["isSubstitute"]:
        return not candidate["isSubstitute"]
    # Higher confidence preferred for substitutes
    if candidate["isSubstitute"]:
        if candidate["matchConfidence"] != existing["matchConfidence"]:
            return candidate["matchConfidence"] > existing["matchConfidence"]
    # Lower total MKD preferred
    if candidate["lineTotalMkd"] != existing["lineTotalMkd"]:
        return candidate["lineTotalMkd"] < existing["lineTotalMkd"]
    return candidate["storeId"] < existing["storeId"]
