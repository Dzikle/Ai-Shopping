# AI Shopping — Agent Operating Rules (proposed v2)

**Repository:** `Dzikle/Ai-Shopping`. Keep this project independent of other repositories. Work on isolated branches; no destructive actions, surprise deployments, unapproved paid services, or secrets in source.

## Current state

As of 2026-11-10, `main` contains backend/data milestones M1–M10 (FastAPI in `backend_py/`, PostgreSQL/OpenSearch, retailer adapters, deterministic baskets, seven MCP tools, freshness/metrics/review queue) and M12 Flutter mobile MVP (`mobile/`). M10/M12 are merged; GitHub Actions was green on commit `4118c0f`. M13 AI Shopping Assistant is **implemented on branch `m13-ai-shopping-assistant`** (bounded `POST /api/v1/assistant/turn` + Flutter AI tab, pytest 42 passed, `flutter test` 29 passed) and awaits owner review via PR; live-model verification is pending. The Java tree (`backend/`) and M10 differential harness remain as rollback/regression references. M12 physical-device review and visual polish remain separate follow-ups. See `docs/milestones/current-status.md` for execution evidence and remaining limitations.

**IMPORTANT:** The old roadmap and master plan contain stale `M0 only` instructions; the master plan stack section now reflects FastAPI (ADR-0006). This file supersedes stale operational restrictions. Consult `docs/architecture/product-delivery-plan.md` and the task-specific documents in `docs/milestones/` for next stages; do not treat every proposed stage as authorized.

## Next approved task

**M13 AI Shopping Assistant was implemented 2026-11-10 on branch `m13-ai-shopping-assistant`** per `docs/milestones/m13-ai-shopping-assistant-task.md`; see `docs/milestones/m13-results.md` for evidence. Owner follow-up decisions: (a) PR review/merge, (b) provider credentials for a live-model verification demo, (c) any M14/M15 approval. Reuse FastAPI's existing bounded read-only shopping MCP/domain tools and the M12 Flutter local basket; the assistant proposes changes, and only user confirmation applies them. All authoritative prices and optimizer totals remain server-side. No new paid model/provider, public deployment, Java rollback deletion, M14 or M15 without separate approval.

## Mandatory engineering rules

1. Inspect code/contracts, record baseline and preserve existing tests before edits.
2. PostgreSQL authoritative, OpenSearch rebuildable; keep offer provenance, prices, timestamps and store specificity.
3. Identity != substitution. Pending human review is not exact identity. No destructive refresh on an empty/broken scrape.
4. Deterministic server-side money/quantity math; no LLM calculations. Read-only bounded MCP unless newly approved.
5. Preserve backward-compatible HTTP contracts and `/mcp` protocol during migration.
6. Use source-pinned upstream license notices when adapting external code; evaluate Flutter mobile and checkjebon web as independent gated tasks.
7. Keep guest/customer API surfaces separate from administrative match review/metrics and protect privileged operations appropriately.
8. Prefer fast local feedback: hot reload, isolated tests and existing Python adapters; do not require rebuild per source edit.
9. Each PR must include actual execution evidence, regressions, documentation, changed upstream attribution and clear rollback.
10. Update `docs/milestones/current-status.md` and roadmap after accepted milestones; do not describe mock/demo/live tasks as production-ready.

## Next work packages after M10 owner sign-off

- Follow-up: remove `backend/` (Java) and the differential gate once the owner signs off on M10.
- ~~M11 Flutter/KortingKlok feasibility spike~~ Executed together with M12 (owner deferment); reuse audit in `docs/research/kortingklok-reuse.md`.
- ~~M12 mobile MVP~~ Merged into `main` (2026-11-09), pending owner review - see `docs/milestones/m12-results.md`.
- **M13 AI assistant** — implemented 2026-11-10 on branch `m13-ai-shopping-assistant` per the gated plan in `docs/milestones/m13-ai-shopping-assistant-task.md` (evidence in `docs/milestones/m13-results.md`); live-model verification pending owner provider credentials.

## Mobile development (M12+)

- The Flutter app lives in `mobile/` (Flutter 3.47.x, Dart 3.13). Read
  `mobile/README.md` before touching it; run `flutter analyze` and
  `flutter test` before every commit.
- The client is guest-first: the existing product/basket screens use their
  bounded catalog and optimization REST endpoints; M13 chat may additionally
  call only the new guest-safe `/api/v1/assistant/turn` route. Never call
  review-queue/metrics/MCP directly from Flutter or embed AI keys in the build.
  The assistant's shopping-tool access and provider credentials stay server-side.
- Server-side math is authoritative: the app formats but never recomputes
  prices, pack counts or totals (ADR-0001/0003 invariants).
- New UI strings go in `lib/l10n/translations.dart` for **both** `mk` and `en`
  (key-set parity is enforced by `test/models_and_localization_test.dart`).
- Latin→Cyrillic transliteration (`lib/utils/transliteration.dart`) is input
  normalization only; never transliterate server data.

Read `docs/architecture/product-delivery-plan.md` before starting any future milestone.