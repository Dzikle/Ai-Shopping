# Vero adapter contract (M1)

Source: `https://pricelist.vero.com.mk/` - static HTML price list, validated
2026-10-28 (see `docs/research/retailer-sources.md`). Byte-exact page captures:
`tests/fixtures/vero/` (`index.html`, `89_1.html`, `89_2.html`).

## Adapter boundary

The adapter is the only component that knows Vero's page format. It converts
captured HTML into two flat, retailer-agnostic artifacts:

1. `snapshots.ndjson` - one JSON object per captured document (provenance).
2. `records.ndjson` - one JSON object per offer row (facts observed).

Everything downstream (loader SQL, later services) consumes only these files
and the run `manifest.json`.

## Snapshot object

| field | meaning |
| --- | --- |
| `url` | canonical source URL (`https://pricelist.vero.com.mk/89_1.html`) |
| `url_hash` | sha256(url), hex |
| `content_hash` | sha256(raw stored bytes), hex |
| `storage_path` | file name of the byte-exact capture inside the run dir |
| `content_type` | `text/html; charset=utf-8` |
| `byte_size` | stored byte count |
| `fetched_ts` | UTC ISO-8601; capture time (or fixture replay time) |
| `published_ts` | UTC ISO-8601; from "Последно ажурирање" line, Europe/Skopje |

## Record object

`store_external_key`, `sku_key`, `listing_name`, `category`, `currency`,
`price_current`, `unit_price`, `unit_label`, `regular_price`,
`discount_price`, `discount_pct`, `promo_type`, `promo_starts_on`,
`promo_ends_on`, `availability`, `published_ts`, `source_url`,
`fetched_ts`, `snapshot_url_hash`, `snapshot_content_hash`, `snapshot_idx`.

Normalization decisions (all documented as M1 limitations):

- `currency` is always `MKD` - the price list is denominated in denari and the
  pages do not restate the currency.
- `price_current` = "Продажна цена (со ДДВ)" - VAT included, as published.
- `unit_price`/`unit_label` = "Единечна цена" (e.g. `1255 ден/парче`).
- `availability`: `Да` → `in_stock`, `Не` → `out_of_stock`, anything else →
  `unknown` (never dropped).
- `promo_type`/dates = "Вид на продажно потикнување" and "Времетраење...".
- `sku_key` = sha256(normalized listing name + category). Vero publishes no
  GTIN; name-based keys are the documented M1 limitation and will be replaced
  by identity resolution in M2 (ADR-0003). Product identity and substitution
  remain distinct concepts.
- Name normalization: NFC, collapse whitespace, uppercase. Cyrillic/Latin
  homoglyphs are NOT unified (e.g. `ВАЈTВОТЕР` with a Latin T stays as-is).
- Page header format variations are tolerated: the discount column header on
  page 2 lacks the `(со ДДВ)` suffix that page 1 has; parsing does not depend
  on exact header text.

## Quarantine policy

A discovered page that has a price-list header but zero product rows marks the
whole run `quarantined` (e.g. `tests/fixtures/vero/synthetic_empty_page.html`).
`scripts/load-records.ps1` refuses quarantined runs unless `-Force`. Quarantined
runs are recorded in `ingestion_runs`, never used to delete live offers
(AGENTS.md #6).

## Idempotency

- `raw_snapshots` unique on `(source_slug, url_hash, content_hash)`.
- `price_observations` unique on `(retailer_product_id, store_id,
  published_ts, price_current)` - replaying identical publications is a no-op.
- `offers_current` is an upsert keyed by `(store_id, retailer_product_id)`.
- `promotions` unique on `(retailer_product_id, store_id, promo_type,
  starts_on, ends_on)` with `NULLS NOT DISTINCT`.

## Fetching rules (live mode)

Polite defaults: User-Agent `AiShopping-M1-ingestion/0.1`, 1.0 s inter-request
delay, 50 pages per store, hard abort at 200 pages per run. robots.txt has no
restrictions on this path (validated 2026-10-28).
