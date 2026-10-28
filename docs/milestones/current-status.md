# Project status — 2026-10-28

## Implemented (M0, this session)
- **Dependency verification:** Spring Boot 4.1.2 GA (stable), OpenSearch 3.9.0 (2026-09-29), PostgreSQL 18.6 (current 18.x), Java 21 LTS — all compatible with the planned stack. Recorded in ADR-0001/0002.
- **Upstream reuse audit completed:** all four candidate repos audited at pinned commits (`2f951f1` KortingKlok/archived, `aff6880` open-supermarkets, `efb2e0a` checkjebon, `36d5992` price-scraper), MIT confirmed via license blob SHAs, exact reusable file paths recorded in `docs/research/open-source-reuse-audit.md`.
- **Retailer validation:** Vero pricelist fully validated (static HTML, per-store paginated pages `{storeId}_{page}.html`, unit prices, promotions, last-updated timestamp) → recommended first source; Ramstore blocked by its own site terms pending written consent; KAM format unresolved. See `docs/research/retailer-sources.md` and ADR-0005.
- **ADRs 0001–0005** written in `docs/adr/`.
- **Baseline + CI:** `docker-compose.yml` (PostgreSQL + OpenSearch, image-pinned, healthchecked; images overridable via env for local runs), `scripts/validate-baseline.ps1` (also validates .env parsing and versions), `.github/workflows/ci.yml` (docs check + full stack up --wait + validation + teardown), `.gitattributes` (LF normalization).

## Implemented (M1, this session) — owner-approved
- **Schema `migrations/V1__m1_schema.sql`** (Flyway-compatible naming, applied via psql until Spring Boot adopts Flyway): `retailers`, `stores` (17 Vero/Джамбо stores seeded from the validated index page), `retailer_products`, `ingestion_runs`, `raw_snapshots`, `offers_current`, `price_observations` (immutable, dedup on `(retailer_product_id, store_id, published_ts, price_current)`), `promotions` (`NULLS NOT DISTINCT` for nullable promo dates). NUMERIC(12,2) prices, CHECK constraints, provenance columns (`source_url`, `fetched_ts`, `published_ts`, `raw_snapshot_id`, `run_id`).
- **Vero adapter** (`adapters/vero/`, stdlib-only Python): tolerant HTMLParser for the malformed page markup; 10-column row schema; handles both header variants (page 2 discount column lacks `(со ДДВ)`); pagination links; `Да/Не` → `in_stock/out_of_stock`; Europe/Skopje timestamps (zoneinfo with +01:00 fallback); M1 `sku_key` = sha256(normalized name + category) as documented in ADR-0003.
- **CLI** (`adapters/vero/cli.py`): offline replay (`--from-snapshots`) and polite live fetch (`--url`, 1 s delay, 50 pages/store, hard 200-page cap); byte-exact snapshot storage + `snapshots.ndjson` + `records.ndjson` + `manifest.json`.
- **Quarantine policy:** header-without-rows page → run quarantined; loader refuses to ingest quarantined runs (records run, never deletes live offers — AGENTS.md #6).
- **Loader** (`scripts/load-records.sql` via `scripts/load-records.ps1`): staged COPY of NDJSON into the DB; idempotent inserts/upserts; run finalize.
- **Fixtures:** byte-exact captures of 2026-10-28 committed under `tests/fixtures/vero/` (`89_1.html` 277,348 B, `89_2.html` 287,980 B, `index.html` 3,949 B) + synthetic empty-page fixture for the quarantine test.
- **CI:** unit tests + M1 integration test added to `.github/workflows/ci.yml`.

## Execution evidence (2026-10-28, local)
- Adapter unit tests: `docker run ... python:3.12-slim python -B tests.py` → **22/22 OK** (row counts, first-record values, out-of-stock row, published ts `2026-10-28T08:02:00+01:00`, header variant, pagination, 17 stores, sku_key stability, price/unit/percent/date parsing, replay determinism, quarantine).
- `scripts/test-m1.ps1` → **M1 TEST OK**: fresh `ai_shopping_test` DB, migration applied (1 retailer, 17 stores), first load 1000/1000/1000 (observations/offers/promotions) + 2 snapshots, second identical replay → **0 new observations, 0 new promotions**, all counts stable; asserts passed: observation count = 1000, no duplicates, published_ts round-trip, offers match observations, promotions > 0, snapshots linked, 17 stores, run `completed` with `rows_stored = 1000`.
- Cyrillic text round-trips byte-correctly through NDJSON → COPY → jsonb → psql output (verified in sample query output).
- M0 evidence retained: `BASELINE OK` with PostgreSQL 18.3 (cached image override); OpenSearch full-stack still CI-only (see limitations below).

## Blockers / limitations
- Java, Maven, psql not installed natively on this machine (containers and CI provide them; `maven:3.9.9-eclipse-temurin-21` already cached).
- Docker image pulls fail from agent/automation shells (credential helper requires an interactive session). Workaround used: locally cached images; new images must be pulled by the owner or via CI.
- **No OpenSearch image cached locally** → local full-stack validation deferred to CI (OpenSearch 3.9.0 pinned there).
- M1 `sku_key` is name+category based (no GTIN published by Vero) — replacement by real identity resolution is M2 work (ADR-0003).
- Local Postgres runs 18.3 (cached image) via `POSTGRES_IMAGE=postgres:18.3` override; CI pins 18.6. Same major version; acceptable.
- Local clone lives at `C:\Dev\Personal\ao shopping` (outside OneDrive ✓).

## Resolved owner decisions (from `docs/milestones/m1-proposal.md`)
1. M1 scope approved.
2. Daily fetch window after 08:30 local — accepted (documented in fetching rules).
3. Real Vero HTML fixtures committed — accepted (byte-exact captures).
4. Ramstore: skipped for now; owner may request written consent if ever wanted.

## Next smallest testable task (pending owner approval of M2 scope)
M2 proposal: product identity resolution (replace name-hash keys), OpenSearch projection build (consumer from PostgreSQL), second source (KAM format investigation or consent-based Ramstore).
