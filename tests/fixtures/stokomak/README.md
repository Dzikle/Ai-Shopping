# Stokomak fixtures (byte-exact captures)

Captured 2026-10-28 from `https://stokomak.proverkanaceni.mk/` via HTTPS GET
with a documented User-Agent (`AiShopping-M2-ingestion/0.1`). Files are raw
response bytes, unmodified (`-text` in `.gitattributes`):

- `index.html` (18,221 B) - store selector directory (81 `<option>` stores).
- `1_1.html` (139,421 B) - store `org=1` (КИСЕЛА ВОДА), `perPage=100`, `page=1`, 100 product rows (97 standard 6-col rows + 3 promotional 9-col rows).
- `1_3.html` (137,672 B) - store `org=1` (КИСЕЛА ВОДА), `perPage=100`, `page=3`, 100 product rows (includes overlapping national-brand items such as Стоби Флипс 150гр, Супа Алпска 64гр Подравка, Милка Кроасан Чоко 50гр).
- `3_1.html` (140,742 B) - store `org=3` (КАРПОШ 2), `perPage=100`, `page=1`, 100 product rows (96 standard + 4 promotional rows).
- `14_1.html` (139,627 B) - store `org=14` (ЦЕНТАР), `perPage=100`, `page=1`, 100 product rows (97 standard + 3 promotional rows).
