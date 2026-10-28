"""Unit tests for adapters/common shared normalization (stdlib unittest)."""

from __future__ import annotations

import sys
import unittest
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from adapters.common import (
    derive_sku_key,
    normalize_name,
    parse_availability,
    parse_date_range,
    parse_declared_size,
    parse_pct,
    parse_price,
    parse_promo_cell,
    parse_unit_price,
    parse_updated,
)


class CommonNormalizerTest(unittest.TestCase):
    def test_parse_price_formats(self):
        self.assertEqual(parse_price("879"), Decimal("879"))
        self.assertEqual(parse_price("71 ден."), Decimal("71"))
        self.assertEqual(parse_price("1.255,50 ден"), Decimal("1255.50"))
        self.assertEqual(parse_price("142.00 ден."), Decimal("142.00"))
        self.assertIsNone(parse_price(""))
        self.assertIsNone(parse_price("нема"))

    def test_parse_pct_and_promo_cell(self):
        self.assertEqual(parse_pct("10 %"), Decimal("10"))
        self.assertEqual(parse_pct("249 ден.\n \n\n Попуст:31%"), Decimal("31"))
        price, pct = parse_promo_cell("299 ден.\n \n\n Попуст:23%")
        self.assertEqual(price, Decimal("299"))
        self.assertEqual(pct, Decimal("23"))

    def test_parse_unit_price_variants(self):
        self.assertEqual(
            parse_unit_price("1255 ден/парче"),
            (Decimal("1255"), "ден/парче"),
        )
        self.assertEqual(
            parse_unit_price("1кгр = 142.00 ден."),
            (Decimal("142.00"), "1кгр"),
        )
        self.assertEqual(
            parse_unit_price("100gr = 43.75 ден."),
            (Decimal("43.75"), "100gr"),
        )
        self.assertEqual(
            parse_unit_price("1пар = 55.00 ден."),
            (Decimal("55.00"), "1пар"),
        )
        self.assertEqual(parse_unit_price(""), (None, None))

    def test_parse_date_range_variants(self):
        s1, e1 = parse_date_range("28/10/2026 - 10/11/2026")
        self.assertEqual((s1.isoformat(), e1.isoformat()), ("2026-10-28", "2026-11-10"))
        s2, e2 = parse_date_range("23.10.2026 до \n29.10.2026")
        self.assertEqual((s2.isoformat(), e2.isoformat()), ("2026-10-23", "2026-10-29"))
        self.assertEqual(parse_date_range(""), (None, None))

    def test_parse_updated_variants(self):
        dt1 = parse_updated("Последно ажурирање: 28/10/2026 8:02")
        self.assertEqual(dt1.isoformat(), "2026-10-28T08:02:00+01:00")
        dt2 = parse_updated(
            "Датум и време на последно ажурирање на цените: \n 28/10/2026 20:55"
        )
        self.assertEqual(dt2.isoformat(), "2026-10-28T20:55:00+01:00")

    def test_parse_availability(self):
        self.assertEqual(parse_availability("Да"), "in_stock")
        self.assertEqual(parse_availability(" да "), "in_stock")
        self.assertEqual(parse_availability("Не"), "out_of_stock")
        self.assertEqual(parse_availability(""), "unknown")

    def test_parse_declared_size(self):
        s1 = parse_declared_size("АПЕРИТИВ АПЕРОЛ 0.7Л")
        self.assertEqual(s1["normalized_size"], "700ml")
        s2 = parse_declared_size("РАКИЈА ПЕВАЦ ЖОЛТА ДУЊА 40% 700МЛ")
        self.assertEqual(s2["normalized_size"], "700ml")
        s3 = parse_declared_size("КОРИ ЗА ПИТА И БАКЛАВА 500гр. ДОМАШНИ")
        self.assertEqual(s3["normalized_size"], "500g")
        s4 = parse_declared_size("СЕТ ПИВО ЗЛАТЕН ДАБ 4Х0,5Л")
        self.assertEqual(s4["normalized_size"], "4x500ml")
        s5 = parse_declared_size("СЕТ ПИВО ЗЛАТЕН ДАБ 4х500мл ЛИМЕНКА")
        self.assertEqual(s5["normalized_size"], "4x500ml")
        s6 = parse_declared_size("КОНЗЕРВА ТЕО КУЧЕ 1.250гр")
        self.assertEqual(s6["normalized_size"], "1250g")

    def test_normalize_and_sku_key(self):
        self.assertEqual(normalize_name("  млеко  1л "), "МЛЕКО 1Л")
        self.assertEqual(
            derive_sku_key("млеко 1л", "млечни"),
            derive_sku_key("МЛЕКО 1Л", "МЛЕЧНИ"),
        )


if __name__ == "__main__":
    unittest.main()
