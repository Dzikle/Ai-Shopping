"""Unit tests for the OpenSearch projection reindexer and alias swap (stdlib unittest)."""

from __future__ import annotations

import json
import shutil
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from search import mock_opensearch, reindexer

TMP = Path(__file__).resolve().parent / "tmp_search_test"


def setUpModule():
    shutil.rmtree(TMP, ignore_errors=True)
    TMP.mkdir(parents=True, exist_ok=True)


def tearDownModule():
    shutil.rmtree(TMP, ignore_errors=True)


class ReindexerUnitTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv, cls.base_url, cls.state = mock_opensearch.start_background_server()
        cls.stores_file = TMP / "stores.ndjson"
        cls.offers_file = TMP / "offers.ndjson"
        cls.products_file = TMP / "products.ndjson"

        stores = [
            {
                "store_id": 1,
                "retailer_slug": "vero",
                "retailer_name": "Vero",
                "external_key": "89",
                "name": "ВЕРО 1",
                "address": "Бул. Јане Сандански бр.111",
                "city": "Аеродром",
                "active_offers_count": 2,
                "latest_published_ts": "2026-10-28T07:02:00Z",
            },
            {
                "store_id": 2,
                "retailer_slug": "stokomak",
                "retailer_name": "Stokomak",
                "external_key": "1",
                "name": "КИСЕЛА ВОДА",
                "address": None,
                "city": None,
                "active_offers_count": 1,
                "latest_published_ts": "2026-10-28T19:55:00Z",
            },
        ]
        offers = [
            {
                "offer_id": "1:10",
                "store_id": 1,
                "store_external_key": "89",
                "store_name": "ВЕРО 1",
                "city": "Аеродром",
                "retailer_id": 1,
                "retailer_slug": "vero",
                "retailer_name": "Vero",
                "retailer_product_id": 10,
                "sku_key": "sku10",
                "listing_name": "ФЛИПС СТОБИ ФЛИПС 150Г ВИТАМИНКА",
                "normalized_name": "ФЛИПС СТОБИ ФЛИПС 150Г ВИТАМИНКА",
                "category": "ГРИЦКИ",
                "canonical_product_id": 100,
                "canonical_key": "ck100",
                "canonical_name": "СТОБИ ФЛИПС 150ГР ВИТАМИНКА",
                "normalized_size": "150g",
                "currency": "MKD",
                "price_current": 43.00,
                "unit_price": None,
                "unit_label": None,
                "regular_price": 43.00,
                "discount_price": None,
                "discount_pct": None,
                "promo_type": None,
                "promo_starts_on": None,
                "promo_ends_on": None,
                "is_promo": False,
                "availability": "in_stock",
                "published_ts": "2026-10-28T07:02:00Z",
                "fetched_ts": "2026-10-28T12:00:00Z",
                "source_url": "https://pricelist.vero.com.mk/89_1.html",
                "run_id": 1,
            },
            {
                "offer_id": "2:20",
                "store_id": 2,
                "store_external_key": "1",
                "store_name": "КИСЕЛА ВОДА",
                "city": None,
                "retailer_id": 2,
                "retailer_slug": "stokomak",
                "retailer_name": "Stokomak",
                "retailer_product_id": 20,
                "sku_key": "sku20",
                "listing_name": "СТОБИ ФЛИПС 150ГР ВИТАМИНКА",
                "normalized_name": "СТОБИ ФЛИПС 150ГР ВИТАМИНКА",
                "category": "АПЕТИСАНИ",
                "canonical_product_id": 100,
                "canonical_key": "ck100",
                "canonical_name": "СТОБИ ФЛИПС 150ГР ВИТАМИНКА",
                "normalized_size": "150g",
                "currency": "MKD",
                "price_current": 43.00,
                "unit_price": None,
                "unit_label": None,
                "regular_price": 43.00,
                "discount_price": None,
                "discount_pct": None,
                "promo_type": None,
                "promo_starts_on": None,
                "promo_ends_on": None,
                "is_promo": False,
                "availability": "in_stock",
                "published_ts": "2026-10-28T19:55:00Z",
                "fetched_ts": "2026-10-28T20:30:00Z",
                "source_url": "https://stokomak.proverkanaceni.mk/?org=1&perPage=100&page=3",
                "run_id": 2,
            },
        ]
        products = [
            {
                "canonical_product_id": 100,
                "canonical_key": "ck100",
                "canonical_name": "СТОБИ ФЛИПС 150ГР ВИТАМИНКА",
                "normalized_tokens": "ВИТАМИНКА СТОБИ ФЛИПС",
                "normalized_size": "150g",
                "quantity_value": 150.0,
                "quantity_unit": "g",
                "pack_count": 1,
                "gtin": None,
                "retailer_count": 2,
                "store_count": 2,
                "retailers": ["stokomak", "vero"],
                "min_price": 43.00,
                "max_price": 43.00,
                "spread_mkd": 0.00,
                "latest_published_ts": "2026-10-28T19:55:00Z",
                "offers": [],
            }
        ]
        cls.stores_file.write_text("\n".join(json.dumps(s, ensure_ascii=False) for s in stores) + "\n", encoding="utf-8")
        cls.offers_file.write_text("\n".join(json.dumps(o, ensure_ascii=False) for o in offers) + "\n", encoding="utf-8")
        cls.products_file.write_text("\n".join(json.dumps(p, ensure_ascii=False) for p in products) + "\n", encoding="utf-8")

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()

    def test_reindex_and_atomic_alias_swap(self):
        # First reindex pass (v1_run1)
        r1 = reindexer.reindex_all(
            self.base_url,
            self.stores_file,
            self.offers_file,
            self.products_file,
            version_tag="run1",
        )
        self.assertEqual(r1["indices"]["offers"]["physical_index"], "offers_v1_run1")
        self.assertEqual(r1["indices"]["offers"]["documents_indexed"], 2)
        self.assertEqual(
            reindexer.get_existing_alias_targets(self.base_url, "offers"),
            ["offers_v1_run1"],
        )

        # Second reindex pass (v1_run2) must swap aliases and delete superseded physical index
        r2 = reindexer.reindex_all(
            self.base_url,
            self.stores_file,
            self.offers_file,
            self.products_file,
            version_tag="run2",
        )
        self.assertEqual(r2["indices"]["offers"]["physical_index"], "offers_v1_run2")
        self.assertEqual(r2["indices"]["offers"]["replaced_indexes"], ["offers_v1_run1"])
        self.assertEqual(
            reindexer.get_existing_alias_targets(self.base_url, "offers"),
            ["offers_v1_run2"],
        )
        self.assertNotIn("offers_v1_run1", self.state.indices)

    def test_search_over_alias(self):
        reindexer.reindex_all(
            self.base_url,
            self.stores_file,
            self.offers_file,
            self.products_file,
            version_tag="run3",
        )
        status, resp = reindexer._http_json(
            "POST",
            f"{self.base_url}/offers/_search",
            {
                "query": {
                    "bool": {
                        "must": [{"multi_match": {"query": "СТОБИ ФЛИПС"}}],
                        "filter": [{"term": {"retailer_slug": "stokomak"}}],
                    }
                }
            },
        )
        self.assertEqual(status, 200)
        self.assertEqual(resp["hits"]["total"]["value"], 1)
        hit = resp["hits"]["hits"][0]["_source"]
        self.assertEqual(hit["retailer_slug"], "stokomak")
        self.assertEqual(hit["price_current"], 43.0)


if __name__ == "__main__":
    unittest.main()
