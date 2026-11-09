# M13–M15 — AI Assistant, Web Evaluation, Enhancement Tracks

**Status:** Future proposals; require separate owner approval and testable scopes.

## M13 — In-app AI shopping assistant

- Treat the existing M5 read-only MCP tools as the trusted data interface. First audit compatibility and tool boundaries after M10; improve with batched query ergonomics only if a measured need exists.
- Add a server-side AI orchestration gateway (provider-neutral; no credentials in clients) that converts natural-language requests into search candidates and a proposed basket.
- Request clarification for unresolved products/amounts and represent confidence explicitly. Never merge substitutes with exact products or silently spend money.
- On user confirmation, call the **existing deterministic** basket optimizer; the AI may explain results, never invent prices, stock, discounts, route cost or basket totals.
- Flutter chat integrates with the same basket state/screens, not a disconnected chatbot. Provide inspectable product source, price freshness and changed item diff.
- Add evaluation cases: Macedonian Cyrillic/Latin, ambiguous names, packaging mismatch, out-of-stock, stale data, missing products, model/tool failure, hallucinated totals; regression tests must assert sourced numeric fields.
- Checkout is out of scope. User-specific persistence requires separate privacy/auth review.

## M14 — Separate web frontend evaluation (checkjebon reference)

- Audit `https://github.com/supermarkt/checkjebon`, especially `index.html`, `js/site/script.js`, the referenced `checkjebon-js` library and receipt UI. Inspect actual license and bundled libraries.
- Prototype product search + shopping-list comparison using **AI Shopping API**, not checkjebon's Dutch static catalogue or its price calculator.
- Compare two deployment directions: (a) SEO-friendly React/TypeScript HTML-first web with server rendering/pre-rendering as needed; (b) Flutter Web, which might share mobile UI but is not already scaffolded upstream.
- Record edit-to-feedback loop, bundle/startup speed, SEO indexability for public product pages, accessibility, complexity, code reuse and ownership costs.
- Owner selects web direction before production implementation. Do not create two full web apps prematurely.

## M15 — Incremental enrichment and retention

- **KortingKlok:** product watches, historical price alerts, optional push, possibly borrowing its existing notification UX; auth/FCM require their own security/privacy review.
- **checkjebon:** receipt image capture/review workflow; choose licensed OCR library, adapt Macedonian receipts and merchant line formats. Never upload sensitive receipts without explicit consent.
- **open-supermarkets:** compare its MCP batch calls and agent skills with our existing tool set; adapt useful patterns, not checkout/account flows.
- **price-scraper:** validated GTIN/JSON-LD extraction and enrichment utilities where they add product identity value; retain existing ingestion scheduler and queues.
- For every feature: one PR, fixture tests, provenance, failure behavior, third-party notices and explicit approval.