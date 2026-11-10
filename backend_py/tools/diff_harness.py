"""M10 differential regression harness: Java jars vs FastAPI, identical data.

Runs the same ordered corpus against two backend instances backed by identical
PostgreSQL clones (shared OpenSearch), canonicalizes responses (ISO timestamps,
number scale, nested MCP tool JSON) and reports PASS/DIFF per request pair.

Stdlib only, so it also runs inside plain python containers:
    uv run python tools/diff_harness.py --java http://localhost:18088 --python http://localhost:18089
"""

import argparse
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

ISO_TS = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d{1,6})?(Z|[+-]\d{2}:\d{2})?$")


def canonic(value):
    if isinstance(value, dict):
        out = {}
        for k in sorted(value):
            if k == "ageHours" and isinstance(value[k], (int, float)):
                # ageHours = (request-time now - latest_published_ts) in hours;
                # the two sides are hit seconds apart, so only presence/unit is
                # verifiable here, not the wall-clock-derived magnitude.
                out[k] = "<age>"
            else:
                out[k] = canonic(value[k])
        return out
    if isinstance(value, list):
        return [canonic(v) for v in value]
    if isinstance(value, str):
        if ISO_TS.match(value):
            # Wall-clock values (checkedAt, error timestamps) differ per request;
            # data timestamps are identical across clones, so shape+presence is
            # what this harness verifies, not the wall-clock instant itself.
            return "<ts>"
        return value
    return value


def canon_text(body_text):
    if body_text is None or body_text == "":
        return None
    try:
        parsed = json.loads(body_text)
    except ValueError:
        return body_text
    if isinstance(parsed, dict):
        result = parsed.get("result")
        if isinstance(result, dict):
            content = result.get("content")
            if isinstance(content, list) and content and isinstance(content[0], dict):
                text = content[0].get("text")
                if isinstance(text, str):
                    try:
                        content[0]["text"] = json.loads(text)
                    except ValueError:
                        pass
    return canonic(parsed)


class Side:
    def __init__(self, name, base):
        self.name = name
        self.base = base.rstrip("/")
        self.ctx = {}

    def request(self, method, path, body=None):
        url = self.base + path
        data = json.dumps(body).encode("utf-8") if body is not None else None
        req = urllib.request.Request(url, data=data, method=method)
        if data is not None:
            req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return resp.status, resp.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read().decode("utf-8")
        except Exception as exc:  # connection errors etc.
            return None, f"__error__ {type(exc).__name__}: {exc}"


def get(side, path):
    status, body_text = side.request("GET", path)
    parsed = canon_text(body_text)
    return status, parsed


def post(side, path, body):
    status, body_text = side.request("POST", path, body)
    return status, canon_text(body_text)


def _first(obj, key):
    try:
        return obj.get(key)
    except Exception:
        return None


def _discover(side, ctx_key, path, extractor):
    status, parsed = get(side, path)
    side.ctx[ctx_key] = extractor(status, parsed)


