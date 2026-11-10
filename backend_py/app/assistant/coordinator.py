"""Grounded assistant turn orchestration (M13, "Phase 2").

Flow per turn:

1. A provider (or explicit `candidateSelections` echoed from a prior turn)
   yields parsed *labels* to search. The model never returns product IDs,
   prices, stock or totals - only search text.
2. Every label is resolved against the allowlisted read-only tools of the
   shared `McpToolRegistry` (search_products, suggest_product_substitutes),
   bounded by a per-turn tool-call budget.
3. Unambiguous labels become `proposedBasketChanges` built from offer records
   fetched fresh from the catalog; ambiguous labels become `candidateChoices`
   that require an explicit user pick before any proposal exists.
4. A deterministic optimization preview (`optimize_shopping_basket`) may be
   computed over the client's current basket plus the proposed changes. It is
   a preview; nothing is persisted and no totals are invented.

Public clients can only trigger the allowlisted shopping tools; no admin
surface, raw SQL, file access or tool registration is reachable from here.
"""

import datetime as dt
import json
import secrets
from decimal import Decimal

from app.assistant.providers import (
    ALLOWED_UNITS,
    MAX_CONTEXT_CHARS_PER_ENTRY,
    MAX_CONTEXT_ENTRIES,
    MAX_ITEMS_PER_TURN,
    AssistantProvider,
    InterpreterRequest,
    ProviderInvalidResponse,
    ProviderUnavailable,
    provider_info,
)
from app.assistant.transliteration import transliterate_to_cyrillic
from app.schemas.assistant import ASSISTANT_LIMITS

_STALE_HOURS_THRESHOLD = 48.0
_MAX_TOOL_CALLS_PER_TURN = 10  # <= 8 searches + <= 2 bounded extras (substitute probe) - optimizer included
_SEARCH_SIZE = 6
_MAX_CHOICES_PER_AMBIGUOUS_ITEM = 3
_TRIMMED_RANKINGS = 5

_MODEL_UNAVAILABLE_MK = (
    "Асистентот е недостапен: на серверот не е конфигуриран модел "
    "(ASSISTANT_PROVIDER). Локално може да се вклучи детерминистички mock-"
    "интерпретатор со ASSISTANT_PROVIDER=mock; за жив модел се конфигурира "
    "ASSISTANT_PROVIDER=openai_compatible + ASSISTANT_BASE_URL/MODEL."
)


def _new_request_id() -> str:
    return f"asst-{secrets.token_hex(8)}"


class _ToolBudget:
    __slots__ = ("limit", "used")

    def __init__(self, limit: int):
        self.limit = limit
        self.used = 0

    def try_consume(self) -> bool:
        if self.used >= self.limit:
            return False
        self.used += 1
        return True

    @property
    def exhausted(self) -> bool:
        return self.used >= self.limit


