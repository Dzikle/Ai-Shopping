# AI Shopping — Universal Price Intelligence Platform

A retailer-agnostic platform for daily price ingestion, canonical product matching, store-level comparison, price history, and AI-assisted grocery shopping. **Status: M0 + M1 (Vero) + M2 (Stokomak + Zito + canonical identity & matching) + M3 (OpenSearch projections & Spring Boot search/comparison REST API) implemented — see [current status](docs/milestones/current-status.md).** No deployed implementation is implied.

Initial focus: North Macedonia. Expansion: other countries, retailers and product categories.

Start with [the master plan](docs/architecture/master-plan.md), [the milestone roadmap](docs/milestones/roadmap.md) and [AGENTS.md](AGENTS.md).

Core design: Spring Boot / Java 21, PostgreSQL source of truth, OpenSearch derived indexes, independent Python/TypeScript adapters, optional Redis worker queues, Docker Compose, MCP read-only tools.

## Running the M1, M2 & M3 pipelines (replay mode, no network)

```powershell
copy .env.example .env          # once; docker compose reads it
docker compose up -d --wait postgres
./scripts/apply-migrations.ps1  # V1 + V2 schema + Vero/Stokomak/Zito store seeds

# Replay Vero, Stokomak, and Zito fixtures
docker run --rm -v "${PWD}:/w" -w /w python:3.12-slim python -B adapters/vero/cli.py --from-snapshots tests/fixtures/vero --out snapshots/vero/<date>/<run_key> --run-key <run_key>
docker run --rm -v "${PWD}:/w" -w /w python:3.12-slim python -B adapters/stokomak/cli.py --retailer stokomak --from-snapshots tests/fixtures/stokomak --out snapshots/stokomak/<date>/<run_key> --run-key <run_key>
docker run --rm -v "${PWD}:/w" -w /w python:3.12-slim python -B adapters/stokomak/cli.py --retailer zito --from-snapshots tests/fixtures/zito --out snapshots/zito/<date>/<run_key> --run-key <run_key>

# Load runs + run deterministic product matching + cross-retailer report
./scripts/load-records.ps1 -OutDir snapshots/vero/<date>/<run_key> -RunKey <run_key>
./scripts/load-records.ps1 -OutDir snapshots/stokomak/<date>/<run_key> -RunKey <run_key>
./scripts/load-records.ps1 -OutDir snapshots/zito/<date>/<run_key> -RunKey <run_key>
docker run --rm -v "${PWD}:/w" -w /w python:3.12-slim python -B matching/cli.py --run-dirs "snapshots/vero/<date>/<run_key>,snapshots/stokomak/<date>/<run_key>,snapshots/zito/<date>/<run_key>" --out snapshots/matching/<date>/<match_key>
./scripts/load-matches.ps1 -OutDir snapshots/matching/<date>/<match_key>
./scripts/report-cross-retailer.ps1

# Export PostgreSQL state & reindex OpenSearch projections (stores_v1, offers_v1, products_v1)
./scripts/reindex-opensearch.ps1 -VersionTag v1_local
```

## Tests

- Unit tests (stdlib Python 3.12 + JUnit 5 on Java 21):
  - `docker run --rm -v "${PWD}:/w" -w /w/adapters/common python:3.12-slim python -B tests.py`
  - `docker run --rm -v "${PWD}:/w" -w /w/adapters/vero python:3.12-slim python -B tests.py`
  - `docker run --rm -v "${PWD}:/w" -w /w/adapters/stokomak python:3.12-slim python -B tests.py`
  - `docker run --rm -v "${PWD}:/w" -w /w/matching python:3.12-slim python -B tests.py`
  - `docker run --rm -v "${PWD}:/w" -w /w/search python:3.12-slim python -B tests.py`
  - `docker run --rm -v "${PWD}/backend:/w" -v aoshopping-m2-repo:/root/.m2 -w /w maven:3.9.9-eclipse-temurin-21 mvn -B test`
- Integration tests (scratch DB, idempotency, OpenSearch alias swap, REST API + Postgres fallback):
  - `./scripts/test-m1.ps1`
  - `./scripts/test-m2.ps1`
  - `./scripts/test-m3.ps1`

Live fetching (`--url --stores`) follows the politeness rules in
[docs/contracts/vero-adapter-contract.md](docs/contracts/vero-adapter-contract.md) and
[docs/contracts/stokomak-adapter-contract.md](docs/contracts/stokomak-adapter-contract.md);
respect retailer terms and rate limits.
