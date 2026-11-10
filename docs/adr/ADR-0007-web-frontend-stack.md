# ADR-0007: Public web frontend — server-rendered FastAPI + Jinja2 in a standalone `web/` app

- **Status:** Accepted (2026-11-10) — M14 evaluation outcome
- **Context:** M14 requires one publicly discoverable, SEO-capable web
  experience (search, verified cross-retailer comparison, guest basket,
  server-side deterministic optimization) over the existing FastAPI backend.
  Three options were scored in `docs/research/m14-web-stack-evaluation.md`:
  (1) server-rendered FastAPI + Jinja2, (2) Next.js SSR, (3) Flutter Web
  (reusing M12). The decisive criteria were crawlable first-response HTML,
  SEO primitives, the smallest operational surface (no Node runtime, no new
  container class), fast Python dev loop, and reuse of existing DTO shapes and
  M12 formatter/transliteration behavior. Flutter Web fails the SEO-first
  requirement for public catalogue pages; Next.js adds a Node build/runtime
  surface disproportionate to a four-page slice. Checkjebon (MIT, pinned
  `a6e4de7`) was used as an interaction-pattern reference only; its
  client-side price fetching, estimated average prices and JS-only rendering
  were explicitly rejected.
- **Decision:** Build the web tier as a **standalone FastAPI + Jinja2
  application in `web/`** that renders all pages server-side and consumes
  **only the public REST API** (`GET /api/v1/stores|offers/search|
  products/compare|products/{id}/history|freshness`,
  `POST /api/v1/baskets/optimize`) via an HTTP client pointed at
  `API_BASE_URL` (default `http://localhost:18089`). No backend `backend_py`
  imports, no direct DB/OpenSearch access, no second optimizer, no persistent
  chat/basket store: the guest basket lives in browser `localStorage` and all
  money math stays in the existing basket service. The single browser→API
  interaction (optimize) is proxied through one bounded server-side route
  (`POST /basket/optimize`) so the API never needs public CORS exposure.
  Presentation is hand-rolled responsive CSS (system fonts, no third-party
  scripts/trackers/remote fonts), `lang="mk"`, with unique titles, meta
  descriptions, canonical URLs, `robots.txt` and a sitemap limited to stable
  URLs. MKD/quantity/date formatters and Latin→Cyrillic transliteration are
  direct Python ports of `mobile/lib/utils/formatters.dart` and
  `transliteration.dart`, pinned by tests to identical outputs.
- **Alternatives considered:** (a) Jinja2 templates *inside* `backend_py` —
  rejected: couples presentation into the API service and complicates later
  replacement; the standalone process keeps frontend independence at the cost
  of one extra uvicorn process. (b) Next.js — rejected for now: strongest
  frontend ecosystem but a Node toolchain/deployment surface the product does
  not yet need; revisit if the web surface grows beyond server-rendered
  catalogue/basket pages. (c) Flutter Web — rejected: canvas-first rendering
  is weak for document-oriented public catalogue SEO and M12's UI targets
  mobile interaction patterns.
- **Consequences:** One additional Python process to run/monitor
  (`uvicorn webapp.main:create_app --factory` with `API_BASE_URL`,
  `WEB_BASE_URL` env); no CORS configuration required; the API surface stays
  unchanged (only a backward-compatible optional `canonicalId` filter was
  added to `GET /api/v1/products/compare` to support stable canonical detail
  URLs — the documented route gap solution, tested on both search engines).
  SEO claims remain limited to what is verified locally (first-response
  content, robots/sitemap, no-JS fetch evidence); no production deployment,
  hosting or domain work is included in M14. If the web product later needs
  client-heavy interactions or an SPA, the standalone boundary makes a swap
  to any HTML-first framework possible without backend changes.
