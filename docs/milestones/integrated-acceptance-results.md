# Integrated acceptance — M12 mobile MVP, M13 AI assistant, M14 web prototype

Date: 2026-11-10
Branch: `integrated-acceptance` (created from `origin/main` at `45ac099`; M13 `141215d` is an ancestor)
Evidence owner: acceptance run executed locally; screenshots committed under `docs/milestones/acceptance-*.png`.

## Scope and environment

| Item | Value |
| --- | --- |
| Backend | FastAPI `backend_py` on `:18089`, real PostgreSQL + OpenSearch |
| Database | `ai_shopping_m10_diff_py` (the only populated local database) |
| OpenSearch | 3.9.0, single node, cluster `green`; reindexed from PostgreSQL with `scripts\reindex-opensearch.ps1 -Database ai_shopping_m10_diff_py` → `REINDEX OK version_tag=20261110111023` |
| Index counts | `stores_v1` 278 · `offers_v1` 5145 · `products_v1` 2660 — identical to PostgreSQL (`/api/v1/health`) |
| Data snapshot | Prices published 2026-10-28 (vero/zito/stokomak) and 2026-11-08 (kam); fetched 2026-11-09; 9 populated stores |
| Web | `web` on `:8090`, `API_BASE_URL=http://127.0.0.1:18089` |
| Mobile | Flutter debug APK `--dart-define=API_BASE_URL=http://10.0.2.2:18089`, emulator `emulator-5554` (Android 15 / API 35), 1080×2400 |
| Assistant | `ASSISTANT_PROVIDER=mock` (no live model credentials configured) |
| Fixture API | **Not used** for any live evidence below |

All checks below ran against the real ingested catalogue. No production deployment and no M15 work was performed.

## Verdict matrix

| # | Flow | Status | Evidence |
| --- | --- | --- | --- |
| A1 | API health, database/OpenSearch parity | PASS | `/api/v1/health` `status=UP`, `activeSearchEngine=opensearch`, counts 278/3525/5145/2660 |
| A2 | Freshness reporting | PASS | `/api/v1/freshness` `DEGRADED`, 9/9 populated stores stale (>48h) — correct for this snapshot |
| A3 | Cyrillic search | PASS | `q=млеко` 79 offers; web `q=јогурт` 20 offers |
| A4 | Latin input normalization | PASS | Raw API `q=mleko` 0 (documented: transliteration is client-side); web `q=jogurt` → 20 offers + transliteration note; Flutter and assistant transliterate correctly |
| A5 | Verified comparison | PASS | `q=јогурт` one verified group: 2 retailers, 4 stores, 3 offers, 40.00–46.00 ден., spread 6.00 ден.; canonical filter returns exactly the requested group |
| A6 | Local basket (web) | PASS | Add from compare detail, badge increments, basket persisted in browser storage |
| A7 | Single-store optimization | PASS | 3 items → best single KAM, 380.00 ден., 3/3 covered, no missing items |
| A8 | Multi-store optimization | PASS | 2 stores (Zito + KAM), 364.00 ден., `savingsVsBestSingleStoreMkd=16.00`, `meetsMinSavingsThreshold=true` |
| A9 | Quantity/unit conversion | PASS | 300 g of a 150 g pack → 2 packs, 80.00 ден. (server-computed) |
| A10 | Missing offers / incomplete basket | PASS | Unknown canonical id → `missingItems[].reason=product_not_found_in_catalog`; coverage reported honestly; empty basket → HTTP 400 `Basket must contain at least one item` |
| A11 | Out-of-stock handling | PASS | Dataset 5102 `in_stock` / 43 `out_of_stock`; `inStockOnly=true` filter accepted |
| A12 | Web console/runtime errors | PASS | Zero `pageerror` / `console.error` across the whole Playwright journey |
| A13 | Web responsive layout | PASS | True 390×844 mobile viewport renders search results without errors |
| B1 | Flutter home on live API | PASS (warm) | `integration_test/app_smoke_test.dart` home test; first cold run failed once, warm rerun green |
| B2 | Flutter Cyrillic + Latin search | PASS | Same suite, live `q` results |
| B3 | Flutter verified compare + detail | PASS | Same suite, `CompareTile` and verified note |
| B4 | Flutter basket → server optimization | PASS | Same suite, server total rendered |
| B5 | Flutter full suite | PASS | 4/4 tests in 1:53 on `emulator-5554` |
| C1 | Assistant ambiguity (real catalogue) | PASS (mock provider) | “млеко” → `needs_clarification`, 3 real options with candidate ids, warnings `mock_provider_demo_only` + `stale_offers` |
| C2 | Assistant explicit selection | PASS (mock provider) | Candidate selection + quantity 2 → `status=ok`, one `isAdd` proposal, `verifiedIdentity=true`, preview Vero 38 ден., `previewOnly=true`, no server-side basket mutation |
| C3 | Assistant explicit confirmation + optimizer | PASS (mock provider) | On-device test: ambiguous “млеко” → pick option → explicit Apply → optimizer result sheet → item present in basket → manual optimize |
| C4 | Assistant Latin input | PASS (mock provider) | `mleko` / `jogurt` transliterated before search; options returned |
| C5 | Assistant live model | NOT VERIFIED | No provider credentials/approval; mock/scripted only |
| C6 | Assistant on physical device | NOT VERIFIED | Emulator only; owner device review still pending |

