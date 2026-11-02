"""Bounded, allowlisted, strictly read-only HTTP client for the M3/M4 REST API.

Security boundaries (enforced in code, not by convention):

* **Route allowlist** — only the documented read endpoints plus
  ``POST /api/v1/baskets/optimize`` (stateless, non-persisting computation) can
  ever be reached. Persisted shopping-list creation, match review writes and any
  future mutating endpoint are rejected before a socket is opened.
* **No redirects** — a 3xx response is an error, so an upstream redirect can
  never widen the allowlist.
* **Bounded** — connect/read timeout, maximum response size and maximum URL
  length are fixed. Truncated or oversized upstream bodies are rejected rather
  than partially parsed.
* **No credentials** — the client never forwards API keys or cookies; the REST
  surface is public read-only (M3 contract).
"""

from __future__ import annotations

import json
import re
import socket
import urllib.error
import urllib.parse
import urllib.request

from . import MCP_SERVER_NAME, MCP_SERVER_VERSION

DEFAULT_TIMEOUT_SECONDS = 10.0
MAX_TIMEOUT_SECONDS = 30.0
DEFAULT_MAX_RESPONSE_BYTES = 2_000_000
MAX_URL_CHARS = 1024

# (method, compiled path pattern). Keep in sync with docs/contracts/mcp-tools-contract.md.
# Internal review-queue and any persisted shopping-list routes are deliberately absent:
# the MCP surface is customer/agent facing and strictly non-mutating.
_ALLOWED_ROUTES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("GET", re.compile(r"^/api/v1/health$")),
    ("GET", re.compile(r"^/api/v1/stores$")),
    ("GET", re.compile(r"^/api/v1/offers/search$")),
    ("GET", re.compile(r"^/api/v1/products/compare$")),
    ("GET", re.compile(r"^/api/v1/products/[1-9][0-9]{0,9}/history$")),
    ("POST", re.compile(r"^/api/v1/baskets/optimize$")),
)

ALLOWED_ROUTE_DESCRIPTIONS = tuple(f"{method} {pattern.pattern}" for method, pattern in _ALLOWED_ROUTES)


class ReadOnlyViolation(Exception):
    """Raised when a caller tries to reach a route outside the read-only allowlist."""


class UpstreamError(Exception):
    """A bounded, machine-readable upstream failure (never leaks stack traces)."""

    def __init__(self, reason: str, message: str, status: int | None = None):
        super().__init__(message)
        self.reason = reason
        self.message = message
        self.status = status

    def as_dict(self) -> dict:
        payload = {"reason": self.reason, "message": self.message}
        if self.status is not None:
            payload["upstreamStatus"] = self.status
        return payload


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _render_query_value(value) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


