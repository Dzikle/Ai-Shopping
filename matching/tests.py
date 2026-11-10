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

    def test_olympus_fat_percentages_are_not_identical(self):
        zero = extract_signature("ЈОГУРТ ГРЧКИ 0% 150 Г ОЛИМПУС")
        two = extract_signature("ЈОГУРТ ГРЧКИ 2% 150 Г ОЛИМПУС")
        equivalent = extract_signature("ОЛИМПУС ГРЧКИ ЈОГУРТ 0,0 % 150гр")
        self.assertEqual(zero["normalized_size"], "150g")
        self.assertEqual(zero["canonical_key"], equivalent["canonical_key"])
        self.assertNotEqual(zero["canonical_key"], two["canonical_key"])
        self.assertIn("PCT0", zero["tokens"])
        self.assertIn("PCT2", two["tokens"])

    def test_sugar_and_lactose_modifiers_remain_distinct(self):
        variants = (
            ("СО ШЕЌЕР", "БЕЗ ШЕЌЕР"),
            ("СО ЛАКТОЗА", "БЕЗ ЛАКТОЗА"),
            ("ТИП 1", "ТИП 2"),
        )
        for left, right in variants:
            with self.subTest(left=left, right=right):
                a = extract_signature(f"МЛЕКО ТЕСТ {left} 500МЛ")
                b = extract_signature(f"МЛЕКО ТЕСТ {right} 500МЛ")
                self.assertNotEqual(a["canonical_key"], b["canonical_key"])

    def test_cross_retailer_percent_variants_never_auto_merge(self):
        products = [
            {
                "source_slug": slug,
                "sku_key": derive_sku_key(name, "МЛЕЧНИ"),
                "listing_name": name,
            }
            for slug, name in (
                ("vero", "ЈОГУРТ ГРЧКИ 0% 150 Г ОЛИМПУС"),
                ("kam", "ЈОГУРТ ГРЧКИ 2% 150 Г ОЛИМПУС"),
                ("zito", "ОЛИМПУС ГРЧКИ ЈОГУРТ 0% 150гр"),
            )
        ]
        canonicals, matches = match_products(products)
        self.assertEqual(len(canonicals), 2)
        stage1 = [m for m in matches if m["review_status"] == "auto_accepted"]
        keys = {m["source_slug"]: m["canonical_key"] for m in stage1}
        self.assertEqual(keys["vero"], keys["zito"])
        self.assertNotEqual(keys["vero"], keys["kam"])
        self.assertEqual(len(stage1), 3)

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



class ReconciliationAuditTests(unittest.TestCase):
    @staticmethod
    def _row(name, product_id, canonical_id=2634, old_key="legacy-group",
             status="auto_accepted", reviewed_at=""):
        return {
            "source_slug": "vero" if product_id % 2 else "kam",
            "sku_key": f"sku-{product_id}",
            "retailer_product_id": str(product_id),
            "listing_name": name,
            "canonical_product_id": str(canonical_id),
            "canonical_key": old_key,
            "match_id": str(product_id + 10_000),
            "review_status": status,
            "reviewed_at": reviewed_at,
        }

    def test_yogurt_old_group_splits_and_no_db_mutation(self):
        from matching.reconciliation_audit import audit_rows

        rows = [
            self._row("ЈОГУРТ ГРЧКИ 0% 150 Г ОЛИМПУС", 983),
            self._row("ЈОГУРТ ГРЧКИ 2% 150 Г ОЛИМПУС", 984),
            self._row("ОЛИМПУС ГРЧКИ ЈОГУРТ 0,0% 150гр", 985),
        ]
        audit = audit_rows(rows)
        summary = audit["summary"]
        self.assertEqual(summary["source_rows"], 3)
        self.assertEqual(summary["split_canonical_group_ids"], [2634])
        self.assertEqual(summary["auto_key_changed"], 3)
        self.assertEqual(summary["database_mutations_performed"], 0)
        self.assertFalse(summary["safe_to_apply_automatically"])
        by_id = {r["retailer_product_id"]: r for r in audit["all_rows"]}
        self.assertEqual(by_id[983]["proposed_canonical_key"], by_id[985]["proposed_canonical_key"])
        self.assertNotEqual(by_id[983]["proposed_canonical_key"], by_id[984]["proposed_canonical_key"])
        self.assertTrue(all(r["old_group_splits"] for r in audit["review_rows"]))

    def test_manual_reviews_are_protected_even_if_signature_changes(self):
        from matching.reconciliation_audit import audit_rows

        row = self._row("ЈОГУРТ ГРЧКИ 2% 150 Г ОЛИМПУС", 984,
                        status="approved", reviewed_at="2026-11-09T12:00:00Z")
        report = audit_rows([row])
        self.assertEqual(report["all_rows"][0]["classification"], "HUMAN_REVIEW_PROTECTED")
        self.assertEqual(report["summary"]["human_review_protected"], 1)

    def test_two_old_groups_for_one_signature_require_consolidation_review(self):
        from matching.reconciliation_audit import audit_rows

        rows = [
            self._row("ЈОГУРТ ГРЧКИ 0% 150 Г ОЛИМПУС", 983, canonical_id=10),
            self._row("ОЛИМПУС ГРЧКИ ЈОГУРТ 0,0% 150гр", 985, canonical_id=11),
        ]
        report = audit_rows(rows)
        self.assertEqual(report["summary"]["consolidation_candidate_group_count"], 1)
        self.assertTrue(all(r["new_key_spans_old_groups"] for r in report["review_rows"]))

    def test_duplicate_verified_identity_or_empty_export_fails_closed(self):
        from matching.reconciliation_audit import audit_rows

        row = self._row("ЈОГУРТ ГРЧКИ 0% 150Г ОЛИМПУС", 983)
        with self.assertRaises(ValueError):
            audit_rows([])
        with self.assertRaises(ValueError):
            audit_rows([row, row])

    def test_csv_export_and_cli_generate_review_files(self):
        import csv
        import json
        import tempfile
        from matching.reconciliation_audit import COLUMNS, main

        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            source = work / "export.csv"
            with source.open("w", encoding="utf-8", newline="") as output:
                writer = csv.DictWriter(output, fieldnames=COLUMNS)
                writer.writeheader()
                writer.writerow(self._row("ЈОГУРТ ГРЧКИ 2% 150 Г ОЛИМПУС", 984))
            out = work / "results"
            self.assertEqual(main(["--input", str(source), "--out", str(out)]), 0)
            summary = json.loads((out / "summary.json").read_text(encoding="utf-8"))
            self.assertEqual(summary["auto_key_changed"], 1)
            self.assertEqual(len((out / "review_required.csv").read_text().splitlines()), 2)


if __name__ == "__main__":
    unittest.main()
