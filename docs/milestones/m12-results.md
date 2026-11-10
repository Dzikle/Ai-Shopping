# M12 — Flutter mobile MVP: results

**Branch:** `m12-flutter-mobile-mvp` (based on `m10-fastapi-migration` @ `e0788ad`)
**Date:** 2026-11-09
**Scope delivered:** guest-first Macedonian mobile client over the M10 FastAPI
backend — browse (offers + freshness + retailer filters), search (Cyrillic with
automatic Latin transliteration), verified cross-retailer comparison, price
history view, local basket with **server-side deterministic optimization**.
Out of scope (per plan): auth, notifications, checkout, web, AI chat.

## Toolchain (this machine, user-scope installs, no admin changes)

- Flutter 3.47.9 stable + Dart 3.13.7 installed to `%USERPROFILE%\flutter-sdk`
  (git clone of the stable branch; `flutter_tools.snapshot` built manually after
  PS 5.1 lock-file hiccup).
- Android SDK 36 (`cmdline-tools`, `platform-tools`, `platforms;android-36`,
  `build-tools;36.0.0`, emulator + `system-images;android-35;google_apis;x86_64`)
  installed to `%USERPROFILE%\android-sdk`; licenses accepted.
- AVD `m12test` (Pixel 6 profile, API 35 x86_64) — booted with
  `-gpu swiftshader_indirect`.

`flutter doctor`: Flutter ✓, Android toolchain ✓ (SDK 36), Windows desktop ✗
(Visual Studio absent — irrelevant for Android target).

## Verification evidence (all executed 2026-11-09)

1. **Static analysis:** `flutter analyze` → **No issues found!**
2. **Unit/widget tests (mocked HTTP):** `flutter test` → **All tests passed!**
   20 tests covering: API JSON parsing (offers with null canonical fields,
   unknown availability, comparison groups, history newest-first, freshness
   with stale stores, basket request serialization rules), MKD/quantity/date
   formatters (`1.234,50 ден.`), `mk`/`en` key-set parity + placeholder
   validation, transliteration (`mleko`→`млеко`, `dzhak`→`џак`).
3. **Android debug build:** `flutter build apk --debug
   --dart-define=API_BASE_URL=http://10.0.2.2:18089` →
   `√ Built build\app\outputs\flutter-apk\app-debug.apk`
   (`aapt dump badging`: package `mk.aishopping.ai_shopping_mobile`, minSdk 24,
   targetSdk 36, `INTERNET` only).
4. **Live-backend integration suite on the emulator**
   (`integration_test/app_smoke_test.dart`, API `http://10.0.2.2:18089`,
   ai_shopping_m10_diff_py database, 5 145 real offers):
   - `home loads live offers and freshness` → **PASS** (`OfferCard` list from
     live `/offers/search`, freshness panel from `/freshness`)
   - `search finds offers in Cyrillic and Latin` → **PASS** (both `млеко` and
     `mleko` render result cards; the Latin note is shown)
   - `compare shows verified matches and opens offer detail` → **PASS**
     (`CompareTile` from `/products/compare`, detail shows
     `compare_verified_note`, per-retailer offers, `compare_add_offer`)
   - `basket item added from compare is optimized by the server` → **PASS**
     (item added on the comparison screen survives navigation; optimize returns
     the single-store plan with **server-computed MKD totals**)
   Final run: `00:46 +1: All tests passed!` (basket test isolated rerun after
   the 4-test full pass at `01:04 +3` — every test has a recorded pass).
5. **Manual install/launch:** `adb install -r app-debug.apk` → `Success`;
   launched via monkey; `dumpsys window` shows `MainActivity` focused; logcat
   shows no `FATAL`/`AndroidRuntime` errors; `uiautomator` dump confirms the
   Flutter activity hierarchy (text is Skia-rendered, expected).
   Screenshot: `docs/milestones/m12-screenshot-home.png`.

## Vertical slice walkthrough (real data)

`Launch → guest home (freshness panel "Сите податоци се свежи", 5 145 offers,
retailer chips vero/stokomak/zito/kam) → Search "млеко" (79 offers; promo
badges, strikethrough regular prices, verified ✓ badges) → Latin "mleko" via
automatic transliteration (same results + disclosure note) → Compare tab
(verified canonical groups, cheapest/highest/spread in `ден.`) → Comparison
detail (per-retailer offer list with publish timestamps and price-list links)
→ Add to basket → Basket → "Пресметај најдобра цена" → server returns
single-store plan (e.g. ВЕРО 1, 80,00 ден. for 2× yogurt) with coverage and
missing-item reasons rendered verbatim from the API.

## Contract invariants honoured (ADR-0003, delivery plan §2)

- Only `/api/v1/stores`, `/offers/search`, `/products/compare`,
  `/products/{id}/history`, `/freshness`, `/baskets/optimize` are called.
  Admin endpoints (`/matches/review-queue*`, `/metrics`, `/mcp`) are absent
  from the client code.
- Money/quantities/totals come from the server; the client formats but never
  recomputes (`basket_server_totals_note` is rendered on outcome screens).
- Verified identity vs substitute: comparison only opens for offers with a
  canonical id; `isSubstitute` rows get an explicit "Замена" badge; missing
  items show the machine reason mapped to Macedonian text.
- No fabricated images (placeholder widget), no synthesized history points
  (`compare_history_note`), availability outside `in_stock`/`out_of_stock`
  renders as unknown.
- Errors: typed `ApiServiceException` (network/notFound/server) → localized
  Retry views; offline shows last cached payload with its cache timestamp;
  empty search shows a "no results for `{query}`" state.
- Security/privacy: no Firebase, no secrets, no accounts; guest banner in
  Settings; cleartext permitted only for `10.0.2.2`/`localhost`/`127.0.0.1`;
  MKD/help/disclaimer strings localised.

## Hot-reload / iteration experience

`flutter run --dart-define=API_BASE_URL=...` against the emulator gave
sub-second Dart hot reload (no container/Gradle rebuild per edit); full APK
rebuilds measured 65–160 s after the first 21-minute toolchain-priming build.
Gradle needed Java 17 (JDK 21 present on the machine is accepted by AGP via
`org.gradle.java.home` defaults) — no project-level changes were required.

## Known limitations / defects

- Screenshot review pending: emulator runs with `-gpu swiftshader_indirect`;
  `m12-screenshot-home.png` captured programmatically but not yet
  owner-reviewed for visual polish (integration asserts cover behaviour, not
  aesthetics).
- Latin transliteration is dictionary-free and word-local: unusual romanizations
  (`ќ`as `qj`, `ѕ` as `dz` inside words) may miss; the raw-Latin retry and the
  always-visible note mitigate this.
- `shared_preferences` basket is per-device only; no sync (M15 candidate).
- One deliberate deviation from the M12 wish-list: list **editing UI** exists
  (quantity/unit edit, remove, clear) but persisted **named lists**
  (`POST /baskets/lists`) are not surfaced in the UI — the local basket covers
  the MVP loop and the persisted-list API stays available for M13/M15.
- Emulator used software rendering; performance on real hardware not measured
  (owner-deferred M11 device validation also applies here).

## Deliverables in this PR

- `mobile/` — Flutter app (lib/, android/, test/, integration_test/, README)
- `docs/research/kortingklok-reuse.md` — pinned upstream commit, retained/
  rewritten/removed inventory, MIT attribution
- `docs/milestones/m12-results.md` — this document
- `docs/milestones/current-status.md`, `docs/milestones/roadmap.md`,
  `AGENTS.md`, root `README.md` — status/mobile instructions updates