class CatalogApiClient:
    """Thin deterministic pass-through client; performs no business arithmetic."""

    def __init__(
        self,
        base_url: str,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        max_response_bytes: int = DEFAULT_MAX_RESPONSE_BYTES,
    ):
        parsed = urllib.parse.urlparse(base_url)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise ValueError(f"base_url must be an absolute http(s) URL, got: {base_url!r}")
        if not (0 < timeout <= MAX_TIMEOUT_SECONDS):
            raise ValueError(f"timeout must be in (0, {MAX_TIMEOUT_SECONDS}]")
        if not (0 < max_response_bytes <= DEFAULT_MAX_RESPONSE_BYTES):
            raise ValueError(f"max_response_bytes must be in (0, {DEFAULT_MAX_RESPONSE_BYTES}]")
        self.base_url = base_url.rstrip("/")
        self.timeout = float(timeout)
        self.max_response_bytes = int(max_response_bytes)
        self._opener = urllib.request.build_opener(_NoRedirectHandler)

    @staticmethod
    def ensure_allowed(method: str, path: str) -> None:
        method = (method or "").upper()
        for allowed_method, pattern in _ALLOWED_ROUTES:
            if method == allowed_method and pattern.match(path or ""):
                return
        raise ReadOnlyViolation(
            f"{method} {path} is not on the read-only allowlist; "
            "the MCP layer can never write to the catalog"
        )

    def _build_url(self, path: str, query: dict | None) -> str:
        url = f"{self.base_url}{path}"
        if query:
            rendered = {k: _render_query_value(v) for k, v in query.items() if v is not None}
            if rendered:
                url = f"{url}?{urllib.parse.urlencode(rendered, quote_via=urllib.parse.quote)}"
        if len(url) > MAX_URL_CHARS:
            raise ReadOnlyViolation(f"request URL exceeds {MAX_URL_CHARS} characters")
        return url

    def get(self, path: str, query: dict | None = None) -> dict:
        return self.request("GET", path, query=query)

    def post(self, path: str, payload: dict | None = None) -> dict:
        return self.request("POST", path, payload=payload)

    def request(self, method: str, path: str, query: dict | None = None, payload: dict | None = None) -> dict:
        method = (method or "").upper()
        self.ensure_allowed(method, path)
        url = self._build_url(path, query)

        data = None
        headers = {
            "Accept": "application/json",
            "User-Agent": f"{MCP_SERVER_NAME}/{MCP_SERVER_VERSION} (read-only)",
        }
        if payload is not None:
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"

        req = urllib.request.Request(url, data=data, method=method, headers=headers)
        try:
            with self._opener.open(req, timeout=self.timeout) as response:
                status = response.status
                body = response.read(self.max_response_bytes + 1)
        except urllib.error.HTTPError as exc:
            body = b""
            try:
                body = exc.read(self.max_response_bytes + 1)
            except Exception:  # pragma: no cover - defensive
                pass
            raise self._http_error(exc.code, body) from None
        except (socket.timeout, TimeoutError):
            raise UpstreamError(
                "upstream_timeout", f"catalog API did not answer within {self.timeout:g}s"
            ) from None
        except urllib.error.URLError as exc:
            reason = getattr(exc, "reason", None)
            if isinstance(reason, (socket.timeout, TimeoutError)):
                raise UpstreamError(
                    "upstream_timeout", f"catalog API did not answer within {self.timeout:g}s"
                ) from None
            raise UpstreamError(
                "upstream_unavailable",
                "catalog API is unreachable; no price data is being invented or cached",
            ) from None
        except OSError:
            raise UpstreamError("upstream_unavailable", "catalog API connection failed") from None

        if status >= 300:
            raise self._http_error(status, body)
        if len(body) > self.max_response_bytes:
            raise UpstreamError(
                "upstream_response_too_large",
                f"catalog API response exceeded {self.max_response_bytes} bytes; narrow the query",
            )
        try:
            parsed = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise UpstreamError("upstream_invalid_json", "catalog API returned a non-JSON response") from None
        if not isinstance(parsed, dict):
            raise UpstreamError(
                "upstream_invalid_json", "catalog API returned an unexpected JSON document type"
            )
        return parsed

    @staticmethod
    def _http_error(status: int, body: bytes) -> UpstreamError:
        detail = ""
        if body:
            try:
                parsed = json.loads(body.decode("utf-8"))
                if isinstance(parsed, dict):
                    detail = str(parsed.get("message") or parsed.get("error") or "")[:300]
            except (UnicodeDecodeError, json.JSONDecodeError):
                detail = ""
        if status == 404:
            return UpstreamError("product_not_found", detail or "requested resource does not exist", status)
        if 300 <= status < 400:
            return UpstreamError("upstream_redirect_not_allowed", "catalog API attempted a redirect", status)
        if status == 400:
            return UpstreamError("upstream_rejected_request", detail or "catalog API rejected the request", status)
        if status == 429:
            return UpstreamError("upstream_rate_limited", "catalog API rate limit reached", status)
        if status >= 500:
            return UpstreamError("upstream_error", detail or "catalog API failed", status)
        return UpstreamError("upstream_error", detail or f"catalog API returned HTTP {status}", status)
