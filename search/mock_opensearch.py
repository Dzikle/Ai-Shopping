"""Lightweight OpenSearch 3.x-compatible HTTP server for unit & local integration testing.

Implements the exact OpenSearch REST endpoints used by the reindexer and the
Spring Boot search client:
- GET /                         version info (3.9.0)
- GET /_cluster/health          cluster health
- PUT /{index}                  create index with mappings
- DELETE /{index}               delete index
- POST /{index}/_bulk           bulk index NDJSON documents
- GET /{index_or_alias}/_count  document count
- GET /_alias/{alias}           alias lookup
- GET /_aliases                 all aliases
- POST /_aliases                atomic alias swap (add/remove)
- POST /{index_or_alias}/_search OpenSearch Query DSL (bool/must/filter, multi_match, term, range, sort, from, size)
"""

from __future__ import annotations

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse


class OpenSearchState:
    def __init__(self):
        self.indices: dict[str, dict] = {}
        self.aliases: dict[str, set[str]] = {}

    def resolve_indices(self, target: str) -> list[str]:
        if target in self.indices:
            return [target]
        if target in self.aliases:
            return sorted(i for i in self.aliases[target] if i in self.indices)
        return []


def _match_clause(doc: dict, clause: dict) -> bool:
    if "match_all" in clause:
        return True
    if "term" in clause:
        for field, val in clause["term"].items():
            target = val.get("value") if isinstance(val, dict) else val
            f_clean = field[:-8] if field.endswith(".keyword") else field
            doc_val = doc.get(f_clean)
            if isinstance(doc_val, list):
                if target not in doc_val:
                    return False
            elif str(doc_val) != str(target) and doc_val != target:
                return False
        return True
    if "terms" in clause:
        for field, vals in clause["terms"].items():
            f_clean = field[:-8] if field.endswith(".keyword") else field
            doc_val = doc.get(f_clean)
            if isinstance(doc_val, list):
                if not any(v in doc_val for v in vals):
                    return False
            elif doc_val not in vals and str(doc_val) not in [str(v) for v in vals]:
                return False
        return True
    if "range" in clause:
        for field, conds in clause["range"].items():
            raw_val = doc.get(field)
            if raw_val is None:
                return False
            try:
                num = float(raw_val)
            except (TypeError, ValueError):
                num = raw_val
            if "gte" in conds and conds["gte"] is not None:
                if num < float(conds["gte"]):
                    return False
            if "gt" in conds and conds["gt"] is not None:
                if num <= float(conds["gt"]):
                    return False
            if "lte" in conds and conds["lte"] is not None:
                if num > float(conds["lte"]):
                    return False
            if "lt" in conds and conds["lt"] is not None:
                if num >= float(conds["lt"]):
                    return False
        return True
    if "multi_match" in clause:
        mm = clause["multi_match"]
        query = (mm.get("query") or "").strip().lower()
        if not query:
            return True
        fields = mm.get("fields") or ["listing_name", "canonical_name", "category", "name", "city"]
        tokens = [t for t in query.split() if t]
        haystack_parts = []
        for f in fields:
            f_clean = f.split("^")[0]
            if f_clean.endswith(".text") or f_clean.endswith(".keyword"):
                f_clean = f_clean.rsplit(".", 1)[0]
            val = doc.get(f_clean)
            if val is not None:
                haystack_parts.append(str(val).lower())
        haystack = " ".join(haystack_parts)
        return all(tok in haystack for tok in tokens)
    if "match" in clause:
        for field, spec in clause["match"].items():
            q = (spec.get("query") if isinstance(spec, dict) else spec) or ""
            q = str(q).strip().lower()
            f_clean = field.rsplit(".", 1)[0] if ("." in field) else field
            val = str(doc.get(f_clean) or "").lower()
            if not all(tok in val for tok in q.split()):
                return False
        return True
    if "bool" in clause:
        b = clause["bool"]
        for c in b.get("must", []):
            if not _match_clause(doc, c):
                return False
        for c in b.get("filter", []):
            if not _match_clause(doc, c):
                return False
        for c in b.get("must_not", []):
            if _match_clause(doc, c):
                return False
        shoulds = b.get("should", [])
        if shoulds and int(b.get("minimum_should_match", 1)) > 0:
            if not any(_match_clause(doc, c) for c in shoulds):
                return False
        return True
    return True