class AssistantCoordinator:
    def __init__(self, registry, provider: AssistantProvider | None):
        self._registry = registry
        self._provider = provider

    # ------------------------------------------------------------------ turn

    def run_turn(self, request) -> dict:
        warnings: list[str] = []
        tool_calls: list[dict] = []
        choices: list[dict] = []
        proposals: list[dict] = []
        unresolved: list[dict] = []
        items_considered: list[dict] = []
        stale_seen = False

        # ---- 1. obtain parsed items -------------------------------
        selections = request.candidateSelections or []
        if selections:
            items = [
                _Parsed(
                    label=sel.itemLabel.strip(),
                    query=transliterate_to_cyrillic((sel.query or sel.itemLabel).strip()),
                    quantity=sel.quantity,
                    unit=sel.unit,
                    expected_candidate_id=sel.candidateId,
                )
                for sel in selections[:MAX_ITEMS_PER_TURN]
            ]
            model_message = None
        elif self._provider is None:
            return self._model_unavailable_response()
        else:
            plan = self._plan_via_provider(request)
            if plan.status == "plan":
                model_message = plan.message
                items = [
                    _Parsed(label=p.label, query=p.search_query, quantity=p.quantity, unit=p.unit)
                    for p in plan.items
                ]
            else:
                return self._failure_response(plan.status, plan.message, plan.warnings_extra)
            if "mock_provider_demo_only" not in warnings and self._provider.is_mock:
                warnings.append("mock_provider_demo_only")

        if len(items) > MAX_ITEMS_PER_TURN:
            warnings.append("item_count_bounded")
        items = items[:MAX_ITEMS_PER_TURN]

        # ---- 2. resolve each item against the catalog -------------
        budget = _ToolBudget(_MAX_TOOL_CALLS_PER_TURN)
        needs_clarification = False

        for item in items:
            if budget.exhausted:
                unresolved.append({"label": item.label, "reason": "tool_budget_exhausted"})
                items_considered.append(self._cons(item, "unresolved"))
                continue

            envelope = self._call_tool(
                "search_products",
                {"query": item.query, "size": _SEARCH_SIZE},
                f"search:{item.label[:32]}:{len(tool_calls)}",
                tool_calls,
                budget,
                {"query": item.query},
            )
            document = envelope.get("document")
            if envelope["status"] != "ok" or document is None:
                unresolved.append({"label": item.label, "reason": "search_failed"})
                items_considered.append(self._cons(item, "unresolved"))
                continue

            offers = _sanitize_offers(document.get("items"), item.query)
            if _doc_freshness_is_stale(document):
                stale_seen = True
            if not offers:
                unresolved.append({"label": item.label, "reason": "no_offers_found"})
                items_considered.append(self._cons(item, "unresolved"))
                continue

            outcome = _resolve_one_item(
                self, item, offers, budget, tool_calls, warnings
            )
            if outcome[0] == "proposal":
                resolution, offer = outcome[1], outcome[2]
                if _offer_is_stale(offer):
                    stale_seen = True
                outcome_kind = self._build_proposal(
                    proposals, resolution, offer, item,
                    request.currentBasket or [],
                )
                items_considered.append(self._cons(item, outcome_kind))
            elif outcome[0] == "choices":
                payload = outcome[1]
                needs_clarification = True
                for option in payload["options"]:
                    if _offer_is_stale(option):
                        stale_seen = True
                choices.append(payload)
                items_considered.append(self._cons(item, "needs_clarification"))
            else:
                unresolved.append({"label": item.label, "reason": outcome[1]})
                items_considered.append(self._cons(item, "unresolved"))

        # ---- 3. deterministic preview --------------------------------
        preview = self._optimization_preview(
            proposals, request, budget, tool_calls, warnings
        )

        message = model_message or _compose_status_message(
            needs_clarification=needs_clarification,
            proposed=len(proposals),
            unresolved=len(unresolved),
            choices=len(choices),
            warnings=warnings,
        )

        if stale_seen:
            warnings.append("stale_offers")

        return {
            "requestId": _new_request_id(),
            "status": "needs_clarification" if needs_clarification else "ok",
            "assistantMessage": message,
            "provider": provider_info(self._provider),
            "itemsConsidered": items_considered,
            "candidateChoices": choices,
            "proposedBasketChanges": proposals,
            "unresolvedItems": unresolved,
            "toolCalls": tool_calls,
            "optimizationPreview": preview,
            "warnings": warnings,
            "limits": dict(ASSISTANT_LIMITS),
        }

    @staticmethod
    def _cons(item: "_Parsed", outcome: str) -> dict:
        return {
            "label": item.label,
            "requestedQuantity": item.quantity,
            "requestedUnit": item.unit,
            "outcome": outcome,
        }

    # ------------------------------------------------------- provider call

    def _plan_via_provider(self, request):
        context = [
            {
                "role": e.role if e.role in ("user", "assistant") else "user",
                "content": (e.content or "")[:MAX_CONTEXT_CHARS_PER_ENTRY],
            }
            for e in (request.conversationContext or [])[:MAX_CONTEXT_ENTRIES]
        ]
        basket_labels = [(e.label or "")[:60] for e in (request.currentBasket or []) if e.label][:20]
        interpreter_request = InterpreterRequest(
            message=(request.message or ""),
            locale=request.locale or "mk",
            context=context,
            basket_labels=basket_labels,
        )
        try:
            return _ProviderPlan.ok(self._provider.plan_turn(interpreter_request))
        except ProviderUnavailable:
            return _ProviderPlan.fail(
                "model_unavailable", _MODEL_UNAVAILABLE_MK, ["provider_outage"]
            )
        except ProviderInvalidResponse:
            return _ProviderPlan.fail(
                "model_error",
                "Моделот врати нестандарен одговор и ништо не беше применето; обидете се повторно.",
                ["model_invalid_response"],
            )
        except Exception:
            # Any provider bug must degrade to an honest outage, never a pass.
            return _ProviderPlan.fail(
                "model_unavailable", _MODEL_UNAVAILABLE_MK, ["provider_outage"]
            )

    # ------------------------------------------------------------ resolution

    def _build_proposal(self, proposals: list, resolution: tuple, offer: dict,
                        item: "_Parsed", current_basket: list) -> str:
        canonical_id, retailer_id = resolution
        requested_qty = float(Decimal(str(item.quantity))) if item.quantity is not None else 1.0
        requested_unit = item.unit if item.unit in ALLOWED_UNITS else "pack"

        existing = _matching_basket_entry(current_basket, canonical_id, retailer_id)
        if existing is not None:
            echo_qty = existing.quantity
            echo_unit = existing.unit or "pack"
            try:
                same = (
                    echo_qty is not None
                    and abs(Decimal(str(echo_qty)) - Decimal(str(requested_qty))) <= Decimal("0.0001")
                    and echo_unit == requested_unit
                )
            except Exception:
                same = False
            if same:
                return "already_in_basket"
            proposals.append({
                "changeType": "replace_quantity",
                "itemLabel": item.label,
                "canonicalProductId": canonical_id,
                "retailerProductId": retailer_id,
                "listingName": offer["listingName"],
                "retailerSlug": offer["retailerSlug"],
                "quantity": requested_qty,
                "unit": requested_unit,
                "oldQuantity": float(Decimal(str(echo_qty))) if echo_qty is not None else None,
                "oldUnit": echo_unit,
                "priceCurrentMkd": offer["priceCurrentMkd"],
                "verifiedIdentity": canonical_id is not None,
                "isSubstitute": bool(offer.get("isSubstituteCandidate")),
                "publishedTs": offer["publishedTs"],
                "fetchedTs": offer["fetchedTs"],
                "sourceUrl": offer["sourceUrl"],
            })
            return "replace_quantity"

        proposals.append({
            "changeType": "add",
            "itemLabel": item.label,
            "canonicalProductId": canonical_id,
            "retailerProductId": retailer_id,
            "listingName": offer["listingName"],
            "retailerSlug": offer["retailerSlug"],
            "quantity": requested_qty,
            "unit": requested_unit,
            "oldQuantity": None,
            "oldUnit": None,
            "priceCurrentMkd": offer["priceCurrentMkd"],
            "verifiedIdentity": canonical_id is not None,
            "isSubstitute": bool(offer.get("isSubstituteCandidate")),
            "publishedTs": offer["publishedTs"],
            "fetchedTs": offer["fetchedTs"],
            "sourceUrl": offer["sourceUrl"],
        })
        return "add"

    def _optimization_preview(self, proposals: list, request, budget: _ToolBudget,
                              tool_calls: list, warnings: list):
        basket_entries = request.currentBasket or []
        if not proposals and not basket_entries:
            return None
        preview_items = [
            {
                "canonicalProductId": e.canonicalProductId,
                "retailerProductId": e.retailerProductId,
                "itemLabel": e.label,
                "quantity": float(e.quantity) if e.quantity is not None else 1.0,
                "unit": e.unit or "pack",
            }
            for e in basket_entries
        ]
        replaced_pairs = {
            _pair(p.get("canonicalProductId"), p.get("retailerProductId"))
            for p in proposals
            if p.get("changeType") == "replace_quantity"
        }
        preview_items = [
            e for e in preview_items
            if _pair(e.get("canonicalProductId"), e.get("retailerProductId")) not in replaced_pairs
        ]
        for proposal in proposals:
            preview_items.append({
                "canonicalProductId": proposal.get("canonicalProductId"),
                "retailerProductId": proposal.get("retailerProductId"),
                "itemLabel": proposal.get("itemLabel")[:120],
                "quantity": proposal.get("quantity"),
                "unit": proposal.get("unit"),
            })
        if not preview_items:
            return None

        preferences = request.preferences
        arguments = {
            "items": preview_items,
            "allowSubstitutes": preferences.allowSubstitutes is True if preferences else False,
            "inStockOnly": True,
            "maxStores": preferences.maxStores if preferences and preferences.maxStores else 2,
        }
        if preferences and preferences.city:
            arguments["city"] = preferences.city
        envelope = self._call_tool(
            "optimize_shopping_basket",
            arguments,
            "optimize:preview",
            tool_calls,
            budget,
            {"items": len(preview_items)},
        )
        document = envelope.get("document")
        if envelope["status"] != "ok" or not isinstance(document, dict):
            warnings.append("optimizer_preview_unavailable")
            return None
        rankings = document.get("allSingleStoreRankings")
        if isinstance(rankings, list) and len(rankings) > _TRIMMED_RANKINGS:
            document["singleStoreRankings"] = rankings[:_TRIMMED_RANKINGS]
        elif isinstance(rankings, list):
            document["singleStoreRankings"] = rankings
        document.pop("allSingleStoreRankings", None)
        document["previewOnly"] = True
        return document

    # ------------------------------------------------------------- tool call

    def _call_tool(self, tool: str, arguments: dict, call_id: str,
                   tool_calls: list, budget: _ToolBudget, summary: dict) -> dict:
        if not budget.try_consume():
            tool_calls.append({"tool": tool, "id": call_id, "status": "skipped_budget", "summary": summary})
            return {"status": "skipped", "document": None}
        raw = self._registry.call_tool(tool, arguments)
        parts = raw.get("content") or []
        text = parts[0].get("text") if parts and isinstance(parts[0], dict) else None
        document = None
        if isinstance(text, str) and text.strip():
            try:
                document = json.loads(text)
            except json.JSONDecodeError:
                document = None
        status = "ok" if (not raw.get("isError") and document is not None) else "error"
        tool_calls.append({"tool": tool, "id": call_id, "status": status, "summary": summary})
        return {"status": status, "document": document}

    # -------------------------------------------------------------- statuses

    def _model_unavailable_response(self) -> dict:
        return {
            "requestId": _new_request_id(),
            "status": "model_unavailable",
            "assistantMessage": _MODEL_UNAVAILABLE_MK,
            "provider": provider_info(self._provider),
            "itemsConsidered": [],
            "candidateChoices": [],
            "proposedBasketChanges": [],
            "unresolvedItems": [],
            "toolCalls": [],
            "optimizationPreview": None,
            "warnings": ["model_not_configured"],
            "limits": dict(ASSISTANT_LIMITS),
        }

    def _failure_response(self, status: str, message: str, warnings_extra: list) -> dict:
        return {
            "requestId": _new_request_id(),
            "status": status,
            "assistantMessage": message,
            "provider": provider_info(self._provider),
            "itemsConsidered": [],
            "candidateChoices": [],
            "proposedBasketChanges": [],
            "unresolvedItems": [],
            "toolCalls": [],
            "optimizationPreview": None,
            "warnings": warnings_extra,
            "limits": dict(ASSISTANT_LIMITS),
        }


