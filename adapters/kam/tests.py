"""Unit tests for the KAM Market (kam.com.mk) adapter (stdlib unittest)."""

from __future__ import annotations

import json
import shutil
import unittest
from decimal import Decimal
from pathlib import Path

import cli
import kam

REPO_ROOT = Path(__file__).resolve().parents[2]
KAM_FIXTURES = REPO_ROOT / "tests" / "fixtures" / "kam"
TMP = Path(__file__).resolve().parent / "tmp_run_out"

RECORD_FIELDS = {
    "store_external_key",
    "sku_key",
    "listing_name",
    "category",
    "currency",
    "price_current",
    "unit_price",
    "unit_label",
    "regular_price",
    "discount_price",
    "discount_pct",
    "promo_type",
    "promo_starts_on",
    "promo_ends_on",
    "availability",
    "published_ts",
    "source_url",
}

SNAPSHOT_FIELDS = {
    "url",
    "url_hash",
    "content_hash",
    "storage_path",
    "content_type",
    "byte_size",
    "fetched_ts",
    "published_ts",
}


def setUpModule():
    shutil.rmtree(TMP, ignore_errors=True)


def tearDownModule():
    shutil.rmtree(TMP, ignore_errors=True)


class TimestampAndHelpersTest(unittest.TestCase):
    def test_parse_updated_am(self):
        ts = kam.parse_updated(
            "Датум и време на последно ажурирање на цените: 08.11.2026  5:48:54AM"
        )
        self.assertIsNotNone(ts)
        self.assertEqual(ts.isoformat(), "2026-11-08T05:48:54+01:00")

    def test_parse_updated_pm_and_12oclock(self):
        ts = kam.parse_updated("Датум и време на последно ажурирање на цените: 28.11.2026 12:30:00PM")
        self.assertEqual(ts.isoformat(), "2026-11-28T12:30:00+01:00")
        ts0 = kam.parse_updated("Датум и време на последно ажурирање на цените: 28.11.2026 12:30:00AM")
        self.assertEqual(ts0.isoformat(), "2026-11-28T00:30:00+01:00")

    def test_parse_updated_rejects_statutory_missing(self):
        self.assertIsNone(kam.parse_updated("08.11.2026 5:48:54AM"))
        self.assertIsNone(kam.parse_updated(None))

    def test_build_pdf_url(self):
        self.assertEqual(
            kam.build_pdf_url("https://kam.com.mk", "2026/11/08/73.pdf"),
            "https://kam.com.mk/2026/11/08/73.pdf",
        )


class StoreDirectoryTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw = (KAM_FIXTURES / "shops_2026-11-08.json").read_bytes()
        cls.stores = kam.discover_stores(cls.raw)

    def test_store_count_and_keys(self):
        self.assertEqual(len(self.stores), 86)
        keys = [s["external_key"] for s in self.stores]
        self.assertEqual(keys, sorted(keys))
        self.assertIn("73", keys)
        self.assertIn("46", keys)

    def test_store_attributes(self):
        s73 = next(s for s in self.stores if s["external_key"] == "73")
        self.assertTrue(s73["name"])
        self.assertTrue(s73["city"])
        self.assertLess(float(s73["latitude"]), 43.0)
        self.assertGreater(float(s73["latitude"]), 40.0)
        self.assertLess(float(s73["longitude"]), 24.0)
        self.assertGreater(float(s73["longitude"]), 20.0)

    def test_mini_payload(self):
        mini = json.dumps(
            [
                {
                    "Id": 5,
                    "Name": "ТЕСТ",
                    "Address": "Ул. 1",
                    "City": "Скопје",
                    "Coordinates": "41.9981, 21.4254",
                    "ShopFiles": [{"RelativePath": "2026/11/08/5.PDF"}],
                },
                {"Id": 5, "Name": "DUP"},
                {"Id": "bad", "Name": None},
            ]
        ).encode("utf-8")
        stores = kam.discover_stores(mini)
        self.assertEqual(len(stores), 1)
        s = stores[0]
        self.assertEqual(s["external_key"], "5")
        self.assertEqual(s["price_list_path"], "2026/11/08/5.pdf")
        self.assertEqual(s["latitude"], "41.9981")
        self.assertEqual(s["longitude"], "21.4254")


