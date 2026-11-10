# M14 — Public web frontend evaluation and functional prototype

**Repository:** https://github.com/Dzikle/Ai-Shopping  
**Owner approval:** 2026-11-10 ("Ok next" after the M13 delivery)  
**Starting point:** M10 FastAPI + M12 Flutter are merged in `main`. M13 PR #4 passed GitHub Actions but remains open/unmerged at the time of this authorization.  
**Status:** Approved for M14 **evaluation and a working web vertical slice**, not production launch or a full web rewrite.  
**Reference:** https://github.com/supermarkt/checkjebon — pin upstream commit/license before copying code; it is a UX and architecture reference, not our price engine.

## Why M14

AI Shopping needs a publicly discoverable, fast, accessible supermarket-price comparison experience for North Macedonia. A website should be indexable by search engines and share the exact same FastAPI/PostgreSQL/OpenSearch data and M4 basket optimizer as the Flutter app.

An app-centric Flutter Web build is attractive for code reuse, but its normal canvas rendering is weaker for SEO-centric public product pages. Official Flutter documentation recommends document-oriented HTML/Jaspr for SEO-heavy public pages. Compare options pragmatically; don't conflate a private shopping-app SPA with public catalogue pages.

The M14 goal is to produce **one functional, reviewable, HTML-first web prototype with real catalogue data** and a grounded decision about the best maintainable web stack. Do not build three separate applications just to compare frameworks.

## Core user journey (real data)

On desktop and mobile browsers:

`Home → Search "млеко" or "mleko" → Inspect real offer prices in ден. → Open verified cross-retailer comparison → Add item(s) to local guest basket → Optimize basket via FastAPI → See real best single- and multi-store prices, coverage and missing items.`

If the baseline lacks enough catalogue records for a requested term, use documented fixture data and report it honestly. Never show hardcoded examples as real market prices.

## Phase 1 — audit and choose a minimally sufficient stack

Read:

- `AGENTS.md`, `docs/architecture/product-delivery-plan.md`
- `docs/milestones/m12-results.md`, `docs/milestones/m13-results.md` (from M13 PR if not merged)
- `docs/contracts/search-api-contract.md`, `docs/contracts/basket-api-contract.md`
- `mobile/lib/models/api_models.dart`, `mobile/lib/services/api_client.dart`
- `backend_py/app/routes/catalog.py`, `backend_py/app/routes/baskets.py`

Audit pinned Checkjebon files (`index.html`, `js/site/script.js`, `css/`, its `checkjebon-js` library) and license. Identify what to adopt as interaction patterns: query-to-list, supermarket selection, price comparison, list persistence, mobile-friendly basket, shareability. Do **not** copy their Dutch retailer data, guessed average prices, matching algorithm or separate optimizer. Our backend is authoritative; exact identity and substitutions remain distinct.

Evaluate the following options with a short decision matrix:

1. **Lightweight HTML-first server rendering** using the existing FastAPI runtime (Jinja2 + modest JS/HTMX or equivalent) — minimal deployment/operational complexity, server-generated semantic markup, but may complicate frontend independence.
2. **Modern HTML-first React framework** with SSR/SSG/ISR where appropriate (e.g. Next.js) — good route-level SEO and UI ecosystem, but adds a Node/JS deployment surface.
3. **Flutter Web** with existing M12 code — maximum UI reuse but weaker document-oriented public catalogue SEO and potentially heavier web bundles.

Score: crawlable first-response content, sitemap/canonical support, accessibility, browse/search speed, mobile usability, reuse, maintainability, dev loop and actual operating costs. Prefer the **smallest stack** that meets the product's near-term needs. Default to HTML-first, but don't pre-decide FastAPI templates vs SSR framework without a concrete trade-off. Record an ADR in `docs/adr/` and a short `docs/research/m14-web-stack-evaluation.md`.

Avoid adding microservices, Redis, queues, a new shopping engine, separate database, or a large frontend component library for the spike.

## Phase 2 — implement one working web vertical slice

Use `web/` for a standalone frontend, or a deliberately isolated FastAPI template/static module if that option wins; document the structure and startup command. Do not modify the Flutter app just to implement web, or add a new public deployment.

Required pages/interactions:

### Public homepage
- Clear Macedonian-first value proposition and prominent product search box.
- Actual supported retailers and data freshness/scope based on FastAPI, not invented nationwide coverage.
- Responsive and usable at narrow phone widths and on desktop.
- Helpful empty/error/loading states.

### Catalogue search
- Consume `GET /api/v1/offers/search` and/or `GET /api/v1/stores`.
- Support Macedonian Cyrillic and reasonable Latin input handling, consistent with backend and M12; document any transliteration limitations.
- Display offer name, retailer/store, pack/quantity/unit where known, actual MKD price, date/source, promotional markers only if backed by data.
- Store/retailer filters, pagination and no-results/error states.
- Stable shareable `?q=` URLs, with query encoding that supports Cyrillic.

