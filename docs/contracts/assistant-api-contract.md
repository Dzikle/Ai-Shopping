# Assistant API contract (M13)

- Route: `POST /api/v1/assistant/turn` (also `GET /api/v1/assistant/tools` for discovery).
- Guest-safe: unauthenticated, read-only, never mutates a server basket and never
  mutates the client basket — the response only *proposes* changes that a client
  must apply only after an explicit user confirmation.
- Transport: FastAPI, `RestJSONResponse` rendering (Decimals → JSON numbers, ISO-8601
  `Z` instants). Status codes: `200` on typed results, `400`/`422` on request violations,
  `429` rate-limited, `503` when the concurrency cap is reached.
- System prompt, provider credentials and admin tools never reach the client.

## Provider configuration (server-side only)

| Env var | Meaning |
| --- | --- |
| `ASSISTANT_PROVIDER` | `mock` (local deterministic demo) / `openai_compatible` / unset (no model) |
| `ASSISTANT_MODEL` | model id for `openai_compatible` |
| `ASSISTANT_BASE_URL` | OpenAI-compatible base URL (…/v1) |
| `ASSISTANT_API_KEY` | optional bearer token |
| `ASSISTANT_MAX_OUTPUT_TOKENS` | default 1024, clamped 256…4096 |
| `ASSISTANT_TIMEOUT_SECONDS` | default 20, min 5 |
| `ASSISTANT_RATE_LIMIT_REQUESTS` / `ASSISTANT_RATE_LIMIT_WINDOW_SECONDS` | per-client sliding window (30 / 300) |
| `ASSISTANT_MAX_CONCURRENCY` | process-wide concurrent turns (4) |

```bash
# Live model (OpenAI-compatible, any vendor)
ASSISTANT_PROVIDER=openai_compatible ASSISTANT_MODEL=… ASSISTANT_BASE_URL=https://vendor/v1 uv run uvicorn app.main:app --port 8000

# Deterministic demo interpreter (always flagged isMock + warning)
ASSISTANT_PROVIDER=mock uv run uvicorn app.main:app --port 8000
```

When no provider is configured the endpoint answers honestly with
`status=model_unavailable` and warning `model_not_configured`; it never
fabricates assistance.

## Request

```json
{
  "message": "млеко, 500 г брашно и 2 литра јогурт",
  "locale": "mk",
  "conversationContext": [{"role": "user", "content": "…"}],
  "currentBasket": [
    {
      "label": "МАСЛО ПОЗНАТА МАРКА 200Г",
      "canonicalProductId": 2315,
      "retailerProductId": 498,
      "quantity": 1,
      "unit": "pack"
    }
  ],
  "preferences": {"city": "Скопје", "maxStores": 2, "allowSubstitutes": false},
  "candidateSelections": [
    {
      "itemLabel": "каша",
      "query": "каша",
      "candidateId": "c:20:201",
      "quantity": 2,
      "unit": "pack"
    }
  ]
}
```

Bounds: `message` ≤ 500 chars (may be omitted only when `candidateSelections`
is present); `conversationContext` ≤ 6 entries × 400 chars; `currentBasket` ≤ 20
items (label ≤ 120, quantity 0…100000, unit `pack|pcs|g|kg|ml|l`);
`candidateSelections` ≤ 8. `locale` is `mk` (default) or `en`.

`candidateId` format: `c:{canonicalProductId|'u'}:{retailerProductId|offerId}`.
A `c:u:…` id marks an offer whose canonical identity is unverified (a
retailer-product level proposal only).

## Response (200)

```json
{
  "requestId": "asst-0f3a…",
  "status": "ok",
  "assistantMessage": "Прегледав каталог…",
  "provider": {"id": "mock", "model": null, "isMock": true, "configured": true},
  "itemsConsidered": [
    {"label": "млеко", "requestedQuantity": 1.0, "requestedUnit": "pack", "outcome": "proposed_add"}
  ],
  "candidateChoices": [
    {
      "itemLabel": "каша",
      "query": "каша",
      "reason": "multiple_products",
      "requestedQuantity": 1.0,
      "requestedUnit": "pack",
      "options": [
        {
          "candidateId": "c:20:201",
          "canonicalProductId": 20,
          "canonicalName": "КАША ЗРНА 500Г",
          "retailerProductId": 201,
          "listingName": "КАША ЗРНА 500Г",
          "retailerSlug": "vero",
          "storeName": "Веро Тафталиџе",
          "city": "Скопје",
          "normalizedSize": "1x500g",
          "unitPrice": 120.0,
          "unitLabel": "240г/кг",
          "priceCurrentMkd": 60.0,
          "regularPrice": null,
          "discountPct": null,
          "isPromo": false,
          "availability": "in_stock",
          "publishedTs": "2026-10-28T08:00:00Z",
          "fetchedTs": "2026-10-28T09:00:00Z",
          "sourceUrl": "https://…",
          "isSubstituteCandidate": false
        }
      ]
    }
  ],
  "proposedBasketChanges": [
    {
      "changeType": "add",
      "itemLabel": "млеко",
      "canonicalProductId": 10,
      "retailerProductId": 101,
      "listingName": "МЛЕКО БИМИЛК 3.2% 1Л",
      "retailerSlug": "vero",
      "quantity": 1.0,
      "unit": "pack",
      "oldQuantity": null,
      "oldUnit": null,
      "priceCurrentMkd": 75.0,
      "verifiedIdentity": true,
      "isSubstitute": false,
      "publishedTs": "2026-10-28T08:00:00Z",
      "fetchedTs": "2026-10-28T09:00:00Z",
      "sourceUrl": "https://…"
    }
  ],
  "unresolvedItems": [
    {"label": "пикадо", "reason": "no_offers_found"}
  ],
  "toolCalls": [
    {"tool": "search_products", "id": "search:млеко:0", "status": "ok", "summary": {"query": "млеко"}}
  ],
  "optimizationPreview": {
    "previewOnly": true,
    "totalItemsRequested": 2,
    "bestSingleStore": {"…": "existing basket optimizer result shape"},
    "singleStoreRankings": ["… trimmed to 5 entries"]
  },
  "warnings": ["stale_offers"],
  "limits": {
    "messageMaxChars": 500,
    "conversationContextMaxEntries": 6,
    "conversationContextMaxCharsPerEntry": 400,
    "currentBasketMaxItems": 20,
    "maxItemsPerTurn": 8,
    "maxToolCallsPerTurn": 10,
    "candidateSelectionsMax": 8
  }
}
```

