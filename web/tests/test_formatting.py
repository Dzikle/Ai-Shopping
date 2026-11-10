"""Macedonian formatting parity with the M12 mobile app formatters."""

from app.formatting import (
    format_date,
    format_datetime,
    format_mkd,
    format_number,
    format_price_range,
    format_quantity,
    unit_price_for_offer,
)


def test_format_mkd():
    assert format_mkd(1234.5) == "1.234,50 ден."
    assert format_mkd(75) == "75,00 ден."
    assert format_mkd("99.99") == "99,99 ден."
    assert format_mkd(12345678.9) == "12.345.678,90 ден."


def test_format_number_and_quantity():
    assert format_number(1200, decimals=0) == "1.200"
    assert format_quantity(2) == "2"
    assert format_quantity(0.5) == "0,5"
    assert format_quantity(1.25) == "1,25"
    assert format_quantity(500) == "500"


def test_dates():
    assert format_date("2026-04-17T10:00:00Z") == "17.04.2026"
    assert format_datetime("2026-04-17T10:00:00Z") == "17.04.2026 10:00"
    assert format_date(None) == "–"
    assert format_date("not-a-date") == "–"


def test_price_range():
    assert format_price_range(85, 99) == "85,00–99,00 ден."
    assert format_price_range(85, 85) == "85,00 ден."
    assert format_price_range(None, 99) == "99,00 ден."
    assert format_price_range(None, None) == "–"



def test_unit_price_basis_cannot_be_relabelled_from_gram_to_kilo():
    bread = {
        "normalizedSize": "500g",
        "priceCurrent": "32.00",
        "unitPrice": "64.00",
        "unitLabel": "1 гр",
    }
    assert unit_price_for_offer(bread) == {"text": None, "warning": True}
    bread["unitLabel"] = "1 кг"
    assert unit_price_for_offer(bread) == {
        "text": "64,00 ден./кг", "warning": False,
    }


def test_unit_price_basis_and_promo_regular_price():
    item = {
        "normalizedSize": "500g",
        "priceCurrent": "30.00",
        "regularPrice": "32.00",
        "unitPrice": "6.40",
        "unitLabel": "100 гр",
    }
    assert unit_price_for_offer(item) == {
        "text": "6,40 ден./100 г", "warning": False,
    }
    item.update(normalizedSize="1000ml", unitPrice="40", unitLabel="1л")
    assert unit_price_for_offer(item) == {
        "text": None, "warning": True,
    }
    item.update(unitPrice="30")
    assert unit_price_for_offer(item)["text"] == "30,00 ден./л"


def test_unit_price_multipack_inconsistent_unknown_and_missing():
    item = {
        "normalizedSize": "4x500ml",
        "priceCurrent": "100",
        "unitPrice": "50",
        "unitLabel": "1 л",
    }
    assert unit_price_for_offer(item)["text"] == "50,00 ден./л"
    item["normalizedSize"] = "not a verified size"
    assert unit_price_for_offer(item)["warning"] is True
    item["unitPrice"] = None
    assert unit_price_for_offer(item) == {"text": None, "warning": False}
    item.update(unitPrice="10", unitLabel="unknown", normalizedSize="500ml")
    assert unit_price_for_offer(item)["warning"] is True
