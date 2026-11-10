# M13 — AI Shopping Assistant (owner-approved 2026-11-10)

**Repository:** https://github.com/Dzikle/Ai-Shopping  
**Status:** Approved for implementation; no claim of completed features.  
**Baseline:** `main` at/after commit `4118c0f` contains merged M10 FastAPI (`backend_py/`) and M12 Flutter (`mobile/`). Confirm current branch and tests before changes.  
**Priority:** Deliver a usable, grounded Macedonian-language shopping assistant inside the existing Flutter application, with explicit user approval before changing a basket.

## Goal and demo

A user opens the AI tab and says:

> „Направи ми список за неделно пазарење: млеко, јајца, леб, јогурт и кафе. Најди ми каде ќе поминам најевтино.“

The assistant extracts requested items and units, searches the actual catalog, offers grounded product choices where ambiguous, and **previews** proposed additions/edits. The user reviews the choices and taps **Apply to my basket**. The existing M12 basket state is updated via its normal APIs, then the **existing M4 deterministic optimizer** returns genuine best-store/multi-store totals, coverage, unavailable products, and optionally savings.

The model is only a language interpreter and explanation layer. **It must never invent prices, unit conversions, available stock, verified identities, pack scaling, savings, or basket totals.**

## Architecture — smallest reliable change

```text
Flutter chat UI / local basket
    -> POST /api/v1/assistant/turn (new, bounded guest endpoint)
       -> assistant coordinator (backend_py)
          -> provider-neutral LLM client (optional/configured on server only)
          -> allowlisted existing M5 McpToolRegistry/domain services
          -> catalog-verified product IDs and candidate resolution
       <- typed response: message, evidence, candidates, proposed basket patch,
                          unresolved items, freshness/warnings, request limits
    -> Flutter shows preview + explicit confirmation
    -> existing AppState basket add/update/remove, locally persisted
    -> existing POST /api/v1/baskets/optimize for authoritative result
```

Reuse `backend_py/app/mcp/tool_registry.py` and `backend_py/app/services/*`; do not create another backend, agent platform, OpenSearch mapping, persistent chat DB or copy of basket optimization logic. Call the shared registry/service in-process; there is no need to call the app's own HTTP `/mcp` endpoint or create a second MCP server. The public assistant route must expose **only** an explicit allowlist of read-only shopping operations: `search_products`, `compare_product_prices`, `get_price_history`, `list_stores`, `find_current_discounts`, `optimize_shopping_basket`, and `suggest_product_substitutes` when context warrants. Never surface administrative match review, direct SQL, file access, network-browsing tools, arbitrary MCP tools, or tool registration to untrusted clients.

### Provider configuration

- Implement a narrow provider adapter at the FastAPI boundary; keep it mockable. Choose a straightforward adapter for a **user-configured provider** or compatible local model, not an elaborate provider router. Model identifier, base URL, API key, max tokens, timeouts and invocation budget belong in environment config. Never embed credentials in Flutter, Git or test logs.
- Do not procure/enable paid APIs or third-party hosting without explicit owner approval. Support a local/offline/mock provider for tests. If no usable model is configured, respond with an honest `model_unavailable` state; do **not** pretend scripted parsing is live AI or fabricate LLM passes.
- Keep provider-specific input/output handling isolated. Prefer structured outputs / tool-call validation and explicitly handle invalid or nonconforming model responses. Guard against model output passing arbitrary IDs or totals to UI.
- Do not require users to log in for a local development demo; add bounded unauthenticated request controls before public exposure (message/token/tool-call limits, rate limiting, request timeout, bounded conversation context and cost/budget safeguards).

## Phase 1 — inventory and contracts

Read `AGENTS.md`, `docs/architecture/product-delivery-plan.md`, `docs/milestones/m13-m15-web-ai-enhancements.md`, `docs/contracts/mcp-tools-contract.md`, `docs/contracts/basket-api-contract.md`, `docs/milestones/m12-results.md`, and relevant `backend_py/` and `mobile/lib/` source.

- Record exact tool shapes and the MCP registry's result envelope (`content[].text` contains JSON), including error signals (`isError`). Avoid using a text-formatted response as trusted structured data without parsing/validating it.
- Identify the existing `AppState` local basket actions and optimized-basket request shape.
- Choose typed Pydantic request/response schemas and a minimal client contract. Add `docs/contracts/assistant-api-contract.md` with concrete valid/error/clarification/preview JSON examples based on implementation.
- Keep /api/v1/catalog, /mcp, M1–M10 existing behavior compatible. Do not change Java rollback files or the differential harness in this milestone.

## Phase 2 — grounded assistant coordinator (FastAPI)

Implement a bounded `POST /api/v1/assistant/turn` endpoint in the current app, dependency-injectable model provider, scoped orchestration, and Pydantic schemas.

Suggested request: `{message, locale, conversationContext?, currentBasket?, preferences?}`; derive final shape from real Flutter models. Do not trust client-supplied amounts, product IDs or prices as evidence. Suggested response: `{assistantMessage, status, candidateChoices, proposedBasketChanges, unresolvedItems, evidence, warnings, requestId}` and an optional authoritative optimization snapshot if actually run.

