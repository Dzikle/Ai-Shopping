# Open-source reuse audit

Audited 2026-10-28 via GitHub REST API (`/repos/{repo}` and `/git/trees/{sha}`). All four projects are MIT-licensed per GitHub license detection; LICENSE blob SHAs are pinned below so the exact license text version is recorded. **The GitHub project license does not settle retailer data-access terms.**

## Pinned upstream references

| Repository | Default branch | Pinned commit | Commit date | Status | License (blob SHA) |
|---|---|---|---|---|---|
| [KortingKlok](https://github.com/RashadAnsari/KortingKlok) | `master` | `2f951f18754a8e6d2dc7ce1e2fe9511e31e7f459` | 2026-09-14 | **Archived** (read-only; no upstream fixes) | MIT (`caa8fd2d9de36756217b44ffe961bbf8bed96b29`) |
| [open-supermarkets](https://github.com/abracadabra50/open-supermarkets) | `main` | `aff6880435ab3c43f4f79f3896dd4cf40142171c` | 2026-09-28 | Active (129 stars, 31 forks) | MIT (`663742b29726aa0e82e7bac91eeb7f92359d0748`) |
| [checkjebon](https://github.com/supermarkt/checkjebon) | `main` | `efb2e0a8aa99200127397755d825a481d08712e9` | 2026-10-28 | Active (252 stars) | MIT (`f72ca89030778b92dd563a0a06d61d3db3b6ffdb`) |
| [price-scraper](https://github.com/Don-Monteverdi/price-scraper) | `main` | `36d599263ffe4d43c48fdec74693d2faab8198c5` | 2026-03-19 | Low activity (0 stars, single author, AI-co-authored commits) | MIT (`af26c2de6d5c4b358cf59e7dea7207840b432780`) |

## Code-level reuse suitability (exact files at pinned commits)

### KortingKlok — Django/Celery price tracker (NL supermarkets)
Reusable patterns live in `backend/`:
- `backend/apps/products/scrapers/base.py` (1.6 KB) — scraper base class/contract.
- `backend/apps/products/scrapers/dtos.py` (744 B) — scrape-result DTOs.
- `backend/apps/products/scrapers/registry.py` (1.1 KB) — per-retailer scraper registry.
- `backend/apps/products/scrapers/persists.py` (4.1 KB) — result persistence flow.
- `backend/apps/products/scrapers/impls/{ah,jumbo,lidl}.py` — retailer parsers (NL-specific; reference only).
- `backend/apps/products/scrapers/tests.py` + `impls/tests.py` (~34 KB) — fixture-based scraper tests; pattern worth copying.
- `backend/apps/products/models.py` + `migrations/0001_initial.py` — product/price schema (reference for our PostgreSQL design).
- `backend/apps/products/notifications/tasks.py` (7.2 KB) — price-change diffing.

**Decision:** Adapt/reference. Do **not** adopt Django/Celery as our backend (our stack is Spring Boot + independent workers). Copy test structure and scraper-contract ideas with MIT attribution.

### open-supermarkets — TS providers + MCP for AI agents
- `src/providers/types.ts` (6.2 KB) — provider capability interface; strongest candidate for our adapter contract.
- `src/providers/registry.ts` (9.8 KB) + `src/providers/index.ts` — provider registry/capability declarations.
- `src/mcp-server.ts` (29.4 KB) — bounded MCP tool surface; reference for M5.
- `src/batch.ts` (6.7 KB) — batch search across providers.
- `src/enrich/openfoodfacts.ts` (10.8 KB) — GTIN/product enrichment via OpenFoodFacts (open data; relevant to identity resolution).
- `src/commands/basket.ts` — basket interface shape.
- `test/` — test layout reference.

**Decision:** Adapt interfaces and selected code (MIT). No Macedonian sources exist upstream; checkout/slots code is out of scope (we are read-only price intelligence first).

### checkjebon — NL price comparison site
- `js/site/script.js` (15.1 KB) — basket comparison/fuzzy product matching logic (client-side).
- `js/fuse/fuse.js` — vendored Fuse.js fuzzy matching (Apache-2.0/BSD-3 upstream — check vendored license header before reuse).
- `js/tesseract/` — vendored receipt OCR (out of scope for M0–M4).
- `data/` — per-supermarket data files (NL; structure reference only).

**Decision:** Reference/adapt comparison and matching approach with stronger quantity/unit and exactness checks than upstream. Note the vendored third-party libs carry their own licenses; do not copy vendored bundles.

### price-scraper — EAN/GTIN price-intelligence pipeline (HU)
- `pipeline/job_queue.py` (7.6 KB) + `pipeline/worker.py` (6.5 KB) — job queue/worker pattern; reference for our worker contract (we will centralize job state in PostgreSQL instead).
- `price_scraper.py` (12.2 KB) — GTIN extraction, JSON-LD discovery.
- `scrapers/`, `config/`, `tests/` — per-shop scrapers and fixtures.

**Decision:** Adapt extraction/validation utilities and fixture-test layout. Single-author, low-adoption repo — review carefully for quality/security before any code lands.

## Obligations and process for any reuse
1. Record exact upstream commit SHA + file paths in the PR introducing reused code.
2. Preserve MIT copyright/license notices (add `THIRD-PARTY-NOTICES.md` when first code is copied).
3. Run upstream-relevant tests or write equivalent tests for adapted code before merge.
4. Document modification scope and rationale per reused file.
5. Re-verify vendored third-party licenses separately (e.g., Fuse.js inside checkjebon).

## Limitations of this audit
- File sizes/tree SHAs recorded from the GitHub API on 2026-10-28; contents not yet reviewed line-by-line. Deep per-file review happens in M1 when a specific file is actually adapted.
- checkjebon `data/` tree and price-scraper `scrapers/`/`tests/` trees not enumerated yet (low reuse value for M0; enumerate on demand in M1).
