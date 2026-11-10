# M14 — Public web frontend: stack evaluation

**Date:** 2026-11-10 · **Branch:** `m14-web-evaluation` · **Decision:** see
`docs/adr/ADR-0007-web-frontend-stack.md` (Option 1: server-rendered FastAPI +
Jinja2 in a standalone `web/` app over the existing REST API).

## 1. Upstream reference audit — `supermarkt/checkjebon`

**Pinned commit:** `a6e4de791151920db14cb1d6a8eb29967d9464ad` (repo `main`,
2026-11-10, "Update supermarkets.json").
**License:** MIT (`LICENSE`, "Copyright (c) 2022 supermarkt") — verified from
the pinned tree, license blob `f72ca89030778b92dd563a0a06d61d3db3b6ffdb`.
**Scope of use:** UX/interaction reference only. Per M14 task doc and AGENTS.md
rule 6: no Dutch retailer data, no guessed average prices, no client-side
matching/optimizer, and no frontend code copied.

### Architecture as observed at the pinned commit

`index.html` (static shell) + `js/site/script.js` (Vue 2 root component) +
`css/site/` Tailwind/Lato/FontAwesome assets + `js/tesseract/tesseract.min.js`
(receipt OCR) + `js/fuse/fuse.js` (client-side fuzzy matching) + the external
`checkjebon-js` library loaded from GitHub Pages (client-side retailer price
fetching, product matching, basket plan/optimizer). Everything user-relevant —
product rows, supermarket rankings, totals, the shopping plan table — is
rendered client-side by Vue `v-for` templates after JavaScript loads.

### What we adopt (interaction patterns, not code/data)

| Checkjebon pattern | Adoption in the AI Shopping web slice |
|---|---|
| One shopping-list-centric page flow (enter list → compare → plan) | Search-first journey: `Home → /search?q=… → /compare → /basket → optimize` |
| "Winkel bij meerdere supermarkten" toggle + multi-store plan table with per-store subtotals, total, best-single-store row, extra-savings row | Render `bestMultiStorePlan.storeAllocations` + `savingsVsBestSingleStoreMkd` verbatim from `POST /api/v1/baskets/optimize`; identical table shape |
| Per-product checkbox (bought it), pencil edit, "Niet gevonden" honesty with reason | Basket rows with quantity/unit edit + remove; missing items render machine reasons (`no_offer_at_store`, …) mapped to Macedonian labels |
| Explicit warning that a price is an **estimate** (`~` prefix) | Rejected as a feature — we never estimate; unverified matches render as clearly-labeled Stage-2 substitutes or are excluded |
| Shareable state | Stable shareable `?q=` search URLs + `?retailer=&page=` filters; canonical compare detail URLs `/compare/{canonicalProductId}` |
| Supermarket selection cards | Retailer filter derived from live `/api/v1/freshness` aggregates (no invented retailers) |
| Footer honesty about why supermarkets are missing | Footer states actual coverage: retailers, populated stores, offer counts, freshness timestamp from the API |

### What we deliberately do not adopt

- **Client-side price fetching / matching / optimization** — our FastAPI
  backend is authoritative (ADR-0001/0002/0003); the browser performs no money
  or identity math.
- **Estimated average prices** for unmatched products — forbidden by the task
  and by ADR-0003 (identity ≠ substitution; no invented prices).
- **Vue 2 / Tailwind / FontAwesome / Google Fonts / Tesseract / Fuse.js CDNs** —
  third-party runtime scripts conflict with the "no unapproved third-party
  scripts, no remote fonts" constraint and worsen first-response payload; the
  matching algorithm is not ours to reuse.
- **Receipt OCR** — explicit M14 exclusion.
- **JS-only product content** — the opposite of our SEO requirement (§3).

## 2. Option evaluation (decision matrix)

Scores 1–5 (5 best). "Crawlability" = primary page content present in the
first HTML response without JS; "Ops" = deployment/operational surface added;
"Dev loop" = edit→verify speed on this repo's tooling (Python toolchain
already present; Node/Flutter noted); "Reuse" = reuse of existing
contracts/formatters/patterns; "Risk" = dependency/upgrade risk for a
prototype that must stay maintainable by a small team.

