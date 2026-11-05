# M7 proposal — Stage-2 product-match review queue (approve/reject workflow)

**Status:** Owner-approved & implemented (approval recorded 2026-11-05; implementation completed 2026-11-04/05).
**Depends on:** M2 (canonical identity & matching evidence), M3 (PostgreSQL-backed REST API + review-queue listing), M6 (V4 operations schema & CI).

## Goal

Give a human operator the ability to accept or reject Stage-2 (`candidate_token_size_v1`) match candidates
with a full audit trail, so that appendix risk is managed by governance instead of luck:

- Stage-2 candidates remain excluded from price comparisons until decided
- Every decision is recorded with `reviewed_by`, `reviewed_at`, `review_notes`
- Approved matches immediately flow into cross-retailer comparisons and OpenSearch projections
- Rejected matches stay visible in history (audit), never auto-deleted

## Owner decisions needed (resolved)

1. **Approval surface:** REST API + operator CLI overlaying `backend` services (no separate UI) — accepted.
2. **Identity semantics:** approval converts `review_status = 'pending_review'` → `'approved'` and that is final
   from a Stage-2 perspective; loader preserves human rows (`WHERE reviewed_at IS NULL`). Accepted.

## Architectural alignment (ADR-0002, ADR-0003, AGENTS.md)

1. **PostgreSQL remains sole authority (ADR-0002):** decisions live in `product_matches` (columns `review_status`,
   `reviewed_by`, `reviewed_at`, `review_notes`, `updated_at` — introduced in M2 `V2__m2_identity.sql`). Nothing is
   decided inside OpenSearch; a reindex projects only `review_status IN ('auto_accepted', 'approved')`.
2. **Identity vs substitution (ADR-0003):** until `approved`, a Stage-2 candidate can only surface as an explicit
   `isSubstitute = true / substituteReason = 'stage2_pending_review_candidate'` basket line (`allowSubstitutes = true`).
   After approval it joins exact identity flows in comparisons and baskets.
3. **Conditional, idempotent updates:** approve/reject UPDATE only rows whose `review_status IS 'pending_review'`;
   retry-safe; re-approving an already-approved row is a no-op error, mirroring the unique active-identity concept.
4. **No paid APIs / no LLM in the loop (AGENTS.md #2, M2 decisions):** decision authority is strictly the human operator.

## Deliverables (implemented)

### 1. REST endpoints (`backend/src/main/java/mk/aishopping/controller/CatalogController.java`)
- `POST /api/v1/matches/review-queue/{id}/approve`
- `POST /api/v1/matches/review-queue/{id}/reject`
- Request body `ReviewQueueActionRequest { reviewedBy, reviewNotes }`
- Response `ReviewQueueDecisionDto { matchId, reviewStatus, reviewedBy, reviewNotes }`
- Error semantics: 4-level — unknown match id, wrong status (`pending_review` required), missing `reviewedBy`.

### 2. Repository layer (`PostgresCatalogRepository.java`)
- `approveMatch()` / `rejectMatch()` — conditional `UPDATE product_matches SET review_status = 'approved'|'rejected'`,
  `reviewed_by`, `reviewed_at = now()`, `review_notes`, `updated_at` where `review_status = 'pending_review'`;
  throws `IllegalArgumentException` if the match is missing or not pending.

### 3. Service layer (`CatalogSearchService.java`)
- Delegates decide logic to repository with parameter validation.

### 4. Operator CLI (`scripts/review-queue.ps1`)
- `--List` — shows pending_review candidates with shared tokens, confidence, declared size
- `--Approve <id> --ReviewedBy <user> [--ReviewNotes "..."]`
- `--Reject <id> --ReviewedBy <user> [--ReviewNotes "..."]`
- Exits non-zero on validation errors; structured output; works against `http://localhost:8080` by default.

### 5. Tests
- JUnit: `CatalogApiTest.testReviewQueueApproveAndRejectEndpoints` — end-to-end approve → reject round-trip verifying
  status transitions, reviewedBy/reviewNotes propagation and Mockito-verified repository calls.
- Python suites untouched (13 JUnit; 52 Python tests total). CI runs the full matrix on every push.

## Exit criterion (roadmap M7)

Pending matches can be approved/rejected with full audit; approved matches flow into cross-retailer comparisons:
- `POST .../approve` on a Stage-2 candidate returns `reviewStatus = 'approved'` with `reviewedBy`/`reviewNotes` echoed
- Repeated decisions are rejected with a clear error (only `pending_review` is actionable)
- After approval + reindex, the product appears in `products/compare` with its Stage-2 partner retailer

## Non-goals (explicitly out of M7)

- Bulk approval / batched queue UI
- Re-opening previously rejected matches (would require new status semantics; deferred)
- Notification system for operators when the queue exceeds a threshold (candidate for M8 monitoring)
- LLM-assisted suggestions for candidate acceptance

## Risks & mitigations

| Risk | Mitigation |
|------|------------|
| Operator approves a wrong identity | Full audit trail including `review_notes`; evidence JSONB preserved on the row; identity change history recoverable from `updated_at` |
| Approvals happen on stale projections | Fresh OpenSearch reindex reflects approvals automatically; staleness reported by `/api/v1/freshness` |
| Stale matches stay pending forever | Queue listing is bounded (`--List --Limit`); M8 monitoring candidate: "review-queue-depth" metric |
| Concurrent operators on same match | Conditional UPDATE on pending_review; last qualifying write wins; validations give a clear error |

## Validation evidence

- `scripts/test-m3.ps1` → review queue: 20 pending_review fixtures both from OpenSearch projection and PostgreSQL fallback
- `CatalogApiTest.testReviewQueueApproveAndRejectEndpoints` part of the 13/13 JUnit green suite (CI run 41939594293, 2026-11-05)
- Deterministic Stage-2 candidates: `stage2_queue=20` on every M2/M6 replay fixture set