class _Parsed:
    __slots__ = ("label", "query", "quantity", "unit", "expectedCandidateId")

    def __init__(self, label: str, query: str, quantity, unit, expected_candidate_id: str | None = None):
        self.label = label
        self.query = query
        self.quantity = None if quantity is None else float(quantity)
        self.unit = unit or "pack"
        self.expectedCandidateId = expected_candidate_id


class _ProviderPlan:
    __slots__ = ("status", "items", "message", "warnings_extra")

    def __init__(self, status: str, items: list, message: str | None, warnings_extra: list):
        self.status = status
        self.items = items
        self.message = message
        self.warnings_extra = warnings_extra

    @classmethod
    def ok(cls, plan):
        return cls("plan", plan.items, plan.assistant_message, [])

    @classmethod
    def fail(cls, status: str, message: str, warnings_extra: list):
        return cls(status, [], message, warnings_extra)


def _compose_status_message(needs_clarification: bool, proposed: int,
                            unresolved: int, choices: int, warnings: list) -> str:
    parts: list[str] = []
    if needs_clarification:
        parts.append(
            f"За {choices} производ(и) има повеќе категории/големини; изберете точно производ."
        )
    if proposed:
        parts.append(
            f"Пронајдов {proposed} производ(и) со верифицирани понуди; "
            "проверете ги предлог-промените и потврдете „Примени во кошница“."
        )
    if unresolved:
        parts.append(
            f"{unresolved} барање не можеше да се поврзе со производ од каталогот."
        )
    if not parts:
        parts.append("Не можев да извадам производи од барањето; напишете на пример: „млеко, јајца и леб“.")
    if "mock_provider_demo_only" in warnings:
        parts.append(
            "Напомена: серверот работи со детерминистички mock-интерпретатор (без жив модел); "
            "цените и резултатите доаѓаат од вистинскиот каталог."
        )
    if "stale_offers" in warnings:
        parts.append("Внимание: некои понуди се стара од повеќе од 48 часа.")
    return " ".join(parts)


