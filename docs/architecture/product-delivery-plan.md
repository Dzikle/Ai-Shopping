# AI Shopping — Product Delivery Plan v2

**Repository:** https://github.com/Dzikle/Ai-Shopping  
**Reviewed against:** `main`, November 9, 2026.  
**Purpose:** Fill the missing consumer-product, Flutter, web, and AI-assistant work after the data-platform milestones.  
**Status:** Proposed forward plan, not authorization to implement every phase. Owner review gates apply.

## Current baseline — verified from repository contents, not independently executed

- M1-M4: PostgreSQL ingestion, normalized product identity, OpenSearch projections/API, deterministic basket optimization.
- M5: `/mcp` server exposing seven bounded, read-only shopping tools.
- M6: scheduler, quarantine, freshness endpoint and daily pipeline.
- M7: manual product-match review endpoints and CLI.
- M8: metrics REST endpoint and Prometheus-style exporter.
- M9: KAM PDF adapter, live-source discovery and fixture-based integration tests.
- `backend/` on `main` is still Java/Spring Boot and Maven. A FastAPI replacement is **not merged** into `main`.
- There is **no consumer frontend** (`mobile/`, `frontend/`, `web/`) in `main`.
- Existing `docs/milestones/roadmap.md`, `docs/architecture/master-plan.md`, `AGENTS.md` and README have outdated scopes/status. Update these after owner approval; do not mistake their M0 instructions for current progress.
- Some integrations are validated by fixture replay, not by unattended production-like live ingestion. Do not advertise deployment or all-store completeness.

## Architectural invariants

1. PostgreSQL is authoritative; OpenSearch is a rebuildable projection.
2. Product identity is distinct from a substitute, and every displayed price must preserve chain/store, currency, price unit, source URL, publication timestamp, fetch timestamp and freshness.
3. Calculations (unit conversion, pack count, complete-basket ranking, savings) remain deterministic and server-side.
4. Retailer adapters cannot directly mutate the search index; source failures must not delete healthy offers.
5. Public clients must not receive admin/review-queue privileges or credentials. Never embed paid AI API keys in a Flutter build.
6. Preserve existing HTTP/API semantics and matching quality through migration.
7. Prefer code reuse that *reduces* ownership complexity; archived upstream code must be maintained by us and receive attribution.
8. No new paid services or deploying to third-party infrastructure without owner approval.

## Ordered milestones and workstreams

| Stage | Name | Core deliverable | Gate |
| --- | --- | --- | --- |
| **M10 — do now** | Spring Boot → FastAPI migration | Contract-compatible REST **and MCP**, basket, reviews, freshness, metrics with Python hot-reload development loop | Differential checks against existing Java, M1–M9 fixture/integration tests, no regressions; owner review |
| **M11 — next** | KortingKlok mobile feasibility spike | Run upstream Flutter app with mocked feeds, inventory reusable files and dependency liabilities, exercise a real FastAPI endpoint | Android debug build / Flutter tests / realistic reuse estimate; no forced Firebase signup |
| **M12 — mobile MVP** | Flutter customer experience | Macedonian guest browsing, search, retailer comparison, price history, persisted or local shopping list and M4 basket optimizer | End-to-end on Android with fresh/stale/missing-offer handling and deterministic totals |
| **M13** | AI shopping assistant | In-app agent UX invoking bounded MCP/domain tools, structured shopping list creation and editing, evidence-backed explanations | Agent never invents prices or computes totals, user approves basket edits, no checkout |
| **M14 — evaluate alongside M12** | Public web product experience | Compare reusing checkjebon vs new web app, SEO and rendering decision, small functional prototype | Same shared FastAPI contracts, measurable reuse/maintenance cost, owner decision |
| **M15** | Enhancements | Price alerts, receipts, barcode enrichment, history charts, saved lists, notifications | Small independent increments, each fixture-tested, explicit privacy and data-quality constraints |
| **M16** | Release readiness | Accessibility, localization, reliability/monitoring, privacy/security, real-device QA, distribution strategy | Release checklist and real-source coverage, not fixture-only proof |

M10 is an already-stated priority. **Do not automatically begin M11–M16 without an explicit owner go-ahead.** While M10 proceeds, research tasks for M11/M14 can be documented on a separate branch, without replacing running code.

## Upstream reuse map

### KortingKlok (Flutter mobile: primary reuse target)

URL: https://github.com/RashadAnsari/KortingKlok/tree/master/mobile

