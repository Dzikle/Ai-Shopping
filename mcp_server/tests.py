"""Contract tests for the bounded, read-only MCP server (stdlib unittest only).

Run with:
    python -B mcp_server/tests.py
"""

from __future__ import annotations

import json
import subprocess
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from mcp_server import MCP_TOOLS_VERSION, contract, tools  # noqa: E402
from mcp_server.api_client import CatalogApiClient, ReadOnlyViolation, UpstreamError  # noqa: E402
from mcp_server.mock_catalog_api import start_background_server  # noqa: E402
from mcp_server.server import McpServer  # noqa: E402


def call(server: McpServer, name: str, arguments: dict | None = None, request_id: int = 1) -> dict:
    return server.handle_message(
        {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments or {}},
        }
    )


def structured(response: dict) -> dict:
    return response["result"]["structuredContent"]


class McpServerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.httpd, cls.base_url, cls.state = start_background_server()
        cls.client = CatalogApiClient(cls.base_url, timeout=5.0)
        cls.server = McpServer(cls.client)

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()

    def setUp(self):
        self.state.requests.clear()
        self.state.forced_status = None

    # -- lifecycle & protocol ----------------------------------------------
    def test_initialize_negotiates_protocol_and_declares_tools_only(self):
        response = self.server.handle_message(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "t"}},
            }
        )
        result = response["result"]
        self.assertEqual(result["protocolVersion"], "2025-06-18")
        self.assertEqual(result["capabilities"], {"tools": {"listChanged": False}})
        self.assertEqual(result["serverInfo"]["name"], "ai-shopping-mcp")
        self.assertIn("read-only", result["instructions"].lower())

    def test_initialize_falls_back_to_supported_protocol(self):
        response = self.server.handle_message(
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "1999-01-01"}}
        )
        self.assertEqual(response["result"]["protocolVersion"], contract.DEFAULT_PROTOCOL_VERSION)

    def test_ping_and_notifications(self):
        self.assertEqual(
            self.server.handle_message({"jsonrpc": "2.0", "id": 7, "method": "ping"})["result"], {}
        )
        self.assertIsNone(
            self.server.handle_message({"jsonrpc": "2.0", "method": "notifications/initialized"})
        )
        self.assertIsNone(self.server.handle_message({"jsonrpc": "2.0", "method": "notifications/cancelled"}))

    def test_unknown_method_is_method_not_found(self):
        response = self.server.handle_message({"jsonrpc": "2.0", "id": 2, "method": "resources/list"})
        self.assertEqual(response["error"]["code"], -32601)

    def test_tools_list_contract_is_read_only_and_bounded(self):
        response = self.server.handle_message({"jsonrpc": "2.0", "id": 3, "method": "tools/list"})
        listed = response["result"]["tools"]
        self.assertEqual([tool["name"] for tool in listed], list(contract.TOOL_NAMES))
        self.assertEqual(response["result"]["_meta"]["toolsVersion"], MCP_TOOLS_VERSION)
        for tool in listed:
            self.assertTrue(tool["annotations"]["readOnlyHint"])
            self.assertFalse(tool["annotations"]["destructiveHint"])
            schema = tool["inputSchema"]
            self.assertEqual(schema["type"], "object")
            self.assertFalse(schema["additionalProperties"])
            limit = schema["properties"].get("limit")
            if limit is not None:
                self.assertIn(limit["maximum"], (contract.MAX_LIMIT, contract.MAX_PRICE_OBSERVATIONS))
                self.assertLessEqual(limit["maximum"], contract.MAX_PRICE_OBSERVATIONS)

    def test_bad_frames_are_rejected_without_crashing(self):
        self.assertEqual(json.loads(self.server.handle_raw("not json"))["error"]["code"], -32700)
        self.assertEqual(json.loads(self.server.handle_raw(""))["error"]["code"], -32700)
        self.assertEqual(json.loads(self.server.handle_raw("[]"))["error"]["code"], -32600)
        huge = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "ping", "params": {"x": "y" * 300000}})
        self.assertEqual(json.loads(self.server.handle_raw(huge))["error"]["code"], -32600)

    def test_batch_frames_are_supported(self):
        batch = json.dumps(
            [
                {"jsonrpc": "2.0", "id": 1, "method": "ping"},
                {"jsonrpc": "2.0", "method": "notifications/initialized"},
                {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
            ]
        )
        parsed = json.loads(self.server.handle_raw(batch))
        self.assertEqual([item["id"] for item in parsed], [1, 2])

    def test_unknown_tool_is_invalid_params(self):
        response = call(self.server, "delete_everything")
        self.assertEqual(response["error"]["code"], -32602)
        self.assertIn("availableTools", response["error"]["data"])
        self.assertEqual(self.state.requests, [], "unknown tools must not hit the API")

    # -- search -------------------------------------------------------------
    def test_search_products_forwards_filters_and_preserves_prices(self):
        response = call(
            self.server,
            "search_products",
            {"q": "флипс", "retailer": "stokomak", "inStockOnly": True, "promoOnly": True, "limit": 1},
        )
        result = structured(response)
        self.assertFalse(response["result"]["isError"])
        request = self.state.requests[-1]
        self.assertEqual(request["path"], "/api/v1/offers/search")
        self.assertEqual(request["query"]["retailer"], ["stokomak"])
        self.assertEqual(request["query"]["inStockOnly"], ["true"])
        self.assertEqual(request["query"]["promoOnly"], ["true"])
        self.assertEqual(request["query"]["size"], ["1"])
        self.assertEqual(result["returned"], 1)
        item = result["items"][0]
        self.assertEqual(item["offerId"], "202:1")
        self.assertEqual(item["priceCurrent"], 41.5)
        self.assertEqual(item["sourceUrl"], "https://stokomak.proverkanaceni.mk/?org=1&perPage=100&page=1")
        self.assertEqual(result["provenance"]["latestPublishedTs"], "2026-10-28T19:55:00Z")

    def test_search_products_text_is_json_and_keeps_cyrillic(self):
        response = call(self.server, "search_products", {"q": "МЛЕКО"})
        text = response["result"]["content"][0]["text"]
        self.assertEqual(json.loads(text), response["result"]["structuredContent"])
        self.assertIn("МЛЕКО", text, "Macedonian Cyrillic must stay readable in tool text")

    def test_search_products_rejects_unbounded_or_invalid_arguments(self):
        cases = [
            {"limit": contract.MAX_LIMIT + 1},
            {"limit": 0},
            {"q": "x" * (contract.MAX_QUERY_CHARS + 1)},
            {"sort": "newest"},
            {"retailer": "lidl"},
            {"minPrice": 100, "maxPrice": 10},
            {"inStockOnly": "yes"},
            {"page": 2},
        ]
        for arguments in cases:
            with self.subTest(arguments=str(arguments)[:60]):
                response = call(self.server, "search_products", arguments)
                self.assertTrue(response["result"]["isError"])
                self.assertIn(
                    structured(response)["error"]["reason"],
                    ("invalid_argument", "unknown_argument"),
                )

    # -- comparison, details, history, stores, discounts ---------------------
    def test_compare_product_prices_uses_verified_identity_scope(self):
        response = call(self.server, "compare_product_prices", {"q": "СТОБИ", "minRetailers": 2})
        result = structured(response)
        self.assertEqual(self.state.requests[-1]["query"]["minRetailers"], ["2"])
        self.assertEqual(result["identityScope"], "verified_identity_only")
        self.assertEqual(result["total"], 1)
        comparison = result["items"][0]
        self.assertEqual(comparison["canonicalProductId"], 897)
        self.assertEqual(comparison["cheapestMkd"], 41.5)
        self.assertEqual(comparison["highestMkd"], 43.0)
        self.assertEqual(comparison["spreadMkd"], 1.5)
        self.assertEqual([offer["retailerSlug"] for offer in comparison["offers"]], ["stokomak", "vero"])

    def test_get_price_history_returns_immutable_observations(self):
        response = call(self.server, "get_price_history", {"canonicalProductId": 897})
        result = structured(response)
        self.assertEqual(result["observationCount"], 2)
        self.assertEqual([observation["observationId"] for observation in result["observations"]], [1, 2])
        self.assertEqual(result["observations"][1]["priceCurrent"], 41.5)
        self.assertEqual(result["provenance"]["sourceUrlCount"], 2)

    def test_get_price_history_missing_product_is_structured_error(self):
        response = call(self.server, "get_price_history", {"canonicalProductId": 999999})
        self.assertTrue(response["result"]["isError"])
        self.assertEqual(structured(response)["error"]["reason"], "product_not_found")


    def test_get_product_details_combines_history_and_verified_offers(self):
        response = call(self.server, "get_product_details", {"canonicalProductId": 897, "offerLimit": 1})
        result = structured(response)
        self.assertEqual(result["canonicalName"], "СТОБИ ФЛИПС 150ГР ВИТАМИНКА")
        self.assertEqual(result["observationCount"], 2)
        self.assertEqual(result["currentOfferCount"], 2)
        self.assertEqual(len(result["currentOffers"]), 1)
        self.assertTrue(result["offersTruncated"])
        self.assertEqual(result["currentOffers"][0]["canonicalProductId"], 897)
        self.assertEqual(result["identityScope"], "verified_identity_only")
        search_request = self.state.requests[-1]
        self.assertEqual(search_request["query"]["size"], [str(contract.MAX_LIMIT)])

    def test_get_product_details_resolves_listing_name_size_suffix(self):
        # Canonical name `МЛЕКО БИТОЛСКО 1ЛР` vs listing `МЛЕКО БИТОЛСКО 1Л`: the
        # search seed drops the size token, then only verified canonical ids are kept.
        result = structured(call(self.server, "get_product_details", {"canonicalProductId": 1116}))
        self.assertEqual(result["offerSearchSeed"], "МЛЕКО БИТОЛСКО")
        self.assertEqual(result["currentOfferCount"], 2)
        self.assertEqual(
            sorted(offer["retailerSlug"] for offer in result["currentOffers"]), ["vero", "zito"]
        )
        self.assertTrue(all(offer["canonicalProductId"] == 1116 for offer in result["currentOffers"]))
        self.assertEqual(self.state.requests[-1]["query"]["q"], ["МЛЕКО БИТОЛСКО"])

    def test_search_seed_drops_size_tokens_only(self):
        self.assertEqual(tools._search_seed("СТОБИ ФЛИПС 150ГР ВИТАМИНКА"), "СТОБИ ФЛИПС")
        self.assertEqual(tools._search_seed("МЛЕКО БИТОЛСКО 1ЛР"), "МЛЕКО БИТОЛСКО")
        self.assertEqual(tools._search_seed("1Л"), "1Л")

    def test_find_stores_filters_by_city(self):
        response = call(self.server, "find_stores", {"city": "Битола"})
        result = structured(response)
        self.assertEqual(result["total"], 1)
        self.assertEqual(result["items"][0]["storeId"], 303)
        self.assertEqual(result["items"][0]["activeOffersCount"], 1)
        self.assertEqual(result["geoScope"], "city_text_filter_only")

    def test_find_current_discounts_thresholds_and_sorts_deterministically(self):
        all_promos = structured(call(self.server, "find_current_discounts", {}))
        self.assertEqual([item["offerId"] for item in all_promos["discounts"]], ["303:1", "202:1"])
        self.assertEqual(self.state.requests[-1]["query"]["promoOnly"], ["true"])

        filtered = structured(call(self.server, "find_current_discounts", {"minDiscountPct": 20}))
        self.assertEqual([item["offerId"] for item in filtered["discounts"]], ["303:1"])
        self.assertEqual(filtered["discounts"][0]["discountPct"], 23.0)
        self.assertEqual(filtered["discounts"][0]["regularPrice"], 80.52)

    def test_suggest_product_substitutes_never_claims_equivalence(self):
        response = call(
            self.server,
            "suggest_product_substitutes",
            {"canonicalProductId": 897, "category": "ГРИЦКИ"},
        )
        result = structured(response)
        self.assertEqual(result["seed"]["query"], "СТОБИ ФЛИПС 150ГР ВИТАМИНКА")
        self.assertEqual(result["equivalenceStatus"], "not_verified_equivalent")
        self.assertEqual([item["canonicalProductId"] for item in result["candidates"]], [898])
        self.assertEqual(result["candidates"][0]["equivalenceStatus"], "not_verified_equivalent")
        self.assertEqual(result["candidates"][0]["priceCurrent"], 58.0)

    def test_suggest_substitutes_requires_a_seed(self):
        response = call(self.server, "suggest_product_substitutes", {})
        self.assertTrue(response["result"]["isError"])
        self.assertEqual(structured(response)["error"]["reason"], "missing_argument")

    def test_get_catalog_health_reports_engine_and_counts(self):
        result = structured(call(self.server, "get_catalog_health", {}))
        self.assertEqual(result["activeSearchEngine"], "opensearch")
        self.assertEqual(result["counts"]["offers_current"], 1896)
        self.assertIn("postgresql_fallback", result["note"])


    # -- basket optimization -------------------------------------------------
    def test_optimize_basket_forwards_payload_and_preserves_backend_totals(self):
        arguments = {
            "items": [
                {"canonicalProductId": 1116, "quantity": 2, "unit": "pack"},
                {"canonicalProductId": 897, "quantity": 800, "unit": "g"},
            ],
            "city": "Битола",
            "retailers": ["vero", "stokomak", "zito"],
            "maxStores": 2,
            "minSplitSavingsMkd": 15.00,
            "allowSubstitutes": False,
            "inStockOnly": True,
        }
        first = structured(call(self.server, "optimize_shopping_basket", arguments))
        second = structured(call(self.server, "optimize_shopping_basket", arguments))

        self.assertEqual(first["bestSingleStore"]["totalMkd"], 498.0)
        self.assertEqual(first["bestMultiStorePlan"]["totalMkd"], 483.5)
        self.assertEqual(first["bestMultiStorePlan"]["savingsVsBestSingleStoreMkd"], 14.5)
        self.assertEqual(first["computation"], "server_side_deterministic_bigdecimal")
        self.assertEqual(first["identityPolicy"], "exact_identity_only")
        self.assertEqual(first["bestSingleStore"]["totalMkd"], second["bestSingleStore"]["totalMkd"])
        self.assertEqual(first["bestMultiStorePlan"]["totalMkd"], second["bestMultiStorePlan"]["totalMkd"])

        request = self.state.requests[-1]
        self.assertEqual(request["method"], "POST")
        self.assertEqual(request["path"], "/api/v1/baskets/optimize")
        self.assertEqual(request["body"]["items"][1]["quantity"], 800)
        self.assertEqual(request["body"]["items"][1]["unit"], "g")
        self.assertEqual(request["body"]["maxStores"], 2)
        self.assertFalse(request["body"]["allowSubstitutes"])
        line = first["bestSingleStore"]["coveredItems"][1]
        self.assertEqual(line["packsNeeded"], 6)
        self.assertEqual(line["lineTotalMkd"], 374.0)
        self.assertFalse(line["isSubstitute"])

    def test_optimize_basket_flags_substitutes_only_when_allowed(self):
        arguments = {
            "items": [{"canonicalProductId": 897, "quantity": 1, "unit": "pack"}],
            "allowSubstitutes": True,
        }
        result = structured(call(self.server, "optimize_shopping_basket", arguments))
        self.assertEqual(result["identityPolicy"], "exact_identity_with_flagged_substitutes")
        self.assertTrue(result["allowSubstitutes"])
        self.assertTrue(self.state.requests[-1]["body"]["allowSubstitutes"])

    def test_optimize_basket_rejects_invalid_lines_without_calling_api(self):
        too_many = [{"canonicalProductId": 1}] * (contract.MAX_BASKET_ITEMS + 1)
        cases = [
            {"items": []},
            {"items": [{"canonicalProductId": 1, "retailerProductId": 2}]},
            {"items": [{"itemLabel": "no ids"}]},
            {"items": [{"canonicalProductId": 1, "quantity": 0}]},
            {"items": [{"canonicalProductId": 1, "quantity": 1, "unit": "oz"}]},
            {"items": [{"canonicalProductId": 1, "barcode": "123"}]},
            {"items": too_many},
            {"items": [{"canonicalProductId": 1}], "retailers": ["lidl"]},
            {"items": [{"canonicalProductId": 1}], "maxStores": contract.MAX_STORES_ALLOWED + 1},
            {"items": [{"canonicalProductId": 1}], "minSplitSavingsMkd": -1},
            {"items": [{"canonicalProductId": 1}], "allowSubstitutes": "no"},
        ]
        for arguments in cases:
            with self.subTest(arguments=str(arguments)[:60]):
                response = call(self.server, "optimize_shopping_basket", arguments)
                self.assertTrue(response["result"]["isError"])
                self.assertIn(
                    structured(response)["error"]["reason"],
                    ("invalid_argument", "missing_argument", "unknown_argument"),
                )
        self.assertEqual(self.state.requests, [], "invalid baskets must never reach the backend")


    # -- failure modes & read-only enforcement -------------------------------
    def test_upstream_failure_is_structured_error_and_server_survives(self):
        self.state.forced_status = 500
        response = call(self.server, "search_products", {"q": "млеко"})
        self.assertTrue(response["result"]["isError"])
        error = structured(response)["error"]
        self.assertEqual(error["reason"], "upstream_error")
        self.assertEqual(error["upstreamStatus"], 500)

        self.state.forced_status = None
        recovered = structured(call(self.server, "search_products", {"q": "млеко"}))
        self.assertGreaterEqual(recovered["total"], 1)

    def test_unreachable_api_is_reported_not_invented(self):
        offline_client = CatalogApiClient("http://127.0.0.1:1", timeout=1.0)
        offline_server = McpServer(offline_client)
        response = call(offline_server, "search_products", {"q": "млеко"})
        self.assertTrue(response["result"]["isError"])
        self.assertEqual(structured(response)["error"]["reason"], "upstream_unavailable")

    def test_api_client_allowlist_blocks_writes_and_path_escapes(self):
        with self.assertRaises(ReadOnlyViolation):
            self.client.post("/api/v1/baskets/lists", {"name": "x", "items": []})
        with self.assertRaises(ReadOnlyViolation):
            self.client.request("DELETE", "/api/v1/products/897/history")
        with self.assertRaises(ReadOnlyViolation):
            self.client.get("/api/v1/products/../../api/v1/health")
        with self.assertRaises(ReadOnlyViolation):
            self.client.get("/api/v1/offers/search?size=1")
        with self.assertRaises(ReadOnlyViolation):
            self.client.request("GET", "/api/v1/baskets/optimize")
        self.assertIn("status", self.client.get("/api/v1/health"))
        optimized = self.client.post("/api/v1/baskets/optimize", {"items": [], "maxStores": 2})
        self.assertEqual(optimized["bestSingleStore"]["totalMkd"], 498.0)

    def test_redirects_are_refused(self):
        class RedirectHandler(BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802 - stdlib hook
                self.send_response(302)
                self.send_header("Location", "http://example.invalid/api/v1/health")
                self.send_header("Content-Length", "0")
                self.end_headers()

            def log_message(self, format, *args):  # noqa: A002 - stdlib signature
                return

        httpd = ThreadingHTTPServer(("127.0.0.1", 0), RedirectHandler)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        try:
            client = CatalogApiClient(f"http://127.0.0.1:{httpd.server_address[1]}", timeout=5.0)
            with self.assertRaises(UpstreamError) as raised:
                client.get("/api/v1/health")
            self.assertEqual(raised.exception.reason, "upstream_redirect_not_allowed")
        finally:
            httpd.shutdown()
            httpd.server_close()


class McpStdioTest(unittest.TestCase):
    """End-to-end stdio transport test against the mock REST API."""

    @classmethod
    def setUpClass(cls):
        cls.httpd, cls.base_url, cls.state = start_background_server()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()

    def test_stdio_roundtrip(self):
        frames = [
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {"protocolVersion": "2025-06-18", "capabilities": {}},
            },
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {"name": "search_products", "arguments": {"q": "МЛЕКО", "limit": 2}},
            },
        ]
        process = subprocess.run(
            [
                sys.executable,
                "-B",
                str(REPO_ROOT / "mcp_server" / "cli.py"),
                "--api-base",
                self.base_url,
                "--timeout",
                "5",
            ],
            input="\n".join(json.dumps(frame, ensure_ascii=False) for frame in frames) + "\n",
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=120,
            cwd=str(REPO_ROOT),
        )
        self.assertEqual(process.returncode, 0, process.stderr)
        responses = [json.loads(line) for line in process.stdout.splitlines() if line.strip()]
        self.assertEqual([response["id"] for response in responses], [1, 2])
        self.assertEqual(responses[0]["result"]["serverInfo"]["name"], "ai-shopping-mcp")
        payload = responses[1]["result"]["structuredContent"]
        self.assertEqual(payload["returned"], 2)
        self.assertEqual(payload["items"][0]["priceCurrent"], 62.0)
        self.assertIn("stdio ready", process.stderr)

    def test_list_tools_flag_prints_contract(self):
        process = subprocess.run(
            [sys.executable, "-B", str(REPO_ROOT / "mcp_server" / "cli.py"), "--list-tools"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=120,
            cwd=str(REPO_ROOT),
        )
        self.assertEqual(process.returncode, 0, process.stderr)
        payload = json.loads(process.stdout)
        self.assertEqual(payload["server"]["name"], "ai-shopping-mcp")
        self.assertEqual([tool["name"] for tool in payload["tools"]], list(contract.TOOL_NAMES))
        self.assertEqual(len(payload["allowedRoutes"]), 6)


if __name__ == "__main__":
    unittest.main()

