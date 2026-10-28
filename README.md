# AI Shopping — Universal Price Intelligence Platform

A retailer-agnostic platform for daily price ingestion, canonical product matching, store-level comparison, price history, and AI-assisted grocery shopping. **Status: M0 done + M1 (Vero ingestion) implemented — see [current status](docs/milestones/current-status.md).** No deployed implementation is implied.

Initial focus: North Macedonia. Expansion: other countries, retailers and product categories.

Start with [the master plan](docs/architecture/master-plan.md), [the milestone roadmap](docs/milestones/roadmap.md) and [AGENTS.md](AGENTS.md).

Core design: Spring Boot / Java 21, PostgreSQL source of truth, OpenSearch derived indexes, independent Python/TypeScript adapters, optional Redis worker queues, Docker Compose, MCP read-only tools. Exact versions and compatibility must be verified during M0.

## Running the M1 pipeline (replay mode, no network)

```powershell
copy .env.example .env          # once; docker compose reads it
docker compose up -d --wait postgres
./scripts/apply-migrations.ps1                          # schema + store seeds
docker run --rm -v "${PWD}:/w" -w /w python:3.12-slim python -B adapters/vero/cli.py --from-snapshots tests/fixtures/vero --out snapshots/vero/<date>/<run_key> --run-key <run_key>
./scripts/load-records.ps1 -OutDir snapshots/vero/<date>/<run_key> -RunKey <run_key>
```

Unit tests: `docker run --rm -v "${PWD}:/w" -w /w/adapters/vero python:3.12-slim python -B tests.py`
Integration test (scratch DB, idempotency, integrity asserts): `./scripts/test-m1.ps1`

Live fetching (`--url --stores`) follows the politeness rules in
[docs/contracts/vero-adapter-contract.md](docs/contracts/vero-adapter-contract.md);
respect retailer terms and rate limits.
