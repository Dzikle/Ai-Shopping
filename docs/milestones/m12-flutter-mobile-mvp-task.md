# AI Shopping — M12: Complete Flutter Mobile MVP

**Repository:** https://github.com/Dzikle/Ai-Shopping  
**Starting point:** M10 FastAPI backend + M11 adapted KortingKlok Flutter mobile application.  
**Decision:** Owner approved proceeding to M12 on 2026-11-09, without waiting for M11 Flutter/Android validation.  
**Status:** Implementation authorized; not yet verified.

## Mission

Transform the existing adapted Flutter application into a functional supermarket price-comparison and shopping-basket optimization app for North Macedonia.

**Do not rebuild the Flutter app or restart the project from scratch.** Work autonomously on an isolated M12 branch, reusing existing code and preserving backend behavior.

**Important prerequisite:** Inspect Git state before editing. At the time this document was committed, remote `main` still contained the Java backend, the `m10-fastapi-migration` branch existed, and no M11 branch had been pushed. Locate the actual completed M10 and M11 commits (local or remote), establish correct ancestry, then branch from that combined code. Do not silently recreate or overwrite either milestone. If M11 files are only local, commit/push them to a suitable branch before starting M12. This is a baseline-selection requirement, **not** a demand to run deferred M11 Android validation.

## Explicit validation deferral

The owner has deferred M11 Flutter build and real-device validation. Do not block M12 implementation on installing Flutter SDK, Android SDK, emulator, or M11 sign-off. Run whatever static/unit/API tests the available environment supports, document what cannot be executed, and **never claim a working Android release without build/device evidence**. Do not fabricate screenshots or successful test results.

## Phase 1 — Review existing implementation

Inspect actual mobile source, backend source, schemas and docs, especially:

- `AGENTS.md`
- `docs/architecture/product-delivery-plan.md`
- `docs/milestones/m11-flutter-adaptation-task.md`
- `docs/contracts/search-api-contract.md`
- `docs/contracts/basket-api-contract.md`

Map the existing Flutter screens, widgets, state and API client; use FastAPI's real response schemas (not KortingKlok's old DTOs). Verify support for:

- `GET /api/v1/stores`
- `GET /api/v1/offers/search`
- `GET /api/v1/products/compare`
- `GET /api/v1/products/{canonicalId}/history`
- `POST /api/v1/baskets/optimize`
- `POST /api/v1/baskets/lists`
- `GET /api/v1/baskets/lists/{listId}`
- `POST /api/v1/baskets/lists/{listId}/optimize`

Do not duplicate server-side basket calculations in Flutter. Where an endpoint is not suitable for guest users, prefer local guest state and defer account-dependent features.

## Phase 2 — Product search and comparison

Improve existing search and product-detail flows:

- Search across supported supermarkets; default to all retailers.
- Offer retailer/store filters where supported by the API.
- Support Macedonian Cyrillic and Latin input; do not invent unsupported transliteration.
- Show product name, chain/store, current MKD price, quantity/pack, unit price and publication date where available.
- Show only verified canonical cross-retailer matches as exact comparisons; clearly flag or exclude unverified substitutes.
- Gracefully handle absent images, categories, stock information, product history and canonical matches.
- Show freshness/source information, and warn about stale prices.
- Never synthesize offers, price history, discounts or availability.

**Mapping caution:** `/api/v1/stores` returns an API search-response object, not necessarily the bare list expected by KortingKlok; `/api/v1/products/{id}/history` is a history route, not a general product-detail route. Adapt clients to actual FastAPI payloads.

## Phase 3 — Shopping list management

Create a dedicated **Shopping List** screen where users can:

1. Search and choose an actual catalogue product.
2. Add it to their list.
3. Specify quantity and supported unit.
4. Edit quantity/unit and remove items.
5. Review all items.
6. Save locally and restore across application restarts.
7. Optionally create/load server-persisted lists if supported safely for guests.

