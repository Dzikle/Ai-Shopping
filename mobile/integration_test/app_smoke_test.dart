import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:ai_shopping_mobile/l10n/translations.dart';
import 'package:ai_shopping_mobile/main.dart';
import 'package:ai_shopping_mobile/widgets/compare_tile.dart';
import 'package:ai_shopping_mobile/widgets/offer_card.dart';

/// End-to-end smoke test against a live FastAPI backend.
///
/// Run with:
///   flutter test integration_test/app_smoke_test.dart -d emulator-5554 \
///     --dart-define=API_BASE_URL=http://10.0.2.2:18089
///
/// Only observable behaviour is asserted: real offers load, search works with
/// Cyrillic and Latin input, verified comparisons open, and the basket total is
/// computed and returned by the server. Nothing is fabricated client-side.
void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();

  final mk = translations['mk']!;
  String mkText(String key) => mk[key]!;
  String mkPrefix(String key) => mk[key]!.split('{').first.trim();

  setUp(() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.clear();
  });

  Future<void> settle(WidgetTester tester, {int seconds = 4}) async {
    await tester.pump();
    for (var i = 0; i < seconds * 2; i++) {
      await tester.pump(const Duration(milliseconds: 500));
    }
  }

  Future<void> boot(WidgetTester tester) async {
    await tester.pumpWidget(const AiShoppingRoot());
    await settle(tester, seconds: 10);
  }

  testWidgets('home loads live offers and freshness', (tester) async {
    await boot(tester);

    expect(find.byType(MaterialApp), findsOneWidget);
    expect(find.byType(OfferCard), findsWidgets,
        reason: 'no offers rendered from the live API');
    // Freshness summary line is one Text composed of offers/stores/stale counts.
    expect(
      find.textContaining(mkPrefix('home_freshness_stores')),
      findsWidgets,
      reason: 'freshness panel missing (backend metrics unavailable?)',
    );
    expect(find.text(mkText('error_network')), findsNothing);
    expect(tester.takeException(), isNull);
  });

  testWidgets('search finds offers in Cyrillic and Latin', (tester) async {
    await boot(tester);

    await tester.tap(find.text(mkText('nav_search')));
    await settle(tester, seconds: 2);

    final field = find.byType(TextField).first;
    await tester.enterText(field, 'млеко');
    await tester.testTextInput.receiveAction(TextInputAction.search);
    await settle(tester, seconds: 6);

    expect(find.byType(OfferCard), findsWidgets,
        reason: 'Cyrillic search "млеко" returned no offers');
    expect(tester.takeException(), isNull);

    await tester.enterText(field, 'mleko');
    await tester.testTextInput.receiveAction(TextInputAction.search);
    await settle(tester, seconds: 6);

    expect(find.byType(OfferCard), findsWidgets,
        reason: 'Latin "mleko" was not transliterated into a search hit');
    expect(tester.takeException(), isNull);
  });

  testWidgets('compare shows verified matches and opens offer detail',
      (tester) async {
    await boot(tester);

    await tester.tap(find.text(mkText('compare_title')));
    await settle(tester, seconds: 8);

    expect(find.byType(CompareTile), findsWidgets,
        reason: 'no verified comparisons rendered');
    expect(tester.takeException(), isNull);

    await tester.tap(find.byType(CompareTile).first);
    await settle(tester, seconds: 6);

    expect(find.text(mkText('compare_verified_note')), findsOneWidget);
    expect(find.text(mkText('compare_offers_title')), findsOneWidget);
    expect(find.text(mkText('compare_add_offer')), findsWidgets);
    expect(tester.takeException(), isNull);
  });

  testWidgets('basket item added from compare is optimized by the server',
      (tester) async {
    await boot(tester);

    await tester.tap(find.text(mkText('compare_title')));
    await settle(tester, seconds: 8);

    await tester.tap(find.byType(CompareTile).first);
    await settle(tester, seconds: 6);

    await tester.tap(find.text(mkText('compare_add_offer')).first);
    await settle(tester, seconds: 1);
    expect(find.text(mkText('offer_added_to_basket')), findsOneWidget);

    await tester.tap(find.byType(BackButton));
    await settle(tester, seconds: 2);

    await tester.tap(find.text(mkText('nav_basket')));
    await settle(tester, seconds: 2);

    expect(find.text(mkText('basket_empty_title')), findsNothing,
        reason: 'basket item added on the comparison screen disappeared');

    await tester.tap(find.text(mkText('basket_optimize')));
    await settle(tester, seconds: 12);

    expect(find.textContaining(mkPrefix('basket_best_single')), findsWidgets,
        reason: 'no single-store plan returned by the optimizer');
    // Totals must arrive from the server, formatted in MKD, never recomputed.
    expect(find.textContaining('ден.'), findsWidgets);
    expect(find.text(mkText('error_server')), findsNothing);
    expect(tester.takeException(), isNull);
  });
}
