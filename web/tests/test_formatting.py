"""Macedonian formatting parity with the M12 mobile app formatters."""

from app.formatting import (
    format_date,
    format_datetime,
    format_mkd,
    format_number,
    format_price_range,
    format_quantity,
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
