# Milestone roadmap

| Milestone | Deliverables | Exit criteria |
|---|---|---|
| M0 Foundation | Repo configuration, master plan, upstream reuse audit, ADRs, framework compatibility checks, basic CI, M1 design | Clone and run baseline validation; owner approves M1 |
| M1 One source | PostgreSQL schema/migrations, worker contract, raw snapshots, one retailer parser, job runs/retries, fixtures | Replay real source without duplicate or corrupt records |
| M2 Multiple sources | Second independent adapter, normalization, canonical identity, product matching evidence, offer histories | Verified exact product comparison across retailers |
| M3 Search/API | Versioned OpenSearch indexes, reindexing, search/filter REST endpoints, store-level comparison | Real products searchable with correct source and freshness |
| M4 Baskets | Shopping lists, unit conversion, deterministic full-basket/store and multi-store optimization | Repeatable totals and explicit missing-item behavior |
| M5 AI/MCP | Bounded read-only MCP, natural language interpretation, evidence-backed results, provider abstraction | Agent uses actual offer data and deterministic totals |
| M6 Operations | Scheduled jobs, monitoring, alerts, trends, backup/recovery, performance checks | Unattended daily runs with measured freshness and quality |
| M7 Review Queue | Stage-2 product match review queue: REST approve/reject endpoints, CLI script, audit trail (`reviewed_by`, `reviewed_at`, `review_notes`) | Pending matches can be approved/rejected with full audit; approved matches flow into cross-retailer comparisons |
| M8 Metrics | `GET /api/v1/metrics` run-quality aggregates + Prometheus exporter | Recent-run quality observable without SQL access |
| M9 KAM PDF source | Fourth retailer adapter (stdlib PDF parser), V5 store references, scheduler/pipeline integration | KAM replay ingests 86 stores idempotently; quarantine semantics hold |
| M10 FastAPI migration | Python/FastAPI backend replacing Spring Boot (ADR-0006), differential regression suite, CI/script switch, measured dev-loop gains | 48/48 differential pairs equal on identical data; ported unit suite green; owner sign-off before Java removal |
| M11 KortingKlok spike | Upstream commit pinned, isolated evaluation, one vertical slice against FastAPI, reuse inventory | Executed in kombinacija with M12 delivery (owner deferred standalone M11 device validation); see `docs/research/kortingklok-reuse.md` |
| M12 mobile MVP | Guest-first Flutter app: browse/search/compare/history + local basket with server-side optimization, mk/en localization, offline & stale handling | `flutter analyze` clean, 20 unit tests + 4 live-backend integration tests on API-35 emulator, debug APK built; see `docs/milestones/m12-results.md` |
| M13 AI assistant (owner-approved 2026-11-10) | Bounded model-agnostic FastAPI assistant over existing MCP/domain services + Flutter chat with confirm-before-apply basket proposals | **Implemented on branch `m13-ai-shopping-assistant` (pending owner review):** real catalog resolution and explainable evidence, zero invented prices/totals, confirmed basket changes only, backend pytest 42 passed + `flutter analyze` clean / `flutter test` 29 passed. **Live-model verification pending** (no provider credentials configured); mock + scripted compatible-server tests only - see `docs/milestones/m13-results.md` and `docs/contracts/assistant-api-contract.md` |

**Instruction:** The `Implement only M0 now` gate from the original plan is historical — every milestone above is owner-approved before implementation and records evidence in `docs/milestones/current-status.md`. Stale `M0 only` text elsewhere is superseded by AGENTS.md.

**M6 implemented:** `docs/milestones/m6-proposal.md` (2026-11-04) — owner-approved and verified via `scripts/test-m6.ps1`.

**M7 implemented & owner-approved (2026-11-05):** `docs/milestones/m7-proposal.md` — review queue approve/reject REST endpoints + `scripts/review-queue.ps1` CLI + audit trail, verified via `CatalogApiTest.testReviewQueueApproveAndRejectEndpoints` (13 JUnit tests pass; CI green runs 41938782736/41939594293).