def build_steps():
    steps = []

    def step(name, fn):
        steps.append((name, fn))

    # --- 1. catalog ---
    def s_discover_compare(side):
        status, parsed = get(side, "/api/v1/products/compare?minRetailers=2&page=0&size=10")
        items = _first(parsed, "items") or []
        if not items:
            return status, parsed
        side.ctx["canonical_id"] = items[0].get("canonicalProductId")
        return status, parsed

    step("compare_products", s_discover_compare)

    def s_search_offers(side):
        q = side.ctx.get("query", "БИМИЛК")
        status, parsed = get(side, f"/api/v1/offers/search?q={urllib.parse.quote(q)}&inStockOnly=true&size=10")
        items = _first(parsed, "items") or []
        return status, parsed

    step("offers_search_query", s_search_offers)

    def s_search_offers_promo(side):
        status, parsed = get(side, "/api/v1/offers/search?promoOnly=true&size=10&sort=price_desc")
        return status, parsed

    step("offers_search_promo", s_search_offers_promo)

    def s_stores_all(side):
        status, parsed = get(side, "/api/v1/stores")
        return status, parsed

    step("stores_all", s_stores_all)

    def s_stores_filtered(side):
        status, parsed = get(side, "/api/v1/stores?retailer=vero&city=Скопје")
        return status, parsed

    step("stores_filtered", s_stores_filtered)

    def s_health(side):
        status, parsed = get(side, "/api/v1/health")
        return status, parsed

    step("health", s_health)

    def s_history(side):
        cid = side.ctx.get("canonical_id")
        path = f"/api/v1/products/{cid}/history" if isinstance(cid, int) else "/api/v1/products/99999/history"
        return get(side, path)

    step("product_history", s_history)

    def s_history_404(side):
        return get(side, "/api/v1/products/99999/history")

    step("product_history_missing", s_history_404)

    # --- 2. operations ---
    def s_review_queue(side):
        status, parsed = get(side, "/api/v1/matches/review-queue?limit=5")
        if isinstance(parsed, list) and parsed:
            side.ctx["match_id"] = parsed[0].get("matchId")
        return status, parsed

    step("review_queue", s_review_queue)

    def s_review_approve(side):
        match_id = side.ctx.get("match_id", 999999)
        return post(side, f"/api/v1/matches/review-queue/{match_id}/approve",
                    {"reviewedBy": "diff-operator@example.com", "reviewNotes": "M10 differential approve"})

    step("review_approve", s_review_approve)

    def s_review_approve_again(side):
        match_id = side.ctx.get("match_id", 999999)
        # second call: no longer pending -> Java 500 whitelabel / Python 500 Spring shape
        return post(side, f"/api/v1/matches/review-queue/{match_id}/approve",
                    {"reviewedBy": "diff-operator@example.com", "reviewNotes": "M10 differential approve"})

    step("review_approve_repeat", s_review_approve_again)

    def s_review_reject(side):
        match_id = side.ctx.get("match_id", 999999)
        return post(side, f"/api/v1/matches/review-queue/{match_id}/reject",
                    {"reviewedBy": "diff-operator@example.com", "reviewNotes": "M10 differential reject"})

    step("review_reject", s_review_reject)

    def s_review_reject_404(side):
        return post(side, "/api/v1/matches/review-queue/999999/reject",
                    {"reviewedBy": "diff-operator@example.com", "reviewNotes": "missing"})

    step("review_reject_missing", s_review_reject_404)

    def s_freshness_default(side):
        return get(side, "/api/v1/freshness")

    step("freshness_default", s_freshness_default)

    def s_freshness_24h(side):
        return get(side, "/api/v1/freshness?staleThresholdHours=24&quarantineWindowDays=7")

    step("freshness_24h", s_freshness_24h)

    def s_metrics(side):
        return get(side, "/api/v1/metrics")

    step("metrics", s_metrics)

    # --- 3. baskets ---
    def s_optimize(side):
        cid = side.ctx.get("canonical_id", 99999)
        body = {
            "items": [
                {"canonicalProductId": cid, "quantity": 0.8, "unit": "kg"},
                {"canonicalProductId": cid, "quantity": 2, "unit": "pack"},
                {"canonicalProductId": 99999, "itemLabel": "Мистериозен продукт", "quantity": 1, "unit": "pack"},
            ],
            "maxStores": 3,
            "allowSubstitutes": True,
            "inStockOnly": True,
            "minSplitSavingsMkd": 20,
        }
        return post(side, "/api/v1/baskets/optimize", body)

    step("optimize_adhoc", s_optimize)

    def s_optimize_subset_retailers(side):
        cid = side.ctx.get("canonical_id", 99999)
        body = {
            "items": [{"canonicalProductId": cid, "itemLabel": "Производ", "quantity": 1, "unit": "pack"}],
            "retailers": ["vero", "stokomak"],
            "maxStores": 1,
        }
        return post(side, "/api/v1/baskets/optimize", body)

    step("optimize_retailer_filter", s_optimize_subset_retailers)

    def s_optimize_invalid(side):
        return post(side, "/api/v1/baskets/optimize", {"items": []})

    step("optimize_empty_items", s_optimize_invalid)

    def s_optimize_too_many(side):
        return post(side, "/api/v1/baskets/optimize", {"items": [{"canonicalProductId": 1} for _ in range(25)]})

    step("optimize_too_many_items", s_optimize_too_many)

    def s_create_list(side):
        cid = side.ctx.get("canonical_id", 99999)
        body = {
            "name": "Диф тест листа",
            "cityFilter": "Скопје",
            "items": [
                {"canonicalProductId": cid, "quantity": 1.5, "unit": "kg", "itemLabel": "Млеко"},
            ],
        }
        status, parsed = post(side, "/api/v1/baskets/lists", body)
        if isinstance(parsed, dict) and isinstance(parsed.get("id"), int):
            side.ctx["created_list_id"] = parsed["id"]
            side.ctx["item_id"] = (parsed.get("items") or [{}])[0].get("id")
        return status, parsed

    step("create_list", s_create_list)

    def s_create_list_bad_product(side):
        body = {
            "name": "Диф фк листа",
            "cityFilter": None,
            "items": [{"canonicalProductId": 99999, "quantity": 1, "unit": "pack"}],
        }
        return post(side, "/api/v1/baskets/lists", body)

    step("create_list_bad_product_fk", s_create_list_bad_product)

    def s_get_list(side):
        list_id = side.ctx.get("created_list_id")
        if list_id is None:
            return None, None
        return get(side, f"/api/v1/baskets/lists/{list_id}")

    step("get_list", s_get_list)

    def s_list_404(side):
        return get(side, "/api/v1/baskets/lists/99999")

    step("get_list_missing", s_list_404)

    def s_optimize_saved(side):
        list_id = side.ctx.get("created_list_id")
        if list_id is None:
            return None, None
        return post(side, f"/api/v1/baskets/lists/{list_id}/optimize", None)

    step("optimize_saved_list", s_optimize_saved)

    def s_optimize_saved_overrides(side):
        list_id = side.ctx.get("created_list_id")
        if list_id is None:
            return None, None
        return post(side, f"/api/v1/baskets/lists/{list_id}/optimize",
                    {"maxStores": 2, "city": "Скопје", "allowSubstitutes": True,
                     "inStockOnly": True, "minSplitSavingsMkd": 10})

    step("optimize_saved_list_overrides", s_optimize_saved_overrides)

    def s_optimize_saved_missing(side):
        return post(side, "/api/v1/baskets/lists/99999/optimize", None)

    step("optimize_saved_list_missing", s_optimize_saved_missing)

    def s_create_list_invalid(side):
        return post(side, "/api/v1/baskets/lists", {"name": "  ", "items": [{"canonicalProductId": 1}]})

    step("create_list_blank_name", s_create_list_invalid)

    # --- 4. MCP ---
    def s_mcp_info(side):
        return get(side, "/mcp")

    step("mcp_server_info", s_mcp_info)

    def s_mcp_initialize(side):
        return post(side, "/mcp", {"jsonrpc": "2.0", "id": 1, "method": "initialize",
                                   "params": {"protocolVersion": "2024-11-05", "clientInfo": {"name": "diff", "version": "1.0"}}})

    step("mcp_initialize", s_mcp_initialize)

    def s_mcp_ping(side):
        return post(side, "/mcp", {"jsonrpc": "2.0", "id": 2, "method": "ping"})

    step("mcp_ping", s_mcp_ping)

    def s_mcp_tools_list(side):
        return post(side, "/mcp", {"jsonrpc": "2.0", "id": 3, "method": "tools/list"})

    step("mcp_tools_list", s_mcp_tools_list)

    def s_mcp_initialized_no_id(side):
        return post(side, "/mcp", {"jsonrpc": "2.0", "method": "notifications/initialized"})

    step("mcp_notification_initialized", s_mcp_initialized_no_id)

    def s_mcp_call_search(side):
        q = side.ctx.get("query", "БИМИЛК")
        return post(side, "/mcp", {"jsonrpc": "2.0", "id": 10, "method": "tools/call",
                                   "params": {"name": "search_products", "arguments": {"query": q, "size": 10}}})

    step("mcp_tool_search_products", s_mcp_call_search)

    def s_mcp_call_compare(side):
        q = side.ctx.get("query", "БИМИЛК")
        return post(side, "/mcp", {"jsonrpc": "2.0", "id": 11, "method": "tools/call",
                                   "params": {"name": "compare_product_prices", "arguments": {"query": q, "minRetailers": 2}}})

    step("mcp_tool_compare_prices", s_mcp_call_compare)

    def s_mcp_call_history(side):
        cid = side.ctx.get("canonical_id", 99999)
        return post(side, "/mcp", {"jsonrpc": "2.0", "id": 12, "method": "tools/call",
                                   "params": {"name": "get_price_history", "arguments": {"canonicalProductId": cid}}})

    step("mcp_tool_price_history", s_mcp_call_history)

    def s_mcp_call_stores(side):
        return post(side, "/mcp", {"jsonrpc": "2.0", "id": 13, "method": "tools/call",
                                   "params": {"name": "list_stores", "arguments": {}}})

    step("mcp_tool_list_stores", s_mcp_call_stores)

    def s_mcp_call_discounts(side):
        return post(side, "/mcp", {"jsonrpc": "2.0", "id": 14, "method": "tools/call",
                                   "params": {"name": "find_current_discounts", "arguments": {"size": 10}}})

    step("mcp_tool_current_discounts", s_mcp_call_discounts)

    def s_mcp_call_optimize(side):
        cid = side.ctx.get("canonical_id", 99999)
        return post(side, "/mcp", {"jsonrpc": "2.0", "id": 15, "method": "tools/call",
                                   "params": {"name": "optimize_shopping_basket", "arguments": {
                                       "items": [{"canonicalProductId": cid, "quantity": 1, "unit": "pack"}],
                                       "maxStores": 2}}})

    step("mcp_tool_optimize_basket", s_mcp_call_optimize)

    def s_mcp_call_substitutes(side):
        cid = side.ctx.get("canonical_id", 99999)
        return post(side, "/mcp", {"jsonrpc": "2.0", "id": 16, "method": "tools/call",
                                   "params": {"name": "suggest_product_substitutes", "arguments": {"canonicalProductId": cid}}})

    step("mcp_tool_suggest_substitutes", s_mcp_call_substitutes)

    def s_mcp_unknown_tool(side):
        return post(side, "/mcp", {"jsonrpc": "2.0", "id": 17, "method": "tools/call",
                                   "params": {"name": "non_existent_tool"}})

    step("mcp_unknown_tool", s_mcp_unknown_tool)

    def s_mcp_missing_name(side):
        return post(side, "/mcp", {"jsonrpc": "2.0", "id": 18, "method": "tools/call", "params": {}})

    step("mcp_missing_tool_name", s_mcp_missing_name)

    def s_mcp_unknown_method(side):
        return post(side, "/mcp", {"jsonrpc": "2.0", "id": 19, "method": "zzz/unknown"})

    step("mcp_unknown_method", s_mcp_unknown_method)

    def s_mcp_missing_method(side):
        return post(side, "/mcp", {"jsonrpc": "2.0", "id": 20})

    step("mcp_missing_method", s_mcp_missing_method)

    def s_mcp_unknown_notification_idem(side):
        # id != null and method notifications/* not initialized -> -32601
        return post(side, "/mcp", {"jsonrpc": "2.0", "id": 21, "method": "notifications/other"})

    step("mcp_notification_with_id", s_mcp_unknown_notification_idem)

    # --- 5. container-level parity ---
    def s_404_route(side):
        return get(side, "/api/v1/unknown/route")

    step("http_404_spring_shape", s_404_route)

    def s_bad_query_param(side):
        return get(side, "/api/v1/offers/search?page=bogus")

    step("http_bad_query_param", s_bad_query_param)

    def s_bad_decimal(side):
        return get(side, "/api/v1/offers/search?minPrice=abc")

    step("http_bad_decimal_param", s_bad_decimal)

    return steps


