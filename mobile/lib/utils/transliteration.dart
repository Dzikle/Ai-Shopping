/// Macedonian Latin -> Cyrillic transliteration used for search input.
///
/// The OpenSearch indexes are built from Macedonian Cyrillic source names, so a
/// user typing on a Latin keyboard ("mleko", "jogurt") would otherwise get zero
/// results. Transliteration is a deterministic input normalization; it never
/// rewrites product data returned by the server.
library;

const Map<String, String> _trigraphs = <String, String>{
  'dzh': '\u045f', // dzh -> џ
};

const Map<String, String> _digraphs = <String, String>{
  'd\u017e': '\u045f', // dž -> џ
  'dj': '\u045f', // dj -> џ
  'dz': '\u0455', // dz -> ѕ
  'lj': '\u0459', // lj -> љ
  'nj': '\u045a', // nj -> њ
  'gj': '\u0453', // gj -> ѓ
  'kj': '\u045c', // kj -> ќ
  'ch': '\u0447', // ch -> ч
  'sh': '\u0448', // sh -> ш
  'zh': '\u0436', // zh -> ж
};

const Map<String, String> _letters = <String, String>{
  'a': '\u0430', // а
  'b': '\u0431', // б
  'c': '\u0446', // ц
  '\u010d': '\u0447', // č -> ч
  '\u0107': '\u045c', // ć -> ќ
  'd': '\u0434', // д
  'e': '\u0435', // е
  'f': '\u0444', // ф
  'g': '\u0433', // г
  'h': '\u0445', // х
  'i': '\u0438', // и
  'j': '\u0458', // ј
  'k': '\u043a', // к
  'l': '\u043b', // л
  'm': '\u043c', // м
  'n': '\u043d', // н
  'o': '\u043e', // о
  'p': '\u043f', // п
  'r': '\u0440', // р
  's': '\u0441', // с
  '\u0161': '\u0448', // š -> ш
  't': '\u0442', // т
  'u': '\u0443', // у
  'v': '\u0432', // в
  'z': '\u0437', // з
  '\u017e': '\u0436', // ž -> ж
};

final RegExp _latinPattern = RegExp(r'[A-Za-zČčĆćŠšŽž]');

bool containsLatinLetters(String text) => _latinPattern.hasMatch(text);

/// Returns the Cyrillic form of a mostly-Latin query, or the input unchanged
/// when it already contains Cyrillic letters or has no Latin letters.
String transliterateToCyrillic(String input) {
  if (input.isEmpty) return input;
  if (RegExp('[\u0400-\u04FF]').hasMatch(input)) return input;
  if (!containsLatinLetters(input)) return input;

  final lower = input.toLowerCase();
  final buffer = StringBuffer();
  var i = 0;
  while (i < lower.length) {
    final three = i + 2 < lower.length ? lower.substring(i, i + 3) : '';
    final trigraph = _trigraphs[three];
    if (trigraph != null) {
      buffer.write(trigraph);
      i += 3;
      continue;
    }
    final two = i + 1 < lower.length ? lower.substring(i, i + 2) : '';
    final digraph = _digraphs[two];
    if (digraph != null) {
      buffer.write(digraph);
      i += 2;
      continue;
    }
    final ch = lower[i];
    buffer.write(_letters[ch] ?? ch);
    i += 1;
  }
  return buffer.toString();
}
