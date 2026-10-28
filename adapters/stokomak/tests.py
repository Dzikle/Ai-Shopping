"""Unit tests for the Stokomak / Zito (proverkanaceni.mk) adapter (stdlib unittest)."""

from __future__ import annotations

import json
import shutil
import unittest
from datetime import datetime, timezone
from pathlib import Path

import cli
import stokomak

REPO_ROOT = Path(__file__).resolve().parents[2]
STOKOMAK_FIXTURES = REPO_ROOT / "tests" / "fixtures" / "stokomak"
ZITO_FIXTURES = REPO_ROOT / "tests" / "fixtures" / "zito"
TMP = Path(__file__).resolve().parent / "tmp_run_out"


def setUpModule():
    shutil.rmtree(TMP, ignore_errors=True)


def tearDownModule():
    shutil.rmtree(TMP, ignore_errors=True)


class StokomakIndexAndPageTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.index_html = (STOKOMAK_FIXTURES / "index.html").read_text(encoding="utf-8-sig")
        cls.stores = stokomak.parse_index(cls.index_html)
        cls.p1_url = stokomak.build_page_url(stokomak.RETAILER_URLS["stokomak"], 1, page=1)
        cls.p1_html = (STOKOMAK_FIXTURES / "1_1.html").read_text(encoding="utf-8-sig")
        cls.records, cls.info = stokomak.parse_page(cls.p1_html, cls.p1_url)

    def test_store_selector_count(self):
        self.assertEqual(len(self.stores), 81)
        s1 = next(s for s in self.stores if s["external_key"] == "1")
        self.assertEqual(s1["name"], "КИСЕЛА ВОДА")
        s14 = next(s for s in self.stores if s["external_key"] == "14")
        self.assertEqual(s14["name"], "ЦЕНТАР")

    def test_page_row_count_and_meta(self):
        self.assertEqual(len(self.records), 100)
        self.assertEqual(self.info["rows_seen"], 100)
        self.assertEqual(self.info["rows_skipped"], 0)
        self.assertEqual(self.info["promo_rows_seen"], 3)
        self.assertEqual(self.info["store_external_key"], "1")
        self.assertEqual(self.info["store_name"], "КИСЕЛА ВОДА")
        self.assertTrue(self.info["header_present"])
        self.assertFalse(self.info["empty_notice"])
        self.assertIsNotNone(self.info["published_ts"])
        self.assertEqual(self.info["current_page"], 1)
        self.assertIsNotNone(self.info["next_page_url"])

    def test_first_standard_row(self):
        r = self.records[0]
        self.assertEqual(r["listing_name"], "КОРИ ЗА ПИТА И БАКЛАВА 500гр. ДОМАШНИ")
        self.assertEqual(r["price_current"], "71")
        self.assertEqual(r["unit_price"], "142.00")
        self.assertEqual(r["unit_label"], "1кгр")
        self.assertEqual(r["category"], "СВЕЖИ КОРИ")
        self.assertEqual(r["availability"], "in_stock")
        self.assertEqual(r["regular_price"], "71")
        self.assertIsNone(r["discount_price"])
        self.assertIsNone(r["promo_type"])

    def test_promo_row_parsed(self):
        promos = [r for r in self.records if r["promo_type"] is not None]
        self.assertEqual(len(promos), 3)
        kare = next(r for r in promos if "КАРЕ СВИНСКО" in r["listing_name"])
        self.assertEqual(kare["price_current"], "299")
        self.assertEqual(kare["regular_price"], "389")
        self.assertEqual(kare["discount_price"], "299")
        self.assertEqual(kare["discount_pct"], "23")
        self.assertEqual(kare["promo_type"], "акциска цена")
        self.assertEqual(kare["promo_starts_on"], "2026-10-23")
        self.assertEqual(kare["promo_ends_on"], "2026-10-29")


class ZitoIndexAndQuarantineTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.index_html = (ZITO_FIXTURES / "index.html").read_text(encoding="utf-8-sig")
        cls.stores = stokomak.parse_index(cls.index_html)
        cls.p1_url = stokomak.build_page_url(stokomak.RETAILER_URLS["zito"], 2, page=1)
        cls.p1_html = (ZITO_FIXTURES / "2_1.html").read_text(encoding="utf-8-sig")
        cls.records, cls.info = stokomak.parse_page(cls.p1_html, cls.p1_url)

    def test_zito_sparse_store_ids_start_at_2(self):
        keys = [s["external_key"] for s in self.stores]
        self.assertNotIn("1", keys)
        self.assertEqual(keys[0], "2")
        s2 = self.stores[0]
        self.assertEqual(s2["name"], "2 Трговски - Велес")
        self.assertEqual(s2["city"], "Велес")
        self.assertGreaterEqual(len(self.stores), 90)

    def test_zito_store_2_page_1(self):
        self.assertEqual(len(self.records), 100)
        self.assertEqual(self.info["promo_rows_seen"], 9)
        self.assertEqual(self.info["store_external_key"], "2")

    def test_zito_empty_org_quarantines_run(self):
        raw = (ZITO_FIXTURES / "empty_1_1.html").read_bytes()
        url = stokomak.build_page_url(stokomak.RETAILER_URLS["zito"], 1, page=1)
        records, info = stokomak.parse_page(raw.decode("utf-8-sig"), url)
        self.assertEqual(len(records), 0)
        self.assertTrue(info["header_present"])
        self.assertTrue(info["empty_notice"])

        src = {"url": url, "html_text": raw.decode("utf-8-sig"), "raw_bytes": raw}
        out = TMP / "zito_quarantine"
        recs, manifest, _ = cli.build_run([src], out, "zito-quar-1", source_slug="zito")
        self.assertEqual(len(recs), 0)
        self.assertTrue(manifest["quarantined"])
        self.assertIn("org=1", manifest["quarantine_reason"])


class CliBuildRunTest(unittest.TestCase):
    def test_stokomak_replay_end_to_end(self):
        sources = cli.discover_snapshot_files(
            STOKOMAK_FIXTURES, stokomak.RETAILER_URLS["stokomak"]
        )
        self.assertEqual(len(sources), 4)
        out = TMP / "stokomak_replay"
        fixed = datetime(2026, 10, 28, 20, 0, tzinfo=timezone.utc)
        records, manifest, out_dir = cli.build_run(
            sources, out, "stoko-replay-1", source_slug="stokomak", fetched_ts=fixed
        )
        self.assertEqual(len(records), 400)
        self.assertEqual(manifest["rows_stored"], 400)
        self.assertEqual(manifest["source_slug"], "stokomak")
        self.assertFalse(manifest["quarantined"])
        snaps = (
            (out_dir / "snapshots.ndjson")
            .read_text(encoding="utf-8")
            .strip()
            .splitlines()
        )
        self.assertEqual(len(snaps), 4)
        first_snap = json.loads(snaps[0])
        self.assertEqual(
            len((out_dir / first_snap["storage_path"]).read_bytes()),
            first_snap["byte_size"],
        )

    def test_zito_replay_end_to_end(self):
        sources = cli.discover_snapshot_files(
            ZITO_FIXTURES, stokomak.RETAILER_URLS["zito"]
        )
        self.assertEqual(len(sources), 5)
        out = TMP / "zito_replay"
        records, manifest, _ = cli.build_run(
            sources, out, "zito-replay-1", source_slug="zito"
        )
        self.assertEqual(len(records), 500)
        self.assertEqual(manifest["source_slug"], "zito")
        self.assertFalse(manifest["quarantined"])


if __name__ == "__main__":
    unittest.main()
