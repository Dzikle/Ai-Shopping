# KAM Market (kam.com.mk) adapter contract (M9)

Source validated 2026-11-08 (see `docs/research/retailer-sources.md` and
`docs/milestones/m9-proposal.md`):

- **Store directory:** `POST https://kam.com.mk/ShopsWeb/LoadShopList`
  (empty body, `Content-Type: application/x-www-form-urlencoded`) returns a
  UTF-8 JSON array with 86 stores: `Id`, `Name`, `Address`, `City,
  `Municipality`, `Coordinates` ("lat, lon" string), `WorkingHours`,
  `ShopFiles[0].RelativePath` (`{YYYY}/{MM}/{DD}/{storeId}.pdf`, uploaded
  ~23:00 the previous evening). `Visible` is always `false` (site quirk;
  ignored). `robots.txt` exists and is empty.
- **Price lists:** one PDF per store,
  `https://kam.com.mk/{Y}/{M}/{D}/{storeId}.pdf` (~1.7–6.7k rows/day;
  fixture samples: 155 pages/store 73, 142 pages/store 46).

## Adapter boundary

`adapters/kam/` converts captured PDFs into the standard Worker Contract v1
artifacts (`snapshots.ndjson`, `records.ndjson`, `manifest.json`). Shared
normalization lives in `adapters/common/`. Standard library only.

## Fixture reference data (pinned, binary-tagged)

`tests/fixtures/kam/` (added `-text` in `.gitattributes`; PDFs also match the
existing `*.pdf binary` rule):

- `shops_2026-11-08.json` — full store-directory response (60,647 bytes);
  source for migration `V5__m9_kam_refs.sql`. Stored with `-text` so content
  hashes stay byte-stable across checkouts.
- `2026-11-08_73.pdf` — 474,381 bytes, 155 pages, store 73 (Скопје, centar).
- `2026-11-08_46.pdf` — 439,218 bytes, 142 pages, store 46 (Штип 2).

## PDF format handled by the parser (fixed statutory sheet, %PDF-1.7)

1. Classic xref table, no ObjStm/XRef streams; one `FlateDecode` content
   stream per page under a leading `1 0 0 1 0 595.3 cm` transform; pages are
   enumerated strictly in `/Pages /Kids` tree order (object numbers differ
   from page order and differ per store file).
2. Two subset TrueType fonts per sheet (`/9` Cyrillic, `/a` latin/digits),
   glyph-coded literal strings restored via per-font `/ToUnicode` CMaps
   (`bfchar`/`bfrange`). Font object numbers differ per store file and are
   derived dynamically.
3. Ruled grid: 10 vertical rules (col edges observed at x = 6 … 800.25) and
   a 14-line horizontal ladder (2-band header of ~117 units + 11 uniform
   data rows of 37.45 units). The bottom-most run of uniform-height bands
   is the data table; everything above it is the statutory two-band header.
4. Column semantics are derived per page from the header labels bucketed by
   grid column (`Назив на стока - производ`, `Продажна цена`,
   `Единична цена`, `Опис на стока`, `Достапност во продажен објект`,
   `Редовна цена`, `Цена со попуст (%)`, `Вид на продажно поттикнување`,
   `Времетраење на промоција или попуст` -> name, sale_price, unit_price,
   description, availability, regular_price, discount_price, promo_type,
   promo_note). The statutory sheet has no separate promo-% column; the
   percentage rides inside the discount cell (`75 ден Попуст : 16%`), parsed
   with `parse_promo_cell`.
5. Text flows with relative `Td` moves (PDF spec); an in-cell line break is
   `|dx| <= 1.5, |dy| in [5, 30]`. Multiple anchored spans inside one grid
   cell are joined in content order; bare "." tokens are dropped.
6. The statutory footnote above the grid ("Датум и време на последно
   ажурирање на цените: DD.MM.YYYY h:MM:SStt", 12-hour AM/PM) is the
   per-page published timestamp; token order may be scrambled, so date and
   time tokens are extracted independently.

## Normalization and record schema

Records use the exact M1/M2 loader field set (adapters/stokomak records).
`price_current` prefers the sale column, falling back to the regular column
(promo-only rows carry the promo price in the sale column with an empty
regular cell — `regular_price` stays `NULL` there). `category` is `NULL`
(the statutory sheet has none). `promo_starts_on`/`promo_ends_on` are set
from the `Времетраење` cell date range when present (`до` separated).

## Known source defects handled

- 13/1697 rows (store 73 sample) have `promo_type` drawn with glyphs the
  latin subset font lacks (question-mark glyph codes present in the PDF
  itself). The adapter stores `promo_type = NULL` for such cells and adds
  a note (`unreadable promo_type cells stored as null`); rows are kept
  because name/price are intact.
- Store `Visible` flag is always `false`; ignored.

## Quarantine rules

Structural failures are never raised to the caller; they quarantine the run:
- unusable PDF structure (no page tree, no pages, inflate failure);
- a page with data rows but no identifiable statutory header;
- statutory columns missing (`name`, `sale_price`, `regular_price`);
- a full source with zero parsed rows.
Exit code `2` for quarantined runs, same as M2 adapters.

## Fetching rules (live mode)

Polite defaults: User-Agent
`Mozilla/5.0 (compatible; AiShopping-M9-ingestion/0.1; +contact: owner)`,
`1.0 s` inter-request delay, POST for the store directory, hard store cap
from `--stores` list. Replay mode reads fixtures only and needs no network.
