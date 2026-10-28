"""Versioned OpenSearch projection builder with atomic alias swap (ADR-0002).

Reads exported PostgreSQL NDJSON documents for:
  - stores   -> physical index stores_v1_<version>, aliases ['stores', 'stores_v1']
  - offers   -> physical index offers_v1_<version>, aliases ['offers', 'offers_v1']
  - products -> physical index products_v1_<version>, aliases ['products', 'products_v1']

Reindex lifecycle per index family:
1. Create fresh physical index `*_v1_<version>` using `search/mappings/*_v1.json`.
2. Bulk-index documents (`POST /{physical}/_bulk?refresh=true`) in bounded batches.
3. Verify `GET /{physical}/_count` equals the source document count.
4. Inspect `GET /_alias/{family}` to find any prior physical indexes holding the alias.
5. Atomically swap aliases (`POST /_aliases`) from prior physical indexes to the new one.
6. Delete superseded physical indexes (`DELETE /{old_physical}`).
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

MAPPINGS_DIR = Path(__file__).resolve().parent / "mappings"

INDEX_SPECS = {
    "stores": {
        "mapping_file": "stores_v1.json",
        "id_field": "store_id",
        "aliases": ["stores", "stores_v1"],
        "prefix": "stores_v1_",
    },
    "offers": {
        "mapping_file": "offers_v1.json",
        "id_field": "offer_id",
        "aliases": ["offers", "offers_v1"],
        "prefix": "offers_v1_",
    },
    "products": {
        "mapping_file": "products_v1.json",
        "id_field": "canonical_product_id",
        "aliases": ["products", "products_v1"],
        "prefix": "products_v1_",
    },
}


def _http_json(method: str, url: str, body: dict | str | bytes | None = None, content_type: str = "application/json") -> tuple[int, dict]:
    data = None
    if body is not None:
        if isinstance(body, (dict, list)):
            data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        elif isinstance(body, str):
            data = body.encode("utf-8")
        else:
            data = body
    req = urllib.request.Request(url, data=data, method=method)
    if data is not None:
        req.add_header("Content-Type", content_type)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8")
            return resp.status, (json.loads(raw) if raw else {})
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(raw) if raw else {}
        except Exception:
            parsed = {"error": raw}
        return e.code, parsed


def load_ndjson(path: Path) -> list[dict]:
    if not path.exists():
        raise FileNotFoundError(f"NDJSON file not found: {path}")
    docs = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            docs.append(json.loads(line))
    return docs


def get_existing_alias_targets(base_url: str, alias: str) -> list[str]:
    status, payload = _http_json("GET", f"{base_url.rstrip('/')}/_alias/{alias}")
    if status == 404 or not isinstance(payload, dict):
        return []
    if "error" in payload:
        return []
    return sorted(payload.keys())


def reindex_family(
    base_url: str,
    family: str,
    docs: list[dict],
    version_tag: str,
    batch_size: int = 500,
) -> dict:
    spec = INDEX_SPECS[family]
    base = base_url.rstrip("/")
    physical_index = f"{spec['prefix']}{version_tag}"
    mapping_path = MAPPINGS_DIR / spec["mapping_file"]
    mapping_body = json.loads(mapping_path.read_text(encoding="utf-8"))

    # If same physical_index already exists (e.g. re-run with same version_tag), drop it first
    _http_json("DELETE", f"{base}/{physical_index}")

    status, resp = _http_json("PUT", f"{base}/{physical_index}", mapping_body)
    if status not in (200, 201):
        raise RuntimeError(f"failed to create index {physical_index}: status={status} resp={resp}")

    # Bulk index in batches
    id_field = spec["id_field"]
    for i in range(0, len(docs), batch_size):
        chunk = docs[i : i + batch_size]
        lines = []
        for d in chunk:
            doc_id = str(d[id_field])
            lines.append(json.dumps({"index": {"_index": physical_index, "_id": doc_id}}, ensure_ascii=False))
            lines.append(json.dumps(d, ensure_ascii=False))
        ndjson_payload = "\n".join(lines) + "\n"
        b_status, b_resp = _http_json(
            "POST",
            f"{base}/{physical_index}/_bulk?refresh=true",
            ndjson_payload,
            content_type="application/x-ndjson",
        )
        if b_status not in (200, 201) or b_resp.get("errors"):
            raise RuntimeError(f"bulk indexing errors on {physical_index}: status={b_status} resp={b_resp}")

    # Verify count
    c_status, c_resp = _http_json("GET", f"{base}/{physical_index}/_count")
    if c_status != 200 or c_resp.get("count") != len(docs):
        raise RuntimeError(
            f"count mismatch on {physical_index}: expected {len(docs)}, got {c_resp}"
        )

    # Atomic alias swap
    old_targets = set()
    for alias in spec["aliases"]:
        for t in get_existing_alias_targets(base, alias):
            if t != physical_index:
                old_targets.add(t)

    actions = []
    for old_idx in sorted(old_targets):
        for alias in spec["aliases"]:
            actions.append({"remove": {"index": old_idx, "alias": alias}})
    for alias in spec["aliases"]:
        actions.append({"add": {"index": physical_index, "alias": alias}})

    a_status, a_resp = _http_json("POST", f"{base}/_aliases", {"actions": actions})
    if a_status != 200:
        raise RuntimeError(f"alias swap failed for {physical_index}: status={a_status} resp={a_resp}")

    for old_idx in sorted(old_targets):
        if old_idx.startswith(spec["prefix"]):
            _http_json("DELETE", f"{base}/{old_idx}")

    return {
        "family": family,
        "physical_index": physical_index,
        "aliases": spec["aliases"],
        "documents_indexed": len(docs),
        "replaced_indexes": sorted(old_targets),
    }


def reindex_all(
    opensearch_url: str,
    stores_path: Path,
    offers_path: Path,
    products_path: Path,
    version_tag: str | None = None,
) -> dict:
    vtag = version_tag or datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    stores_docs = load_ndjson(stores_path)
    offers_docs = load_ndjson(offers_path)
    products_docs = load_ndjson(products_path)

    res_stores = reindex_family(opensearch_url, "stores", stores_docs, vtag)
    res_offers = reindex_family(opensearch_url, "offers", offers_docs, vtag)
    res_products = reindex_family(opensearch_url, "products", products_docs, vtag)

    return {
        "status": "completed",
        "version_tag": vtag,
        "opensearch_url": opensearch_url,
        "indices": {
            "stores": res_stores,
            "offers": res_offers,
            "products": res_products,
        },
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description="Versioned OpenSearch projection reindexer (M3)")
    ap.add_argument("--opensearch-url", default="http://localhost:9200")
    ap.add_argument("--stores-ndjson", required=True)
    ap.add_argument("--offers-ndjson", required=True)
    ap.add_argument("--products-ndjson", required=True)
    ap.add_argument("--version-tag", help="explicit version suffix for physical index names")
    args = ap.parse_args(argv)

    summary = reindex_all(
        args.opensearch_url,
        Path(args.stores_ndjson),
        Path(args.offers_ndjson),
        Path(args.products_ndjson),
        version_tag=args.version_tag,
    )
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