## Execution commands

```powershell
# Stack (PowerShell; values mirror .env, database is the populated one)
docker compose up -d postgres opensearch
.\scripts\reindex-opensearch.ps1 -Database ai_shopping_m10_diff_py

# Backend
cd backend_py
$env:POSTGRES_DB="ai_shopping_m10_diff_py"; $env:ASSISTANT_PROVIDER="mock"
.\.venv\Scripts\python.exe -m uvicorn app.main:create_app --factory --host 0.0.0.0 --port 18089

# Web
cd web
$env:API_BASE_URL="http://127.0.0.1:18089"; $env:WEB_BASE_URL="http://127.0.0.1:8090"
.\.venv\Scripts\python.exe -m uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8090

# Flutter, live backend on the emulator
$env:ANDROID_HOME="$env:USERPROFILE\android-sdk"; $env:ANDROID_SDK_ROOT="$env:ANDROID_HOME"
flutter test integration_test/app_smoke_test.dart -d emulator-5554 --dart-define=API_BASE_URL=http://10.0.2.2:18089
flutter test integration_test/assistant_mock_test.dart -d emulator-5554 --dart-define=API_BASE_URL=http://10.0.2.2:18089
```

Web journey: an ad-hoc Playwright script (`chromium`, 1280×900 plus a 390×844 mobile context) drove home → search (`јогурт`, `jogurt`, nonsense) → compare → compare detail → add → basket → optimize, asserting rendered server text and collecting console errors. The same journey is reproducible with `web/tools/browser_smoke.py` pointed at the live API instead of the fixture runner.

Representative defect probes:

```powershell
# quantity 0 / negative / unknown unit are accepted and coerced to 1 pack
POST /api/v1/baskets/optimize
{"items":[{"canonicalProductId":2634,"quantity":0,"unit":"pack"}],"allowSubstitutes":false}
# -> 200, bestSingleStore.totalMkd = 40.00

# comparison group mixes fat variants
GET /api/v1/products/compare?q=%D1%98%D0%BE%D0%B3%D1%83%D1%80%D1%82
# -> canonical 2634 "ЈОГУРТ ГРЧКИ 0% 150 Г ОЛИМПУС" includes Vero listing 984 "ЈОГУРТ ГРЧКИ 2% 150ГР ОЛИМПУС"
```

## Prioritized defects

No defect blocked the M12/M13/M14 journeys, so no critical fix branch was created. Candidates for scheduling:

| ID | Severity | Area | Finding | Impact | Suggested action |
| --- | --- | --- | --- | --- | --- |
| D1 | Medium | Basket API validation | `POST /api/v1/baskets/optimize` accepts `quantity=0`, `quantity=-2` and unknown `unit="bottles"`, silently coercing to 1 pack; also accepts a 60-item payload | Guest clients send valid values, but the public contract has no bounds; a buggy/malicious client gets plausible-but-wrong totals | Reject non-positive quantities and unsupported units with 400/422; cap item count; keep coercion only as a documented recovery path |
| D2 | Medium | Product matching precision | Canonical 2634 “ЈОГУРТ ГРЧКИ 0% 150 Г ОЛИМПУС” has an auto-accepted Vero “2%” listing (retailer product 984), so the verified comparison spans 0% and 2% products | User-visible price comparison can mix variants; affects 1 of the 12 multi-retailer groups in this snapshot | Add fat/variant tokens to the identity guard and route these to human review; check confidence threshold for auto-accept |
| D3 | Low | Assistant mock ranking | “млеко” options are led by “ТОРТИЦА БАРНИ МЛЕКО 30ГР”; “кечап полимарк 1кг пица” returns 3 generic ketchup variants instead of the exact 1 kg pick | Mock-provider usability only; live model behaviour is unverified | Improve mock/demo ranking or treat as expected demo limitation in M13 results; keep live-model evaluation as the real gate |
| D4 | Low | Flutter test harness | Home integration test failed once on cold start (`app_smoke_test.dart:48`) and passed on the warm rerun | Test flake, not a product defect | Replace fixed settle windows with a bounded wait-for-`OfferCard` poll |
| D5 | Info | Dataset coverage | Only 12 canonical products have ≥2 verified retailers; “млеко” has no verifiable multi-retailer group, so acceptance used “јогурт” | Comparison coverage is thin until a fuller ingest | Track as data coverage, not a code defect; re-run comparison checks after the next full ingest |
| D6 | Info | Freshness | `DEGRADED` with 9/9 stores stale | Expected for the 2026-10-28/11-08 snapshot at a 48 h threshold | None; the UI badge and API status are truthful |

## Limitations and open items

- M13 live model is **NOT VERIFIED**; every assistant assertion above used the deterministic mock provider and is flagged as such by the UI/API (`mock_provider_demo_only`).
- Mobile acceptance ran on an emulator (Android 15/API 35), not a physical device. Screenshots are supplementary; the integration tests are the functional proof.
- No deployment, no M15, no schema/data changes; PostgreSQL remains authoritative and OpenSearch stayed rebuildable.
- Screenshots: `acceptance-web-{home,search-cyrillic,search-empty,compare,compare-detail,basket,basket-results,mobile-search}.png`, `acceptance-mobile-{home,search,basket,assistant}.png`.
