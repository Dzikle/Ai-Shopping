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
   - Normalizes listing name (NFC, uppercase, whitespace collapsed), strips
     declared package-size tokens, and sorts unique word tokens. Only neutral
     connectors (`ОД`, `ЗА`, `ВО`, `НА`, `И`) are discarded; `СО` and
     `БЕЗ` are preserved because they distinguish product variants.
   - Matcher signature v2 (`m2.v2`): preserves meaningful single-digit tokens
     and encodes percentages as `PCT0`, `PCT2`, `PCT2D5`, etc. Thus
     `0%` and `2%` Greek yogurt do not share an exact identity, while
     `2,0%` and `2%` do. Exact-match method remains `normalized_exact_v1`
     for database contract compatibility; evidence carries matcher v2.
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

## Existing-data reconciliation after signature v2

The signature change produces **new canonical keys** for affected products.
`scripts/load-matches.sql` upserts matches and **does not remove old auto-accepted
mappings**. The unique partial index `uq_product_matches_active_retailer_product`
also means reloading new active identities before detaching old active identities
can fail. **Do not blindly reload against a populated production database.**

1. Run the read-only `scripts/audit-catalog-correctness.sql` and save its output.
2. Back up PostgreSQL and immutable raw snapshots; use a disposable database
   restored from the backup to derive the proposed old→new mapping.
3. Generate matching output with v2 and compare product identity IDs, verified
   statuses, source listing names, pending/manual reviews, history and basket
   references. Produce a per-row dry-run diff with a count of affected records.
4. Review the dry-run, preserve manual approvals/rejections and their audit
   evidence, then require explicit owner approval for a reviewed transactional
   reconciliation script. Do not delete `price_observations` or healthy offers.
5. Only after approved reconciliation, rebuild OpenSearch projections, retest
   comparison/optimizer/history flows and verify existing client basket IDs
   against the new identities. Roll back from the backup on any mismatch.

Code deploy alone **does not repair** already persisted incorrect groupings.
