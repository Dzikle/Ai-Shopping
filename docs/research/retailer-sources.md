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

### 3. KAM — landing page verified, format unresolved
- **URL:** `https://kam.com.mk/ceni-vo-marketi.nspx` — page exists ("Ценовник - КАМ") but content is JS-driven (cookie-consent wall; embedded viewers render empty without JS). Likely an embedded document (possibly PDF).
- **robots.txt:** request returned empty (no restrictions found / possibly no file).
- **Next step:** inspect embedded document URLs behind the viewer (M1); do not attempt JS-heavy scraping until format is confirmed.

## Other candidates (unverified)
| Retailer | Starting URL | Status |
|---|---|---|
| Tinex | https://www.tinex.com.mk/ | Inspect linked full-list destination |
| Stokomak | https://stokomak.proverkanaceni.mk/?org=5 | Structured paginated listing candidate |
| Kipper | https://kipper.mk/ | Store-specific listing candidate |
| Konto | https://www.kontomarket.com.mk/cenovnik | Store-level listing candidate |
| Reptil | https://www.reptilmarketi.mk/ | Store-level links; verify |
| Elida | https://www.elida.com.mk/Products | Product catalog; full legal price list unconfirmed |
| Zito | https://zito.com.mk/ | Full list unresolved |
| Zur | https://zurmarket.mk/ | Full list unresolved |
| Tamaro | official URL to discover | Full list unresolved |

## Rule
Use fixtures from real allowed publications; log retailer-published timestamps separately from ingestion time; never infer current prices from stale snapshots.
