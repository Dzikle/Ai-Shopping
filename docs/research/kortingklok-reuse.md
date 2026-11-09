# KortingKlok reuse audit (M11/M12)

**Upstream:** https://github.com/RashadAnsari/KortingKlok
**Pinned commit:** `2f951f1` (same commit audited in
`docs/research/open-source-reuse-audit.md`, M0). Cloned read-only into an
isolated evaluation directory; nothing upstream is imported at build time and
no upstream backend (Django) code or Firebase configuration was copied.

**License:** MIT (`LICENSE` at repository root, copyright preserved). The
mobile code is adapted, not vendored; attribution is preserved in
(a) file-level header comments on adapted files,
(b) the in-app Settings → Attribution entry,
(c) this document.

## What was retained vs rewritten

| Upstream file | Disposition | Notes |
|---|---|---|
| `mobile/lib/theme/app_colors.dart`, `app_theme.dart` | **Retained (light edits)** | Same design system (orange/dark-blue, flat cards). No upstream branding assets. |
| `mobile/lib/widgets/error_view.dart`, `store_chip.dart` | **Retained (adapted)** | `ErrorView` gained a `message` parameter; chip restyled for retailer slugs. |
| `mobile/lib/l10n/*` structure | **Rewritten (pattern retained)** | Upstream flat-map + delegate approach kept; content replaced with `mk`/`en` price-app strings. |
| `mobile/lib/screens/main_shell.dart` | **Rewritten (pattern retained)** | Upstream shell had Firebase messaging/lifecycle wiring; ours is a plain 5-tab `IndexedStack`. |
| `mobile/lib/services/api_service.dart` | **Rewritten (pattern retained)** | Upstream required `FirebaseAuth.currentUser!` tokens. Ours is guest-first, adds timeouts, typed `ApiServiceException`, response decoding. |
| `mobile/lib/models/*` | **Rewritten** | Upstream `ApiProduct`/`Supermarket`/`Category` match the Django API; replaced with FastAPI contract models (`Offer`, `Store`, `CanonicalComparison`, `ProductHistory`, `FreshnessReport`, basket DTOs). |
| Auth screens (`login`, `register`, `forgot`, `profile`), `auth_service.dart`, `notification_service.dart`, `firebase_*`, `social_button`, `terms_text`, `kk_logo` | **Removed** | Guest-first requirement; no Firebase, no secrets, no upstream branding. |
| Android scaffolding | **Regenerated** (`flutter create`, org `mk.aishopping`) | Upstream package id/manifest not reused. `INTERNET` + cleartext-dev exception only. |
| Assets (logo SVGs, app icon) | **Not copied** | Placeholder programmatic logo until owner-approved branding. |

## Assumptions upstream made that we replaced

1. `${API_HOST}/v1` Django routes (`/products/supermarkets|search|deals|categories`) →
   FastAPI `/api/v1/stores|offers/search|products/compare|products/{id}/history`.
2. `FirebaseAuth.instance.currentUser!.getIdToken()` per request → unauthenticated.
3. EUR/`€` price strings → server decimals rendered as `ден.` by shared formatters.
4. Dutch/English copy → Macedonian-first with `en` fallback (same key set, tested).
5. Supermarket-scoped category drill-down → cross-retailer verified-identity
   comparison (ADR-0003); unverified offers explicitly cannot open a comparison.

## Reuse scorecard

- **Direct visual/UX reuse:** theme, card/chip/error idioms, shell layout —
  high value, low risk.
- **Code reuse:** ~30% of upstream `lib/` survived in adapted form (theme,
  widgets, l10n pattern, screens architecture); models/services/screens logic
  were necessarily rewritten around the FastAPI contracts.
- **Conclusion:** adoption was cheaper than a from-scratch app for the UI
  framework and navigation patterns; the data layer was effectively new work.
  This matches the "not plug-and-play" expectation from the delivery plan.
