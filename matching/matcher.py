"""Deterministic product identity matcher and review-queue candidate generator.

Implements ADR-0003 for M2:
- Stage 1 (normalized_exact_v1): exact normalized word-token bag + canonical
  declared pack/unit size -> auto_accepted (confidence 1.000).
- Stage 2 (candidate_token_size_v1): same canonical declared size + high token
  overlap (Jaccard >= 0.60 or strict token subset with >= 3 shared tokens)
  across different retailers -> pending_review (never silently merged).
- No LLM in the merge path.
"""

from __future__ import annotations

import hashlib
import re
import sys
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from adapters.common import normalize_name, parse_declared_size

MATCHER_VERSION = "m2.v1"

# Macedonian prepositions/conjunctions that vary across retailer listing titles
STOPWORDS = frozenset({"ОД", "СО", "ЗА", "ВО", "НА", "И", "БЕЗ"})

_SIZE_STRIP_RE = re.compile(
    r"(?<![0-9A-Za-zА-Яа-я])(?:\d{1,2}\s*[xхXХ*]\s*)?\d+(?:[.,]\d+)?\s*"
    r"(?:кг|кгр|kg|гр|г|g|gr|мл|ml|л|l)(?![A-Za-zА-Яа-я])\.?",
    re.IGNORECASE,
)
_WORD_TOKEN_RE = re.compile(r"[A-ZА-ЯЃЅЈЉЊЌЏ0-9]+")


def extract_signature(listing_name: str | None) -> dict | None:
    """Extract normalized identity signature from a retailer listing title.

    Returns dict with:
      - tokens: tuple[str, ...] (sorted, deduplicated non-stopword tokens)
      - normalized_tokens: str (space-joined tokens)
      - normalized_size: str (e.g. '150g', '700ml', '4x500ml')
      - quantity_value: str (decimal string in canonical unit)
      - quantity_unit: str ('g' | 'ml')
      - pack_count: int
      - canonical_key: str (sha256 hex of normalized_tokens + normalized_size)
    or None if the title lacks a declared size or usable tokens.
    """
    if not listing_name:
        return None
    size_info = parse_declared_size(listing_name)
    if not size_info:
        return None
    norm = normalize_name(listing_name)
    without_size = _SIZE_STRIP_RE.sub(" ", norm)
    raw_tokens = _WORD_TOKEN_RE.findall(without_size)
    tokens = tuple(
        sorted({t for t in raw_tokens if t not in STOPWORDS and len(t) > 1})
    )
    if not tokens:
        return None
    norm_tokens = " ".join(tokens)
    norm_size = size_info["normalized_size"]
    basis = f"{norm_tokens}\x1f{norm_size}"
    ckey = hashlib.sha256(basis.encode("utf-8")).hexdigest()
    return {
        "tokens": tokens,
        "normalized_tokens": norm_tokens,
        "normalized_size": norm_size,
        "quantity_value": str(size_info["quantity_value"]),
        "quantity_unit": size_info["quantity_unit"],
        "pack_count": size_info["pack_count"],
        "canonical_key": ckey,
    }


def _fmt_conf(val: float) -> str:
    d = Decimal(str(val)).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
    return str(d)