### `status` values

| Value | Meaning | Client reaction |
| --- | --- | --- |
| `ok` | grounded turn; proposals may exist and pending picks may too | show proposals / choices normally |
| `needs_clarification` | ambiguous items rejected auto-resolution; explicit `candidateChoices` | user must pick one option each |
| `model_unavailable` | provider outage or no model configured; **no shopping data was fetched this turn** | honest error state; retry |
| `model_error` | provider reachable but output violated the strict contract; nothing applied | honest error; retry |
| `assistant_error` | unexpected server-side failure (details suppressed) | retry |

### `outcome` values (`itemsConsidered`)

`proposed_add`, `proposed_replace`, `already_in_basket`, `needs_clarification`,
`unresolved`.

### Unresolved reasons

`no_offers_found`, `search_failed`, `ambiguous_needs_clarification`,
`tool_budget_exhausted`, `candidate_not_confirmed`, `invalid_quantity`.

`candidate_not_confirmed`: a previously selected `candidateId` did not appear in
the *fresh* catalog search this turn — the proposal is refused instead of
silently replaced with another offer.

### `changeType` values (`proposedBasketChanges`)

- `add` — item absent from the echoed basket; `oldQuantity`/`oldUnit` null.
- `replace_quantity` — same identity found in the echoed basket with a different
  quantity/unit; `oldQuantity`/`oldUnit` echo the basket value.
- `already_in_basket` items appear only in `itemsConsidered` (outcome), never as
  a proposal.

A faithful selection turn (echoing `candidateId`) that resolves returns a
proposal targeted exactly at the selected offer (not the price-best one).

### Warnings

`model_not_configured`, `mock_provider_demo_only`, `provider_outage`,
`model_invalid_response`, `tool_budget_exhausted`,
`substitute_candidates_unverified`, `optimizer_preview_unavailable`,
`stale_offers` (whole search offer set older than 48 h), `internal_error`.

`limits` mirrors the enforced payload bounds so clients can prevalidate input.

### Preview

`optimizationPreview` is the *existing* deterministic
`optimize_shopping_basket` result over the echoed basket plus the proposals
(replaced items are dropped first), with `allowSubstitutes` from the request
preferences (default false), `inStockOnly: true`, `maxStores` default 2,
`singleStoreRankings` trimmed to 5, and `previewOnly: true`. Nothing is
persisted; clients must re-run the normal basket optimizer to confirm totals
after applying.

## Roles and tool surface

- Only allowlisted read-only shopping tools are reachable:
  `search_products`, `compare_product_prices`, `get_price_history`,
  `list_stores`, `find_current_discounts`, `optimize_shopping_basket`,
  `suggest_product_substitutes` — with the current coordinator dispatching
  `search_products`, `suggest_product_substitutes`, `optimize_shopping_basket`
  (`GET /api/v1/assistant/tools` reports both sets).
- Per-turn tool-call budget: 10 calls (≤ 8 item searches of size 6, ≤ 1
  substitute probe with ≤ 2 supporting searches, 1 optimizer preview).
- Reviewer/queue/admin tools, raw SQL and tool registration are structurally
  unreachable from this route.

## Model contract (`openai_compatible`)

One `POST {base_url}/chat/completions` per turn, `temperature: 0`, no retries,
no streaming. The model must answer with exactly:

```json
{"items": [{"label": "производ", "quantity": 2, "unit": "l"}], "assistantMessage": "…"}
```

Labels only (≤ 8 items, ≤ 80 chars, normalized to Cyrillic); never product IDs,
prices, stock or totals. Any top-level money-like key (`price|total|cost|…`,
including a trailing `denar`/`mkd` alias key such as `estimatedTotalMkd`) makes
the turn fail as `model_error`; fenced JSON is tolerated; unknown keys ignored.
HTTP/4xx/5xx, timeout or unreachable → `model_unavailable`.

## Known limits

- Rate limiting/concurrency are per-process (single-process deployment);
  a shared store is required for multi-worker deployments.
- Substitute suggestions are Stage-2 review-queue records: they are offered
  only as explicitly flagged unverified choices (`isSubstituteCandidate: true`,
  warning `substitute_candidates_unverified`), never as verified identities.
- The model has no per-turn server state; the client supplies the prior
  conversation context and basket echo explicitly every turn.
