# AI Shopping — Universal Price Intelligence Platform

A retailer-agnostic platform for daily price ingestion, canonical product matching, store-level comparison, price history, deterministic basket optimization, and AI-assisted grocery shopping. **Status: M0 + M1 (Vero) + M2 (Stokomak + Zito + canonical identity & matching) + M3 (OpenSearch projections & search/comparison REST API) + M4 (Shopping lists, unit conversion & deterministic single/multi-store basket optimization) + M5 (Bounded read-only MCP server over catalog & basket optimizer) + M6 (Daily ingestion scheduler, freshness API & automated pipeline) + M7 (Match review queue) + M8 (Metrics API) + M9 (KAM Market PDF adapter) + M10 (FastAPI backend migration, differential-verified) implemented — see [current status](docs/milestones/current-status.md).** No deployed implementation is implied.

Initial focus: North Macedonia. Expansion: other countries, retailers and product categories.

Start with [the master plan](docs/architecture/master-plan.md), [the milestone roadmap](docs/milestones/roadmap.md) and [AGENTS.md](AGENTS.md).

Core design: FastAPI / Python 3.12 backend (ADR-0006, replaces the original Spring Boot stack), PostgreSQL source of truth, OpenSearch derived indexes, independent Python/TypeScript adapters, optional Redis worker queues, Docker Compose, MCP read-only tools.

## Running the backend (FastAPI, M10)

```powershell
cd backend_py
uv sync --locked                                  # install locked deps
uv run uvicorn app.main:create_app --factory --reload   # dev server with hot reload
uv run pytest -q                                  # backend test suite
```

Environment (see `.env.example`): `POSTGRES_HOST/PORT/DB/USER/PASSWORD`, `OPENSEARCH_URL`. OpenSearch down is not fatal — the API automatically falls back to PostgreSQL (`activeSearchEngine: postgresql_fallback`).

## Running the M1–M4 pipelines (replay mode, no network)

```powershell
copy .env.example .env          # once; docker compose reads it
docker compose up -d --wait postgres
./scripts/apply-migrations.ps1  # V1 + V2 + V3 schema + Vero/Stokomak/Zito store seeds

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

## Running the M6 daily pipeline

```powershell
# Run full daily pipeline once (offline fixture replay)
./scripts/run-daily-pipeline.ps1 -FromSnapshots -RunTag m6-local

# Or run polite live scrape for selected stores per retailer
./scripts/run-daily-pipeline.ps1 -Live -StoresMap 'vero=89,stokomak=1,zito=2' -MaxPages 5 -RunTag m6-live

# Start scheduler worker in continuous daemon mode (aligned to 08:30 Europe/Skopje)
docker run -d --name aishopping-scheduler `
  -v "${PWD}:/w" -w /w python:3.12-slim `
  python -B adapters/scheduler/cli.py --daemon --target-time 08:30 --live

# Check freshness & quarantine telemetry via REST API or CLI
curl http://localhost:8080/api/v1/freshness
./scripts/check-freshness.ps1 -ApiUrl http://localhost:8080 -StaleThresholdHours 48
```

## Tests

- Unit tests (stdlib Python 3.12 + JUnit 5 on Java 21):
  - `docker run --rm -v "${PWD}:/w" -w /w/adapters/common python:3.12-slim python -B tests.py`
  - `docker run --rm -v "${PWD}:/w" -w /w/adapters/vero python:3.12-slim python -B tests.py`
  - `docker run --rm -v "${PWD}:/w" -w /w/adapters/stokomak python:3.12-slim python -B tests.py`
  - `docker run --rm -v "${PWD}:/w" -w /w/matching python:3.12-slim python -B tests.py`
  - `docker run --rm -v "${PWD}:/w" -w /w/search python:3.12-slim python -B tests.py`
  - `docker run --rm -v "${PWD}:/w" -w /w/adapters/scheduler python:3.12-slim python -B tests.py`
  - Backend (FastAPI): `cd backend_py && uv run pytest -q`
- Integration tests (scratch DB, idempotency, OpenSearch alias swap, REST API + Postgres fallback, deterministic basket optimization, bounded MCP server, daily pipeline & freshness monitor):
  - `./scripts/test-m1.ps1`
  - `./scripts/test-m2.ps1`
  - `./scripts/test-m3.ps1`
  - `./scripts/test-m4.ps1`
  - `./scripts/test-m5.ps1`
  - `./scripts/test-m6.ps1`
  - `./scripts/test-m9.ps1`
  - `./scripts/test-m10-diff.ps1` (differential: Spring Boot jar vs FastAPI on identical data — regression gate kept until owner sign-off)

## Model Context Protocol (MCP) Server

The FastAPI backend exposes a Model Context Protocol (`2024-11-05`) JSON-RPC 2.0 server at `POST /mcp` (discovery info at `GET /mcp` and `GET /mcp/sse`), enabling AI agents (such as Claude Desktop or Antigravity) to query product intelligence and optimize shopping baskets deterministically without paid LLM APIs on the backend. See [MCP tools contract](docs/contracts/mcp-tools-contract.md).

Registered tools:
1. `search_products`: Catalog offer search with filters and freshness.
2. `compare_product_prices`: Cross-retailer price comparison and spread.
3. `get_price_history`: Immutable observation timeline for canonical products.
4. `list_stores`: Retailer store branch discovery.
5. `find_current_discounts`: Top promotional sales sorted by discount percentage.
6. `optimize_shopping_basket`: Pack-scaled, coverage-first basket optimizer (single & multi-store).
7. `suggest_product_substitutes`: Stage-2 candidate substitutes labeled with confidence and token evidence.

Live fetching (`--url --stores`) follows the politeness rules in
[docs/contracts/vero-adapter-contract.md](docs/contracts/vero-adapter-contract.md) and
[docs/contracts/stokomak-adapter-contract.md](docs/contracts/stokomak-adapter-contract.md);
respect retailer terms and rate limits.