def match_products(products: list[dict]) -> tuple[list[dict], list[dict]]:
    """Run Stage-1 exact matching and Stage-2 candidate generation.

    products: list of dicts with at least:
      {source_slug, sku_key, listing_name, category (optional)}

    Returns (canonical_products, product_matches) ready for NDJSON emission.
    """
    deduped = {}
    for p in products:
        key = (p["source_slug"], p["sku_key"])
        if key not in deduped:
            deduped[key] = p

    ordered_products = sorted(
        deduped.values(), key=lambda x: (x["source_slug"], x["sku_key"])
    )

    by_ckey: dict[str, list[tuple[dict, dict]]] = {}
    for prod in ordered_products:
        sig = extract_signature(prod.get("listing_name"))
        if sig is None:
            continue
        by_ckey.setdefault(sig["canonical_key"], []).append((prod, sig))

    canonical_list: list[dict] = []
    matches_list: list[dict] = []

    for ckey in sorted(by_ckey.keys()):
        members = by_ckey[ckey]
        first_prod, sig = members[0]
        retailers_in_group = sorted({m[0]["source_slug"] for m in members})
        canonical_name = min(
            (m[0]["listing_name"] for m in members),
            key=lambda s: (len(s), s),
        )
        canonical_list.append(
            {
                "canonical_key": ckey,
                "canonical_name": canonical_name,
                "normalized_tokens": sig["normalized_tokens"],
                "normalized_size": sig["normalized_size"],
                "quantity_value": sig["quantity_value"],
                "quantity_unit": sig["quantity_unit"],
                "pack_count": sig["pack_count"],
                "gtin": None,
            }
        )
        for prod, _ in members:
            matches_list.append(
                {
                    "source_slug": prod["source_slug"],
                    "sku_key": prod["sku_key"],
                    "canonical_key": ckey,
                    "method": "normalized_exact_v1",
                    "confidence": "1.000",
                    "review_status": "auto_accepted",
                    "evidence": {
                        "matcher_version": MATCHER_VERSION,
                        "stage": "stage1_exact_normalized",
                        "source_listing_name": prod["listing_name"],
                        "normalized_tokens": list(sig["tokens"]),
                        "normalized_size": sig["normalized_size"],
                        "matched_retailers": retailers_in_group,
                        "cross_retailer": len(retailers_in_group) >= 2,
                    },
                }
            )

    # Stage 2: Candidate generation for singleton groups -> pending_review queue
    # Compare across different retailers sharing the exact same normalized_size.
    by_size: dict[str, list[tuple[str, list[tuple[dict, dict]], set[str]]]] = {}
    for ckey, members in by_ckey.items():
        sig = members[0][1]
        by_size.setdefault(sig["normalized_size"], []).append(
            (ckey, members, set(sig["tokens"]))
        )

    seen_candidates = set()
    for norm_size, groups in sorted(by_size.items()):
        if len(groups) < 2:
            continue
        for i, (ckey_a, members_a, tokens_a) in enumerate(groups):
            rets_a = {m[0]["source_slug"] for m in members_a}
            for j, (ckey_b, members_b, tokens_b) in enumerate(groups):
                if i == j or ckey_a == ckey_b:
                    continue
                rets_b = {m[0]["source_slug"] for m in members_b}
                if rets_a == rets_b:
                    continue
                shared = tokens_a & tokens_b
                if len(shared) < 2:
                    continue
                union = tokens_a | tokens_b
                jaccard = len(shared) / len(union)
                is_subset = (tokens_a < tokens_b or tokens_b < tokens_a) and len(shared) >= 2
                if jaccard < 0.60 and not is_subset:
                    continue
                conf = _fmt_conf(min(jaccard, 0.95))
                target_name = members_b[0][0]["listing_name"]
                for prod_a, _ in members_a:
                    if prod_a["source_slug"] in rets_b:
                        continue
                    cand_id = (prod_a["source_slug"], prod_a["sku_key"], ckey_b)
                    if cand_id in seen_candidates:
                        continue
                    seen_candidates.add(cand_id)
                    matches_list.append(
                        {
                            "source_slug": prod_a["source_slug"],
                            "sku_key": prod_a["sku_key"],
                            "canonical_key": ckey_b,
                            "method": "candidate_token_size_v1",
                            "confidence": conf,
                            "review_status": "pending_review",
                            "evidence": {
                                "matcher_version": MATCHER_VERSION,
                                "stage": "stage2_candidate_review_queue",
                                "source_listing_name": prod_a["listing_name"],
                                "target_canonical_name": target_name,
                                "shared_tokens": sorted(shared),
                                "source_only_tokens": sorted(tokens_a - tokens_b),
                                "target_only_tokens": sorted(tokens_b - tokens_a),
                                "normalized_size": norm_size,
                                "jaccard": float(conf),
                            },
                        }
                    )

    return canonical_list, matches_list
