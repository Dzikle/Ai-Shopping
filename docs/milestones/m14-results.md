# M14 — Public web frontend evaluation and prototype: results

**Branch:** `m14-web-evaluation` (based on `main` @ `4ba0e94`)
**Date:** 2026-11-10
**Status:** **Evaluated, functional prototype** — not a production launch.
**Decision:** ADR-0007 — standalone server-rendered **FastAPI + Jinja2** app in
`web/` over the existing REST API (no Node runtime, no Flutter Web, no CORS
exposure). Evaluation + pinned Checkjebon audit:
`docs/research/m14-web-stack-evaluation.md`.

## Scope delivered

One HTML-first web vertical slice (`web/`), Macedonian-first (`lang="mk"`),
consuming only the public guest-safe API:

- **Home `/`** — value proposition, search box, live retailer coverage and
  freshness from `GET /api/v1/freshness` (status badge, per-retailer offer
  counts/store counts/latest published date), "how it works".
- **Search `/search?q=…&retailer=…&instock=…&promo=…&sort=…&page=…`** —
  real offers from `GET /api/v1/offers/search` (name, catalog name, retailer,
  store, city, normalized size, unit price, MKD price, promo badge only when
  `isPromo` is backed by data, strikethrough regular price, availability
  note, published date, source link). Latin input is transliterated to
  Cyrillic server-side (direct port of the M12 Dart algorithm; a note is
  shown). Retailer filter is derived from freshness data — nothing invented.
  Stable shareable URLs (GET form), pagination preserving all filters.
- **Comparisons `/compare?q=…` and `/compare/{canonicalProductId}`** — only
  verified identity groups (`minRetailers=2`); cheapest/highest/spread in
  MKD, per-retailer price ranges, store counts, publish dates, source links;
  single-retailer products honestly labeled. The stable canonical detail URL
  is served through a **backward-compatible optional `canonicalId` filter**
  added to `GET /api/v1/products/compare` (documented route-gap solution;
  OS term filter + PG WHERE clause, existing behavior unchanged).
- **Basket `/basket`** — guest basket in browser `localStorage` (no account);
  quantity/unit editing, remove, clear; **Optimize** relays to the existing
  `POST /api/v1/baskets/optimize` (server-side deterministic math; the
  browser formats but never computes). Renders best single store (coverage
  first, `X/Y`, savings vs highest covered single store), multi-store plan
  (per-store subtotals, savings vs best single, threshold verdict,
  recommendation reason), top-5 rankings, and missing items with machine
  reasons mapped to Macedonian labels. `allowSubstitutes=false` — no
  Stage-2 leakage. 0-coverage stores show `–` instead of a fake total.
- **SEO/technical** — semantic SSR HTML (content present in the first
  response, no JS required), unique titles/meta descriptions/canonical URLs,
  `robots.txt` (`Disallow: /basket`, `/api/`) and a sitemap restricted to
  `/` and `/compare`; `noindex` on search and paginated compare pages;
  security headers (CSP `default-src 'self'`, nosniff, referrer policy); no
  trackers, analytics, remote fonts or third-party scripts (system fonts,
  hand-rolled ~7.6 KB CSS, ~15.5 KB progressive-enhancement JS).

## Stack decision evidence (summary)

Scores in `docs/research/m14-web-stack-evaluation.md`: FastAPI+Jinja2 **52**,
Next.js 37, Flutter Web 27 across crawlability/SEO/ops/dev-loop/reuse/
maintainability. Checkjebon (MIT, pinned `a6e4de791151920db14cb1d6a8eb29967d
9464ad`) was used for interaction patterns only; its client-side price
fetching, **estimated average prices**, JS-only rendering and CDN libraries
were explicitly rejected.

## Verification evidence (all executed 2026-11-10)

1. **Backend regression:** `pytest` in `backend_py` → **25 passed**
   (24 pre-existing + 1 new `canonicalId` test covering the OpenSearch path,
   the PostgreSQL fallback path, and omitted-parameter backward compatibility).
2. **Web unit/integration:** `pytest` in `web` → **33 passed** (real local
   stub API over a socket): server-rendered search/compare/detail/basket,
   transliteration (`mleko`→`млеко` recorded by the stub), filter/sort/pagination
   forwarding, XSS escaping (`<script>` in `q` is escaped), honest empty
   states, API-outage error page (503) with graceful home degradation,
   MKD/quantity/date formatting parity, robots/sitemap/noindex/canonical
   rules, security headers, and the optimize relay (payload relay fidelity,
   400/422/413/503 semantics, oversized item list rejection).