class ParsedStore73Test(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pdf = (KAM_FIXTURES / "2026-11-08_73.pdf").read_bytes()
        cls.url = kam.build_pdf_url(kam.BASE_URLS["kam"], "2026/11/08/73.pdf")
        cls.records, cls.info = kam.parse_pdf(cls.pdf, url=cls.url)

    def test_full_file_stats(self):
        self.assertEqual(self.info["pages_seen"], 155)
        self.assertEqual(self.info["rows_seen"], 1697)
        self.assertEqual(self.info["rows_skipped"], 0)
        self.assertEqual(self.info["rows_stored"], 1697)
        self.assertFalse(self.info["quarantined"])
        self.assertTrue(self.info["header_present"])
        self.assertEqual(self.info["published_ts"], "2026-11-08T04:48:54+00:00")

    def test_columns_identified(self):
        cm = self.info["columns"]
        self.assertEqual(
            cm,
            {
                "name": 0,
                "sale_price": 1,
                "unit_price": 2,
                "description": 3,
                "availability": 4,
                "regular_price": 5,
                "discount_price": 6,
                "promo_type": 7,
                "promo_note": 8,
            },
        )

    def test_first_record_values(self):
        r = self.records[0]
        self.assertEqual(r["listing_name"], "БОНБОНИ ЕВРОПА НОИР 100 ГР")
        self.assertEqual(r["price_current"], "24")
        self.assertEqual(r["regular_price"], "24")
        self.assertEqual(r["availability"], "in_stock")
        self.assertEqual(r["published_ts"], "2026-11-08T05:48:54+01:00")
        self.assertEqual(r["source_url"], self.url)
        self.assertEqual(r["currency"], "MKD")
        self.assertIsNone(r["category"])
        self.assertEqual(
            r["sku_key"], kam.derive_sku_key(r["listing_name"], None)
        )

    def test_record_field_set(self):
        self.assertTrue(RECORD_FIELDS.issubset(set(self.records[0].keys())))

    def test_promo_and_unit_coverage(self):
        with_promo = [r for r in self.records if r["discount_price"]]
        self.assertGreaterEqual(len(with_promo), 40)
        none_regular = [r for r in with_promo if not r["regular_price"]]
        for r in none_regular:
            self.assertGreaterEqual(Decimal(r["price_current"]), Decimal("1"))
        self.assertGreaterEqual(len(with_promo) - len(none_regular), 40)
        with_unit = [r for r in self.records if r["unit_price"]]
        self.assertGreaterEqual(len(with_unit), 1100)
        r = next(r for r in self.records if r["unit_price"] and r["unit_label"] == "100 гр")
        self.assertIsInstance(Decimal(r["unit_price"]), Decimal)

    def test_unreadable_promo_type_stored_as_null(self):
        r = next(r for r in self.records if r["listing_name"] == "МАСТИКА ГРОЗД 43% АЛК 1 Л")
        self.assertIsNone(r["promo_type"])
        self.assertEqual(r["discount_price"], "815")
        self.assertEqual(r["promo_starts_on"], "2026-11-02")
        self.assertEqual(r["promo_ends_on"], "2026-11-08")
        self.assertTrue(
            any("unreadable promo_type" in n for n in self.info["notes"])
        )
        good = next(r for r in self.records if r["promo_type"])
        self.assertNotIn("?", good["promo_type"])

    def test_max_pages_limit(self):
        recs, info = kam.parse_pdf(self.pdf, url=self.url, max_pages=2)
        self.assertEqual(info["pages_seen"], 2)
        self.assertEqual(len(recs), 22)
        self.assertFalse(info["quarantined"])


class ParsingFailureTest(unittest.TestCase):
    def test_garbage_bytes_quarantine(self):
        records, info = kam.parse_pdf(b"not a pdf at all", url="https://kam.com.mk/x.pdf")
        self.assertEqual(records, [])
        self.assertTrue(info["quarantined"])
        self.assertTrue(info["quarantine_reasons"])

    def test_empty_pdf_no_pages(self):
        records, info = kam.parse_pdf(b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\n", url="https://kam.com.mk/x.pdf")
        self.assertEqual(records, [])
        self.assertTrue(info["quarantined"])


class CliReplayTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.out_dir = TMP / "m9-kam-test"
        cls.records, cls.manifest, cls.out = cli.build_run(
            cli.discover_snapshot_files(KAM_FIXTURES),
            cls.out_dir,
            "m9-kam-test",
            store_directory={
                "file": "shops_2026-11-08.json",
                "content_hash": kam.content_hash_sha256(
                    (KAM_FIXTURES / "shops_2026-11-08.json").read_bytes()
                ),
                "stores": 86,
            },
        )

    def test_manifest_shape(self):
        self.assertEqual(self.manifest["run_key"], "m9-kam-test")
        self.assertEqual(self.manifest["source_slug"], "kam")
        self.assertEqual(self.manifest["pages_seen"], 2)
        self.assertEqual(self.manifest["rows_seen"], 3258)
        self.assertEqual(self.manifest["rows_stored"], 3258)
        self.assertFalse(self.manifest["quarantined"])
        self.assertIsNone(self.manifest["quarantine_reason"])
        self.assertEqual(self.manifest["store_directory"]["stores"], 86)
        self.assertEqual(len(self.manifest["sources"]), 2)
        rows_by_store = {s["store_external_key"]: s["rows"] for s in self.manifest["sources"]}
        self.assertEqual(rows_by_store["73"], 1697)
        self.assertEqual(rows_by_store["46"], 1561)

    def test_ndjson_outputs(self):
        snap_lines = (self.out / "snapshots.ndjson").read_text(encoding="utf-8").splitlines()
        rec_lines = (self.out / "records.ndjson").read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(rec_lines), 3258)
        self.assertEqual(len(snap_lines), 2)
        snap = json.loads(snap_lines[0])
        self.assertTrue(SNAPSHOT_FIELDS.issubset(set(snap.keys())))
        self.assertEqual(snap["content_type"], "application/pdf")
        rec = json.loads(rec_lines[0])
        self.assertEqual(rec["store_external_key"], "46")
        self.assertIn("fetched_ts", rec)
        self.assertIn("snapshot_url_hash", rec)
        for line in snap_lines:
            path = self.out / json.loads(line)["storage_path"]
            self.assertTrue(path.exists())
            self.assertEqual(path.stat().st_size, json.loads(line)["byte_size"])


if __name__ == "__main__":
    unittest.main()
