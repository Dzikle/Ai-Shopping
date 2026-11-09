# M10 — Spring Boot to FastAPI Migration (Agent Task)

**Status:** Approved direction, completion unverified. Work against current `main`; do not assume an old M4 snapshot reflects today's functionality.

## Why
Faster edit-test feedback and simpler integration with existing Python adapters/matching, without losing existing behavior.

## Baseline first
- Read `README.md`, `docs/milestones/current-status.md`, `docs/contracts/*`, `backend/src/main`, and the full Java test suite.
- Snapshot the current API, statuses, error shapes and response fields with golden contract fixtures. Use the same PostgreSQL state and mocked/real OpenSearch during differential testing.
- Record all Java routes and MCP tools. **The migration scope is M1–M9, not just M1–M4.**
- Measure startup, targeted-test latency, live-edit reload, and suite runtime before migration.

## Mandatory parity inventory
- `GET /api/v1/health`, `/stores`, `/offers/search`, `/products/compare`, `/products/{id}/history`, `/matches/review-queue`.
- `POST /api/v1/matches/review-queue/{id}/approve|reject` including review audit, authorization design, errors and concurrency semantics.
- `POST /api/v1/baskets/optimize`, `POST /api/v1/baskets/lists`, `GET /api/v1/baskets/lists/{id}`, `POST /api/v1/baskets/lists/{id}/optimize`.
- `GET /api/v1/freshness` and `GET /api/v1/metrics`.
- `/mcp` protocol handshake, tool listing, seven tools, bounds, freshness envelope and deterministic equivalence to the REST optimizer.
- PostgreSQL fallback when OpenSearch is unavailable, alias/contract compatibility, source/retailer extensibility (including KAM).
- Preserve SQL migrations V1..V5, adapter/scheduler and the current PowerShell scripts; update scripts when needed rather than replacing working ingestion.

## Implementation constraints
- FastAPI + Pydantic + `uv` + `pytest` + PostgreSQL + compatible OpenSearch client. Use Python `Decimal` for money and integer pack counts.
- Keep domain logic separate from HTTP schemas and persistence; do not expose raw SQL or OpenSearch through public MCP.
- Reuse existing Python code instead of porting it twice. Preserve response casing if clients already depend on camelCase.
- Local dev: `uv sync`, `uv run uvicorn ... --reload`, `uv run pytest -q`; enable hot reload without container rebuilds.
- Run old and new APIs side by side on different ports with a deterministic fixture database; assert HTTP status, JSON, sorting, missing-items, match behavior, and outputs.
- Explicitly test full-coverage-before-cheapest, `maxStores <= 3`, no substitution by default, unit conversions, two-store savings and unknown/stale stock handling.
- Keep old Java backend until equivalence is demonstrated; switch CI and Docker Compose only after tests pass.

## Deliverables and gate
- Migration inventory, ADR superseding the old backend-stack ADR, new Python backend, automated differential regression suite, updated CI/Compose/docs, measured dev-loop improvements, rollback instructions.
- `AGENTS.md` and master plan must no longer prescribe Spring Boot or M0-only instructions.
- No production migration, data reset or destructive changes without explicit approval.