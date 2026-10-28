# Stokomak / proverkanaceni.mk adapter contract (M2)

Sources on the shared `*.proverkanaceni.mk` statutory price-check platform
(validated 2026-10-28, see `docs/research/retailer-sources.md` and
`docs/milestones/m2-proposal.md`):

- **Stokomak:** `https://stokomak.proverkanaceni.mk/` (`tests/fixtures/stokomak/`)
- **Zito:** `https://zito.proverkanaceni.mk/` (`tests/fixtures/zito/`)

## Adapter boundary

`adapters/stokomak/` converts captured HTML from `*.proverkanaceni.mk` into the
standard Worker Contract v1 artifacts (`snapshots.ndjson`, `records.ndjson`,
`manifest.json`). Shared normalization lives in `adapters/common/`.

## Format characteristics handled by the adapter

1. **Store discovery (`parse_index`)**:
   - Extracts `<option value="{org}">` entries from `<select name="org">`.
   - Ignores empty `value=""` ("Одберете маркет") and deduplicates repeated
     `org` values.
   - Required for retailers with sparse `org` IDs (e.g., Zito starts at `org=2`
     and returns an empty table for `org=1`).
2. **Query-parameter pagination**:
   - Canonical store page URL: `{base_url}/?org={org}&perPage={perPage}&page={page}`.
   - Pagination links parsed from `<ul class="pagination">`.
3. **Variable column count (`6` vs `9` `<td>` cells)**:
   - Standard rows have **6** `<td>` cells: listing name, selling price, unit
     price, category/description, availability (`Да`/`Не`), regular price.
   - Promotional rows have **9** `<td>` cells: the 6 standard columns plus
     combined discount price + percentage (`299 ден.\n Попуст:23%`), promo type
     (`акциска цена` / `промотивна цена`), and date range
     (`23.10.2026 до \n29.10.2026`).
4. **Unit price normalization (`adapters/common/`)**:
   - `1кгр = 142.00 ден.` -> `unit_price = 142.00`, `unit_label = '1кгр'`
   - `100gr = 43.75 ден.` -> `unit_price = 43.75`, `unit_label = '100gr'`
   - `1пар = 55.00 ден.`  -> `unit_price = 55.00`, `unit_label = '1пар'`
5. **Quarantine**:
   - Pages with a price-table header (`Назив на стока-производ`) and zero
     product rows (including the `Нема податоци за прикажување` notice, e.g.
     `tests/fixtures/zito/empty_1_1.html`) mark the run `quarantined = true`
     and exit with code `2`.

## Fetching rules (live mode)

Polite defaults: User-Agent `AiShopping-M2-ingestion/0.1 (+contact: owner)`,
`1.0 s` inter-request delay, `perPage=100`, 3-store subset per retailer in M2,
hard abort at 200 pages per run.
