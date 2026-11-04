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

**Instruction:** Implement only M0 now. No premature scrapers, product matching, OpenSearch application code, basket optimizer or AI tools until the respective designs are reviewed. Record tests, limitations and owner approvals per milestone.

**M6 implemented:** `docs/milestones/m6-proposal.md` (2026-11-04) — owner-approved and verified via `scripts/test-m6.ps1`.

**M7 implemented:** `scripts/review-queue.ps1`, `POST /api/v1/matches/review-queue/{id}/approve|reject` — verified via `CatalogApiTest.testReviewQueueApproveAndRejectEndpoints` (13 JUnit tests pass).
