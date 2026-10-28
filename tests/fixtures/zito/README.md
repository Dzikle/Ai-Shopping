# Zito fixtures (byte-exact captures)

Captured 2026-10-28 from `https://zito.proverkanaceni.mk/` via HTTPS GET
with a documented User-Agent (`AiShopping-M2-ingestion/0.1`). Files are raw
response bytes, unmodified (`-text` in `.gitattributes`):

- `index.html` (21,569 B) - store selector directory (sparse `org` IDs starting at 2, 93 `<option>` stores).
- `2_1.html` (148,149 B) - store `org=2` (2 Трговски - Велес), `perPage=100`, `page=1`, 100 product rows (91 standard + 9 promotional rows).
- `2_20.html` (154,994 B) - store `org=2` (2 Трговски - Велес), `perPage=100`, `page=20`, 100 product rows (soups, sauces, pasta — includes overlapping Podravka and Maggi items).
- `2_25.html` (147,782 B) - store `org=2` (2 Трговски - Велес), `perPage=100`, `page=25`, 100 product rows (confectionery — includes overlapping Kadaif Hastel 400g and Milka Croissant Choco 50g).
- `8_1.html` (146,805 B) - store `org=8` (8 Бутел1 - Скопје), `perPage=100`, `page=1`, 100 product rows (93 standard + 7 promotional rows).
- `13_1.html` (143,256 B) - store `org=13` (13 Центар ЗОИЛ - Скопје), `perPage=100`, `page=1`, 100 product rows (96 standard + 4 promotional rows).
- `empty_1_1.html` (23,638 B) - real response for unpopulated `org=1` (`Прикажи 1 - 0 од 0 артикли` / `Нема податоци за прикажување` with table header present), used to verify quarantine detection.
