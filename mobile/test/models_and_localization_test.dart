import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:ai_shopping_mobile/l10n/app_localizations.dart';
import 'package:ai_shopping_mobile/l10n/translations.dart';
import 'package:ai_shopping_mobile/models/api_models.dart';
import 'package:ai_shopping_mobile/utils/formatters.dart';
import 'package:ai_shopping_mobile/utils/transliteration.dart';

void main() {
  group('transliteration', () {
    test('transliterates common Latin queries to Cyrillic', () {
      expect(transliterateToCyrillic('mleko'), 'млеко');
      expect(transliterateToCyrillic('jogurt'), 'јогурт');
      expect(transliterateToCyrillic('hleb'), 'хлеб');
      expect(transliterateToCyrillic('kafe'), 'кафе');
      expect(transliterateToCyrillic('sirenje'), 'сирење');
      expect(transliterateToCyrillic('chokolado'), 'чоколадо');
      expect(transliterateToCyrillic('dzhak'), 'џак');
    });

    test('keeps Cyrillic input unchanged', () {
      const cyrillic = 'млеко';
      expect(transliterateToCyrillic(cyrillic), cyrillic);
    });

    test('leaves digits and spaces intact', () {
      expect(transliterateToCyrillic('mleko 3.5%'), 'млеко 3.5%');
    });

    test('detects Latin letters', () {
      expect(containsLatinLetters('mleko'), isTrue);
      expect(containsLatinLetters('млеко'), isFalse);
    });
  });

  group('formatters', () {
    test('formats MKD with Macedonian separators and suffix', () {
      expect(formatMkd(1234.5), '1.234,50 ден.');
      expect(formatMkd(40), '40,00 ден.');
      expect(formatMkd(0.01), '0,01 ден.');
      expect(formatMkd(1234567.89), '1.234.567,89 ден.');
    });

    test('formats quantities without trailing zeros', () {
      expect(formatQuantity(2), '2');
      expect(formatQuantity(0.5), '0,5');
      expect(formatQuantity(1.25), '1,25');
      expect(formatQuantity(3.0), '3');
    });

    test('formats timestamps in dd.MM.yyyy HH:mm', () {
      final utc = DateTime.utc(2026, 11, 9, 18, 5);
      final rendered = formatDateTime(utc);
      expect(rendered, matches(RegExp(r'\d{2}\.\d{2}\.2026 \d{2}:\d{2}')));
    });

    test('formats ISO promo dates', () {
      expect(formatIsoDate('2026-10-31'), isNot('—'));
      expect(formatIsoDate(null), '—');
    });
  });

  group('api models', () {
    test('parses an offer payload with null canonical fields', () {
      final offer = Offer.fromJson({
        'offerId': '1:498',
        'storeId': 1,
        'storeExternalKey': '89',
        'storeName': 'ВЕРО 1',
        'city': 'Аеродром',
        'retailerSlug': 'vero',
        'retailerName': 'Vero',
        'retailerProductId': 498,
        'listingName': 'ТОРТИЦА БАРНИ МЛЕКО 30ГР',
        'canonicalProductId': null,
        'canonicalName': null,
        'normalizedSize': null,
        'currency': 'MKD',
        'priceCurrent': 19,
        'unitPrice': null,
        'regularPrice': 24,
        'discountPrice': 19,
        'discountPct': 20,
        'isPromo': true,
        'availability': 'in_stock',
        'publishedTs': '2026-10-28T07:02:00+00:00',
        'fetchedTs': '2026-11-09T18:01:13.292584+00:00',
      });
      expect(offer.priceCurrent, 19);
      expect(offer.hasVerifiedIdentity, isFalse);
      expect(offer.isInStock, isTrue);
      expect(offer.discountPct, 20);
    });

    test('marks unknown availability', () {
      final offer = Offer.fromJson({
        'offerId': 'x',
        'retailerSlug': 'kam',
        'retailerProductId': 1,
        'listingName': 'n',
        'priceCurrent': 1,
        'availability': 'unknown',
      });
      expect(offer.isAvailabilityUnknown, isTrue);
      expect(offer.isInStock, isFalse);
      expect(offer.isOutOfStock, isFalse);
    });

    test('parses a verified comparison group', () {
      final comparison = CanonicalComparison.fromJson({
        'canonicalProductId': 2634,
        'canonicalName': 'ЈОГУРТ ГРЧКИ 0% 150 Г ОЛИМПУС',
        'normalizedSize': '150g',
        'retailerCount': 2,
        'storeCount': 4,
        'cheapestMkd': 40,
        'highestMkd': 46,
        'spreadMkd': 6,
        'latestPublishedTs': '2026-11-08T04:48:54+00:00',
        'offers': [
          {
            'retailerSlug': 'vero',
            'retailerProductId': 398,
            'listingName': 'ЈОГУРТ 0%',
            'minPrice': 40,
            'maxPrice': 40,
            'storeCount': 1,
            'latestPublishedTs': '2026-10-28T07:02:00+00:00',
          },
          {
            'retailerSlug': 'kam',
            'retailerProductId': 1874,
            'listingName': 'ЈОГУРТ 0%',
            'minPrice': 46,
            'maxPrice': 46,
            'storeCount': 2,
            'latestPublishedTs': '2026-11-08T04:48:54+00:00',
          },
        ],
      });
      expect(comparison.retailerSlugs, ['vero', 'kam']);
      expect(comparison.cheapestMkd, 40);
      expect(comparison.offers, hasLength(2));
    });

    test('parses basket optimization with missing items and substitutes', () {
      final optimization = BasketOptimization.fromJson({
        'totalItemsRequested': 2,
        'allowSubstitutes': true,
        'inStockOnly': true,
        'maxStoresAllowed': 3,
        'minSplitSavingsMkd': 0,
        'bestSingleStore': {
          'storeId': 1,
          'retailerSlug': 'vero',
          'retailerName': 'Vero',
          'storeName': 'ВЕРО 1',
          'itemsCovered': 1,
          'totalItemsRequested': 2,
          'coverageRatio': 0.5,
          'totalMkd': 80,
          'savingsVsHighestCoveredSingleStoreMkd': 12,
          'exactMatchesCount': 1,
          'substitutesCount': 0,
          'coveredItems': [
            {
              'itemIndex': 0,
              'canonicalProductId': 2634,
              'requestedName': 'јогурт',
              'requestedQuantity': 2,
              'requestedUnit': 'pack',
              'storeId': 1,
              'storeName': 'ВЕРО 1',
              'retailerSlug': 'vero',
              'matchedRetailerProductId': 398,
              'matchedListingName': 'ЈОГУРТ 0% 150ГР',
              'packsNeeded': 2,
              'unitPackPriceMkd': 40,
              'lineTotalMkd': 80,
              'isSubstitute': false,
              'publishedTs': '2026-10-28T07:02:00+00:00',
            }
          ],
          'missingItems': [
            {
              'itemIndex': 1,
              'canonicalProductId': 999999,
              'requestedName': 'непознат',
              'requestedQuantity': 1,
              'requestedUnit': 'pcs',
              'reason': 'product_not_found_in_catalog',
            }
          ],
        },
        'singleStoreRankings': [],
        'bestMultiStorePlan': null,
      });
      expect(optimization.bestSingleStore, isNotNull);
      expect(optimization.bestSingleStore!.missingItems, hasLength(1));
      expect(
        optimization.bestSingleStore!.missingItems.first.reason,
        'product_not_found_in_catalog',
      );
    });

    test('parses history observations newest-first', () {
      final history = ProductHistory.fromJson({
        'canonicalProductId': 2634,
        'canonicalName': 'ЈОГУРТ',
        'observations': [
          {
            'observationId': 953,
            'retailerSlug': 'vero',
            'storeName': 'ВЕРО 1',
            'listingName': 'ЈОГУРТ',
            'priceCurrent': 40,
            'availability': 'in_stock',
            'publishedTs': '2026-10-28T07:02:00+00:00',
          },
          {
            'observationId': 4319,
            'retailerSlug': 'kam',
            'storeName': 'ШТИП',
            'listingName': 'ЈОГУРТ',
            'priceCurrent': 46,
            'availability': 'in_stock',
            'publishedTs': '2026-11-08T04:48:54+00:00',
          },
        ],
      });
      expect(history.newestFirst.first.observationId, 4319);
      expect(history.newestFirst.last.observationId, 953);
    });

    test('parses freshness report with stale stores', () {
      final report = FreshnessReport.fromJson({
        'status': 'DEGRADED',
        'checkedAt': '2026-11-09T20:21:20.134665+00:00',
        'staleThresholdHours': 48,
        'quarantineWindowDays': 7,
        'totalOffers': 5145,
        'totalPopulatedStores': 9,
        'totalStaleStores': 3,
        'totalQuarantinedRuns': 0,
        'retailers': [
          {
            'retailerSlug': 'stokomak',
            'retailerName': 'Stokomak',
            'seededStoresCount': 81,
            'populatedStoresCount': 3,
            'offerCount': 400,
            'staleStoresCount': 3,
            'staleStores': [
              {
                'storeId': 18,
                'storeName': 'КИСЕЛА ВОДА',
                'offerCount': 200,
                'ageHours': 287,
              }
            ],
            'quarantinedRunsCount': 0,
          }
        ],
      });
      expect(report.hasStaleData, isTrue);
      expect(report.retailers.first.staleStores, hasLength(1));
      expect(report.isHealthy, isFalse);
    });

    test('basket request serializes only allowed backend fields', () {
      final request = BasketOptimizeRequest(items: [
        BasketItem(
          localId: 'b1',
          label: 'ЈОГУРТ',
          canonicalProductId: 2634,
          quantity: 2,
          unit: 'pack',
        ),
        BasketItem(
          localId: 'b2',
          label: 'Непознат производ',
          quantity: 1,
          unit: 'pcs',
        ),
      ], maxStores: 3, allowSubstitutes: true);
      final json = request.toJson();
      expect(json['maxStores'], 3);
      expect(json['allowSubstitutes'], isTrue);
      final items = json['items'] as List;
      expect(items[0]['canonicalProductId'], 2634);
      expect(items[1]['itemLabel'], 'Непознат производ');
      expect(items[1]['canonicalProductId'], isNull);
    });
  });

  group('localization', () {
    test('mk and en locales define the same key set', () {
      expect(translations['mk']!.keys.toSet(), translations['en']!.keys.toSet());
    });

    test('no translation value contains a raw placeholder without params', () {
      const allowed = [
        'store', 'ts', 'query', 'count', 'hours', 'amount', 'percent',
        'price', 'unit', 'date', 'email', 'engine', 'covered', 'total',
      ];
      translations.forEach((locale, map) {
        map.forEach((key, value) {
          final placeholders = RegExp(r'\{(\w+)\}').allMatches(value);
          for (final match in placeholders) {
            final name = match.group(1)!;
            expect(
              allowed.contains(name),
              isTrue,
              reason: '$locale/$key has unexpected placeholder {$name}',
            );
          }
        });
      });
    });

    test('params are substituted', () {
      const l = AppLocalizations(Locale('mk'));
      expect(
        l.t('search_no_results_body', {'query': 'млеко'}),
        contains('млеко'),
      );
      expect(
        l.t('basket_coverage_value', {
          'covered': '1',
          'total': '2',
          'percent': '50',
        }),
        contains('50%'),
      );
    });

    test('mk is Macedonian, en falls back to English keys', () {
      const mk = AppLocalizations(Locale('mk'));
      const en = AppLocalizations(Locale('en'));
      expect(mk.isMacedonian, isTrue);
      expect(en.isMacedonian, isFalse);
      expect(mk.t('nav_home'), isNot(en.t('nav_home')));
    });

    test('missing reason keys map to friendly text', () {
      const l = AppLocalizations(Locale('mk'));
      expect(
        l.missingReason('product_not_found_in_catalog'),
        isNot('product_not_found_in_catalog'),
      );
    });
  });
}
