# ADR-0003: Product identity separate from equivalence/substitution

- **Status:** Accepted (2026-10-28)
- **Context:** Comparing prices meaningfully requires knowing two retailer products are the *same* product, not merely similar. Auto-merging similar products corrupts comparisons and price history. Retailer listings in MK sources mostly lack GTINs.
- **Decision:** Exact identity is asserted only with verified evidence: GTIN/EAN where checkable, plus variant/pack-size checks; otherwise deterministic normalized-attribute rules, and LLM assistance only to *review* ambiguous candidate pairs (never to auto-merge). Substitutes/equivalents ("any 1.5L cola") are a separate relation, computed and labeled as such, never folded into identity.
- **Consequences:** `ProductMatch` carries method, confidence, evidence and review status. M2 matching must produce evidence, not silent merges. Ambiguous pairs queue for review instead of guessing.
