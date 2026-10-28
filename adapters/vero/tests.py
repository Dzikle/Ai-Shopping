"""Unit tests for the Vero adapter (stdlib unittest, no third-party deps).

Run:  python tests.py            (from adapters/vero)
Or:   python -m unittest tests   (same directory)
Fixtures: repo-root tests/fixtures/vero (byte-exact captures 2026-10-28).
"""

import json
import shutil
import unittest
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import vero
import cli

REPO_FIXTURES = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "vero"
PAGE1_URL = f"{vero.BASE_URL}/89_1.html"
PAGE2_URL = f"{vero.BASE_URL}/89_2.html"
TMP = Path(__file__).resolve().parent / "tmp_run_out"


def setUpModule():
    shutil.rmtree(TMP, ignore_errors=True)


def tearDownModule():
    shutil.rmtree(TMP, ignore_errors=True)


def _page(path_name, url):
    raw = (REPO_FIXTURES / path_name).read_bytes()
    text = raw.decode("utf-8-sig")
    return text, raw


class VeroPage1Test(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text, cls.raw = _page("89_1.html", PAGE1_URL)
        cls.records, cls.info = vero.parse_page(cls.text, PAGE1_URL)

    def test_row_count(self):
        self.assertEqual(len(self.records), 500)
        self.assertEqual(self.info["rows_seen"], 500)
        self.assertEqual(self.info["rows_skipped"], 0)

    def test_store_key_from_url(self):
        self.assertEqual(self.info["store_external_key"], "89")

    def test_published_ts(self):
        self.assertEqual(
            self.info["published_ts"].isoformat(), "2026-10-28T08:02:00+01:00"
        )

    def test_first_record(self):
        r = self.records[0]
        self.assertEqual(r["listing_name"], "АПЕРИТИВ АПЕРОЛ 0.7Л")
        self.assertEqual(r["price_current"], "879")
        self.assertEqual(r["unit_price"], "1255")
        self.assertEqual(r["unit_label"], "ден/парче")
        self.assertEqual(r["availability"], "in_stock")
        self.assertEqual(r["category"], "АЛКОХОЛНИ ПИЈАЛОЦИ - АПЕРИТИВИ")
        self.assertEqual(r["regular_price"], "985")
        self.assertEqual(r["discount_price"], "879")
        self.assertEqual(r["discount_pct"], "10")
        self.assertEqual(r["promo_type"], "Акциска цена")
        self.assertEqual(r["promo_starts_on"], "2026-10-28")
        self.assertEqual(r["promo_ends_on"], "2026-11-10")
        self.assertEqual(r["published_ts"], "2026-10-28T08:02:00+01:00")
        self.assertEqual(r["source_url"], PAGE1_URL)

    def test_out_of_stock_row(self):
        rows = [
            r
            for r in self.records
            if r["availability"] == "out_of_stock"
        ]
        self.assertGreater(len(rows), 0)
        whisky = next(
            r for r in rows if "ЏОНИ ВОКЕР" in r["listing_name"]
        )
        self.assertEqual(whisky["listing_name"], "ВИСКИ ЏОНИ ВОКЕР ДАБЛ БЛЕК 0,7Л")
        self.assertEqual(whisky["price_current"], "2596")
        self.assertEqual(whisky["availability"], "out_of_stock")

    def test_pagination_next(self):
        self.assertEqual(self.info["next_page_url"], "89_2.html")
        self.assertIsNone(self.info["prev_page_url"])

    def test_header_flags(self):
        self.assertTrue(self.info["header_present"])
        self.assertTrue(self.info["header_discount_has_ddv"])


class VeroPage2Test(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text, cls.raw = _page("89_2.html", PAGE2_URL)
        cls.records, cls.info = vero.parse_page(cls.text, PAGE2_URL)

    def test_row_count(self):
        self.assertEqual(len(self.records), 500)

    def test_header_variant_without_ddv_suffix(self):
        self.assertTrue(self.info["header_present"])
        self.assertFalse(self.info["header_discount_has_ddv"])

    def test_pagination_prev_and_next(self):
        self.assertEqual(self.info["prev_page_url"], "89_1.html")
        self.assertEqual(self.info["next_page_url"], "89_3.html")


class VeroIndexTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        raw = (REPO_FIXTURES / "index.html").read_bytes()
        cls.stores = vero.parse_index(raw.decode("utf-8-sig"))

    def test_store_count(self):
        self.assertEqual(len(self.stores), 17)

    def test_vero_14(self):
        s = next(s for s in self.stores if s["external_key"] == "164")
        self.assertEqual(s["name"], "ВЕРО 14")
        self.assertEqual(s["address"], "Ул. ЈНА бр.106 – Куманово")
        self.assertEqual(s["city"], "Куманово")

    def test_jambo_3(self):
        s = next(s for s in self.stores if s["external_key"] == "168")
        self.assertEqual(s["name"], "ЏАМБО 3")
        self.assertEqual(s["city"], "Гевгелија")


class NormalizationTest(unittest.TestCase):
    def test_sku_key_stable(self):
        a = vero.derive_sku_key("аперитив аперол 0.7л", "алкохолни пијалоци - аперитиви")
        b = vero.derive_sku_key("  АПЕРИТИВ  АПЕРОЛ 0.7Л ", "АЛКОХОЛНИ ПИЈАЛОЦИ - АПЕРИТИВИ")
        self.assertEqual(a, b)
        self.assertEqual(len(a), 64)

    def test_sku_key_differs(self):
        a = vero.derive_sku_key("МИЛЕКО 1Л", "млеко")
        b = vero.derive_sku_key("МИЛЕКО 1Л", "млечни производи")
        self.assertNotEqual(a, b)

    def test_parse_price_variants(self):
        self.assertEqual(vero.parse_price("879"), Decimal("879"))
        self.assertEqual(vero.parse_price("1.255,50"), Decimal("1255.50"))
        self.assertEqual(vero.parse_price("879,50 ден"), Decimal("879.50"))
        self.assertIsNone(vero.parse_price(""))

    def test_parse_unit_price(self):
        v, label = vero.parse_unit_price("1255 ден/парче")
        self.assertEqual(v, Decimal("1255"))
        self.assertEqual(label, "ден/парче")
        self.assertEqual(vero.parse_unit_price(""), (None, None))

    def test_parse_date_range(self):
        s, e = vero.parse_date_range("28/10/2026 - 10/11/2026")
        self.assertEqual((s.isoformat(), e.isoformat()), ("2026-10-28", "2026-11-10"))
        self.assertEqual(vero.parse_date_range("n/a"), (None, None))

    def test_mixed_script_name_preserved(self):
        name = "ГЕЛ ЗА ТУШИРАЊЕ ОЛД СПАЈС ВАЈTВОТЕР"
        self.assertEqual(
            vero.derive_sku_key(name, "cat"),
            vero.derive_sku_key(name.lower(), "cat"),
        )


class CliBuildRunTest(unittest.TestCase):
    def test_replay_fixtures_end_to_end(self):
        sources = cli.discover_snapshot_files(REPO_FIXTURES)
        self.assertEqual(len(sources), 2)
        out = TMP / "replay"
        records, manifest, out_dir = cli.build_run(sources, out, "replay-test-1")
        self.assertEqual(len(records), 1000)
        self.assertEqual(manifest["rows_stored"], 1000)
        self.assertFalse(manifest["quarantined"])
        self.assertTrue((out_dir / "records.ndjson").exists())
        lines = (out_dir / "snapshots.ndjson").read_text(encoding="utf-8").strip().splitlines()
        self.assertEqual(len(lines), 2)
        snap = json.loads(lines[0])
        self.assertIn("url_hash", snap)
        self.assertEqual(snap["published_ts"], "2026-10-28T07:02:00+00:00")
        # byte-exact snapshot storage
        stored = (out_dir / snap["storage_path"]).read_bytes()
        self.assertEqual(len(stored), snap["byte_size"])

    def test_replay_determinism(self):
        sources = cli.discover_snapshot_files(REPO_FIXTURES)
        out1 = TMP / "det1"
        out2 = TMP / "det2"
        fixed = datetime(2026, 10, 28, 6, 0, tzinfo=timezone.utc)
        _r1, m1, _o1 = cli.build_run(sources, out1, "det-run", fetched_ts=fixed)
        _r2, m2, _o2 = cli.build_run(sources, out2, "det-run", fetched_ts=fixed)
        self.assertEqual(
            (out1 / "records.ndjson").read_bytes(), (out2 / "records.ndjson").read_bytes()
        )
        self.assertEqual(m1["pages"], m2["pages"])
        self.assertEqual(m1["rows_stored"], m2["rows_stored"])

    def test_synthetic_empty_page_quarantines_run(self):
        raw = (REPO_FIXTURES / "synthetic_empty_page.html").read_bytes()
        src = {
            "url": f"{vero.BASE_URL}/999_1.html",
            "html_text": raw.decode("utf-8-sig"),
            "raw_bytes": raw,
        }
        out = TMP / "quarantine"
        records, manifest, _ = cli.build_run([src], out, "quar-test")
        self.assertEqual(len(records), 0)
        self.assertTrue(manifest["quarantined"])
        self.assertIn("999_1.html", manifest["quarantine_reason"])


if __name__ == "__main__":
    unittest.main()
