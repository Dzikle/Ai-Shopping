# Vero fixtures (byte-exact captures)

Captured 2026-10-28 ~12:00 local (Europe/Skopje) from
`https://pricelist.vero.com.mk/` via HTTPS GET with a documented User-Agent
(`AiShopping-M0-validation/0.1`). Files are the raw response bytes, unmodified:

- `index.html` (3,949 B) - store directory, 17 stores.
- `89_1.html` (277,348 B) - ВЕРО 1, page 1 of 3, 500 product rows.
- `89_2.html` (287,980 B) - ВЕРО 1, page 2 of 3, 500 product rows.
- `synthetic_empty_page.html` - NOT a capture: hand-written minimal page with
  a header and zero product rows, used to unit-test the quarantine policy.

Page-2 rows use the same 10-column layout; its discount column header omits
the `(со ДДВ)` suffix (parser handles both variants). The last-updated line
reads `Последно ажурирање: 28/10/2026 8:02` on both pages.
