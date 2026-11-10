"""Ports of the M12 transliteration test expectations (mobile parity)."""

from app.transliteration import transliterate_to_cyrillic


def test_latin_to_cyrillic():
    assert transliterate_to_cyrillic("mleko") == "млеко"
    assert transliterate_to_cyrillic("jogurt") == "јогурт"
    assert transliterate_to_cyrillic("dzhak") == "џак"
    assert transliterate_to_cyrillic("mleko i lebas") == "млеко и лебас"
    assert transliterate_to_cyrillic("sirenje") == "сирење"
    assert transliterate_to_cyrillic("caj") == "цај"


def test_cyrillic_and_non_latin_pass_through():
    assert transliterate_to_cyrillic("млеко") == "млеко"
    assert transliterate_to_cyrillic("млеко 1л") == "млеко 1л"
    assert transliterate_to_cyrillic("") == ""
    assert transliterate_to_cyrillic("123 456") == "123 456"
