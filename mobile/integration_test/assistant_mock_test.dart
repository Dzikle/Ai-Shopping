import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:ai_shopping_mobile/l10n/translations.dart';
import 'package:ai_shopping_mobile/main.dart';

/// Live-backend assistant acceptance (mock provider configured server-side):
/// ambiguity -> explicit option pick -> explicit Apply -> basket -> optimizer.
///
///   flutter test integration_test/assistant_mock_test.dart -d emulator-5554 \
///     --dart-define=API_BASE_URL=http://10.0.2.2:18089
void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();

  final mk = translations['mk']!;
  String mkText(String key) => mk[key]!;
  String mkPrefix(String key) => mk[key]!.split('{').first.trim();

  Future<void> settle(WidgetTester tester, {int seconds = 4}) async {
    await tester.pump();
    for (var i = 0; i < seconds * 2; i++) {
      await tester.pump(const Duration(milliseconds: 500));
    }
  }

  testWidgets('assistant ambiguity, explicit apply and server optimization',
      (tester) async {
    SharedPreferences.setMockInitialValues({});
    await tester.pumpWidget(const AiShoppingRoot());
    await settle(tester, seconds: 12);

    await tester.tap(find.text(mkText('nav_ai')));
    await settle(tester, seconds: 3);

    final field = find.byType(TextField).last;
    await tester.enterText(field, 'млеко');
    await tester.tap(find.byIcon(Icons.send));
    await settle(tester, seconds: 12);

    expect(find.text(mkText('assistant_demo_chip')), findsWidgets,
        reason: 'mock-provider banner missing (ASSISTANT_PROVIDER=mock)');
    expect(find.text(mkText('assistant_pick_option')), findsWidgets,
        reason: 'no clarification options for "млеко"');

    final firstOption = find.byType(InkWell).first;
    await tester.ensureVisible(firstOption);
    await tester.tap(firstOption);
    await settle(tester, seconds: 10);

    final apply = find.byKey(const Key('assistant_apply'));
    expect(apply, findsOneWidget, reason: 'explicit confirmation strip missing');
    await tester.ensureVisible(apply);
    await tester.tap(apply);
    await settle(tester, seconds: 12);
    expect(find.textContaining(mkPrefix('assistant_applied')), findsWidgets,
        reason: 'assistant did not confirm the applied basket changes');
    expect(find.text(mkText('basket_best_single')), findsWidgets,
        reason: 'applied proposal was not optimized by the server');
    expect(tester.takeException(), isNull);

    await tester.tapAt(const Offset(8, 8));
    await settle(tester, seconds: 2);
    FocusManager.instance.primaryFocus?.unfocus();
    await settle(tester, seconds: 2);
    await tester.tap(find.text(mkText('nav_basket')));
    await settle(tester, seconds: 2);
    expect(find.text(mkText('basket_empty_title')), findsNothing,
        reason: 'confirmed assistant proposal was not added to the basket');

    await tester.scrollUntilVisible(
      find.text(mkText('basket_optimize')),
      400,
      scrollable: find.byType(Scrollable).first,
    );
    await tester.tap(find.text(mkText('basket_optimize')));
    await settle(tester, seconds: 12);
    expect(find.textContaining(mkPrefix('basket_best_single')), findsWidgets,
        reason: 'optimizer returned no single-store result');
    expect(find.textContaining('ден.'), findsWidgets);
    expect(find.text(mkText('error_server')), findsNothing);
    expect(tester.takeException(), isNull);
  });
}
