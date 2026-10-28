# Product identity and matching contract (M2 / ADR-0003)

Implements [ADR-0003](../adr/ADR-0003-identity-vs-substitution.md): product
identity is distinct from product equivalence/substitution, and ambiguous
candidates are queued for review rather than silently merged.

## Pipeline stages (`matching/`)

1. **Signature extraction (`extract_signature`)**:
   - Extracts declared pack/unit size via `adapters.common.parse_declared_size`
     and normalizes to canonical base units (`g` for mass, `ml` for volume,
     `{N}x{val}{unit}` for multipacks, e.g. `0.7Л` and `700МЛ` -> `700ml`,
     `4Х0,5Л` and `4х500мл` -> `4x500ml`).
   - Listings without an explicit declared size return `None` and never
     auto-merge across retailers.
   - Normalizes listing name (NFC, uppercase, whitespace collapsed), strips size
     tokens, removes Macedonian prepositions/conjunctions
     (`ОД`, `СО`, `ЗА`, `ВО`, `НА`, `И`, `БЕЗ`), and sorts unique word tokens.
   - Computes deterministic `canonical_key = sha256(normalized_tokens + "\x1f" + normalized_size)`.

2. **Stage 1 — Exact-normalized identity (`normalized_exact_v1`)**:
   - Products with identical `(normalized_tokens, normalized_size)` map to the
     same `canonical_products` record with:
     - `method = 'normalized_exact_v1'`
     - `confidence = 1.000`
     - `review_status = 'auto_accepted'`
     - `evidence` JSONB recording `matcher_version`, `stage`,
       `source_listing_name`, `normalized_tokens`, `normalized_size`,
       `matched_retailers`, and `cross_retailer`.

3. **Stage 2 — Ambiguous candidate review queue (`candidate_token_size_v1`)**:
   - Pairs from different retailers with the **exact same `normalized_size`**
     and high token overlap (`>= 2` shared tokens and Jaccard `>= 0.60` or
     strict token subset, e.g. `ЗЛАТЕН ДАБ СВЕТЛО ПИВО 500мл. ЛИМЕНКА` vs
     `ПИВО ЗЛАТЕН ДАБ 500мл ЛИМЕНКА`) are emitted with:
     - `method = 'candidate_token_size_v1'`
     - `confidence < 1.000`
     - `review_status = 'pending_review'`
     - `evidence` JSONB recording `shared_tokens`, `source_only_tokens`,
       `target_only_tokens`, `normalized_size`, and `jaccard`.
   - `pending_review` rows are **excluded** from cross-retailer price comparison
     queries until explicitly approved (`review_status = 'approved'`).
   - Re-running `scripts/load-matches.ps1` preserves human-reviewed rows
     (`WHERE product_matches.reviewed_at IS NULL`).