- Reuse/adapt `mobile/lib/screens/` (`home_screen.dart`, `search_screen.dart`, `api_product_detail_screen.dart`, `main_shell.dart`), `widgets/`, `theme/`, `models/`, `services/`, `l10n/`, and `mobile/test/`.
- Existing app supports Flutter Android/iOS, product list, search, detail, product following, authentication, FCM push notifications, and Dutch/English localization.
- **Not plug-and-play:** `api_service.dart` sends requests to `${API_HOST}/v1`, assumes `FirebaseAuth.instance.currentUser!`, and calls upstream-specific `/products/...` endpoints. AI Shopping exposes `/api/v1/...` with different DTOs. Product-detail UI uses euro (`€`) formatting, not MKD. Existing search is supermarket-oriented; cross-retailer search/compare is central to this product.
- In `main.dart`, Firebase is initialized before the app and sign-in determines entry route. Introduce **guest-first public read-only browsing** with a mockable auth/notification layer before requiring users to configure Firebase. Never ship upstream configuration/identifiers or secrets.
- Handle missing imagery, missing categories and unknown availability as normal conditions; not all statutory feeds supply those fields.
- Add Macedonian Cyrillic localization; Latin queries and English can be supported later. Assess bundle identifiers, licenses and accessibility.
- A mobile target is confirmed; **Flutter Web is not already scaffolded in the upstream repository**, so cross-platform web support is a separate feasibility decision.

### checkjebon (web UX and basket/receipt reference)

URL: https://github.com/supermarkt/checkjebon

- Review `index.html`, `js/site/script.js` and its linked `checkjebon-js` library; extract shopping-list workflow, comparison views, store-selection/splitting interactions and receipt-processing ideas.
- Current site uses older Vue-style global scripting and downloaded local price files. **Do not adopt the full frontend unchanged** or duplicate authoritative basket arithmetic already implemented in the backend.
- For a public searchable catalogue, evaluate server-rendered/SEO-friendly HTML against Flutter Web. Decide after a thin prototype and performance/accessibility comparison.
- Receipt OCR is optional M15 scope, with Macedonian receipts/languages and privacy rules; do not copy vendored OCR/Fuse bundles without separate license checks.

### open-supermarkets (agent integration reference)

URL: https://github.com/abracadabra50/open-supermarkets

- Review `src/mcp-server.ts`, `src/batch.ts`, provider manifest/capability declarations, `SKILL.md` and `src/commands/basket.ts`.
- We **already have M5 MCP**; evaluate *gaps* (batch searches, tool ergonomics, agent skill guidance), do not stand up a second MCP service by default.
- No Macedonian providers upstream; authentication/checkout flows are unrelated to the initial read-only local shopping platform.

### price-scraper (data-enrichment utility reference)

URL: https://github.com/Don-Monteverdi/price-scraper

- Inspect GTIN/JSON-LD extraction, source discovery and resumable execution patterns only where missing in current adapters.
- Existing four-retailer architecture already has scheduler, snapshots and durable runs. Do not replace it with an unrelated SQLite job system.
- Barcode enrichment is M15, not prerequisite for mobile search.

## Consumer experiences to deliver

- **Browse:** promoted/discounted and popular products, retailer and city filters, precise current price, units, source and stale warnings.
- **Search:** Cyrillic and Latin queries, all-retailer results by default, exact product versus substitute clearly distinguished.
- **Compare:** verified canonical product offers by chain/store, quantity and freshness; display missing/unknown stock correctly.
- **Basket:** add/edit quantities, create lists, compare best single store and multi-store plan, explain uncovered items and travel not included unless modeled.
- **AI:** natural-language shopping request → candidate product resolution/confirmation → deterministic optimization → inspectable basket and citations to published offers.
- **Web:** public searchable pages and shopping app may have different rendering requirements; do not force one framework for both without a trade-off study.

## Contracts consumed by Flutter (existing, subject to parity in M10)

- `GET /api/v1/stores`
- `GET /api/v1/offers/search`
- `GET /api/v1/products/compare`
- `GET /api/v1/products/{canonicalId}/history`
- `POST /api/v1/baskets/optimize`
- `POST /api/v1/baskets/lists`, `GET /api/v1/baskets/lists/{listId}`, `POST .../optimize`
- `GET /api/v1/freshness` for high-level freshness indicators.

Existing APIs may require a read-only product-detail aggregate or guest-safe lists/auth behavior. Do **not** fabricate these endpoints: record a specific API contract change request with tests. Backend-admin endpoints for review and operational metrics must not appear in public mobile navigation.

## Agent workflow and evidence

For each milestone: identify exact upstream commit SHA, implement in an isolated branch, preserve licenses, create a failing contract/UI test first when possible, run focused unit tests then integration/device tests, provide screenshots/logs **with actual backend data**, update `docs/milestones/current-status.md` and release an auditable PR. Preserve legacy working code until parity has been verified. Never mark UI complete on mock data alone.