- Parse Macedonian Cyrillic, Romanized Macedonian/Latin and English requests, quantities and common units (`pack`, `pcs`, `g`, `kg`, `ml`, `l`). Use existing M12 transliteration concepts only where appropriate; do not invent product identity from spelling.
- Search authoritative offers through the allowlisted domain/MCP tool surface; resolve `canonicalProductId` or `retailerProductId` from actual returned records.
- Model-generated product choices are untrusted proposals; validate IDs, quantity, unit and equality/substitution flags against the catalog before constructing a preview. Exact matching defaults to strict; Stage-2 substitutes are explicitly flagged and require opt-in.
- If products or sizes are ambiguous, return choices with evidence and request user clarification instead of picking silently. Support a bounded multi-turn clarification flow with compact client-provided context; cap its size. Unresolved items must remain visible.
- Never add, edit or clear the persisted/local basket in response to just a message. Return an immutable proposal/patch for user review. Include change type, target product IDs, requested quantity/unit and old/new diff where relevant.
- Ensure repeated/late responses cannot overwrite a newer basket: version/hash or equivalent check before applying a confirmed proposal in Flutter. Revalidate proposed candidate IDs or stale changes as needed.
- Numerical totals/savings must come **only** from the existing optimizer. If it cannot optimize, say so; never generate fallback prices.
- Expose tool/source provenance and freshness dates, plus clear caveats for old/unknown availability or uncovered items. Model prose must not claim stronger guarantees than the structured evidence.
- Use a finite tool-call/turn limit with clear recoverable errors. No background jobs/loops.
- Treat catalog text, retailer pages, results and model tool arguments as untrusted. Prompt injection embedded in product fields must not redirect the assistant or access privileged operations.

## Phase 3 — Flutter integrated experience

Extend `mobile/` rather than creating another UI. Provide a discoverable **AI** tab or action from the existing `MainShell`, preserving home/search/compare/basket/settings access. Avoid breaking existing navigation; a tab swap or secondary route is acceptable with a brief rationale.

- Chat screen with Macedonian-first strings and English translations, user/assistant bubbles, text input, submit/retry/cancel, loading, network errors and `model_unavailable` state.
- Show actual catalogue candidates with store, quantity/pack, MKD offer, dates, source link and explicit identity/substitute status. Handle missing images and product history gracefully.
- Provide inline question/selection UI to resolve ambiguous products; remember compact context only for the active guest conversation.
- Provide a **reviewable shopping-list diff**; only after an explicit tap should the Flutter app mutate its existing `AppState` basket. Reject stale proposals, allow user to cancel, handle existing duplicates carefully and preserve old quantities unless user confirmed replacement.
- After applying, launch existing optimizer (via `ShoppingApi.optimizeBasket` / `/api/v1/baskets/optimize`) and render the same typed `BasketOptimization` used by M12. Never calculate MKD totals in chat UI.
- Local guest experience only; do not persist sensitive chat transcripts by default or silently upload entire historical baskets. Show a concise notice if a configured remote model receives user-entered shopping text.
- Reuse `mobile/lib/l10n/translations.dart`; keep mk/en keys in parity.

## Phase 4 — tests and verification

**Backend unit + integration tests:** mock provider deterministic response, real bounded MCP/domain tool dispatch where useful, valid/invalid tool calls, no-tool behavior, search + disambiguation, unknown product ID, pack/unit validation, 20-item basket bound, provider outage, timeout/rate limit, malformed JSON, prompt injection in a product name, stale source and no-prices behavior, no admin-tool calls, and no backend basket mutations.

**Flutter tests:** parse typed assistant replies, clarification selection, preview diff rendering, confirm vs cancel, stale proposal refusal, duplicate resolution, local basket persistence, no totals calculated client-side, localization, provider-unavailable and API errors.

**Integration demo:** with a configured real model **if available and approved**, verify Macedonian basket prompt → real catalog candidates → clarification/confirmation → local basket update → deterministic MKD optimizer. Include a Romanized Macedonian example and a deliberate ambiguous-size query. Record the exact model/provider *name* (not secret), input, tool calls, actual offer IDs and output. If no model/provider is configured, run mock-provider E2E, mark the live-model demo **NOT VERIFIED**, and do not call M13 fully live.

Retain and run existing backend Python and M1–M10 CI tests, plus `flutter analyze`, `flutter test`, and appropriate emulator smoke where feasible. Add a lean backend assistant test gate and Flutter unit gate in CI if feasible without destabilizing existing pipeline. Avoid introducing network calls to paid providers in CI.

## Security / cost boundary

- No keys in Flutter or source control; never let a model emit direct DB queries or choose arbitrary tools.
- Keep public/guest assistant requests throttled and bounded; ensure secrets, stack traces, internal prompts and provider errors are not reflected to the client.
- Do not send unnecessary raw catalog dumps, private device state, addresses or chat logs to model providers.
- No automatic purchases, checkout, notification setup, account creation, remote basket persistence, deployment or new paid infrastructure.
- Explicit confirmation is mandatory for any local basket change; the AI cannot authorize actions on its own.
- Document data sent to a third-party model and how to disable the feature.

## Delivery and acceptance

1. Start from up-to-date `main`, create `m13-ai-shopping-assistant` implementation branch.
2. Deliver typed FastAPI assistant route + provider abstraction + allowlisted MCP/domain coordinator, and `docs/contracts/assistant-api-contract.md`.
3. Deliver integrated Flutter chat and confirmed local-basket preview/Apply flow (not a standalone demo chatbot).
4. Update `mobile/README.md`, `backend_py/README.md` (or backend docs), `docs/milestones/current-status.md`, `docs/milestones/roadmap.md`, and `AGENTS.md`. Create `docs/milestones/m13-results.md` with evidence and explicit limitations.
5. Commit and push a reviewable PR, no automatic merge. Include tests executed/failed/skipped, model/provider used or not configured, sample grounded results, security/cost assumptions and screenshots if actually captured.
6. Mark M13 **implemented** only when the code/UI works with deterministic mock tests and the correct backend. Mark it **live-model verified** only after a successful real-provider tool-calling demonstration.

**Do not begin M14, M15 or delete the Java rollback reference. Proceed autonomously through implementation and testing; request owner decisions only for external costs, provider credentials and deployment.**
