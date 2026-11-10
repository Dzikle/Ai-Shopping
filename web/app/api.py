"""HTTP client for the public AI Shopping REST API (read-only surfaces).

The web tier consumes only the guest-safe endpoints documented in
docs/contracts/search-api-contract.md and basket-api-contract.md. No admin
endpoints, no /mcp, no review queue, no metrics. All money math stays in the
backend optimizer; this module only fetches and relays JSON.
"""

from typing import Any

import httpx


class ApiError(Exception):
    """The API is unreachable, too slow, or answered with a server error."""


class ApiNotFound(Exception):
    """The API answered 404 for a well-formed request."""


class ApiClient:
    def __init__(self, base_url: str, timeout: float = 8.0, transport: httpx.BaseTransport | None = None):
        self._client = httpx.Client(
            base_url=base_url.rstrip("/"),
            timeout=httpx.Timeout(timeout),
            transport=transport,
            headers={"Accept": "application/json"},
            follow_redirects=False,
        )

    def close(self) -> None:
        self._client.close()

    # ---- read-only catalog surfaces -------------------------------------

    def get_freshness(self) -> dict[str, Any]:
        return self._get_json("/api/v1/freshness")

    def search_offers(self, params: dict[str, Any]) -> dict[str, Any]:
        return self._get_json("/api/v1/offers/search", params=params)

    def compare_products(self, params: dict[str, Any]) -> dict[str, Any]:
        return self._get_json("/api/v1/products/compare", params=params)

    # ---- basket optimization (relayed to the browser) -------------------

    def optimize_basket(self, payload: dict[str, Any]) -> tuple[int, dict[str, Any] | None]:
        """POST /api/v1/baskets/optimize; returns (status, body) so the web
        route can relay the API's own validation/status semantics."""
        try:
            response = self._client.post("/api/v1/baskets/optimize", json=payload)
        except httpx.HTTPError:
            return 503, None
        if response.status_code >= 500:
            return response.status_code, None
        try:
            return response.status_code, response.json()
        except ValueError:
            return 502, None

    # ---- internals -------------------------------------------------------

    def _get_json(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        try:
            response = self._client.get(path, params=params)
        except httpx.HTTPError as exc:
            raise ApiError(str(exc) or exc.__class__.__name__) from exc
        if response.status_code == 404:
            raise ApiNotFound(path)
        if response.status_code >= 400:
            raise ApiError(f"api status {response.status_code}")
        try:
            body = response.json()
        except ValueError as exc:
            raise ApiError("api returned non-JSON content") from exc
        if not isinstance(body, dict):
            raise ApiError("api returned unexpected JSON shape")
        return body
