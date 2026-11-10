"""Latin -> Cyrillic input normalization for assistant search queries.

Same concept as the M12 mobile client (`mobile/lib/utils/transliteration.dart`):
OpenSearch indexes are built from Macedonian Cyrillic source names, so a user
typing "jagodа" on a Latin keyboard would otherwise search unrelated rows.
Deterministic input normalization only; server data is never transliterated.
"""

_TRIGRAPHS = {
    "dzh": "џ",
}

_DIGRAPHS = {
    "dž": "џ",
    "dj": "џ",
    "dz": "ѕ",
    "lj": "љ",
    "nj": "њ",
    "gj": "ѓ",
    "kj": "ќ",
    "ch": "ч",
    "sh": "ш",
    "zh": "ж",
}

_LETTERS = {
    "a": "а",
    "b": "б",
    "c": "ц",
    "č": "ч",
    "ć": "ќ",
    "d": "д",
    "e": "е",
    "f": "ф",
    "g": "г",
    "h": "х",
    "i": "и",
    "j": "ј",
    "k": "к",
    "l": "л",
    "m": "м",
    "n": "н",
    "o": "о",
    "p": "п",
    "r": "р",
    "s": "с",
    "š": "ш",
    "t": "т",
    "u": "у",
    "v": "в",
    "z": "з",
    "ž": "ж",
}


def has_cyrillic(text: str) -> bool:
    return any("\u0400" <= ch <= "\u04FF" for ch in text)


def has_latin(text: str) -> bool:
    return any(
        ("a" <= ch <= "z") or ("A" <= ch <= "Z") or ch in "ČčĆćŠšŽž"
        for ch in text
    )


def transliterate_to_cyrillic(text: str) -> str:
    """Cyrillic form of a Latin Macedonian query, or the input unchanged."""
    if not text or has_cyrillic(text) or not has_latin(text):
        return text
    lowered = text.lower()
    out: list[str] = []
    i = 0
    while i < len(lowered):
        three = lowered[i : i + 3]
        digraph2 = lowered[i : i + 2]
        if three in _TRIGRAPHS:
            out.append(_TRIGRAPHS[three])
            i += 3
            continue
        if digraph2 in _DIGRAPHS:
            out.append(_DIGRAPHS[digraph2])
            i += 2
            continue
        ch = lowered[i]
        out.append(_LETTERS.get(ch, ch))
        i += 1
    return "".join(out)