def _sort_docs(hits: list[tuple[str, str, dict]], sort_spec: list) -> list[tuple[str, str, dict]]:
    if not sort_spec:
        return hits
    result = list(hits)
    for spec in reversed(sort_spec):
        if isinstance(spec, str):
            field, order = spec, "asc"
        elif isinstance(spec, dict):
            field, val = next(iter(spec.items()))
            order = val.get("order", "asc") if isinstance(val, dict) else str(val)
        else:
            continue
        f_clean = field[:-8] if field.endswith(".keyword") else field
        reverse = order.lower() == "desc"

        def _key(item, f=f_clean):
            v = item[2].get(f)
            if v is None:
                return (1, "")
            try:
                return (0, float(v))
            except (TypeError, ValueError):
                return (0, str(v))

        result.sort(key=_key, reverse=reverse)
    return result


def make_handler(state: OpenSearchState):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            return

        def _send_json(self, status: int, payload: dict):
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _read_body(self) -> bytes:
            length = int(self.headers.get("Content-Length") or 0)
            return self.rfile.read(length) if length > 0 else b""

        def do_GET(self):
            parsed = urlparse(self.path)
            parts = [p for p in parsed.path.strip("/").split("/") if p]
            if not parts:
                return self._send_json(
                    200,
                    {
                        "name": "opensearch-node-1",
                        "cluster_name": "opensearch-cluster",
                        "version": {"distribution": "opensearch", "number": "3.9.0"},
                    },
                )
            if parts == ["_cluster", "health"]:
                return self._send_json(
                    200,
                    {
                        "cluster_name": "opensearch-cluster",
                        "status": "green",
                        "number_of_nodes": 1,
                    },
                )
            if parts == ["_aliases"]:
                out = {}
                for idx in state.indices:
                    al = {
                        a: {}
                        for a, targets in state.aliases.items()
                        if idx in targets
                    }
                    out[idx] = {"aliases": al}
                return self._send_json(200, out)
            if len(parts) == 2 and parts[0] == "_alias":
                alias = parts[1]
                targets = state.aliases.get(alias, set())
                if not targets:
                    return self._send_json(404, {"error": f"alias [{alias}] missing", "status": 404})
                out = {idx: {"aliases": {alias: {}}} for idx in sorted(targets) if idx in state.indices}
                return self._send_json(200, out)
            if len(parts) == 2 and parts[1] == "_count":
                target = parts[0]
                resolved = state.resolve_indices(target)
                if not resolved:
                    return self._send_json(404, {"error": "index_not_found_exception", "status": 404})
                total = sum(len(state.indices[i]["docs"]) for i in resolved)
                return self._send_json(200, {"count": total})
            if len(parts) == 2 and parts[1] == "_search":
                return self._handle_search(parts[0], {})
            return self._send_json(404, {"error": "not_found"})

        def do_PUT(self):
            parsed = urlparse(self.path)
            parts = [p for p in parsed.path.strip("/").split("/") if p]
            raw = self._read_body()
            body = json.loads(raw.decode("utf-8")) if raw else {}
            if len(parts) == 1:
                idx = parts[0]
                state.indices[idx] = {"meta": body, "docs": {}}
                return self._send_json(200, {"acknowledged": True, "index": idx})
            return self._send_json(400, {"error": "unsupported PUT"})

        def do_DELETE(self):
            parsed = urlparse(self.path)
            parts = [p for p in parsed.path.strip("/").split("/") if p]
            if len(parts) == 1:
                idx = parts[0]
                if idx not in state.indices:
                    return self._send_json(404, {"error": "index_not_found_exception", "status": 404})
                del state.indices[idx]
                for targets in state.aliases.values():
                    targets.discard(idx)
                return self._send_json(200, {"acknowledged": True})
            return self._send_json(404, {"error": "not_found"})

        def do_POST(self):
            parsed = urlparse(self.path)
            parts = [p for p in parsed.path.strip("/").split("/") if p]
            raw = self._read_body()
            if parts == ["_aliases"]:
                body = json.loads(raw.decode("utf-8")) if raw else {}
                for act in body.get("actions", []):
                    if "remove" in act:
                        r = act["remove"]
                        state.aliases.setdefault(r["alias"], set()).discard(r["index"])
                    if "add" in act:
                        a = act["add"]
                        if a["index"] not in state.indices:
                            return self._send_json(404, {"error": f"index {a['index']} missing"})
                        state.aliases.setdefault(a["alias"], set()).add(a["index"])
                return self._send_json(200, {"acknowledged": True})
            if len(parts) == 2 and parts[1] == "_bulk":
                idx = parts[0]
                if idx not in state.indices:
                    return self._send_json(404, {"error": "index_not_found_exception"})
                lines = [ln for ln in raw.decode("utf-8").splitlines() if ln.strip()]
                items = []
                for i in range(0, len(lines), 2):
                    meta = json.loads(lines[i])
                    doc = json.loads(lines[i + 1])
                    op = next(iter(meta.values()))
                    doc_id = str(op.get("_id", i))
                    state.indices[idx]["docs"][doc_id] = doc
                    items.append({"index": {"_index": idx, "_id": doc_id, "status": 201}})
                return self._send_json(200, {"took": 1, "errors": False, "items": items})
            if len(parts) == 2 and parts[1] == "_search":
                body = json.loads(raw.decode("utf-8")) if raw else {}
                return self._handle_search(parts[0], body)
            return self._send_json(404, {"error": "not_found"})

        def _handle_search(self, target: str, body: dict):
            resolved = state.resolve_indices(target)
            if not resolved:
                return self._send_json(404, {"error": "index_not_found_exception", "status": 404})
            query = body.get("query") or {"match_all": {}}
            matched: list[tuple[str, str, dict]] = []
            for idx in resolved:
                for doc_id, doc in state.indices[idx]["docs"].items():
                    if _match_clause(doc, query):
                        matched.append((idx, doc_id, doc))
            sort_spec = body.get("sort") or []
            matched = _sort_docs(matched, sort_spec)
            offset = int(body.get("from", 0))
            size = int(body.get("size", 20))
            sliced = matched[offset : offset + size]
            return self._send_json(
                200,
                {
                    "took": 1,
                    "timed_out": False,
                    "hits": {
                        "total": {"value": len(matched), "relation": "eq"},
                        "hits": [
                            {"_index": idx, "_id": doc_id, "_score": 1.0, "_source": doc}
                            for idx, doc_id, doc in sliced
                        ],
                    },
                },
            )

    return Handler


def start_background_server(host: str = "127.0.0.1", port: int = 0) -> tuple[ThreadingHTTPServer, str, OpenSearchState]:
    import threading

    state = OpenSearchState()
    srv = ThreadingHTTPServer((host, port), make_handler(state))
    actual_port = srv.server_address[1]
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    return srv, f"http://{host}:{actual_port}", state


def main(argv=None):
    ap = argparse.ArgumentParser(description="Mock OpenSearch 3.9.0 HTTP server")
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=9200)
    args = ap.parse_args(argv)
    state = OpenSearchState()
    srv = ThreadingHTTPServer((args.host, args.port), make_handler(state))
    print(f"Mock OpenSearch 3.9.0 listening on http://{args.host}:{args.port}", flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
