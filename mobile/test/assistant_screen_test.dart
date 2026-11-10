import 'package:ai_shopping_mobile/l10n/app_localizations.dart';
import 'package:ai_shopping_mobile/models/api_models.dart';
import 'package:ai_shopping_mobile/models/assistant_models.dart';
import 'package:ai_shopping_mobile/providers/app_state.dart';
import 'package:ai_shopping_mobile/screens/assistant_screen.dart';
import 'package:ai_shopping_mobile/services/api_client.dart';
import 'package:ai_shopping_mobile/services/api_service.dart';
import 'package:ai_shopping_mobile/services/assistant_api.dart';
import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// Deterministic fake assistant transport: scripted turn responses.
class FakeAssistantApi implements AssistantApi {
  FakeAssistantApi(this.scriptedTurns, [this.failFirst = false]);

  final List<AssistantTurnResponseBuilder> scriptedTurns;
  final bool failFirst;
  int calls = 0;
  final List<Map<String, dynamic>> requests = [];

  AssistantTurnResponseBuilder builderForCall(int index) =>
      scriptedTurns[index.clamp(0, scriptedTurns.length - 1)];

  @override
  Future<AssistantTurn> sendTurn(AssistantTurnRequest request) async {
    requests.add(request.toJson());
    final builder = builderForCall(calls);
    calls += 1;
    if (failFirst && calls == 1) {
      throw ApiServiceException.network('timeout', '/api/v1/assistant/turn');
    }
    return AssistantTurn.fromJson(builder(request));
  }
}

typedef AssistantTurnResponseBuilder = Map<String, dynamic> Function(
    AssistantTurnRequest request);

/// Deterministic basket optimizer seam; asserts what the client sent.
class FakeBasketApi implements ShoppingApi {
  FakeBasketApi({this.optimization});

  BasketOptimization? optimization;
  List<BasketOptimizeRequest> optimizeCalls = [];

  @override
  Future<ApiResult<SearchPage<CanonicalComparison>>> compareProducts({
    String? query,
    int page = 0,
    int size = 20,
  }) {
    throw UnimplementedError();
  }

  @override
  Future<ApiResult<FreshnessReport>> fetchFreshness() {
    throw UnimplementedError();
  }

  @override
  Future<ApiResult<ProductHistory>> fetchHistory(int canonicalProductId) {
    throw UnimplementedError();
  }

  @override
  Future<ApiResult<List<Store>>> fetchStores({String? retailer, String? city}) {
    throw UnimplementedError();
  }

  @override
  Future<BasketOptimization> optimizeBasket(BasketOptimizeRequest request) async {
    optimizeCalls.add(request);
    return optimization ??
        BasketOptimization.fromJson({
          'totalItemsRequested': 1,
          'allowSubstitutes': false,
          'inStockOnly': true,
          'maxStoresAllowed': 2,
          'minSplitSavingsMkd': 0,
          'bestSingleStore': {
            'storeId': 1,
            'retailerSlug': 'vero',
            'retailerName': 'Vero',
            'storeName': 'Веро Тафталиџе',
            'itemsCovered': 1,
            'totalItemsRequested': 1,
            'coverageRatio': 1,
            'totalMkd': 75,
            'savingsVsHighestCoveredSingleStoreMkd': 0,
            'exactMatchesCount': 1,
            'substitutesCount': 0,
            'coveredItems': [
              {
                'itemIndex': 0,
                'canonicalProductId': 10,
                'requestedName': 'млеко',
                'requestedQuantity': 1,
                'requestedUnit': 'pack',
                'storeId': 1,
                'storeName': 'Веро Тафталиџе',
                'retailerSlug': 'vero',
                'matchedRetailerProductId': 101,
                'matchedListingName': 'МЛЕКО БИМИЛК 3.2% 1Л',
                'packsNeeded': 1,
                'unitPackPriceMkd': 75,
                'lineTotalMkd': 75,
                'isSubstitute': false,
                'publishedTs': '2026-10-28T08:00:00Z',
              }
            ],
            'missingItems': [],
          },
          'singleStoreRankings': [],
          'bestMultiStorePlan': null,
        });
  }

  @override
  Future<ApiResult<SearchPage<Offer>>> searchOffers({
    String? query,
    String? retailer,
    bool inStockOnly = false,
    bool promoOnly = false,
    String sort = 'price_asc',
    int page = 0,
    int size = 20,
  }) {
    throw UnimplementedError();
  }
}