| Criterion | 1. Server-rendered FastAPI + Jinja2 (standalone `web/`) | 2. Next.js SSR (React, HTML-first) | 3. Flutter Web (M12 reuse) |
|---|---|---|---|
| Crawlable first response | **5** (full HTML server-side) | 4 (SSR/SSG, but hydration-dependent widgets) | 1 (canvas/PWAs; HTML mode loses M12 UI reuse) |
| SEO primitives (titles/meta/canonical/sitemap/robots) | **5** (direct template control) | 5 (framework metadata API) | 2 (manual head injection, no SSR content) |
| Accessibility | 4 (plain semantic HTML; standard widgets) | 4 (component ecosystem, larger surface to audit) | 2 (canvas a11y gaps in html renderer) |
| Mobile/desktop responsive, low bandwidth | 4 (hand-rolled CSS, no framework payload) | 4 | 3 (heavy web bundles) |
| Ops: new runtime/toolchain | **5** (Python only, no Node, no new container class) | 2 (Node build+runtime, CI surface) | 3 (Flutter SDK in CI only) |
| Dev loop on this machine/repo | **5** (uvicorn `--reload`, pytest; matches rule 8) | 3 (npm install, build step) | 4 (`flutter run -d web` exists but M12 targets mobile) |
| Reuse of backend contracts (Pydantic DTO shapes, MKD formatters, transliteration) | **5** (same-language ports of `formatters.dart`/`transliteration.dart`; JSON shapes already Python-side) | 3 (re-typeset DTOs in TS) | 3 (Dart models exist, but canvas rendering) |
| Maint. risk for a small team | **5** (Jinja2 + vanilla JS, ~no deps) | 3 (framework churn, lockfile, build config) | 3 (web-specific Flutter quirks) |
| Frontend independence (can later swap/extract) | 4 (standalone process consuming only public REST; no backend imports) | 5 | 3 |
| Cost of running | **5** (one extra Python process; no license/paid deps) | 4 (Node hosting) | 4 |
| **Total** | **52** | **37** | **27** |

Reading: Next.js is the strongest pure-frontend framework but its Node
build/runtime surface buys little for ~4 page types at this stage; Flutter Web
explicitly fails the SEO-first requirement for public catalogue pages (and the
official Flutter guidance for document-oriented public pages recommends
HTML-based rendering — see task doc). The smallest stack meeting the product's
near-term needs is server-rendered HTML from the existing Python toolchain.

### Chosen shape: standalone `web/` FastAPI + Jinja2 app (not backend templates)

The task allows either `web/` standalone or an in-backend template module. We
choose the **standalone `web/` process** that consumes **only the public REST
API over HTTP** (`API_BASE_URL`, default `http://localhost:18089`):

- Zero backend changes for pages: no template/CSS churn inside `backend_py`,
  no new load on the data services beyond normal API calls, and the web tier
  can be replaced later by any other frontend without touching contracts.
- **No CORS exposure**: the browser talks to one origin (the web app); the API
  stays on its private port (localhost/DCI network). The single browser→API
  need (basket optimization) is proxied by one bounded server-side route on
  the web app (`POST /basket/optimize` → `POST /api/v1/baskets/optimize`),
  so no wildcard-CORS privilege is ever opened (task §Phase 3).
- Deployment parity with the API: one extra `uvicorn` process, no build step,
  no Node. In production both processes sit behind the same reverse proxy.

Deliberate limitations (documented, acceptable for the vertical slice):
the MKD/quantity/date formatters and the Latin→Cyrillic transliteration are
re-implemented in `web/app` as direct ports of `mobile/lib/utils/*` (same
behavior, same test expectations) — noted as future shared-package candidates,
not duplicated logic drift (tests pin identical outputs).

## 3. SEO consequences baked into the implementation

- Every page is fully server-rendered semantic HTML (`<main>`, `<article>`,
  headings, tables); product/store names, prices and dates are present in the
  first response without JavaScript (verified by fetching HTML with no JS and
  asserting content — see `docs/milestones/m14-results.md`).
- Unique `<title>`, `<meta name="description">`, `<link rel="canonical">`,
  `lang="mk"` on `<html>`; `<h1>` per page; `aria-live` region for basket
  updates; labelled form controls.
- `robots.txt` + `sitemap.xml` restricted to meaningful stable URLs (`/`,
  `/compare`, canonical compare details); search-result URLs, empty states and
  the basket are excluded from indexing (`noindex` meta on `/search` and
  `/basket`, `Disallow` in robots for API/user paths).
- No trackers, analytics, remote fonts or third-party scripts; system font
  stack only.
