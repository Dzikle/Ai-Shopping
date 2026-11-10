# AI Shopping — Agent Operating Rules (proposed v2)

**Repository:** `Dzikle/Ai-Shopping`. Keep this project independent of other repositories. Work on isolated branches; no destructive actions, surprise deployments, unapproved paid services, or secrets in source.

## Current state

As of 2026-11-09, `main` contains backend/data work through M9, including Vero, Stokomak, Zito and KAM ingestion, PostgreSQL, OpenSearch, baskets, a read-only MCP server, daily scheduling, match review, and metrics. M10 (branch `m10-fastapi-migration`) replaces the Java/Spring Boot backend with Python/FastAPI (`backend_py/`, ADR-0006), verified by a differential regression harness against the Spring Boot jar; the Java tree is retained untouched for rollback until owner sign-off. No Flutter or consumer web application is in `main`. See `docs/milestones/current-status.md` for source of truth; verify actual code/tests before trusting claims.

**IMPORTANT:** The old roadmap and master plan contain stale `M0 only` instructions; the master plan stack section now reflects FastAPI (ADR-0006). This file supersedes stale operational restrictions. Consult `docs/architecture/product-delivery-plan.md` and the task-specific documents in `docs/milestones/` for next stages; do not treat every proposed stage as authorized.

## Next approved task

**M10 FastAPI migration and M12 Flutter mobile MVP are merged into `main` (2026-11-09; M10 owner-signed, M12 awaiting owner review)**. The Python/FastAPI backend in `backend_py/` is authoritative; the Java tree (`backend/`) and the differential gate (`scripts/test-m10-diff.ps1`) remain only as rollback and are to be removed in a follow-up commit once the owner confirms. M11 toolchain/device validation remains owner-deferred. Owner review is requested for the M12 mobile app (see `docs/milestones/m12-results.md`); do not begin M13+ without owner approval.

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
- M13 AI assistant experience using existing bounded MCP/domain tools.

## Mobile development (M12+)

- The Flutter app lives in `mobile/` (Flutter 3.47.x, Dart 3.13). Read
  `mobile/README.md` before touching it; run `flutter analyze` and
  `flutter test` before every commit.
- The client is guest-first and read-only: only the six catalog/basket
  endpoints may be consumed; never call review-queue/metrics/MCP from the app
  and never embed paid AI keys in a build.
- Server-side math is authoritative: the app formats but never recomputes
  prices, pack counts or totals (ADR-0001/0003 invariants).
- New UI strings go in `lib/l10n/translations.dart` for **both** `mk` and `en`
  (key-set parity is enforced by `test/models_and_localization_test.dart`).
- Latin→Cyrillic transliteration (`lib/utils/transliteration.dart`) is input
  normalization only; never transliterate server data.

Read `docs/architecture/product-delivery-plan.md` before starting any future milestone.