Map<String, dynamic> milkProposalTurn(AssistantTurnRequest request) => {
      'requestId': 'asst-1',
      'status': 'ok',
      'assistantMessage': 'Пронајдов млеко.',
      'provider': {'id': 'mock', 'isMock': true, 'configured': true},
      'warnings': ['mock_provider_demo_only'],
      'proposedBasketChanges': [
        {
          'changeType': 'add',
          'itemLabel': 'млеко',
          'canonicalProductId': 10,
          'retailerProductId': 101,
          'listingName': 'МЛЕКО БИМИЛК 3.2% 1Л',
          'retailerSlug': 'vero',
          'quantity': 1,
          'unit': 'pack',
          'verifiedIdentity': true,
          'priceCurrentMkd': 75.0,
        },
      ],
    };

Map<String, dynamic> ambiguousTurn(AssistantTurnRequest request) => {
      'requestId': 'asst-2',
      'status': 'needs_clarification',
      'assistantMessage': 'Иберете.',
      'provider': {'id': 'mock', 'isMock': true, 'configured': true},
      'candidateChoices': [
        {
          'itemLabel': 'каша',
          'query': 'каша',
          'reason': 'multiple_products',
          'options': [
            {
              'candidateId': 'c:20:201',
              'retailerSlug': 'vero',
              'listingName': 'КАША ЗРНА 500Г',
              'priceCurrentMkd': 60.0,
            },
          ],
        },
      ],
    };

Map<String, dynamic> modelUnavailableTurn(AssistantTurnRequest request) => {
      'requestId': 'asst-3',
      'status': 'model_unavailable',
      'assistantMessage': 'Модел недостапен.',
      'provider': {'id': 'none', 'isMock': false, 'configured': false},
    };

