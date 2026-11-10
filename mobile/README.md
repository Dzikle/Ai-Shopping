# AI Shopping Mobile (Flutter)

Guest-first Flutter client for the AI Shopping FastAPI backend. Adapted from
[KortingKlok](https://github.com/RashadAnsari/KortingKlok) (MIT) — see
`docs/research/kortingklok-reuse.md` for the exact reuse inventory and license
obligations.

## What it does (M12 scope)

- Guest browsing, no account / Firebase / sign-in
- Home: data-freshness panel (`GET /api/v1/freshness`), retailer filter chips
  (`GET /api/v1/stores`), promo-only filter and paginated offer feed
  (`GET /api/v1/offers/search`)
- Search: Cyrillic input plus automatic Latin → Cyrillic transliteration
  (`mleko` → `млеко`), in-stock / promo filters, price sorting
- Compare: verified cross-retailer matches only (`GET /api/v1/products/compare`),
  offer detail with per-retailer offers and real price observations
  (`GET /api/v1/products/{id}/history`) — no synthesized datapoints
- Basket: local item list (quantity/unit), deterministic single-store and
  multi-store optimization computed **server-side**
  (`POST /api/v1/baskets/optimize`); totals are never recomputed in the client
- MKD (`ден.`) formatting, Macedonian (`mk`) and English (`en`) locales,
  light/dark/system theme — persisted locally via `shared_preferences`
- Offline banner + last-cached data when the backend is unreachable; explicit
  loading / empty / stale / error states on every screen
- **AI tab (M13):** chat screen calling only
  `POST /api/v1/assistant/turn` (`lib/screens/assistant_screen.dart`). The
  assistant proposes basket changes as a reviewable diff; **only the Apply
  button mutates the local basket**, after which the same server-side
  optimizer is invoked for authoritative totals. Ambiguous products show
  grounded option cards; substitutes are explicitly tagged; stale-basket
  proposals and `model_unavailable` are handled honestly. Provider info
  (`isMock`) is shown as a demo badge when applicable. No AI keys in the app;
  the assistant provider is configured server-side only.

Not in scope: authentication, push notifications, checkout, list editing with
remote persistence.

## Prerequisites

- Flutter SDK 3.47.x / Dart 3.13 (`flutter doctor` must show the Android
  toolchain as green)
- Android SDK 36 installed (`ANDROID_HOME` set)
- A reachable AI Shopping FastAPI instance (see repo root `README.md`)
- Create `mobile/android/local.properties` (`flutter.sdk=...`) automatically by
  running any `flutter` command once; it is machine-specific and not committed

## Run

```powershell
cd mobile
flutter pub get

# API base URL for the build (Android emulator reaches the host via 10.0.2.2):
flutter run --dart-define=API_BASE_URL=http://10.0.2.2:8000
# physical device on the same LAN:
flutter run --dart-define=API_BASE_URL=http://<your-lan-ip>:8000
```

Defaults if the flag is omitted: `http://10.0.2.2:8000` (emulator → host).

Hot reload works as usual (`r` in the run console / IDE save); no container or
APK rebuild is needed for Dart changes.

## Test / analyze / build

```powershell
flutter analyze
flutter test                                     # unit + widget tests (mocked HTTP)
flutter test integration_test/app_smoke_test.dart -d emulator-5554 `
  --dart-define=API_BASE_URL=http://10.0.2.2:18089   # live-backend smoke suite
flutter build apk --debug --dart-define=API_BASE_URL=http://10.0.2.2:8000
```

The integration suite asserts real, observable behaviour against the running
backend: live home feed + freshness, Cyrillic and Latin search, verified
comparison detail, and server-computed basket totals in MKD.

## Cleartext traffic

`android/app/src/main/res/xml/network_security_config.xml` permits cleartext
**only** to `10.0.2.2`, `localhost`, `127.0.0.1` so local dev backends work;
everything else keeps Android's HTTPS default. Never point this exception at a
public host.

## Structure

```
lib/
  main.dart                  app bootstrap (AiShoppingRoot → MainShell)
  models/api_models.dart     typed contracts for every endpoint consumed
  models/assistant_models.dart  typed assistant turn contract (M13)
  services/api_service.dart  HTTP transport, typed errors, timeouts
  services/api_client.dart   cached read-only catalog/basket API
  services/assistant_api.dart  POST /api/v1/assistant/turn client (M13)
  services/response_cache.dart  SharedPreferences-backed offline cache
  providers/app_state.dart   locale/theme/local basket state
  screens/                   home, search, compare, basket, assistant, settings, details
  widgets/                   offer card, compare tile, placeholders, error view
  utils/                     MKD/quantity/date formatting, transliteration
  l10n/                      flat translation maps (mk + en) + delegate
```