### Verified product comparisons
- Consume `GET /api/v1/products/compare`.
- Render only verified canonical identity groups as exact comparisons; don't silently promote Stage-2 substitutes.
- Show price ranges, compared stores, actual quantities, timestamps and source URLs.
- Handle single-retailer offers honestly (offer detail, not fake multi-store comparison).
- If a stable indexed canonical product detail URL cannot be supported from existing endpoints, document the route gap and implement the minimal safe solution rather than inventing a direct product-detail API.

### Guest basket and optimization
- Allow adding real `canonicalProductId` or `retailerProductId` from offer results, editing quantities/units, removing entries, and saving locally in the browser (no account requirement).
- Call existing `POST /api/v1/baskets/optimize`, not browser-side money/quantity math.
- Show best single-store and eligible multi-store plan, coverage, missing items, substitutes only on explicit opt-in and provenance warnings.
- Preserve backend ranking semantics: coverage first. Never present partial subtotals as complete basket savings.

## Phase 3 — SEO and technical essentials

For actual public catalogue pages:

- Deliver semantic HTML containing primary page content at the initial request (or an equivalent verifiably crawlable pre-render). **Do not make search bots depend on client-side CanvasKit, login or JS-only hydration to see titles and text.**
- Use sensible unique page titles, meta descriptions, canonical URLs and proper `lang=mk` where appropriate.
- Use robots/sitemap only for meaningful stable URLs. Do not dynamically index every arbitrary search query, empty result, user basket or internal API endpoint.
- No invented product reviews, aggregate ratings, stock claims, offers or structured data attributes. Add product/offer schema markup only when every field is grounded and the pages qualify.
- Reasonable accessibility: keyboard navigation, labels, headings, contrast, focus, aria-live for asynchronous results where helpful; test screen-reader-visible text.
- Mobile/desktop responsive layout, safe handling of null imagery and slow/offline API.
- Avoid exposing local dev-only API endpoints publicly. If the web frontend is served cross-origin, document CORS and secure routing rather than allowing wildcard privilege. Keep admin endpoints and `/mcp` off the consumer surface.
- Do not add trackers, analytics pixels, remote fonts/asset bundles or unapproved third-party scripts by default.

## Phase 4 — verification

**Automated checks:** syntax/lint/type tests appropriate to chosen stack; contract parsing; currency and timestamp formatting; search/query encoding; canonical identity vs substitutes; basket requests; backend-controlled optimizer totals; input/HTML escaping and XSS; no API/admin secrets in the browser.

**Browser smoke:** run against FastAPI with existing fixture/real locally loaded data, using Playwright or another already-available browser tool if feasible. Verify the end-to-end journey on desktop viewport and narrow mobile viewport. Save screenshots only when they actually render.

**SEO evidence:** inspect fetched HTML without JavaScript and demonstrate title, product/store text and relevant source dates are present; test a meaningful deep link. Distinguish what is and is not indexable.

**Performance:** record local page size, cold/interactive behavior, a simple Lighthouse run or equivalent where available, and toolchain iteration speed; don't claim production Core Web Vitals or SEO rankings from a local test.

**Regression:** avoid changing backend API contracts; if absolutely required, add backward-compatible endpoint tests and keep M1–M10 plus M12 workflows unaffected. M13 remains a separate PR, and merging M14 must not accidentally merge or rewrite the M13 assistant branch.

## Phase 5 — deliver and decision gate

Deliver:
- A runnable web prototype integrated with real FastAPI data.
- `docs/research/m14-web-stack-evaluation.md` (pinned Checkjebon reuse audit + decision matrix).
- A short ADR on chosen web stack and deployment trade-offs.
- `docs/milestones/m14-results.md` including screenshots, test commands/outcomes, real-data examples, SEO evidence and limits.
- Web setup/commands, env handling, README and a lean CI job where practical.
- Updates to roadmap/current-status/AGENTS after actual delivery.

Work on `m14-web-evaluation` branched from up-to-date **`main`**. Push changes and open a pull request. **Do not merge automatically.** Keep AI chat/M13 out of this web prototype while its PR is unmerged; after M13 lands, web AI integration is a separately gated follow-up.

## Explicit exclusions

- No full production web release, hosting, domain configuration, SEO submission or ad/analytics tracking.
- No receipt OCR, barcode/GTIN enrichment, push alerts or checkout.
- No new retailer adapters or rewrites of the existing identity/basket engine.
- No copying Dutch data or speculative/estimated product prices from Checkjebon.
- No unapproved paid service, authentication rollout or Java rollback removal.

## Acceptance

M14 is complete as an **evaluated, functional prototype** when a browser can search a real catalogue, compare verified prices and optimize a local basket using the existing FastAPI backend; HTML/SEO evidence and stack decision are documented; relevant automated/browser checks pass; and a reviewable PR exists. It is not a production launch.

**Proceed autonomously: research quickly, choose one stack, build the thin working slice, test it, document evidence and push the PR.**
