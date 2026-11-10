import '../models/api_models.dart';
import '../utils/transliteration.dart';
import 'api_service.dart';
import 'response_cache.dart';

/// A successful API read plus cache provenance for stale/offline UI states.
class ApiResult<T> {
  const ApiResult({
    required this.data,
    this.fromCache = false,
    this.cachedAt,
    this.error,
  });

  final T data;
  final bool fromCache;
  final DateTime? cachedAt;

  /// The network failure that forced the cache fallback, if any.
  final ApiServiceException? error;
}

/// Read-only catalog API used by the M12 screens.
///
/// All money and basket totals come from the server; the client only parses and
/// formats. Admin/review/metrics endpoints are intentionally not exposed here.
abstract class ShoppingApi {
  Future<ApiResult<List<Store>>> fetchStores({String? retailer, String? city});

  Future<ApiResult<SearchPage<Offer>>> searchOffers({
    String? query,
    String? retailer,
    bool inStockOnly,
    bool promoOnly,
    String sort,
    int page,
    int size,
  });

  Future<ApiResult<SearchPage<CanonicalComparison>>> compareProducts({
    String? query,
    int page,
    int size,
  });

  Future<ApiResult<ProductHistory>> fetchHistory(int canonicalProductId);

  Future<ApiResult<FreshnessReport>> fetchFreshness();

  Future<BasketOptimization> optimizeBasket(BasketOptimizeRequest request);
}

class HttpShoppingApi implements ShoppingApi {
  HttpShoppingApi({required ApiService service, KeyValueCache? cache})
      : _service = service,
        _cache = cache;

  final ApiService _service;
  final KeyValueCache? _cache;

  @override
  Future<ApiResult<List<Store>>> fetchStores({
    String? retailer,
    String? city,
  }) {
    final params = <String, String?>{
      'retailer': retailer,
      'city': city,
    };
    return _cachedList(
      key: 'stores:${retailer ?? ''}:${city ?? ''}',
      path: '/api/v1/stores',
      params: params,
      parse: (json) => SearchPage<Store>.fromJson(json, Store.fromJson).items,
    );
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
  }) async {
    final trimmed = query?.trim();
    // OpenSearch is indexed on Cyrillic source names. A Latin query that is not
    // transliterated first matches unrelated rows (fuzzy hits) rather than the
    // intended product, so the transliterated form is the primary query; the
    // raw Latin form is only retried when transliteration finds nothing.
    final latinFallback = (trimmed != null && containsLatinLetters(trimmed))
        ? transliterateToCyrillic(trimmed)
        : null;
    final primary = latinFallback ?? trimmed;

    Future<SearchPage<Offer>> fetch(String? effectiveQuery) async {
      final json = await _service.get('/api/v1/offers/search', params: {
        'q': effectiveQuery,
        'retailer': retailer,
        'inStockOnly': inStockOnly ? 'true' : null,
        'promoOnly': promoOnly ? 'true' : null,
        'sort': sort,
        'page': page.toString(),
        'size': size.toString(),
      });
      return SearchPage<Offer>.fromJson(json as Map<String, dynamic>, Offer.fromJson)
          .withQueryUsed(effectiveQuery);
    }

    final key = 'search:$trimmed:$retailer:$inStockOnly:$promoOnly:$sort:$page:$size';
    try {
      var result = await fetch(primary);
      if (result.total == 0 &&
          latinFallback != null &&
          trimmed != null &&
          latinFallback != trimmed) {
        final retried = await fetch(trimmed);
        if (retried.total > 0) {
          result = retried;
        }
      }
      await _writeCache(key, _rawFor(result));
      return ApiResult(data: result);
    } on ApiServiceException catch (error) {
      final cached = _readCache(key);
      if (cached != null) {
        final pageResult = SearchPage<Offer>.fromJson(
          cached.data as Map<String, dynamic>,
          Offer.fromJson,
        );
        return ApiResult(
          data: pageResult,
          fromCache: true,
          cachedAt: cached.storedAt,
          error: error,
        );
      }
      rethrow;
    }
  }

  @override
  Future<ApiResult<SearchPage<CanonicalComparison>>> compareProducts({
    String? query,
    int page = 0,
    int size = 20,
  }) async {
    final trimmed = query?.trim();
    final latinFallback = (trimmed != null && containsLatinLetters(trimmed))
        ? transliterateToCyrillic(trimmed)
        : null;
    final primary = latinFallback ?? trimmed;

    Future<SearchPage<CanonicalComparison>> fetch(String? effectiveQuery) async {
      final json = await _service.get('/api/v1/products/compare', params: {
        'q': effectiveQuery,
        'page': page.toString(),
        'size': size.toString(),
      });
      return SearchPage<CanonicalComparison>.fromJson(
        json as Map<String, dynamic>,
        CanonicalComparison.fromJson,
      ).withQueryUsed(effectiveQuery);
    }

    final key = 'compare:$trimmed:$page:$size';
    try {
      var result = await fetch(primary);
      if (result.total == 0 &&
          latinFallback != null &&
          trimmed != null &&
          latinFallback != trimmed) {
        final retried = await fetch(trimmed);
        if (retried.total > 0) {
          result = retried;
        }
      }
      await _writeCache(key, _rawFor(result));
      return ApiResult(data: result);
    } on ApiServiceException catch (error) {
      final cached = _readCache(key);
      if (cached != null) {
        return ApiResult(
          data: SearchPage<CanonicalComparison>.fromJson(
            cached.data as Map<String, dynamic>,
            CanonicalComparison.fromJson,
          ),
          fromCache: true,
          cachedAt: cached.storedAt,
          error: error,
        );
      }
      rethrow;
    }
  }

  @override
  Future<ApiResult<ProductHistory>> fetchHistory(int canonicalProductId) async {
    final key = 'history:$canonicalProductId';
    try {
      final json = await _service.get(
        '/api/v1/products/$canonicalProductId/history',
      );
      final history = ProductHistory.fromJson(json as Map<String, dynamic>);
      await _writeCache(key, json);
      return ApiResult(data: history);
    } on ApiServiceException catch (error) {
      final cached = _readCache(key);
      if (cached != null) {
        return ApiResult(
          data: ProductHistory.fromJson(cached.data as Map<String, dynamic>),
          fromCache: true,
          cachedAt: cached.storedAt,
          error: error,
        );
      }
      rethrow;
    }
  }

  @override
  Future<ApiResult<FreshnessReport>> fetchFreshness() async {
    const key = 'freshness';
    try {
      final json = await _service.get('/api/v1/freshness');
      final report = FreshnessReport.fromJson(json as Map<String, dynamic>);
      await _writeCache(key, json);
      return ApiResult(data: report);
    } on ApiServiceException catch (error) {
      final cached = _readCache(key);
      if (cached != null) {
        return ApiResult(
          data: FreshnessReport.fromJson(cached.data as Map<String, dynamic>),
          fromCache: true,
          cachedAt: cached.storedAt,
          error: error,
        );
      }
      rethrow;
    }
  }

  @override
  Future<BasketOptimization> optimizeBasket(
    BasketOptimizeRequest request,
  ) async {
    final json = await _service.post(
      '/api/v1/baskets/optimize',
      body: request.toJson(),
    );
    return BasketOptimization.fromJson(json as Map<String, dynamic>);
  }

  Future<ApiResult<T>> _cachedList<T>({
    required String key,
    required String path,
    required Map<String, String?> params,
    required T Function(Map<String, dynamic>) parse,
  }) async {
    try {
      final json = await _service.get(path, params: params);
      final parsed = parse(json as Map<String, dynamic>);
      await _writeCache(key, json);
      return ApiResult(data: parsed);
    } on ApiServiceException catch (error) {
      final cached = _readCache(key);
      if (cached != null) {
        return ApiResult(
          data: parse(cached.data as Map<String, dynamic>),
          fromCache: true,
          cachedAt: cached.storedAt,
          error: error,
        );
      }
      rethrow;
    }
  }

  Map<String, dynamic> _rawFor(SearchPage<dynamic> page) => {
        'sourceEngine': page.sourceEngine,
        'total': page.total,
        'page': page.page,
        'size': page.size,
        'items': page.items.map((item) {
          if (item is Offer) return _offerToJson(item);
          if (item is CanonicalComparison) return _comparisonToJson(item);
          return <String, dynamic>{};
        }).toList(growable: false),
      };

  Future<void> _writeCache(String key, Object? json) async {
    await _cache?.put(key, json);
  }

  CachedResponse? _readCache(String key) => _cache?.read(key);
}