Future<void> pumpAssistant(
  WidgetTester tester, {
  required AssistantApi assistantApi,
  required ShoppingApi shoppingApi,
  List<BasketItem> initialBasket = const [],
}) async {
  SharedPreferences.setMockInitialValues({});
  final prefs = await SharedPreferences.getInstance();
  final state = AppState(prefs);
  for (final item in initialBasket) {
    await state.addBasketItem(item);
  }

  await tester.pumpWidget(
    AppScope(
      state: state,
      api: shoppingApi,
      assistantApi: assistantApi,
      child: MaterialApp(
        locale: const Locale('mk'),
        supportedLocales: AppLocalizations.supportedLocales,
        localizationsDelegates: const [
          AppLocalizations.delegate,
          GlobalMaterialLocalizations.delegate,
          GlobalWidgetsLocalizations.delegate,
          GlobalCupertinoLocalizations.delegate,
        ],
        home: const AssistantScreen(),
      ),
    ),
  );
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('sends a turn and applies the proposal to the local basket',
      (tester) async {
    final assistant = FakeAssistantApi([milkProposalTurn]);
    final baskets = FakeBasketApi();
    await pumpAssistant(
      tester,
      assistantApi: assistant,
      shoppingApi: baskets,
    );

    await tester.enterText(find.byType(TextField), 'млеко');
    await tester.tap(find.byIcon(Icons.send));
    await tester.pumpAndSettle();

    // Turn + proposal strip rendered (with server-side preview subtotal).
    expect(assistant.calls, 1);
    expect(assistant.requests.first['message'], 'млеко');
    expect(find.text('Пронајдов млеко.'), findsOneWidget);
    expect(find.byKey(const Key('assistant_apply')), findsOneWidget);

    await tester.tap(find.byKey(const Key('assistant_apply')));
    await tester.pumpAndSettle();

    // Optimizer was invoked with the merged local basket.
    expect(baskets.optimizeCalls, hasLength(1));
    final sentItems = baskets.optimizeCalls.first.items;
    expect(sentItems, hasLength(1));
    expect(sentItems.first.canonicalProductId, 10);
    expect(sentItems.first.quantity, 1);
  });

  testWidgets('ambiguous turn offers pick card and sends explicit selection',
      (tester) async {
    final assistant = FakeAssistantApi([ambiguousTurn, milkProposalTurn]);
    final baskets = FakeBasketApi();
    await pumpAssistant(tester, assistantApi: assistant, shoppingApi: baskets);

    await tester.enterText(find.byType(TextField), 'каша');
    await tester.tap(find.byIcon(Icons.send));
    await tester.pumpAndSettle();

    expect(assistant.calls, 1);
    // Choice option row appears with the listing name.
    expect(find.text('КАША ЗРНА 500Г'), findsOneWidget);

    await tester.tap(find.text('КАША ЗРНА 500Г'));
    await tester.pumpAndSettle();

    // Selection turn: no message field, explicit candidate echo.
    expect(assistant.calls, 2);
    final selectionRequest = assistant.requests[1];
    expect(selectionRequest.containsKey('message'), isFalse);
    final selections = selectionRequest['candidateSelections'] as List;
    expect(selections, hasLength(1));
    expect((selections.first as Map)['candidateId'], 'c:20:201');
    expect((selections.first as Map)['query'], 'каша');
  });

  testWidgets('model_unavailable replies honestly and offers no proposals',
      (tester) async {
    final assistant = FakeAssistantApi([modelUnavailableTurn]);
    final baskets = FakeBasketApi();
    await pumpAssistant(tester, assistantApi: assistant, shoppingApi: baskets);

    await tester.enterText(find.byType(TextField), 'млеко');
    await tester.tap(find.byIcon(Icons.send));
    await tester.pumpAndSettle();

    expect(find.text('Модел недостапен.'), findsOneWidget);
    expect(find.byKey(const Key('assistant_apply')), findsNothing);
    expect(find.byKey(const Key('assistant_apply_strip')), findsNothing);
  });

  testWidgets('apply is refused when the basket changed after the turn',
      (tester) async {
    final assistant = FakeAssistantApi([milkProposalTurn]);
    final baskets = FakeBasketApi();
    final existing = BasketItem(
      localId: 'local-1',
      label: 'ЛЕБ',
      quantity: 1,
      unit: 'pack',
    );
    await pumpAssistant(
      tester,
      assistantApi: assistant,
      shoppingApi: baskets,
      initialBasket: [existing],
    );

    await tester.enterText(find.byType(TextField), 'млеко');
    await tester.tap(find.byIcon(Icons.send));
    await tester.pumpAndSettle();

    // Mutate the local basket outside of the assistant: signature becomes stale.
    final context = tester.state<State>(find.byType(AssistantScreen)).context;
    await AppScope.stateOf(context)
        .addBasketItem(BasketItem(localId: 'local-2', label: 'ЈАЈЦА', quantity: 6, unit: 'pcs'));
    await tester.pumpAndSettle();

    await tester.tap(find.byKey(const Key('assistant_apply')));
    await tester.pumpAndSettle();

    // Refused: no optimizer call and no extra basket mutation from the turn.
    expect(baskets.optimizeCalls, isEmpty);
    expect(AppScope.stateOf(context).basketItems, hasLength(2));
  });

  testWidgets('replace proposal updates the matching local basket entry',
      (tester) async {
    Map<String, dynamic> replaceOnly(AssistantTurnRequest request) => {
          'requestId': 'asst-r',
          'status': 'ok',
          'assistantMessage': 'Промена.',
          'provider': {'id': 'mock', 'isMock': true, 'configured': true},
          'proposedBasketChanges': [
            {
              'changeType': 'replace_quantity',
              'itemLabel': 'МЛЕКО БИМИЛК 1Л',
              'canonicalProductId': 10,
              'retailerProductId': 101,
              'listingName': 'МЛЕКО БИМИЛК 3.2% 1Л',
              'retailerSlug': 'vero',
              'quantity': 2,
              'unit': 'l',
              'oldQuantity': 1,
              'oldUnit': 'pack',
              'verifiedIdentity': true,
            },
          ],
        };
    final assistant = FakeAssistantApi([replaceOnly]);
    final baskets = FakeBasketApi();
    await pumpAssistant(
      tester,
      assistantApi: assistant,
      shoppingApi: baskets,
      initialBasket: [
        BasketItem(
          localId: 'local-milk',
          label: 'МЛЕКО БИМИЛК 1Л',
          canonicalProductId: 10,
          retailerProductId: 101,
          quantity: 1,
          unit: 'pack',
        ),
      ],
    );

    await tester.enterText(find.byType(TextField), '2 литра млеко');
    await tester.tap(find.byIcon(Icons.send));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('assistant_apply')));
    await tester.pumpAndSettle();

    final state = AppScope.stateOf(
      tester.state<State>(find.byType(AssistantScreen)).context,
    );
    final item = state.basketItems.single;
    expect(item.quantity, 2);
    expect(item.unit, 'l');
  });
}
