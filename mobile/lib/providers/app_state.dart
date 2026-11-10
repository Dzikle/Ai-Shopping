import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../models/api_models.dart';
import '../services/api_client.dart';
import '../services/assistant_api.dart';

/// Local, guest-only app state: locale, theme and the on-device basket.
///
/// No account, token or personal data is stored. The basket is a local list of
/// requested products; prices and totals are always obtained from the server.
class AppState extends ChangeNotifier {
  AppState(this._prefs) {
    _restore();
  }

  static const _keyLocale = 'user_locale';
  static const _keyTheme = 'user_theme_mode';
  static const _keyBasket = 'basket_items_v1';

  final SharedPreferences _prefs;

  Locale _locale = const Locale('mk');
  ThemeMode _themeMode = ThemeMode.system;
  List<BasketItem> _basket = const [];

  Locale get locale => _locale;
  ThemeMode get themeMode => _themeMode;
  List<BasketItem> get basketItems => List.unmodifiable(_basket);
  int get basketCount => _basket.length;
  bool get basketIsEmpty => _basket.isEmpty;

  void _restore() {
    final language = _prefs.getString(_keyLocale);
    if (language != null && (language == 'en' || language == 'mk')) {
      _locale = Locale(language);
    }    final theme = _prefs.getString(_keyTheme);
    _themeMode = switch (theme) {
      'light' => ThemeMode.light,
      'dark' => ThemeMode.dark,
      _ => ThemeMode.system,
    };
    final rawBasket = _prefs.getString(_keyBasket);
    if (rawBasket != null) {
      try {
        final decoded = jsonDecode(rawBasket);
        if (decoded is List) {
          _basket = decoded
              .whereType<Map>()
              .map((item) => BasketItem.fromJson(Map<String, dynamic>.from(item)))
              .where((item) => item.localId.isNotEmpty && item.label.isNotEmpty)
              .toList(growable: false);
        }
      } catch (_) {
        _basket = const [];
      }
    }
  }

  Future<void> setLocale(Locale locale) async {
    if (_locale == locale) return;
    _locale = locale;
    notifyListeners();
    await _prefs.setString(_keyLocale, locale.languageCode);
  }

  Future<void> setThemeMode(ThemeMode mode) async {
    if (_themeMode == mode) return;
    _themeMode = mode;
    notifyListeners();
    await _prefs.setString(_keyTheme, switch (mode) {
      ThemeMode.light => 'light',
      ThemeMode.dark => 'dark',
      ThemeMode.system => 'system',
    });
  }

  Future<void> addBasketItem(BasketItem item) async {
    _basket = [..._basket, item];
    notifyListeners();
    await _persistBasket();
  }

  /// Replaces the whole local basket (used by the assistant Apply flow after
  /// user confirmation); callers must have already validated staleness.
  Future<void> replaceAllBasketItems(List<BasketItem> items) async {
    _basket = List.unmodifiable(items);
    notifyListeners();
    await _persistBasket();
  }

  Future<void> updateBasketItem(
    String localId, {
    required double quantity,
    required String unit,
  }) async {
    _basket = _basket
        .map((item) => item.localId == localId
            ? item.copyWith(quantity: quantity, unit: unit)
            : item)
        .toList(growable: false);
    notifyListeners();
    await _persistBasket();
  }

  Future<void> removeBasketItem(String localId) async {
    _basket =
        _basket.where((item) => item.localId != localId).toList(growable: false);
    notifyListeners();
    await _persistBasket();
  }

  Future<void> clearBasket() async {
    _basket = const [];
    notifyListeners();
    await _persistBasket();
  }

  Future<void> _persistBasket() async {
    await _prefs.setString(
      _keyBasket,
      jsonEncode(_basket.map((item) => item.toJson()).toList(growable: false)),
    );
  }

  /// Creates a local id without adding a UUID dependency.
  static String newLocalId() =>
      'basket-${DateTime.now().microsecondsSinceEpoch}';
}

/// Provides app state (as an [InheritedNotifier]) and the API implementations.
class AppScope extends InheritedNotifier<AppState> {
  const AppScope({
    super.key,
    required AppState state,
    required this.api,
    this.assistantApi,
    required super.child,
  }) : super(notifier: state);

  final ShoppingApi api;

  /// Guest-safe assistant transport; tests may omit it, in which case the
  /// assistant screen builds its own HTTP client.
  final AssistantApi? assistantApi;

  static AppScope of(BuildContext context) {
    final scope = context.dependOnInheritedWidgetOfExactType<AppScope>();
    assert(scope != null, 'AppScope is missing above this widget');
    return scope!;
  }

  static AppState stateOf(BuildContext context) => of(context).notifier!;

  @override
  bool updateShouldNotify(covariant AppScope oldWidget) =>
      super.updateShouldNotify(oldWidget) ||
      oldWidget.api != api ||
      oldWidget.assistantApi != assistantApi;
}
