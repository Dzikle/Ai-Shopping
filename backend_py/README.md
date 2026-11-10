# AI Shopping backend (FastAPI)

Python port of the AI Shopping backend (M10; ADR-0006). Serves the guest
catalog/compare endpoints, the deterministic basket optimizer, health/freshness,
and the bounded read-only MCP surface backed by PostgreSQL (authoritative) and
OpenSearch (rebuildable). The M13 AI assistant adds one guest-safe chat route
plus a provider-neutral adapter inside the same app — no second backend.

## Run

```powershell
# infra (PostgreSQL + OpenSearch) from the repo root
docker-compose up -d --wait

# app
cd backend_py
uv sync
uv run uvicorn app.main:app --host 0.0.0.0 --port 18089
```

Health: `GET /api/v1/health` → `{"status":"UP", ...}`. When OpenSearch is
unreachable, catalog/search/compare fall back to PostgreSQL automatically
(`sourceEngine = "postgresql_fallback"`).

Environment (subset): `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`,
`OS_HOST/OS_PORT/OS_SCHEME` (or `SEARCH_ENGINE=postgres`), `SCHEDULER_ENABLED`,
`SHOPPING_LISTS_ENABLED`. M13 assistant keys: `ASSISTANT_PROVIDER`
(`mock` default | `openai_compatible`), `ASSISTANT_MODEL`,
`ASSISTANT_BASE_URL`, `ASSISTANT_API_KEY`, `ASSISTANT_TIMEOUT_SECONDS`,
`ASSISTANT_MAX_TOKENS`, `ASSISTANT_TOOL_CALL_BUDGET`,
`ASSISTANT_RATE_LIMIT_WINDOW_SECONDS`, `ASSISTANT_RATE_LIMIT_MAX`,
`ASSISTANT_MAX_CONCURRENCY`. With no provider configured the assistant answers
with the honest `model_unavailable` status — the mock provider is for
development/tests only.

## Surfaces

- Catalog/guest: `GET /api/v1/stores`, `GET /api/v1/offers/search`,
  `GET /api/v1/products/compare`, `GET /api/v1/products/{id}/history`,
  `GET /api/v1/freshness` (+ persistent list endpoints under `/baskets/lists`
  when enabled).
- Baskets: `POST /api/v1/baskets/optimize` — deterministic MKD totals,
  coverage, missing-item reasons; substitutions only when explicitly allowed.
- MCP: `POST /mcp` JSON-RPC (`tools/list`, `tools/call`) over the same
  read-only domain tools — see `docs/contracts/mcp-tools-contract.md`.
- Assistant (M13): `POST /api/v1/assistant/turn` — bounded single-turn chat;
  the model only selects/labels, the coordinator verifies everything against
  the catalog; proposals are returned, never applied server-side. Plus
  `GET /api/v1/assistant/tools` publishing the tool allowlist vs dispatch.
  Contracts: `docs/contracts/assistant-api-contract.md`,
  `docs/contracts/basket-api-contract.md`.

## Layout

```
app/
  main.py                app factory + routers + module-level assistant wiring
  config.py              typed settings (env)
  db.py                  psycopg connection pool
  jsonx.py               Spring-shaped JSON response helpers
  routes/                catalog, baskets, assistant (M13)
  schemas/               request/response Pydantic models (incl. assistant)
  services/              optimizer, unit conversion, search, OpenSearch client
  repositories/          SQL data access
  mcp/                   tool registry + JSON-RPC protocol
  assistant/             M13 coordinator, provider adapter, rate limiting,
                          transliteration helper
tests/                   pytest suite (42 tests incl. assistant)
tools/                   offline determinism / fairness tools
```

## Tests

```powershell
cd backend_py
.venv\Scripts\python.exe -m pytest       # 42 passed (2026-11-10)
```

Assistant coverage lives in `tests/test_assistant_api.py` (mock provider,
ambiguous requests, candidate-not-confirmed refusals, substitute probes,
stale/echo semantics, provider outage, invalid model output, an in-process
`openai_compatible` chat server, rate limit, tool budget). No test ever calls a
network LLM provider.

## Notes

- Prices/quantities/totals are computed deterministically server-side only;
  assistant responses never carry authoritative totals (clients call the
  optimizer when a proposal is confirmed).
- Basket persistence is intentionally not touched by the assistant route.
- See `docs/milestones/m13-results.md` for M13 evidence and known limits.
