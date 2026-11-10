# AI Shopping Web (M14 prototype)

Server-rendered, HTML-first public web prototype over the existing FastAPI
backend (ADR-0007). Python-only stack: FastAPI + Jinja2 + httpx + vanilla JS.
No Node toolchain, no trackers, no third-party scripts, no remote fonts.

## Pages

| Route | Purpose | SEO |
|---|---|---|
| `/` | Value proposition, search box, live retailer coverage + freshness (`/api/v1/freshness`) | indexable |
| `/search?q=…&retailer=…&instock=…&promo=…&sort=…&page=…` | Real offers from `GET /api/v1/offers/search`; Latin input is transliterated to Cyrillic (M12 parity) | `noindex`, shareable URLs |
| `/compare?q=…` | Verified cross-retailer comparison groups (`GET /api/v1/products/compare`, `minRetailers=2`) | `/compare` indexable; paginated pages `noindex` |
| `/compare/{canonicalProductId}` | Stable canonical product detail (single group via backward-compatible `canonicalId` filter) | indexable, canonical |
| `/basket` | Guest basket in browser `localStorage`; optimization via `POST /basket/optimize` → `POST /api/v1/baskets/optimize` | `noindex, nofollow` |

Supporting routes: `/robots.txt`, `/sitemap.xml` (only `/` and `/compare`),
`/healthz`, `/favicon.ico` (204). The API is never exposed to the browser —
the web app is the only origin (no CORS needed); the single browser→API need
(basket optimize) is a bounded server-side relay (≤64 KB body, ≤50 items).

## Invariants

- All money/quantity/coverage values are rendered verbatim from server
  responses; the browser never computes totals (`web/app/static/basket.js`
  only formats server numbers).
- Only verified identities appear in comparisons; substitutions are never
  silently promoted (optimizer runs with `allowSubstitutes: false`).
- Macedonian (`lang="mk"`) strings in templates; formatters in
  `web/app/formatting.py` and `web/app/static/basket.js` are pinned by tests
  to the same output as the M12 Flutter app (`1.234,50 ден.`).
- Missing availability, empty results and API outages are first-class states
  (503 error page when the catalog is unreachable; home degrades gracefully).

## Run

```powershell
# API on :18089 (see repo root README), then:
cd web
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe -m uvicorn webapp.main:create_app --factory --port 8090   # from repo root
# or, from web/: .venv\Scripts\python.exe -m uvicorn app.main:create_app --app-dir . --factory --port 8090
```

Environment: `API_BASE_URL` (default `http://127.0.0.1:18089`),
`WEB_BASE_URL` (default `http://localhost:8090`; used for canonical URLs and
the sitemap), `API_TIMEOUT_SECONDS` (default `8`).

Open `http://localhost:8090/`.

## Tests

```powershell
cd web
.venv\Scripts\python.exe -m pytest tests -q     # 33 tests (2026-11-10)
```

The suite covers: server-rendered search/compare/basket pages against a real
local stub API (socket-level), Latin→Cyrillic transliteration, MKD/quantity/
date formatting parity, XSS escaping of user input, robots/sitemap/noindex
rules, security headers, and the bounded optimize relay (status relay, size
caps, outage handling). No test accesses the network beyond localhost.
