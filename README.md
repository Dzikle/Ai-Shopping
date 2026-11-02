# AI Shopping — Universal Price Intelligence Platform

A retailer-agnostic platform for daily price ingestion, canonical product matching, store-level comparison, price history, deterministic basket optimization, and AI-assisted grocery shopping. **Status: M0 + M1 (Vero) + M2 (Stokomak + Zito + canonical identity & matching) + M3 (OpenSearch projections & search/comparison REST API) + M4 (Shopping lists, unit conversion & deterministic single/multi-store basket optimization) + M5 (bounded read-only MCP server & AI tool layer) implemented — see [current status](docs/milestones/current-status.md).** No deployed implementation is implied.

Initial focus: North Macedonia. Expansion: other countries, retailers and product categories.

Start with [the master plan](docs/architecture/master-plan.md), [the milestone roadmap](docs/milestones/roadmap.md) and [AGENTS.md](AGENTS.md).

Core design: Spring Boot / Java 21, PostgreSQL source of truth, OpenSearch derived indexes, independent Python/TypeScript adapters, optional Redis worker queues, Docker Compose, MCP read-only tools.

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

## MCP server (read-only AI tool layer, M5)

The MCP server exposes the M3/M4 REST API to AI agents as nine bounded,
strictly read-only tools. It needs only Python 3.12 (stdlib) and a running
backend: no database, JVM or Docker. See
[docs/contracts/mcp-tools-contract.md](docs/contracts/mcp-tools-contract.md).

```bash
python3 -B mcp_server/tests.py                 # contract tests vs. in-process mock API
python3 -B -m mcp_server.cli --list-tools      # print the versioned tool contract

# stdio MCP server (what an agent host launches)
AI_SHOPPING_API_BASE=http://localhost:8080 python3 -B -m mcp_server.cli
```

Tools: `search_products`, `get_product_details`, `compare_product_prices`,
`get_price_history`, `find_stores`, `find_current_discounts`,
`suggest_product_substitutes`, `optimize_shopping_basket`, `get_catalog_health`.
Prices, pack counts, unit conversions and basket totals are always the backend's
deterministic values; substitution candidates are always flagged
`not_verified_equivalent`.

## Tests

- Unit tests (stdlib Python 3.12 + JUnit 5 on Java 21):
  - `docker run --rm -v "${PWD}:/w" -w /w/adapters/common python:3.12-slim python -B tests.py`
  - `docker run --rm -v "${PWD}:/w" -w /w/adapters/vero python:3.12-slim python -B tests.py`
  - `docker run --rm -v "${PWD}:/w" -w /w/adapters/stokomak python:3.12-slim python -B tests.py`
  - `docker run --rm -v "${PWD}:/w" -w /w/matching python:3.12-slim python -B tests.py`
  - `docker run --rm -v "${PWD}:/w" -w /w/search python:3.12-slim python -B tests.py`
  - `docker run --rm -v "${PWD}:/w" -w /w python:3.12-slim python -B mcp_server/tests.py`
  - `docker run --rm -v "${PWD}/backend:/w" -v aoshopping-m2-repo:/root/.m2 -w /w maven:3.9.9-eclipse-temurin-21 mvn -B test`
- Integration tests (scratch DB, idempotency, OpenSearch alias swap, REST API + Postgres fallback, deterministic basket optimization, read-only MCP tool layer):
  - `./scripts/test-m1.ps1`
  - `./scripts/test-m2.ps1`
  - `./scripts/test-m3.ps1`
  - `./scripts/test-m4.ps1`
  - `./scripts/test-m5.ps1` (add `-ApiBase http://localhost:8080` for the live MCP handshake)

Live fetching (`--url --stores`) follows the politeness rules in
[docs/contracts/vero-adapter-contract.md](docs/contracts/vero-adapter-contract.md) and
[docs/contracts/stokomak-adapter-contract.md](docs/contracts/stokomak-adapter-contract.md);
respect retailer terms and rate limits.
