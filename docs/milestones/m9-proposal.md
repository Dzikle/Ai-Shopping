# M9 proposal — KAM adapter: stdlib-only PDF ingestion of daily per-store statutory price lists

**Status:** Owner-approved & implemented (approval given 2026-11-08 for stdlib-only PDF parser, fixture policy, coordinates schema (a) and full M9 scope; implementation completed same day, evidence in `docs/milestones/current-status.md`, `docs/contracts/kam-adapter-contract.md` and `scripts/test-m9.ps1` output).
**Depends on:** M1 (schema + loader contracts), M2 (`adapters/common` normalizers, matching pipeline), M6 (scheduler, quarantine, freshness), M8 (metrics visibility of the new `source_slug`).

## Goal

Ingest **KAM Market** (`kam.com.mk`) daily per-store PDF price lists into the PostgreSQL authoritative tables while keeping the codebase **stdlib-only** (Python 3, `zlib`), reusing the M1/M2 loader, matching, and scheduler machinery:

- Store discovery from `POST https://kam.com.mk/ShopsWeb/LoadShopList` (86 stores with addresses/cities/coordinates).
- Per-store PDFs at `https://kam.com.mk/{YYYY}/{MM}/{DD}/{storeId}.pdf` (today-dated paths from `ShopFiles[0].RelativePath`; ~150 pages, ~1.5–1.7k rows/store/day).
- Authoritative provenance: per-store publish timestamp printed inside every PDF (`Датум и време на последно ажурирање на цените: 08.11.2026 5:45:37AM`) — recorded as `published_ts`/`fetched_ts` per row, never inferred or faked (AGENTS.md #3).

## Owner decisions sought

1. **Stdlib-only PDF parsing (featured decision):** no `pypdf`/`pdfminer`/PyMuPDF dependency. The validation probe shows the PDFs are generator-produced and fully decodable with `zlib` + a small operator/ToUnicode-CMap walker (2 subset fonts per store, glyph-coded strings, uncompressed object scan, classic xref). **Ask:** approve stdlib-only adapter as proposed (fallback option would be adding `pdfminer.six`, which introduces the first non-stdlib runtime dependency into the ingestion layer).
2. **Fixture policy:** commit 2 byte-exact store PDFs (stores `73` & `46`, 2026-11-08 captures, 425–475 KB each) + 1 store-directory JSON snapshot under `tests/fixtures/kam/` (tagged `-binary` in `.gitattributes`). Same policy as Vero/Stokomak M1/M2 fixtures (public consumer price lists; provenance logged). **Ask:** approve.
3. **Store reference schema (KAM has coordinates in the directory API, the `stores` table does not):** options — (a) add optional `latitude`/`longitude` `TEXT` columns via `V5__m9_kam_refs.sql` (explicit, provenance-friendly), or (b) seed only name/address/city and drop coordinates. **Ask:** pick (a) or (b).
4. **Row attribution:** a KAM row has no store-level promo-date columns beyond the promo row type (`promotional` vs standard) — mirroring the proverkanaceni 6/9-column split observed in Stokomak/Zito. **Ask:** confirm reuse of `adapters/common` normalizers so `adapters/kam` records land with identical unit/price/promo semantics.

## Pipeline design (reuse-first)

1. **`adapters/kam/kam.py` (adapter core):**
   - `discover_stores(json_bytes)`: tolerant parse (stdlib `json`), 86 stores → store list identical to M1 Vero store seeding flow.
   - `parse_pdf(pdf_bytes, store_id)`: stdlib-only extraction:
     - Object scan (classic xref-free generator PDF), `zlib` inflate of content streams.
     - Font resources resolved via page `/Resources` → per-font `ToUnicode` CMaps (`beginbfchar`/`beginbfrange`) — **no hardcoded glyph tables**; both sampled stores confirmed full Cyrillic/digit restoration.
     - Operator walk (`Tf/Td/Tm/Tj`) with position tracking → word boxes; table column boundaries derived per page from the drawn gridline path ops (`m/l/re`), matching the drawn table structure — no machine-learning heuristics.
     - Row assembly: cells bucketed by column x-range, then y-row grouping (same convention used by the row layout in each page: statutory column headers printed on every page).
     - Outputs the shared NDJSON record schema identical to `adapters/vero`/`adapters/stokomak` (10-field record rows consumed by `scripts/load-records.sql`), including a quarantine flag on structural anomalies.
2. **`adapters/kam/cli.py`:** `--from-pdf-dir` offline replay (fixtures) and polite live fetch (`--live`) with the M6 delay/backoff context from `adapters/scheduler` (1 s/page default, per-store sequential, `Retry-After` honored), and quarantine on anomaly (empty/unrecognized PDF, page count mismatch).
3. **Loader reuse:** same `scripts/load-records.ps1` staging (provenance + dedup + immutable `price_observations` untouched semantics); `source_slug = 'kam'` with retailer row + 86 stores seeded via `V5__m9_kam_refs.sql`.
4. **Scheduler:** extend `adapters/scheduler` job table with `kam` (same daily 08:30 Europe/Skopje window; KAM PDFs publish ~23:00 the prior evening so the window aligns).
5. **Freshness/metrics:** M6/M7/M8 APIs pick up `kam` automatically once the first successful run records; `GET /api/v1/metrics` shows `aishopping_ingestion_runs_total{source_slug="kam"...}`.

## Tests & fixtures (proposal)

- `adapters/kam/tests.py`: CMap decoder unit tests (synthetic cmap snippets), row-assembly tests on committed byte-exact fixtures (stores 73 & 46 → expected well-formed rows, exact publish timestamps, unit-price parses `{87.5 ГР → 1x87.5g}`, promo rows vs standard rows, empty-page quarantine case via fixture).
- `scripts/test-m9.ps1`: end-to-end replay path — apply migrations incl. `V5`, load, verify uncommitted counts + spot-check a few rows, verify `/freshness` status includes `kam` and the M7 review-queue matching pipeline still treats KAM as second source.

## Risks & unknowns (verifiable before/during implementation)

| Risk | Mitigation |
|------|------------|
| PDF structure drifts across stores (new font subsets, reordered objects) | Derive all object maps dynamically (no hardcoded obj numbers); quarantine unrecognized-but-critical constructs; keep embedded font/CMap-driven decoding |
| Rotated/anti-aliased rows causing column misreads in some pages | Column bucketing uses per-page drawn gridlines (observed consistently); quarantine unknown column layouts instead of misattributing prices |
| Daily volume ~130–145k rows | `price_observations` dedup unchanged rows; OpenSearch reindex limited to current price sets; bounded-batch loader staging as in Vero/Stokomak |
| Visible=False flag on all 86 stores in JSON | Files are delivered publicly and today-dated; visible flag not used as filter (logged as a known quirk in the store-snapshot provenance) |
| Retailer terms change | robots.txt currently empty; polite rates; provenance per fetch; re-check ToS page before production schedule (action item, as with Vero) |

## Non-goals (explicitly out of M9)

- GTIN/barcode enrichment (KAM PDFs carry no barcodes)
- LLM/OCR-assisted parsing — strictly deterministic stdlib code
- Stock-keeping data (`HasStock` flags sit in the directory API but PDFs carry availability independent of stock level)
- Tinex/Konto adapter (still network-blocked; 3rd CHF timeout re-confirmed 2026-11-08)

## Exit criterion

One `scripts/test-m9.ps1` green pass with committed fixtures replays a full KAM run into a migrated DB and produces a non-empty Authority-consistent set (`offers_current` + `price_observations` + `published_ts` from the PDF's own header), with freshness/metrics surfacing `source_slug = 'kam'`.
