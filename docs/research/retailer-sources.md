# Macedonia retailer price source registry

**Validated 2026-10-28** via live HTTP fetches (headless browser). Statuses below reflect verified observations, not assumptions.

## Primary candidates (validation order)

### 1. Vero — VALIDATED, recommended first source
- **Index:** `https://pricelist.vero.com.mk/` — plain static HTML, no JS required.
- **Structure:** per-store pages named `{storeId}_{page}.html` (e.g. `89_1.html`), paginated via "next page" arrow links (`Страна 1 → 89_2.html`).
- **Coverage:** 17 stores listed: ВЕРО 1–14 + ЏАМБО 1–3, each with postal address (addresses verifiable against store registry).
- **Row schema (verified on `89_1.html`):** product name; selling price incl. VAT; unit price (`ден/парче` format); in-store availability (Да/Не); category/description; regular price incl. VAT; discount price incl. VAT; discount %; promo type; promo validity period (date range).
- **Provenance:** page shows `Последно ажурирање: 28/10/2026 8:02` (last-updated timestamp) — usable as retailer-published timestamp. Served with `Cache-Control: no-store`.
- **robots.txt:** content-signals boilerplate only; **no crawl restrictions expressed** (no `Disallow`, no ai-input/ai-train signals).
- **Gaps to resolve in M1:** number of pages per store; whether non-promoted rows omit discount columns consistently (some unit prices empty); no GTIN/barcode column; no brand/size split (must parse from name).
- **Legal note:** price lists of this kind are published for consumers; still log URL + fetch timestamp per snapshot and review ToS before production schedules.

### 2. Ramstore — BLOCKED pending written consent
- **URL:** `https://ramstore.com.mk/` (WordPress; "Види цени" link exists).
- **robots.txt:** standard WordPress — only `/wp-admin/` disallowed; sitemap present.
- **Terms:** site footer states downloading or using content from `ramstore.com.mk`/`ramstoremall.com.mk` (commercial content, logos, trademarks), storing it in any form, publishing or using it for any purpose is **not permitted without written consent from Ramstore Macedonia DOO**.
- **Decision:** Do not ingest until written permission is obtained. Record the request as an owner action item.

### 3. KAM — VALIDATED (2026-11-04); adapter implemented 2026-11-08 (M9, `adapters/kam/`)
- **Landing page:** `https://kam.com.mk/ceni-vo-marketi.nspx` — AngularJS `shopListModule` (`Scripts/Shop/shopList/shopList.min.js`) rendering `/custom-templates/shopList/templates/storesPricelist.html`.
- **Store directory API:** `POST https://kam.com.mk/ShopsWeb/LoadShopList` (`Content-Type: application/json`, body `null`) — returns 60 KB UTF-8 JSON array of **86 stores** (`Id`, `Name`, `Address`, `City`, `Municipality`, `Coordinates`, `WorkingHours`, `Tags`, `ShopFiles[]`). Re-verified 2026-11-08 (today-dated `ShopFiles` entries present for all 86 stores; upload timestamp = 23:00 Europe/Skopje the prior evening).
- **Per-store price-list format:** every store entry carries `ShopFiles[0].RelativePath` of the form `{YYYY}/{MM}/{DD}/{storeId}.pdf` (e.g. `2026/11/08/73.pdf`), downloadable at `https://kam.com.mk/{RelativePath}` (verified `%PDF-1.7`, 425–475 KB per store; 142–155 pages across sampled stores 73 & 46).
- **PDF internal structure (probed with stdlib-only Python on stores 73 & 46 samples):**
  - Classic xref-table PDF (no ObjStm/xref-streams), object numbering varies per store (must scan/dereference by `/Pages` `/Kids` tree, not by sorted object numbers).
  - 0–155 pages; each page = one `FlateDecode` content stream; text via `Tj`/`Ty` literal strings; `Td`/`Tm` positioning; column grid drawn with line/rectangle path operators.
  - Two TrueType subset fonts (`AAAAAA+Tahoma`, `AAAAAB+Tahoma`) per page, glyph-coded strings; each font carries a `ToUnicode` CMap (`beginbfchar`/`beginbfrange`) that fully restores Macedonian Cyrillic + digits (`/9 → obj with cyrillic map`, `/a → digits/latin map`; the mapping is *derived per PDF*, never hardcoded).
  - Extraction proof-of-concept (stdlib `zlib` + operator/CMap walker) reconstructed full rows, e.g. `MILKA-MILKINIS 87.5 ГР … 100 гр = 36.85 ден.`, plus per-store publish timestamp `Датум и време на последно ажурирање на цените: 08.11.2026 5:45:37AM` — usable as authoritative provenance timestamp.
  - All statutory columns are present in the page header: назив на производ, продажна цена, единична цена, цена со попуст, попуст (%), вид на промоција, достапност, опис.
- **robots.txt:** empty (no crawl restrictions). Rate limiting still applies (≥1 s delay/page, IPv4, single daily window).
- **Volume note:** ~1.5–1.7k rows/store/day × 86 stores ≈ 130–145k rows/day; dedup unchanged rows via `price_observations` provenance contract.
- **Next step:** M9 proposal (`docs/milestones/m9-proposal.md`) — stdlib-only PDF adapter; committed byte-exact fixtures for replay tests.

## Other candidates
| Retailer | Starting URL | Status |
|---|---|---|
| Tinex | https://www.tinex.com.mk/ (`ceni.tinex.mk:442`) | Self-hosted statutory price site unreachable (TCP timeout 2026-10-28, 2026-11-04 & 2026-11-08); deferred |
| Stokomak | https://stokomak.proverkanaceni.mk/ | **VALIDATED & INGESTED (M2)** — 81 stores in selector, `?org={org}&perPage={n}&page={k}`, 6/9-col HTML table, no robots restrictions |
| Kipper | https://kipper.mk/mk/marketet/ | WordPress + Elementor + DataTables (`kipper.proverkanaceni.mk` NXDOMAIN); store-level listing URLs to inspect further |
| Konto | https://www.kontomarket.com.mk/cenovnik | **FORMAT IDENTIFIED (2026-11-04)** — Wix page linking stores directly to Tinex's statutory host `https://ceni.tinex.mk:442/?org={org}&search=&perPage=20` (e.g. `org=588, 590, 589, 554, 552`); TCP timeout also re-confirmed 2026-11-08 |
| Reptil | https://www.reptilmarketi.mk/mk/pricelists | **STORE API IDENTIFIED (2026-11-04)** — Next.js frontend backed by WordPress REST `https://cms.reptilmarketi.mk/wp-json/wp/v2/pages/8` (`acf.locations`: 30 stores with addresses/hours; `pricelist` field points to `https://marketonline.mk/`) |
| Elida | https://www.elida.com.mk/Products | Product catalog; full legal price list unconfirmed |
| Zito | https://zito.proverkanaceni.mk/ | **VALIDATED & INGESTED (M2)** — 94 stores in selector (sparse `org` IDs starting at 2; `org=1` returns empty `Нема податоци` table), same `*.proverkanaceni.mk` platform |
| Zur | https://zurmarket.mk/ | Full list unresolved |
| Tamaro | official URL to discover | Full list unresolved |

## Rule
Use fixtures from real allowed publications; log retailer-published timestamps separately from ingestion time; never infer current prices from stale snapshots.