def _pair(a, b) -> tuple:
    return (a, b)


def _matching_basket_entry(current_basket: list, canonical_id, retailer_id):
    for entry in current_basket:
        echo_canon = entry.canonicalProductId
        echo_retail = entry.retailerProductId
        if canonical_id is not None:
            if echo_canon == canonical_id:
                return entry
        elif retailer_id is not None and echo_canon is None and echo_retail == retailer_id:
            return entry
    return None


def _sanitize_offers(raw, query: str) -> list[dict]:
    if not isinstance(raw, list):
        return []
    offers: list[dict] = []
    for entry in raw[:_SEARCH_SIZE]:
        if not isinstance(entry, dict):
            continue
        canonical_id = _safe_int_or_none(entry.get("canonicalProductId"))
        retailer_id = _safe_int_or_none(entry.get("retailerProductId"))
        offer_id = str(entry.get("offerId") or "")[:64]
        offers.append({
            "candidateId": f"c:{canonical_id if canonical_id is not None else 'u'}:{retailer_id if retailer_id is not None else offer_id}",
            "canonicalProductId": canonical_id,
            "canonicalName": _safe_str(entry.get("canonicalName"), 120),
            "retailerProductId": retailer_id,
            "listingName": _safe_str(entry.get("listingName"), 120),
            "retailerSlug": _safe_str(entry.get("retailerSlug"), 32)[:32] or "unknown",
            "storeName": _safe_str(entry.get("storeName"), 80),
            "storeExternalKey": _safe_str(entry.get("storeExternalKey"), 32),
            "city": _safe_str(entry.get("city"), 60),
            "normalizedSize": _safe_str(entry.get("normalizedSize"), 40),
            "unitPrice": _number_or_none(entry.get("unitPrice")),
            "unitLabel": _safe_str(entry.get("unitLabel"), 20),
            "priceCurrentMkd": _number_or_none(entry.get("priceCurrent")),
            "regularPrice": _number_or_none(entry.get("regularPrice")),
            "discountPct": _number_or_none(entry.get("discountPct")),
            "isPromo": bool(entry.get("isPromo")),
            "availability": _safe_str(entry.get("availability"), 24),
            "publishedTs": _safe_iso(entry.get("publishedTs")),
            "fetchedTs": _safe_iso(entry.get("fetchedTs")),
            "sourceUrl": _safe_str(entry.get("sourceUrl"), 300),
            "isSubstituteCandidate": False,
        })
    return [o for o in offers if o["retailerProductId"] is not None or o["canonicalProductId"] is not None]