Represent items with canonical product IDs or retailer product IDs (not just product names). Units: `pack`, `pcs`, `g`, `kg`, `ml`, `l`.

Guest local persistence is the default. Server-persisted lists must not be assumed private merely because a list ID is hard to guess. Avoid login/Firebase scope.

## Phase 4 — Basket optimization

Integrate `POST /api/v1/baskets/optimize` and present:

- Best single-store recommendation.
- Other single-store rankings.
- Best eligible multi-store combination.
- Total MKD cost and potential savings against the best single-store plan.
- Covered items/count, missing items and reasons.
- Clearly flagged substitutes, with substitutes **off by default**.

Allow optional city/retailer filters, maximum store count within API limits, and explicit substitution opt-in.

Preserve the backend's coverage-first ranking. Do not order partially fulfilled stores above complete stores just because their subtotal is lower. Do not imply full-basket savings if coverage differs, and do not count travel costs unless modeled.

**All authoritative totals, unit conversions, pack scaling and savings come from FastAPI.** Flutter may format/display numbers but must not independently recompute authoritative results.

## Phase 5 — Price history

Add a price-history section to product detail using `GET /api/v1/products/{canonicalId}/history`.

- Show only recorded observations, dates and prices.
- Distinguish retailer/store series when supported.
- Gracefully handle products without canonical IDs or available history.
- A simple chronological list or lightweight chart is sufficient.
- Never interpolate or invent missing values.

## Phase 6 — Navigation, localization and UI

Implement coherent bottom navigation, reusing KortingKlok components and styling:

1. **Home** — offers and supermarkets.
2. **Search** — catalogue and comparisons.
3. **My List** — editable shopping list.
4. **Compare** — optimized basket results.

Cover new UI with Macedonian localization, keeping English optional. Format prices in denars. Handle loading, retry, offline, timeouts, empty responses and stale data. Superseded search requests must not overwrite newer results.

Avoid rebuilding the design system or adding elaborate animations.

## Phase 7 — Reliability and tests

Create tests for product-to-list actions, quantity/unit handling, persistence/restoration, optimizer request serialization, FastAPI response mapping, missing-item explanations, single/multi-store result rendering, MKD formatting, empty/malformed/error responses, navigation and localization.

Use deterministic mock HTTP fixtures for unit/widget tests and exercise actual backend contracts where the environment permits.

Run Flutter analyzer/tests/build **only if tools are available**. List each attempted command, result and blocker. Deferred Android validation is acceptable for implementation delivery but must stay explicitly unverified.

## Phase 8 — Delivery

Update:

- `mobile/README.md`
- `docs/milestones/current-status.md`
- `docs/milestones/roadmap.md`
- `AGENTS.md` if necessary

Create `docs/milestones/m12-results.md` summarizing features, execution evidence, deferred validation and limitations.

Push the M12 implementation branch and open a pull request. Do not merge automatically. No deployment or production data changes.

## Out of scope

- AI chat assistant (M13)
- Separate web frontend (M14)
- Firebase/accounts and push notifications
- Receipt OCR, barcode scanning
- App-store publication
- New retailer adapters
- Major backend rewrite

## M12 implementation acceptance criteria

- Users can create, edit, delete and locally persist shopping lists.
- Real catalogue search items can be added to a list.
- Basket optimizer calls use the correct FastAPI contract.
- Single-store/multi-store rankings and missing items are presented correctly.
- Substitutes remain opt-in and visibly labeled.
- Price history is accessible where it exists.
- New screens are localized in Macedonian.
- Committed code, docs and PR exist.
- Executed checks and deferred Flutter/device tests are separated honestly.

**Implementation completed** does not imply a **verified working Android release**.

## Final agent report

Provide exact commit/PR links, implemented screen inventory, backend API integrations, tests run, tests deferred, defects, and remaining work. Do **not** start M13 without the owner's explicit instruction.

**Proceed with M12 implementation autonomously. Reuse existing M11 code, minimize complexity, preserve backend contracts and deliver reviewable changes.**
