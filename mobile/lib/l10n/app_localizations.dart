// Adapted from KortingKlok (MIT) — localization plumbing for AI Shopping.
// Upstream: https://github.com/RashadAnsari/KortingKlok
import 'package:flutter/widgets.dart';

import 'translations.dart';

class AppLocalizations {
  const AppLocalizations(this.locale);

  final Locale locale;

  static AppLocalizations of(BuildContext context) {
    return Localizations.of<AppLocalizations>(context, AppLocalizations)!;
  }

  static const LocalizationsDelegate<AppLocalizations> delegate =
      _AppLocalizationsDelegate();

  static const List<Locale> supportedLocales = [Locale('mk'), Locale('en')];

  bool get isMacedonian => locale.languageCode == 'mk';

  String t(String key, [Map<String, String>? params]) {
    final lang = locale.languageCode;
    var value = translations[lang]?[key] ?? translations['en']?[key] ?? key;
    if (params != null) {
      params.forEach((name, replacement) {
        value = value.replaceAll('{$name}', replacement);
      });
    }
    return value;
  }

  String unit(String unit) => t('unit_$unit');

  String availability(String? raw) {
    if (raw == 'in_stock') return t('offer_availability_in_stock');
    if (raw == 'out_of_stock') return t('offer_availability_out_of_stock');
    return t('offer_availability_unknown');
  }

  String missingReason(String reason) {
    final key = 'reason_$reason';
    final translated = t(key);
    return translated == key ? reason : translated;
  }

  String recommendationReason(String reason) => missingReason(reason);

  String freshnessStatus(String status) {
    switch (status.toUpperCase()) {
      case 'UP':
      case 'OK':
      case 'HEALTHY':
        return t('home_freshness_healthy');
      case 'DEGRADED':
        return t('home_freshness_degraded');
      default:
        return t('home_freshness_down');
    }
  }
}

class _AppLocalizationsDelegate
    extends LocalizationsDelegate<AppLocalizations> {
  const _AppLocalizationsDelegate();

  @override
  bool isSupported(Locale locale) =>
      locale.languageCode == 'mk' || locale.languageCode == 'en';

  @override
  Future<AppLocalizations> load(Locale locale) async =>
      AppLocalizations(locale);

  @override
  bool shouldReload(_AppLocalizationsDelegate old) => false;
}