def _safe_int_or_none(value):
    if isinstance(value, bool) or value is None:
        return None
    try:
        ivalue = int(str(value).strip())
    except (TypeError, ValueError):
        return None
    return ivalue if ivalue >= 0 else None


def _safe_str(value, limit: int) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return text[:limit]


def _number_or_none(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        return round(float(value), 2)
    except (TypeError, ValueError):
        return None


def _safe_iso(value) -> str | None:
    text = _safe_str(value, 60)
    return text


def _offer_is_stale(offer: dict) -> bool:
    iso = offer.get("publishedTs")
    if not iso:
        return True
    try:
        parsed = dt.datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
    except ValueError:
        return True
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.UTC)
    now = dt.datetime.now(dt.UTC)
    return abs((now - parsed.astimezone(dt.UTC)).total_seconds()) > _STALE_HOURS_THRESHOLD * 3600


def _doc_freshness_is_stale(document) -> bool:
    freshness = document.get("dataFreshness") if isinstance(document, dict) else None
    if not isinstance(freshness, dict):
        return False
    oldest = freshness.get("oldestOfferPublishedTs")
    if not oldest:
        return False
    fake_offer = {"publishedTs": str(oldest)}
    return _offer_is_stale(fake_offer)


def _resolve_one_item(coordinator: "AssistantCoordinator", item: "_Parsed",
                      offers: list[dict], budget: _ToolBudget,
                      tool_calls: list, warnings: list):
    """Resolve one item -> ("proposal", resolution, offer) | ("choices", payload) | ("unresolved", reason)."""
    # An explicit user selection must be honored exactly: the chosen candidate
    # has to still exist in the *fresh* catalog search, otherwise the proposal
    # is refused rather than silently replaced by another offer.
    if item.expectedCandidateId:
        expected = next((o for o in offers if o["candidateId"] == item.expectedCandidateId), None)
        if expected is None:
            return "unresolved", "candidate_not_confirmed"
        resolution = (expected["canonicalProductId"], expected["retailerProductId"])
        return "proposal", resolution, expected

    verified = [o for o in offers if o["canonicalProductId"] is not None]
    by_canonical: dict[int, list[dict]] = {}
    for offer in verified:
        by_canonical.setdefault(offer["canonicalProductId"], []).append(offer)

    in_stock = [o for o in offers if o["availability"] == "in_stock"]
    pool = in_stock or offers

    if len(by_canonical) >= 2:
        return "choices", _choices_payload(
            item, "multiple_products", _per_group_candidates(by_canonical),
        )

    if len(by_canonical) == 1:
        canonical_id = next(iter(by_canonical))
        group = [o for o in pool if o["canonicalProductId"] == canonical_id] or by_canonical[canonical_id]
        best = _cheapest_offer(group)
        if best is None:
            return "unresolved", "no_offers_found"
        if not in_stock and best["availability"] != "in_stock":
            substitute_options = _substitute_options(coordinator, canonical_id, budget, tool_calls)
            if substitute_options:
                warnings.append("substitute_candidates_unverified")
                return "choices", _choices_payload(
                    item, "no_in_stock_offers", substitute_options,
                )
            return "choices", _choices_payload(
                item, "no_in_stock_offers", _options_for([best]),
            )
        return "proposal", (canonical_id, best["retailerProductId"]), best

    # No verified identity. Group by retailer product.
    by_retailer: dict[int, list[dict]] = {}
    for offer in pool:
        if offer["retailerProductId"] is not None:
            by_retailer.setdefault(offer["retailerProductId"], []).append(offer)

    if len(by_retailer) == 1:
        retailer_id = next(iter(by_retailer))
        best = _cheapest_offer(by_retailer[retailer_id])
        if best is None:
            return "unresolved", "no_offers_found"
        return "proposal", (None, retailer_id), best

    if not by_retailer:
        return "unresolved", "no_offers_found"

    return "choices", _choices_payload(
        item, "multiple_unverified", _pick_cheapest_per_listing(by_retailer),
    )