def run_side(name, base, steps):
    side = Side(name, base)
    results = []
    for step_name, fn in steps:
        try:
            status, parsed = fn(side)
        except Exception as exc:
            status, parsed = None, {"__harness_exception__": f"{type(exc).__name__}: {exc}"}
        results.append((step_name, status, parsed))
    return side, results


def compare(java_results, py_results):
    failures = []
    for (jname, jstatus, jbody), (pname, pstatus, pbody) in zip(java_results, py_results):
        assert jname == pname
        if jstatus != pstatus:
            failures.append((jname, f"status {jstatus} != {pstatus}", jbody, pbody))
            continue
        if jbody != pbody:
            failures.append((jname, "body differs", jbody, pbody))
    return failures


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        pass
    parser = argparse.ArgumentParser()
    parser.add_argument("--java", required=True)
    parser.add_argument("--python", required=True)
    parser.add_argument("--query", default="БИМИЛК")
    args = parser.parse_args()

    java = Side("java", args.java)
    python = Side("python", args.python)
    java.ctx["query"] = python.ctx["query"] = args.query

    steps = build_steps()
    _, java_results = run_side("java", args.java, steps)
    _, py_results = run_side("python", args.python, steps)

    failures = compare(java_results, py_results)
    total = len(java_results)

    print("=== M10 differential corpus ===")
    for (jname, jstatus, jbody), (pname, pstatus, pbody) in zip(java_results, py_results):
        mark = "PASS" if (jstatus == pstatus and jbody == pbody) else "FAIL"
        print(f"[{mark}] {jname}: java=status={jstatus} python=status={pstatus}")

    if failures:
        print("\n=== DIFFERENCES ===")
        for name, reason, jbody, pbody in failures:
            print(f"\n--- {name}: {reason} ---")
            print(f"java:   {json.dumps(jbody, ensure_ascii=False)[:900]}")
            print(f"python: {json.dumps(pbody, ensure_ascii=False)[:900]}")

    print(f"\nTOTAL={total} PASS={total - len(failures)} FAIL={len(failures)}")
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())
