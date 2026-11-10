# M13 — AI Shopping Assistant: results

**Branch:** `m13-ai-shopping-assistant` (based on `main` @ `4118c0f`)
**Date:** 2026-11-10
**Status:** **Implemented** — deterministic mock-provider verification only.
**Live-model verification:** **NOT VERIFIED / pending** — no real provider was
configured or approved during this milestone, so the coordinator was exercised
exclusively through the mock provider and a scripted `openai_compatible` chat
server in tests. Per the task doc, M13 is *not* claimed to be fully live.

**Scope delivered:** guest-safe bounded `POST /api/v1/assistant/turn` on the
existing FastAPI backend (`backend_py/`) over the allowlisted M5 domain
tools, plus a Flutter **AI chat tab** in `mobile/` with candidate choices,
reviewable basket-diff proposals, explicit Apply-to-basket confirmation and
the existing M4/M12 server-side optimizer for authoritative totals. Contract:
`docs/contracts/assistant-api-contract.md`.

## What was built

### Backend (`backend_py/`, commit `10971e9`)

- **`app/assistant/coordinator.py`** — the single-turn grounded coordinator:
  - Model output is parsed and validated into typed `_Parsed` intents
    (`search`, `expected_candidate_id` follow-ups); nothing model-generated —
    IDs, quantities, units, prices, totals — is trusted without catalog
    verification.
  - Per-item flow: allowlisted `search_offers` (size 6) → `candidate_not_
    confirmed` refusal if a selection's `expectedCandidateId` is absent from
    the fresh search → multiple canonical candidates produce
    `needs_clarification` with at most 3 options carrying real offer evidence
    (store, quantity/pack, MKD price, `isSubstituteCandidate`).
  - Unverified single-listing matches and out-of-stock items are flagged with
    the reason plus a one-shot `suggest_product_substitutes` probe (≤2 extra
    bounded searches), always `isSubstituteCandidate: true` with warning
    `substitute_candidates_unverified`.
  - Tool budget: `_MAX_TOOL_CALLS_PER_TURN = 10` (≤8 item searches, substitution
    probes, 1 optimization preview). Exhaustion yields `tool_budget_exhausted`
    and the turn stays recoverable.
  - Optimization preview trims `singleStoreRankings` to 5 and marks it
    `previewOnly: true`; authoritative totals remain the separate
    `POST /api/v1/baskets/optimize` call made by the client on Apply.
  - Provider outage → `model_unavailable`; nonconforming model output →
    `model_error`; unexpected exception → typed `assistant_error` (**HTTP 200**
    with an error payload, never a stack trace or internal prompt text).
  - Basket echo semantics: `replace_quantity` includes `oldQuantity`/`oldUnit`;
    duplicates collapse into `itemsConsidered.already_in_basket`; **no basket
    mutation happens server-side ever** — only proposals are returned.
- **`app/assistant/providers.py`** — provider-neutral adapter: `mock`
  (deterministic script interpreter), `openai_compatible` (httpx, tool-call
  JSON extraction, malformed-output handling), auto-selection from env
  (`ASSISTANT_PROVIDER`). Macedonian/Latin/English quantity words (`литра`,
  `литре`, `litar`, …) parsed for bounded unit expressions.
- **`app/assistant/rate_limit.py`** — per-process sliding-window `RateLimiter`
  (max 10 000 client keys) + `ConcurrencyGate` semaphore; 429 responses reuse
  the standard spring error body with `Retry-After: 60`.
- **`app/schemas/assistant.py`** — typed Pydantic request/response schemas;
  `ASSISTANT_LIMITS` exported limits are re-enforced per-request by
  `Field(max_length=…)` bounds (message 500 chars, context ≤6, basket echo
  ≤20, selections ≤8).
- **`app/routes/assistant.py`** — `POST /api/v1/assistant/turn` (blank message
  → 400; rate limit → 429; concurrency → 503) and `GET /api/v1/assistant/
  tools` publishing `allowlistedTools` (7 ceilings) vs `dispatchedTools` (3).
  No admin/review-queue/metrics/MCP tool is reachable from this route.
- **`app/main.py`** — wiring only; existing catalog/basket/MCP routes and
  contracts untouched (M10 behavior preserved).

### Flutter (`mobile/`, commit `6cf5d35`)

- `lib/models/assistant_models.dart` — full typed contract matching the
  backend schemas (nullable `message` omitted from JSON when unset).
- `lib/services/assistant_api.dart` — `HttpAssistantApi` calling only
  `POST /api/v1/assistant/turn`; reuses the existing `ApiService` base URL.
- `lib/screens/assistant_screen.dart` — chat UI: user/assistant bubbles,
  pending-turn guard with a local basket-signature staleness check (a basket
  edit while a turn is in flight refuses stale `expectedBasketSignature`),
  `_ChoiceCard` option rows (substitute tag icon, evidence per option),
  unresolved-reason labels, server-provided preview subtotal, `_DemoBanner`
  whenever `provider.isMock` (default, honest), and `_ProposalStrip` with
  checkbox proposals (all default-selected) — **nothing mutates the basket
  until the user taps Apply** (key `assistant_apply`).
- Apply flow mutates the existing local `AppState` basket via
  `replaceAllBasketItems`, then calls the **existing**
  `POST /api/v1/baskets/optimize` (`inStockOnly: true`, `maxStores: 2`) and
  renders the existing `BasketOptimizationResults` sheet — **the chat never
  computes or displays MKD totals itself**.
