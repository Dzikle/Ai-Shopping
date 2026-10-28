"""Unit tests for deterministic product identity and review-queue matching (stdlib unittest)."""

from __future__ import annotations

import shutil
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from adapters.common import derive_sku_key
from matching import extract_signature, match_products
from matching import cli as match_cli

TMP = Path(__file__).resolve().parent / "tmp_match_out"


def setUpModule():
    shutil.rmtree(TMP, ignore_errors=True)


def tearDownModule():
    shutil.rmtree(TMP, ignore_errors=True)


class MatcherUnitTest(unittest.TestCase):
    def test_extract_signature_ignores_word_order_and_stopwords(self):
        s1 = extract_signature("СУПА ПОДРАВКА КОКОШКИНА РЕТРО КОЦКА 60Г")
        s2 = extract_signature("СУПА КОЦКА ПОДРАВКА 60гр КОКОШКИНА РЕТРО")
        self.assertIsNotNone(s1)
        self.assertIsNotNone(s2)
        self.assertEqual(s1["canonical_key"], s2["canonical_key"])
        self.assertEqual(s1["normalized_size"], "60g")

        s3 = extract_signature("ЏЕМ ПОДРАВКА ОД МЕШАНО ОВОШЈЕ 360ГР")
        s4 = extract_signature("ЏЕМ ПОДРАВКА 360гр МЕШАНО ОВОШЈЕ")
        self.assertEqual(s3["canonical_key"], s4["canonical_key"])
        self.assertEqual(s3["normalized_size"], "360g")

    def test_different_sizes_never_match(self):
        s1 = extract_signature("КРЕМ НУТЕЛА 400гр")
        s2 = extract_signature("КРЕМ НУТЕЛА 750гр")
        self.assertNotEqual(s1["canonical_key"], s2["canonical_key"])
        self.assertEqual(s1["normalized_size"], "400g")
        self.assertEqual(s2["normalized_size"], "750g")

    def test_unsized_items_return_none_no_silent_merge(self):
        self.assertIsNone(extract_signature("ЛЕБ СУСАМКА ЦВЕТ ДАЛ ФОРНО"))
        self.assertIsNone(extract_signature("ЖЕНСКИ ХЕЛАНКИ"))

    def test_stage1_exact_and_stage2_review_queue(self):
        products = [
            {
                "source_slug": "vero",
                "sku_key": derive_sku_key("ФЛИПС СТОБИ ФЛИПС 150Г ВИТАМИНКА", "ГРИЦКИ"),
                "listing_name": "ФЛИПС СТОБИ ФЛИПС 150Г ВИТАМИНКА",
                "category": "ГРИЦКИ",
            },
            {
                "source_slug": "stokomak",
                "sku_key": derive_sku_key("СТОБИ ФЛИПС 150ГР ВИТАМИНКА", "АПЕТИСАНИ"),
                "listing_name": "СТОБИ ФЛИПС 150ГР ВИТАМИНКА",
                "category": "АПЕТИСАНИ",
            },
            # Similar but extra token 'СВЕТЛО' -> must go to stage-2 pending_review, NOT stage-1 merge
            {
                "source_slug": "stokomak",
                "sku_key": derive_sku_key("ЗЛАТЕН ДАБ СВЕТЛО ПИВО 500мл. ЛИМЕНКА", "ПИВО"),
                "listing_name": "ЗЛАТЕН ДАБ СВЕТЛО ПИВО 500мл. ЛИМЕНКА",
                "category": "ПИВО",
            },
            {
                "source_slug": "zito",
                "sku_key": derive_sku_key("ПИВО ЗЛАТЕН ДАБ 500мл ЛИМЕНКА", "Пиво"),
                "listing_name": "ПИВО ЗЛАТЕН ДАБ 500мл ЛИМЕНКА",
                "category": "Пиво",
            },
        ]
        canonicals, matches = match_products(products)
        # 3 distinct canonical signatures (Stobi shared, plus the two beer variants kept distinct)
        self.assertEqual(len(canonicals), 3)

        stage1 = [m for m in matches if m["review_status"] == "auto_accepted"]
        stage2 = [m for m in matches if m["review_status"] == "pending_review"]
        self.assertEqual(len(stage1), 4)
        self.assertGreaterEqual(len(stage2), 2)

        stobi_matches = [
            m for m in stage1 if "СТОБИ" in m["evidence"]["source_listing_name"]
        ]
        self.assertEqual(len(stobi_matches), 2)
        self.assertEqual(
            stobi_matches[0]["canonical_key"], stobi_matches[1]["canonical_key"]
        )
        self.assertTrue(stobi_matches[0]["evidence"]["cross_retailer"])

        # Beer variants must NOT share canonical_key in stage 1
        beer_stage1 = [
            m for m in stage1 if "ЗЛАТЕН ДАБ" in m["evidence"]["source_listing_name"]
        ]
        self.assertEqual(len(beer_stage1), 2)
        self.assertNotEqual(
            beer_stage1[0]["canonical_key"], beer_stage1[1]["canonical_key"]
        )

        # Instead they appear in stage 2 pending_review with evidence
        self.assertEqual(stage2[0]["method"], "candidate_token_size_v1")
        self.assertIn("СВЕТЛО", stage2[0]["evidence"]["source_only_tokens"] + stage2[0]["evidence"]["target_only_tokens"])

    def test_write_match_outputs(self):
        products = [
            {
                "source_slug": "vero",
                "sku_key": derive_sku_key("СУПА МАГИ ПИЛЕШКА КОЦКА 60Г", "СУПИ"),
                "listing_name": "СУПА МАГИ ПИЛЕШКА КОЦКА 60Г",
                "category": "СУПИ",
            },
            {
                "source_slug": "zito",
                "sku_key": derive_sku_key("СУПА МАГИ КОЦКА 60гр ПИЛЕШКА", "Супи"),
                "listing_name": "СУПА МАГИ КОЦКА 60гр ПИЛЕШКА",
                "category": "Супи",
            },
        ]
        canonicals, matches = match_products(products)
        summary = match_cli.write_match_outputs(canonicals, matches, TMP / "out1")
        self.assertEqual(summary["canonical_products"], 1)
        self.assertEqual(summary["cross_retailer_canonical_products"], 1)
        self.assertEqual(summary["stage1_auto_accepted"], 2)


if __name__ == "__main__":
    unittest.main()
