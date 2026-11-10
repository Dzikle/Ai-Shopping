import 'package:ai_shopping_mobile/models/assistant_models.dart';
import 'package:ai_shopping_mobile/models/api_models.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  group('assistant models', () {
    test('parses a full actionable turn payload', () {
      final turn = AssistantTurn.fromJson({
        'requestId': 'asst-abc',
        'status': 'needs_clarification',
        'assistantMessage': 'Изберете.',
        'provider': {'id': 'openai_compatible', 'model': 'gpt', 'isMock': false, 'configured': true},
        'warnings': ['stale_offers'],
        'limits': {'messageMaxChars': 500, 'maxItemsPerTurn': 8},
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
            'oldQuantity': null,
            'oldUnit': null,
            'publishedTs': '2026-10-28T08:00:00Z',
            'sourceUrl': 'https://example.com/1',
          },
          {
            'changeType': 'replace_quantity',
            'itemLabel': 'млеко',
            'canonicalProductId': 10,
            'retailerProductId': 101,
            'quantity': 2,
            'unit': 'l',
            'oldQuantity': 1,
            'oldUnit': 'pack',
            'verifiedIdentity': true,
          },
        ],
        'candidateChoices': [
          {
            'itemLabel': 'каша',
            'query': 'каша',
            'reason': 'multiple_products',
            'requestedQuantity': 1,
            'requestedUnit': 'pack',
            'options': [
              {
                'candidateId': 'c:20:201',
                'retailerSlug': 'vero',
                'listingName': 'КАША ЗРНА 500Г',
                'priceCurrentMkd': 60.0,
                'canonicalProductId': 20,
                'isSubstituteCandidate': false,
              },
              {
                'candidateId': 'c:22:501',
                'retailerSlug': 'zito',
                'listingName': 'МЛЕКО СКАЈСНО 1Л',
                'priceCurrentMkd': 55.0,
                'canonicalProductId': 22,
                'isSubstituteCandidate': true,
                'matchConfidence': 0.67,
              },
            ],
          },
        ],
        'unresolvedItems': [
          {'label': 'празно', 'reason': 'no_offers_found'},
        ],
        'optimizationPreview': {
          'previewOnly': true,
          'totalItemsRequested': 1,
          'bestSingleStore': {
            'storeName': 'Веро Тафталиџе',
            'retailerSlug': 'vero',
            'totalMkd': 75.0,
            'itemsCovered': 1,
            'totalItemsRequested': 1,
          },
        },
      });

      expect(turn.status, 'needs_clarification');
      expect(turn.provider.isMock, isFalse);
      expect(turn.proposals, hasLength(2));
      expect(turn.proposals.first.isAdd, isTrue);
      expect(turn.proposals[1].isReplace, isTrue);
      expect(turn.proposals[1].oldQuantity, 1.0);
      expect(turn.proposals[1].oldUnit, 'pack');
      expect(turn.choices, hasLength(1));
      expect(turn.choices.first.options, hasLength(2));
      expect(turn.choices.first.options[1].isSubstituteCandidate, isTrue);
      expect(turn.unresolved.first.reason, 'no_offers_found');
      expect(turn.preview!.previewOnly, isTrue);
      expect(turn.preview!.bestTotalMkd, 75.0);
      expect(turn.hasChoices, isTrue);
      expect(turn.needsClarification, isTrue);
      expect(turn.limits.maxItemsPerTurn, 8);
    });

    test('parses degraded statuses and defaults', () {
      final turn = AssistantTurn.fromJson({
        'status': 'model_unavailable',
        'provider': {'id': 'none', 'isMock': false, 'configured': false},
      });
      expect(turn.status, 'model_unavailable');
      expect(turn.provider.configured, isFalse);
      expect(turn.provider.id, 'none');
      expect(turn.proposals, isEmpty);
      expect(turn.choices, isEmpty);
      expect(turn.unresolved, isEmpty);
      expect(turn.isActionable, isFalse);
      expect(turn.limits.messageMaxChars, 500);
    });

    test('turn request omits empty sections and sends selection turn', () {
      final plain = AssistantTurnRequest(
        message: 'млеко',
        locale: 'mk',
      ).toJson();
      expect(plain['message'], 'млеко');
      expect(plain.containsKey('candidateSelections'), isFalse);
      expect(plain.containsKey('currentBasket'), isFalse);

      final selection = AssistantTurnRequest(
        message: null,
        locale: 'en',
        currentBasket: [],
        candidateSelections: [
          AssistantCandidateSelection(
            itemLabel: 'каша',
            query: 'каша',
            candidateId: 'c:20:201',
            quantity: 2,
            unit: 'pack',
          ),
        ],
      ).toJson();
      expect(selection.containsKey('message'), isFalse);
      expect(selection['candidateSelections'], hasLength(1));
      expect((selection['candidateSelections'] as List).first['candidateId'], 'c:20:201');
      expect((selection['candidateSelections'] as List).first['quantity'], 2.0);
    });

    test('basket echo serializes the local basket shape', () {
      final echo = AssistantBasketEchoItem.fromBasketItem(BasketItem(
        localId: 'b1',
        label: 'МЛЕКО',
        canonicalProductId: 10,
        retailerProductId: 101,
        quantity: 2,
        unit: 'l',
      ));
      expect(echo.toJson(), {
        'label': 'МЛЕКО',
        'quantity': 2.0,
        'unit': 'l',
        'canonicalProductId': 10,
        'retailerProductId': 101,
      });
    });
  });
}