def _substitute_options(coordinator: "AssistantCoordinator", canonical_id: int,
                        budget: _ToolBudget, tool_calls: list) -> list[dict]:
    """Stage-2 substitute candidates for a canonical id without stock.

    The registry returns review-queue records (`pending_review`); they are
    never presented as verified identities. Two bounded extra tool calls:
    one substitute lookup + one supporting search per candidate name.
    """
    envelope = coordinator._call_tool(
        "suggest_product_substitutes",
        {"canonicalProductId": canonical_id, "limit": 3},
        f"substitutes:{canonical_id}",
        tool_calls,
        budget,
        {"canonicalProductId": canonical_id},
    )
    substitutes_doc = envelope.get("document")
    if envelope["status"] != "ok" or not isinstance(substitutes_doc, dict):
        return []
    candidates = substitutes_doc.get("candidates")
    if not isinstance(candidates, list):
        return []

    options: list[dict] = []
    for candidate in candidates[:2]:
        if not isinstance(candidate, dict):
            continue
        candidate_canonical = _safe_int_or_none(candidate.get("candidateCanonicalId"))
        candidate_name = _safe_str(candidate.get("candidateCanonicalName"), 120)
        if candidate_canonical is None or not candidate_name:
            continue
        probe = coordinator._call_tool(
            "search_products",
            {"query": candidate_name, "size": 3},
            f"substitute_search:{candidate_canonical}",
            tool_calls,
            budget,
            {"query": candidate_name},
        )
        probe_doc = probe.get("document")
        if probe["status"] != "ok" or not isinstance(probe_doc, dict):
            continue
        probe_offers = _sanitize_offers(probe_doc.get("items"), candidate_name)
        matching = [o for o in probe_offers if o["canonicalProductId"] == candidate_canonical]
        if not matching:
            continue
        best = _cheapest_offer(matching)
        if best is None:
            continue
        flagged = dict(best)
        flagged["isSubstituteCandidate"] = True
        flagged["matchConfidence"] = _number_or_none(candidate.get("confidence"))
        options.append(flagged)
        if len(options) >= _MAX_CHOICES_PER_AMBIGUOUS_ITEM:
            break
    return options


