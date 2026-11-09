# M11–M12 — KortingKlok Flutter Mobile Adaptation (Agent Tasks)

**Status:** Proposed, not started. **Dependency:** M10 parity verified and merged, or a stable API mock with fixed contracts for an isolated M11 spike.

## M11 — Feasibility / code reuse spike (research + runnable proof)

1. Pin exact upstream commit of https://github.com/RashadAnsari/KortingKlok. Verify its MIT license, transitive third-party notices, Flutter/Dart version and Android build tooling.
2. Clone into an isolated evaluation directory; **do not overwrite AI Shopping source**. Run `flutter pub get`, `flutter analyze`, `flutter test`, Android debug build. Record failures and root causes.
3. Create a mockable HTTP transport and inject typed responses from AI Shopping's documented endpoints. Run without a live Firebase account by isolating auth, crash reporting and push initialization (no upstream secrets copied).
4. Inventory and score these modules: `mobile/lib/screens/{home_screen,search_screen,api_product_detail_screen,main_shell}.dart`, `widgets/`, `theme/`, `l10n/`, `models/`, `services/api_service.dart`, `test/`.
5. Identify all upstream-specific assumptions: API prefix `${API_HOST}/v1` versus `/api/v1`, original `/products/supermarkets|search|deals|categories` routes, hard-required `FirebaseAuth.currentUser!`, EUR (`€`) display, Dutch/English strings, product pictures/category fields not always available.
6. Wire **one vertical slice** against FastAPI: list stores → search live/replay catalogue → view product/offer comparison with MKD and timestamp. Add explicit stale/error/empty responses. Keep unauthenticated browsing working.
7. Compare actual reuse effort with a new Flutter app or a small React Native prototype, only if the KortingKlok code proves costly. Document conclusion; never claim it is already plug-and-play.

**Exit:** Flutter can run with guest-accessible AI Shopping data on Android; test results, screenshots, adaptation inventory and owner go/no-go review. A fake-only UI demonstration does not complete M11.

## M12 — Mobile user-facing MVP (after approval)

- Rebrand UI, icons, package name/bundle ID; remove upstream names/assets where unsuitable, keeping required license notices.
- Add Macedonian (`mk`) text, MKD currency, correct decimal and quantity formatting, Cyrillic/Latin search, accessibility labels.
- Guest-first homepage with promotions and current/freshness indicators; browse all supermarkets; store and city filters.
- Product search and detail; compare verified canonical matches across retailers, showing store, normalized pack, unit-price, stock/unknown, `publishedTs`, and `sourceUrl`.
- Price-history view using existing history endpoint; never synthesize missing datapoints.
- Shopping list creation/editing, quantity and unit selection, single-store and multi-store optimization with missing-item explanation; server controls numeric totals.
- Separate real identity from explicitly labeled substitutes; do not silently show Stage-2 candidate as exact.
- Device state tests: offline, slow API, empty search, stale sources, unknown image/availability, process restart, changed selected store.
- Generate or hand-maintain a typed API client with schema tests based on FastAPI OpenAPI. Keep auth and notifications optional behind adapters until a follow-on milestone.

**Exit:** End-to-end Android interaction using a real API and current/fixture data, `flutter analyze`, `flutter test`, Android smoke suite, M4 optimizer totals identical to backend. Do not require an app-store release yet.

## Later features, not silently included in M12

- User accounts, saved remote lists, FCM price alerts and follow product behavior (explicit auth/consent decision).
- In-app AI chat that writes to the *UI basket* through explicit user confirmation and backend-grounded results (M13).
- Flutter Web viability study; upstream mobile repository has Android/iOS but no existing `web/` project scaffolding (M14).
- Receipt OCR and barcode enrichment (M15, privacy and quality review).