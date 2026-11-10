/// Deterministic formatting for MKD money, quantities and timestamps.
///
/// Deliberately does not depend on runtime locale data: tests and screens use
/// the same output regardless of the device locale. Macedonian conventions:
/// thousands separator `.`, decimal separator `,`, suffix `ден.`.
library;

String _groupInteger(String digits) {
  final buffer = StringBuffer();
  for (var i = 0; i < digits.length; i++) {
    if (i > 0 && (digits.length - i) % 3 == 0) buffer.write('.');
    buffer.write(digits[i]);
  }
  return buffer.toString();
}

/// Formats a number with Macedonian separators (no currency suffix).
String formatNumber(num value, {int decimals = 2}) {
  final fixed = value.toStringAsFixed(decimals);
  final negative = fixed.startsWith('-');
  final unsigned = negative ? fixed.substring(1) : fixed;
  final parts = unsigned.split('.');
  final grouped = _groupInteger(parts[0]);
  final body = parts.length > 1 ? '$grouped,${parts[1]}' : grouped;
  return negative ? '-$body' : body;
}

/// Formats MKD as `1.234,50 ден.`.
String formatMkd(num value) => '${formatNumber(value, decimals: 2)} ден.';

/// Formats a quantity without trailing zeros: `2`, `0,5`, `1,25`.
String formatQuantity(num value) {
  if (value == value.roundToDouble()) return formatNumber(value, decimals: 0);
  var text = value.toStringAsFixed(3);
  while (text.endsWith('0')) {
    text = text.substring(0, text.length - 1);
  }
  if (text.endsWith('.')) text = text.substring(0, text.length - 1);
  return formatNumber(double.parse(text), decimals: text.split('.').last.length);
}

String _two(int value) => value.toString().padLeft(2, '0');

/// Local date/time as `09.11.2026 20:15`.
String formatDateTime(DateTime? value) {
  if (value == null) return '—';
  final local = value.toLocal();
  return '${_two(local.day)}.${_two(local.month)}.${local.year} '
      '${_two(local.hour)}:${_two(local.minute)}';
}

/// Local date as `09.11.2026`.
String formatDate(DateTime? value) {
  if (value == null) return '—';
  final local = value.toLocal();
  return '${_two(local.day)}.${_two(local.month)}.${local.year}';
}

/// Accepts ISO date strings (`2026-10-31`) used for promo windows.
String formatIsoDate(String? value) {
  if (value == null || value.isEmpty) return '—';
  final parsed = DateTime.tryParse(value);
  return parsed == null ? value : formatDate(parsed);
}

/// Human age such as `2 ч.`, `3 дена`, used for freshness hints.
String formatAge(DateTime? published, {DateTime? now}) {
  if (published == null) return '—';
  final delta = (now ?? DateTime.now().toUtc()).difference(published.toUtc());
  if (delta.isNegative) return '0 ч.';
  if (delta.inHours < 1) return '${delta.inMinutes} мин.';
  if (delta.inHours < 48) return '${delta.inHours} ч.';
  return '${delta.inDays} дена';
}