def _per_group_candidates(by_canonical: dict) -> list[dict]:
    options = []
    for group in by_canonical.values():
        best = _cheapest_offer(group)
        if best is not None:
            options.append(best)
    options.sort(key=lambda o: (o["priceCurrentMkd"] is None, o["priceCurrentMkd"] or 0))
    return options[:_MAX_CHOICES_PER_AMBIGUOUS_ITEM]


def _pick_cheapest_per_listing(by_retailer: dict) -> list[dict]:
    bests: list[dict] = []
    for offers in by_retailer.values():
        best = _cheapest_offer(offers)
        if best is not None:
            bests.append(best)
    bests.sort(key=lambda o: (o["priceCurrentMkd"] is None, o["priceCurrentMkd"] or 0))
    return bests[:_MAX_CHOICES_PER_AMBIGUOUS_ITEM]


def _options_for(offers: list[dict]) -> list[dict]:
    options = sorted(
        offers, key=lambda o: (o["priceCurrentMkd"] is None, o["priceCurrentMkd"] or 0)
    )
    return options[:_MAX_CHOICES_PER_AMBIGUOUS_ITEM]


def _cheapest_offer(offers: list[dict]) -> dict | None:
    if not offers:
        return None
    return sorted(offers, key=lambda o: (o["priceCurrentMkd"] is None, o["priceCurrentMkd"] or 0))[0]


def _choices_payload(item: "_Parsed", reason: str, options: list[dict]) -> dict:
    return {
        "itemLabel": item.label,
        "query": item.query,
        "reason": reason,
        "requestedQuantity": item.quantity,
        "requestedUnit": item.unit,
        "options": options[:_MAX_CHOICES_PER_AMBIGUOUS_ITEM],
    }
