"""Direct Python port of mobile/lib/utils/transliteration.dart (M12).

Macedonian Latin -> Cyrillic input normalization for search. The OpenSearch
indexes are built from Macedonian Cyrillic source names, so a user typing on a
Latin keyboard ("mleko", "jogurt") would otherwise get zero results.
Transliteration never rewrites server data — it only normalizes the query
before it is forwarded to the API.
"""

_TRIGRAPHS = {
    "dzh": "\u045f",  # dzh -> џ
}

_DIGRAPHS = {
    "d\u017e": "\u045f",  # dž -> џ
    "dj": "\u045f",  # dj -> џ
    "dz": "\u0455",  # dz -> ѕ
    "lj": "\u0459",  # lj -> љ
    "nj": "\u045a",  # nj -> њ
    "gj": "\u0453",  # gj -> ѓ
    "kj": "\u045c",  # kj -> ќ
    "ch": "\u0447",  # ch -> ч
    "sh": "\u0448",  # sh -> ш
    "zh": "\u0436",  # zh -> ж
}

_LETTERS = {
    "a": "\u0430",
    "b": "\u0431",
    "c": "\u0446",
    "\u010d": "\u0447",  # č -> ч
    "\u0107": "\u045c",  # ć -> ќ
    "d": "\u0434",
    "e": "\u0435",
    "f": "\u0444",
    "g": "\u0433",
    "h": "\u0445",
    "i": "\u0438",
    "j": "\u0458",
    "k": "\u043a",
    "l": "\u043b",
    "m": "\u043c",
    "n": "\u043d",
    "o": "\u043e",
    "p": "\u043f",
    "r": "\u0440",
    "s": "\u0441",
    "\u0161": "\u0448",  # š -> ш
    "t": "\u0442",
    "u": "\u0443",
    "v": "\u0432",
    "z": "\u0437",
    "\u017e": "\u0436",  # ž -> ж
}

_LATIN_PATTERN_EXTRA = "\u010c\u010d\u0106\u0107\u0160\u0161\u017d\u017e"


def contains_latin_letters(text: str) -> bool:
    return any(
        ("A" <= ch <= "Z") or ("a" <= ch <= "z") or ch in _LATIN_PATTERN_EXTRA
        for ch in text
    )


def transliterate_to_cyrillic(text: str) -> str:
    """Cyrillic form of a mostly-Latin query; unchanged when it already has
    Cyrillic letters or no Latin letters at all."""
    if not text:
        return text
    if any("\u0400" <= ch <= "\u04ff" for ch in text):
        return text
    if not contains_latin_letters(text):
        return text

    lower = text.lower()
    out: list[str] = []
    i = 0
    while i < len(lower):
        trigraph = lower[i:i + 3]
        if trigraph in _TRIGRAPHS:
            out.append(_TRIGRAPHS[trigraph])
            i += 3
            continue
        digraph = lower[i:i + 2]
        if digraph in _DIGRAPHS:
            out.append(_DIGRAPHS[digraph])
            i += 2
            continue
        ch = lower[i]
        out.append(_LETTERS.get(ch, ch))
        i += 1
    return "".join(out)