Map<String, dynamic> _offerToJson(Offer o) => {
      'offerId': o.offerId,
      'storeId': o.storeId,
      'storeExternalKey': o.storeExternalKey,
      'storeName': o.storeName,
      'city': o.city,
      'retailerSlug': o.retailerSlug,
      'retailerName': o.retailerName,
      'retailerProductId': o.retailerProductId,
      'skuKey': o.skuKey,
      'listingName': o.listingName,
      'category': o.category,
      'canonicalProductId': o.canonicalProductId,
      'canonicalKey': o.canonicalKey,
      'canonicalName': o.canonicalName,
      'normalizedSize': o.normalizedSize,
      'currency': o.currency,
      'priceCurrent': o.priceCurrent,
      'unitPrice': o.unitPrice,
      'unitLabel': o.unitLabel,
      'regularPrice': o.regularPrice,
      'discountPrice': o.discountPrice,
      'discountPct': o.discountPct,
      'promoType': o.promoType,
      'promoStartsOn': o.promoStartsOn,
      'promoEndsOn': o.promoEndsOn,
      'isPromo': o.isPromo,
      'availability': o.availability,
      'publishedTs': o.publishedTs?.toIso8601String(),
      'fetchedTs': o.fetchedTs?.toIso8601String(),
      'sourceUrl': o.sourceUrl,
      'runId': o.runId,
    };

Map<String, dynamic> _comparisonToJson(CanonicalComparison c) => {
      'canonicalProductId': c.canonicalProductId,
      'canonicalKey': c.canonicalKey,
      'canonicalName': c.canonicalName,
      'normalizedSize': c.normalizedSize,
      'retailerCount': c.retailerCount,
      'storeCount': c.storeCount,
      'cheapestMkd': c.cheapestMkd,
      'highestMkd': c.highestMkd,
      'spreadMkd': c.spreadMkd,
      'latestPublishedTs': c.latestPublishedTs?.toIso8601String(),
      'offers': c.offers
          .map((o) => {
                'retailerSlug': o.retailerSlug,
                'retailerProductId': o.retailerProductId,
                'listingName': o.listingName,
                'minPrice': o.minPrice,
                'maxPrice': o.maxPrice,
                'storeCount': o.storeCount,
                'latestPublishedTs': o.latestPublishedTs?.toIso8601String(),
                'sourceUrl': o.sourceUrl,
              })
          .toList(growable: false),
    };