- `lib/screens/main_shell.dart` — 5th tab “AI” (`Icons.auto_awesome`)
  inserted between Basket and Settings; all pre-existing tabs preserved.
- `lib/l10n/translations.dart` — ~28 new `assistant_*` keys with full
  mk/en parity (enforced by the existing localization test).

## Verification evidence (all executed 2026-11-10)

1. **Backend:** `.venv\Scripts\python.exe -m pytest` → **42 passed**
   (24 pre-existing M10/M12 tests + 18 new `tests/test_assistant_api.py`)
   covering: no-provider `model_unavailable`; blank-message 400; mock
   verified proposal with trimmed preview; ambiguity → `needs_clarification`
   with real offer evidence; unverified single listing; selection turn honoring
   `c:{canonical}:{retailer}` exactly; selected candidate missing from fresh
   search → `candidate_not_confirmed` (no silent swap); out-of-stock +
   substitute probe; stale offers; basket echo replace/already-in-basket;
   provider outage `model_unavailable`; invalid model output `model_error`;
   `openai_compatible` end-to-end against a local scripted chat server,
   including rejection of a tool call smuggling a fraudulent money key;
   rate limit 429; `/assistant/tools` allowlist; and the 10-call tool budget
   with 7 segments (clamped to 8 items).
2. **Flutter:** `flutter analyze` → **No issues found!**; `flutter test` →
   **29 tests passed** (20 pre-existing + 9 new: model parsing
   (`hasChoices`/`isActionable`), request serialization omitting null `message`,
   basket-echo construction, send-and-apply proposal flow (local basket +
   server optimize invoked), ambiguity selection turn, honest
   `model_unavailable` chat rendering, stale-basket refusal, `replace_quantity`
   proposal replacing the prior entry).
3. **Regression safety:** all 24 pre-existing backend tests and all 20
   pre-existing Flutter tests pass unchanged; `/api/v1/catalog`, `/mcp`,
   `/baskets/*` contracts untouched.

## Live-model demo (policy note)

The task doc allows a live demo only with an owner-approved configured
provider. None was configured; no paid API was enabled. E2E grounding was
verified with the deterministic mock provider plus a scripted OpenAI-compatible
chat server whose tool calls arose from real catalog data (intersected,
validated, money keys rejected). **M13 is therefore marked implemented, not
live-model verified.** When the owner supplies provider credentials, rerun:

- „млеко, јајца, леб“ (verified adds + optimizer totals),
- a Latin/Romanized input (“mleko i lebas”),
- a deliberately ambiguous size query,
and record provider name, tool calls and offer IDs in this document.

## Security / cost boundary status

- No secrets in Flutter, source control or test logs; credentials server-side
  env only (`ASSISTANT_PROVIDER`, `ASSISTANT_MODEL`, `ASSISTANT_BASE_URL`,
  `ASSISTANT_API_KEY`, `ASSISTANT_TIMEOUT_SECONDS`, `ASSISTANT_MAX_TOKENS`,
  `ASSISTANT_TOOL_CALL_BUDGET`, `ASSISTANT_RATE_LIMIT`… see the contract doc).
- Requests are throttled (per-client sliding window) and concurrency-capped;
  a failed turn returns structured errors, never stack traces.
- Assistant dispatch limited to 3 read-only domain tools; 7-tool allowlist cap
  published via `/api/v1/assistant/tools`; review queue/metrics/admin/MCP
  stay unreachable from the guest route (guarded by tests).
- Data sent to a remote model (when configured): the user message, ≤6
  compact conversation entries and a ≤20-line basket echo — nothing else;
  no full catalog dumps, no device state, no persisted transcripts. To disable
  the feature, unset `ASSISTANT_PROVIDER` (clients show honest
  `model_unavailable`); the tab cannot be hidden client-side yet.

## Known limitations / deviations

- **Rate limiting/concurrency are per-process** (single-instance FastAPI).
  Multi-worker deployment needs an external limiter (deployment, not M13).
- Substitution lookup is **candidate-centric** (review rows whose
  `candidateCanonicalId` matches the unavailable offer) — confirmed-substitute
  direction variants are a follow-up if review data supports them.
- `item_count_bounded` warning is implemented defensively but effectively
  unreachable because the adapter already clamps segments to the budget cap.
- **No consumer basket persistence server-side** for chat holds; the
  conversation context stays client-provided within strict line/item caps.
- Physical-device / emulator smoke was not run for the new tab in this
  milestone (flutter-only widget tests cover the flows); the M12-pending
  device review still applies.
- Live-model demo pending (see above); mock provider UI is clearly marked
  with `assistant_demo_chip` so demo parity is never mistaken for live AI.

## Deliverables in this PR

- `backend_py/app/assistant/` (coordinator, providers, rate_limits,
  transliteration) + `app/routes/assistant.py`, `app/schemas/assistant.py`,
  `app/main.py`, `app/config.py`
- `backend_py/tests/test_assistant_api.py` (+ `conftest.py` fixture seams)
- `mobile/lib/models/assistant_models.dart`,
  `mobile/lib/services/assistant_api.dart`,
  `mobile/lib/screens/assistant_screen.dart`, `mobile/lib/screens/main_shell.dart`,
  `mobile/lib/providers/app_state.dart`, `mobile/lib/main.dart`,
  mobile/README.md, AGENTS.md, docs/milestones/current-status.md, docs/milestones/roadmap.md,
  docs/contracts/assistant-api-contract.md, docs/milestones/m13-results.md