3. **Browser smoke (Playwright/Chromium, `web/tools/browser_smoke.py`):**
   full journey **desktop 1280×900** and **true mobile 390×844 device
   emulation** — home → Cyrillic search → offer rendered → Latin search note →
   add to basket (badge count) → verified comparison → canonical detail →
   add (duplicate merges into one line, quantity 2) → basket → optimize →
   server totals rendered verbatim (`Вкупно: 75,00 ден.`, `ВЕРО 1`), sent
   payload asserted to carry quantity 2 (no client-side conversion).
   **PASS with zero console/page errors.**
4. **SEO evidence (no JavaScript):** plain HTTP fetch of `/`, `/search?q=млеко`,
   `/compare`, `/compare/10` — titles, `h1`s, offer/comparison names, prices
   (`75,00 ден.`, `85,00 ден.`), dates and canonical links all present in the
   first response; robots/sitemap contents recorded in the test suite.
5. **Performance (local, fixture data — not production Core Web Vitals):**
   Lighthouse 12 on `/compare/10`: **Performance 100, Accessibility 100,
   Best-Practices 100, SEO 100**; FCP 755 ms, LCP 1055 ms, CLS 0, TBT 0 ms.
   Page weight: HTML 3.4–4.1 KB per page + 7.6 KB CSS + 15.5 KB JS; no
   third-party requests. Toolchain iteration speed: `uvicorn --reload`
   sub-second Python template edits (no build step).
6. **Screenshots (fixture data, actually rendered):**
   `docs/milestones/m14-screenshot-{home,search,compare,compare-detail,
   search-mobile,home-mobile,basket-results}.png`.

## Honest scope note: catalogue data

Docker Desktop cannot start on this machine today (WSL2 reports "Failed to
detect nested virtualization"), so a live PostgreSQL/OpenSearch catalogue run
was **not possible in this environment**. The smoke therefore ran against the
**documented fixture API** (`web/tools/run_fixture_api.py`) serving exactly
the canned records used by the test suite (mirroring `backend_py` fixtures:
Vero/Stokomak milk offers). All screenshots show fixture data, clearly
captioned; **no fabricated market prices are presented as real**, and the
same pages render whatever the real API returns when `API_BASE_URL` points at
a live backend. Re-running the journey against a live stack is a follow-up
for an environment where Docker works.

## Known limitations

- `robots.txt`/`sitemap.xml` use `WEB_BASE_URL` — correct absolute URLs
  require setting it in deployment (defaults target localhost).
- Rate limiting/DoS hardening, caching strategy (beyond the 60 s freshness
  TTL) and PRG patterns for the basket are deployment-phase concerns.
- The web tier does not call `/products/{id}/history` (price-history chart is
  a Flutter-screen feature; web follow-up if wanted).
- Macedonian-only UI (no `en` switcher); strings live in templates — a shared
  mk/en mechanism is trivial to add later but was not needed for the slice.
- Transliteration is dictionary-free word-local normalization (same limits as
  M12: exotic romanizations may miss; the raw-Cyrillic search remains usable).
- `web/tools/run_fixture_api.py` is a local demo helper only — it must never
  be deployed or presented as real market data.

## Deliverables in this PR

- `web/` — FastAPI+Jinja2 app (`app/`), templates, static assets, tests,
  fixture-API runner and Playwright smoke (`tools/`), `README.md`,
  `requirements.txt`.
- `backend_py/` — backward-compatible `canonicalId` filter on
  `GET /api/v1/products/compare` (+ contract doc update, + test).
- `docs/research/m14-web-stack-evaluation.md`, `docs/adr/ADR-0007-web-
  frontend-stack.md`, `docs/milestones/m14-results.md` (this document),
  `docs/milestones/current-status.md`, `docs/milestones/roadmap.md`,
  `AGENTS.md`, root `README.md`, `.github/workflows/ci.yml` (web gate).

M13 remains a separate open PR; nothing from `m13-ai-shopping-assistant` was
merged or copied into this branch (M14 branched from `main` @ `4ba0e94`, and
the only backend change is the tested `canonicalId` filter above). No public
deployment, no M15 work.
