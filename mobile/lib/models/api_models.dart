/// Typed models for the AI Shopping FastAPI contracts (v1).
///
/// Field names and nullability mirror the live backend responses:
/// - offers may have null canonical fields and null unit prices,
/// - availability is an open string (`in_stock` / `out_of_stock` / unknown),
/// - comparison offers are retailer-level aggregates (no per-store unit price),
/// - history returns `observations` (never synthesized points).
library;

double? _toDouble(Object? value) {
  if (value == null) return null;
  if (value is num) return value.toDouble();
  return double.tryParse(value.toString());
}

double _toDoubleOrZero(Object? value) => _toDouble(value) ?? 0;

int? _toInt(Object? value) {
  if (value == null) return null;
  if (value is int) return value;
  if (value is num) return value.toInt();
  return int.tryParse(value.toString());
}

int _toIntOrZero(Object? value) => _toInt(value) ?? 0;

String? _toStringOrNull(Object? value) {
  if (value == null) return null;
  final text = value.toString();
  return text.isEmpty ? null : text;
}

DateTime? _toDate(Object? value) {
  final text = _toStringOrNull(value);
  if (text == null) return null;
  return DateTime.tryParse(text);
}

bool _toBool(Object? value) {
  if (value is bool) return value;
  if (value is num) return value != 0;
  return value?.toString().toLowerCase() == 'true';
}

List<T> _toList<T>(Object? value, T Function(Map<String, dynamic>) parse) {
  if (value is! List) return const [];
  return value
      .whereType<Map>()
      .map((item) => parse(Map<String, dynamic>.from(item)))
      .toList(growable: false);
}

Map<String, dynamic> _asMap(Object? value) =>
    value is Map ? Map<String, dynamic>.from(value) : const {};

/// Shared envelope returned by catalog list endpoints.
class SearchPage<T> {
  const SearchPage({
    required this.sourceEngine,
    required this.total,
    required this.page,
    required this.size,
    required this.items,
    this.queryUsed,
  });

  factory SearchPage.fromJson(
    Map<String, dynamic> json,
    T Function(Map<String, dynamic>) parseItem,
  ) {
    return SearchPage<T>(
      sourceEngine: _toStringOrNull(json['sourceEngine']),
      total: _toIntOrZero(json['total']),
      page: _toIntOrZero(json['page']),
      size: _toIntOrZero(json['size']),
      items: _toList(json['items'], parseItem),
    );
  }

  final String? sourceEngine;
  final int total;
  final int page;
  final int size;
  final List<T> items;

  /// Query actually sent to the backend (Latin input may be transliterated).
  final String? queryUsed;

  SearchPage<T> withQueryUsed(String? query) => SearchPage<T>(
        sourceEngine: sourceEngine,
        total: total,
        page: page,
        size: size,
        items: items,
        queryUsed: query,
      );

  bool get hasMore => items.length + page * size < total;
}

class Store {
  const Store({
    required this.storeId,
    required this.retailerSlug,
    required this.retailerName,
    this.externalKey,
    required this.name,
    this.address,
    this.city,
    required this.activeOffersCount,
    this.latestPublishedTs,
  });

  factory Store.fromJson(Map<String, dynamic> json) {
    return Store(
      storeId: _toIntOrZero(json['storeId']),
      retailerSlug: _toStringOrNull(json['retailerSlug']) ?? '',
      retailerName: _toStringOrNull(json['retailerName']) ?? '',
      externalKey: _toStringOrNull(json['externalKey']),
      name: _toStringOrNull(json['name']) ?? '',
      address: _toStringOrNull(json['address']),
      city: _toStringOrNull(json['city']),
      activeOffersCount: _toIntOrZero(json['activeOffersCount']),
      latestPublishedTs: _toDate(json['latestPublishedTs']),
    );
  }

  final int storeId;
  final String retailerSlug;
  final String retailerName;
  final String? externalKey;
  final String name;
  final String? address;
  final String? city;
  final int activeOffersCount;
  final DateTime? latestPublishedTs;
}

class Offer {
  const Offer({
    required this.offerId,
    required this.storeId,
    this.storeExternalKey,
    this.storeName,
    this.city,
    required this.retailerSlug,
    this.retailerName,
    required this.retailerProductId,
    this.skuKey,
    required this.listingName,
    this.category,
    this.canonicalProductId,
    this.canonicalKey,
    this.canonicalName,
    this.normalizedSize,
    this.currency,
    required this.priceCurrent,
    this.unitPrice,
    this.unitLabel,
    this.regularPrice,
    this.discountPrice,
    this.discountPct,
    this.promoType,
    this.promoStartsOn,
    this.promoEndsOn,
    this.isPromo = false,
    this.availability,
    this.publishedTs,
    this.fetchedTs,
    this.sourceUrl,
    this.runId,
  });

  factory Offer.fromJson(Map<String, dynamic> json) {
    return Offer(
      offerId: _toStringOrNull(json['offerId']) ?? '',
      storeId: _toIntOrZero(json['storeId']),
      storeExternalKey: _toStringOrNull(json['storeExternalKey']),
      storeName: _toStringOrNull(json['storeName']),
      city: _toStringOrNull(json['city']),
      retailerSlug: _toStringOrNull(json['retailerSlug']) ?? '',
      retailerName: _toStringOrNull(json['retailerName']),
      retailerProductId: _toIntOrZero(json['retailerProductId']),
      skuKey: _toStringOrNull(json['skuKey']),
      listingName: _toStringOrNull(json['listingName']) ?? '',
      category: _toStringOrNull(json['category']),
      canonicalProductId: _toInt(json['canonicalProductId']),
      canonicalKey: _toStringOrNull(json['canonicalKey']),
      canonicalName: _toStringOrNull(json['canonicalName']),
      normalizedSize: _toStringOrNull(json['normalizedSize']),
      currency: _toStringOrNull(json['currency']),
      priceCurrent: _toDoubleOrZero(json['priceCurrent']),
      unitPrice: _toDouble(json['unitPrice']),
      unitLabel: _toStringOrNull(json['unitLabel']),
      regularPrice: _toDouble(json['regularPrice']),
      discountPrice: _toDouble(json['discountPrice']),
      discountPct: _toDouble(json['discountPct']),
      promoType: _toStringOrNull(json['promoType']),
      promoStartsOn: _toStringOrNull(json['promoStartsOn']),
      promoEndsOn: _toStringOrNull(json['promoEndsOn']),
      isPromo: _toBool(json['isPromo']),
      availability: _toStringOrNull(json['availability']),
      publishedTs: _toDate(json['publishedTs']),
      fetchedTs: _toDate(json['fetchedTs']),
      sourceUrl: _toStringOrNull(json['sourceUrl']),
      runId: _toInt(json['runId']),
    );
  }

  final String offerId;
  final int storeId;
  final String? storeExternalKey;
  final String? storeName;
  final String? city;
  final String retailerSlug;
  final String? retailerName;
  final int retailerProductId;
  final String? skuKey;
  final String listingName;
  final String? category;
  final int? canonicalProductId;
  final String? canonicalKey;
  final String? canonicalName;
  final String? normalizedSize;
  final String? currency;
  final double priceCurrent;
  final double? unitPrice;
  final String? unitLabel;
  final double? regularPrice;
  final double? discountPrice;
  final double? discountPct;
  final String? promoType;
  final String? promoStartsOn;
  final String? promoEndsOn;
  final bool isPromo;
  final String? availability;
  final DateTime? publishedTs;
  final DateTime? fetchedTs;
  final String? sourceUrl;
  final int? runId;

  bool get isInStock => availability == 'in_stock';
  bool get isOutOfStock => availability == 'out_of_stock';
  bool get isAvailabilityUnknown => !isInStock && !isOutOfStock;
  bool get hasVerifiedIdentity => canonicalProductId != null;
}

class ComparisonOffer {
  const ComparisonOffer({
    required this.retailerSlug,
    required this.retailerProductId,
    required this.listingName,
    required this.minPrice,
    required this.maxPrice,
    required this.storeCount,
    this.latestPublishedTs,
    this.sourceUrl,
  });

  factory ComparisonOffer.fromJson(Map<String, dynamic> json) {
    return ComparisonOffer(
      retailerSlug: _toStringOrNull(json['retailerSlug']) ?? '',
      retailerProductId: _toIntOrZero(json['retailerProductId']),
      listingName: _toStringOrNull(json['listingName']) ?? '',
      minPrice: _toDoubleOrZero(json['minPrice']),
      maxPrice: _toDoubleOrZero(json['maxPrice']),
      storeCount: _toIntOrZero(json['storeCount']),
      latestPublishedTs: _toDate(json['latestPublishedTs']),
      sourceUrl: _toStringOrNull(json['sourceUrl']),
    );
  }

  final String retailerSlug;
  final int retailerProductId;
  final String listingName;
  final double minPrice;
  final double maxPrice;
  final int storeCount;
  final DateTime? latestPublishedTs;
  final String? sourceUrl;
}

class CanonicalComparison {
  const CanonicalComparison({
    required this.canonicalProductId,
    this.canonicalKey,
    required this.canonicalName,
    this.normalizedSize,
    required this.retailerCount,
    required this.storeCount,
    required this.cheapestMkd,
    required this.highestMkd,
    required this.spreadMkd,
    this.latestPublishedTs,
    required this.offers,
  });

  factory CanonicalComparison.fromJson(Map<String, dynamic> json) {
    return CanonicalComparison(
      canonicalProductId: _toIntOrZero(json['canonicalProductId']),
      canonicalKey: _toStringOrNull(json['canonicalKey']),
      canonicalName: _toStringOrNull(json['canonicalName']) ?? '',
      normalizedSize: _toStringOrNull(json['normalizedSize']),
      retailerCount: _toIntOrZero(json['retailerCount']),
      storeCount: _toIntOrZero(json['storeCount']),
      cheapestMkd: _toDoubleOrZero(json['cheapestMkd']),
      highestMkd: _toDoubleOrZero(json['highestMkd']),
      spreadMkd: _toDoubleOrZero(json['spreadMkd']),
      latestPublishedTs: _toDate(json['latestPublishedTs']),
      offers: _toList(json['offers'], ComparisonOffer.fromJson),
    );
  }

  final int canonicalProductId;
  final String? canonicalKey;
  final String canonicalName;
  final String? normalizedSize;
  final int retailerCount;
  final int storeCount;
  final double cheapestMkd;
  final double highestMkd;
  final double spreadMkd;
  final DateTime? latestPublishedTs;
  final List<ComparisonOffer> offers;

  /// Distinct retailer slugs present in this verified identity group.
  List<String> get retailerSlugs =>
      offers.map((o) => o.retailerSlug).toSet().toList(growable: false);
}

class PriceObservation {
  const PriceObservation({
    required this.observationId,
    required this.retailerSlug,
    this.storeExternalKey,
    required this.storeName,
    required this.listingName,
    required this.priceCurrent,
    this.regularPrice,
    this.discountPrice,
    this.discountPct,
    this.promoType,
    this.availability,
    this.publishedTs,
    this.fetchedTs,
    this.sourceUrl,
  });

  factory PriceObservation.fromJson(Map<String, dynamic> json) {
    return PriceObservation(
      observationId: _toIntOrZero(json['observationId']),
      retailerSlug: _toStringOrNull(json['retailerSlug']) ?? '',
      storeExternalKey: _toStringOrNull(json['storeExternalKey']),
      storeName: _toStringOrNull(json['storeName']) ?? '',
      listingName: _toStringOrNull(json['listingName']) ?? '',
      priceCurrent: _toDoubleOrZero(json['priceCurrent']),
      regularPrice: _toDouble(json['regularPrice']),
      discountPrice: _toDouble(json['discountPrice']),
      discountPct: _toDouble(json['discountPct']),
      promoType: _toStringOrNull(json['promoType']),
      availability: _toStringOrNull(json['availability']),
      publishedTs: _toDate(json['publishedTs']),
      fetchedTs: _toDate(json['fetchedTs']),
      sourceUrl: _toStringOrNull(json['sourceUrl']),
    );
  }

  final int observationId;
  final String retailerSlug;
  final String? storeExternalKey;
  final String storeName;
  final String listingName;
  final double priceCurrent;
  final double? regularPrice;
  final double? discountPrice;
  final double? discountPct;
  final String? promoType;
  final String? availability;
  final DateTime? publishedTs;
  final DateTime? fetchedTs;
  final String? sourceUrl;

  bool get isInStock => availability == 'in_stock';
}

class ProductHistory {
  const ProductHistory({
    required this.canonicalProductId,
    required this.canonicalName,
    this.normalizedSize,
    required this.observations,
  });

  factory ProductHistory.fromJson(Map<String, dynamic> json) {
    return ProductHistory(
      canonicalProductId: _toIntOrZero(json['canonicalProductId']),
      canonicalName: _toStringOrNull(json['canonicalName']) ?? '',
      normalizedSize: _toStringOrNull(json['normalizedSize']),
      observations: _toList(json['observations'], PriceObservation.fromJson),
    );
  }

  final int canonicalProductId;
  final String canonicalName;
  final String? normalizedSize;
  final List<PriceObservation> observations;

  List<PriceObservation> get newestFirst {
    final sorted = List<PriceObservation>.from(observations);
    sorted.sort((a, b) {
      final ad = a.publishedTs?.millisecondsSinceEpoch ?? 0;
      final bd = b.publishedTs?.millisecondsSinceEpoch ?? 0;
      return bd.compareTo(ad);
    });
    return sorted;
  }
}

class StaleStore {
  const StaleStore({
    required this.storeId,
    this.externalKey,
    required this.storeName,
    this.city,
    required this.offerCount,
    this.latestPublishedTs,
    this.latestFetchedTs,
    this.ageHours,
  });

  factory StaleStore.fromJson(Map<String, dynamic> json) {
    return StaleStore(
      storeId: _toIntOrZero(json['storeId']),
      externalKey: _toStringOrNull(json['externalKey']),
      storeName: _toStringOrNull(json['storeName']) ?? '',
      city: _toStringOrNull(json['city']),
      offerCount: _toIntOrZero(json['offerCount']),
      latestPublishedTs: _toDate(json['latestPublishedTs']),
      latestFetchedTs: _toDate(json['latestFetchedTs']),
      ageHours: _toInt(json['ageHours']),
    );
  }

  final int storeId;
  final String? externalKey;
  final String storeName;
  final String? city;
  final int offerCount;
  final DateTime? latestPublishedTs;
  final DateTime? latestFetchedTs;
  final int? ageHours;
}

class RetailerFreshness {
  const RetailerFreshness({
    required this.retailerSlug,
    required this.retailerName,
    required this.seededStoresCount,
    required this.populatedStoresCount,
    required this.offerCount,
    this.latestPublishedTs,
    this.oldestPublishedTs,
    this.latestFetchedTs,
    required this.staleStoresCount,
    required this.staleStores,
    required this.quarantinedRunsCount,
    this.lastCompletedRunKey,
    this.lastCompletedAt,
  });

  factory RetailerFreshness.fromJson(Map<String, dynamic> json) {
    return RetailerFreshness(
      retailerSlug: _toStringOrNull(json['retailerSlug']) ?? '',
      retailerName: _toStringOrNull(json['retailerName']) ?? '',
      seededStoresCount: _toIntOrZero(json['seededStoresCount']),
      populatedStoresCount: _toIntOrZero(json['populatedStoresCount']),
      offerCount: _toIntOrZero(json['offerCount']),
      latestPublishedTs: _toDate(json['latestPublishedTs']),
      oldestPublishedTs: _toDate(json['oldestPublishedTs']),
      latestFetchedTs: _toDate(json['latestFetchedTs']),
      staleStoresCount: _toIntOrZero(json['staleStoresCount']),
      staleStores: _toList(json['staleStores'], StaleStore.fromJson),
      quarantinedRunsCount: _toIntOrZero(json['quarantinedRunsCount']),
      lastCompletedRunKey: _toStringOrNull(json['lastCompletedRunKey']),
      lastCompletedAt: _toDate(json['lastCompletedAt']),
    );
  }

  final String retailerSlug;
  final String retailerName;
  final int seededStoresCount;
  final int populatedStoresCount;
  final int offerCount;
  final DateTime? latestPublishedTs;
  final DateTime? oldestPublishedTs;
  final DateTime? latestFetchedTs;
  final int staleStoresCount;
  final List<StaleStore> staleStores;
  final int quarantinedRunsCount;
  final String? lastCompletedRunKey;
  final DateTime? lastCompletedAt;

  bool get hasStaleData => staleStoresCount > 0;
}

class FreshnessReport {
  const FreshnessReport({
    required this.status,
    this.checkedAt,
    required this.staleThresholdHours,
    required this.quarantineWindowDays,
    required this.totalOffers,
    required this.totalPopulatedStores,
    required this.totalStaleStores,
    required this.totalQuarantinedRuns,
    required this.retailers,
  });
  factory FreshnessReport.fromJson(Map<String, dynamic> json) {
    return FreshnessReport(
      status: _toStringOrNull(json['status']) ?? 'UNKNOWN',
      checkedAt: _toDate(json['checkedAt']),
      staleThresholdHours: _toIntOrZero(json['staleThresholdHours']),
      quarantineWindowDays: _toIntOrZero(json['quarantineWindowDays']),
      totalOffers: _toIntOrZero(json['totalOffers']),
      totalPopulatedStores: _toIntOrZero(json['totalPopulatedStores']),
      totalStaleStores: _toIntOrZero(json['totalStaleStores']),
      totalQuarantinedRuns: _toIntOrZero(json['totalQuarantinedRuns']),
      retailers: _toList(json['retailers'], RetailerFreshness.fromJson),
    );
  }

  final String status;
  final DateTime? checkedAt;
  final int staleThresholdHours;
  final int quarantineWindowDays;
  final int totalOffers;
  final int totalPopulatedStores;
  final int totalStaleStores;
  final int totalQuarantinedRuns;
  final List<RetailerFreshness> retailers;

  bool get isHealthy => status == 'UP' || status == 'OK' || status == 'HEALTHY';
  bool get hasStaleData => totalStaleStores > 0;
}

// ---------------------------------------------------------------------------
// Basket contracts (M4 deterministic optimizer)
// ---------------------------------------------------------------------------

/// Supported units, matching backend UnitConversionUtil.normalizeUnit.
const basketUnits = <String>['g', 'kg', 'ml', 'l', 'pcs', 'pack'];

class BasketItem {
  const BasketItem({
    required this.localId,
    required this.label,
    this.canonicalProductId,
    this.retailerProductId,
    required this.quantity,
    required this.unit,
  });

  factory BasketItem.fromJson(Map<String, dynamic> json) {
    return BasketItem(
      localId: _toStringOrNull(json['localId']) ?? '',
      label: _toStringOrNull(json['label']) ?? '',
      canonicalProductId: _toInt(json['canonicalProductId']),
      retailerProductId: _toInt(json['retailerProductId']),
      quantity: _toDoubleOrZero(json['quantity']),
      unit: _toStringOrNull(json['unit']) ?? 'pack',
    );
  }

  final String localId;
  final String label;
  final int? canonicalProductId;
  final int? retailerProductId;
  final double quantity;
  final String unit;

  BasketItem copyWith({double? quantity, String? unit}) => BasketItem(
        localId: localId,
        label: label,
        canonicalProductId: canonicalProductId,
        retailerProductId: retailerProductId,
        quantity: quantity ?? this.quantity,
        unit: unit ?? this.unit,
      );

  Map<String, dynamic> toJson() => {
        'localId': localId,
        'label': label,
        if (canonicalProductId != null) 'canonicalProductId': canonicalProductId,
        if (retailerProductId != null) 'retailerProductId': retailerProductId,
        'quantity': quantity,
        'unit': unit,
      };

  Map<String, dynamic> toRequestJson() => {
        if (canonicalProductId != null) 'canonicalProductId': canonicalProductId,
        if (retailerProductId != null) 'retailerProductId': retailerProductId,
        if (canonicalProductId == null && retailerProductId == null) 'itemLabel': label,
        'quantity': quantity,
        'unit': unit,
      };
}

class BasketOptimizeRequest {
  const BasketOptimizeRequest({
    required this.items,
    this.city,
    this.retailers,
    this.maxStores = 2,
    this.minSplitSavingsMkd = 0,
    this.allowSubstitutes = false,
    this.inStockOnly = true,
  });

  final List<BasketItem> items;
  final String? city;
  final List<String>? retailers;
  final int maxStores;
  final double minSplitSavingsMkd;
  final bool allowSubstitutes;
  final bool inStockOnly;

  Map<String, dynamic> toJson() => {
        'items': items.map((i) => i.toRequestJson()).toList(growable: false),
        if (city != null && city!.isNotEmpty) 'city': city,
        if (retailers != null && retailers!.isNotEmpty) 'retailers': retailers,
        'maxStores': maxStores,
        'minSplitSavingsMkd': minSplitSavingsMkd,
        'allowSubstitutes': allowSubstitutes,
        'inStockOnly': inStockOnly,
      };
}

class MissingBasketItem {
  const MissingBasketItem({
    required this.itemIndex,
    this.canonicalProductId,
    this.retailerProductId,
    required this.requestedName,
    this.requestedQuantity,
    this.requestedUnit,
    required this.reason,
  });

  factory MissingBasketItem.fromJson(Map<String, dynamic> json) {
    return MissingBasketItem(
      itemIndex: _toIntOrZero(json['itemIndex']),
      canonicalProductId: _toInt(json['canonicalProductId']),
      retailerProductId: _toInt(json['retailerProductId']),
      requestedName: _toStringOrNull(json['requestedName']) ?? '',
      requestedQuantity: _toDouble(json['requestedQuantity']),
      requestedUnit: _toStringOrNull(json['requestedUnit']),
      reason: _toStringOrNull(json['reason']) ?? 'unknown',
    );
  }

  final int itemIndex;
  final int? canonicalProductId;
  final int? retailerProductId;
  final String requestedName;
  final double? requestedQuantity;
  final String? requestedUnit;
  final String reason;
}

class CoveredBasketItem {
  const CoveredBasketItem({
    required this.itemIndex,
    this.canonicalProductId,
    this.requestedRetailerProductId,
    required this.requestedName,
    this.requestedQuantity,
    this.requestedUnit,
    required this.storeId,
    this.storeExternalKey,
    this.storeName,
    this.retailerSlug,
    this.matchedRetailerProductId,
    this.matchedListingName,
    this.normalizedSize,
    required this.packsNeeded,
    this.unitPackPriceMkd,
    required this.lineTotalMkd,
    this.isSubstitute = false,
    this.substituteReason,
    this.matchConfidence,
    this.publishedTs,
    this.fetchedTs,
    this.sourceUrl,
  });

  factory CoveredBasketItem.fromJson(Map<String, dynamic> json) {
    return CoveredBasketItem(
      itemIndex: _toIntOrZero(json['itemIndex']),
      canonicalProductId: _toInt(json['canonicalProductId']),
      requestedRetailerProductId: _toInt(json['requestedRetailerProductId']),
      requestedName: _toStringOrNull(json['requestedName']) ?? '',
      requestedQuantity: _toDouble(json['requestedQuantity']),
      requestedUnit: _toStringOrNull(json['requestedUnit']),
      storeId: _toIntOrZero(json['storeId']),
      storeExternalKey: _toStringOrNull(json['storeExternalKey']),
      storeName: _toStringOrNull(json['storeName']),
      retailerSlug: _toStringOrNull(json['retailerSlug']),
      matchedRetailerProductId: _toInt(json['matchedRetailerProductId']),
      matchedListingName: _toStringOrNull(json['matchedListingName']),
      normalizedSize: _toStringOrNull(json['normalizedSize']),
      packsNeeded: _toDoubleOrZero(json['packsNeeded']),
      unitPackPriceMkd: _toDouble(json['unitPackPriceMkd']),
      lineTotalMkd: _toDoubleOrZero(json['lineTotalMkd']),
      isSubstitute: _toBool(json['isSubstitute']),
      substituteReason: _toStringOrNull(json['substituteReason']),
      matchConfidence: _toDouble(json['matchConfidence']),
      publishedTs: _toDate(json['publishedTs']),
      fetchedTs: _toDate(json['fetchedTs']),
      sourceUrl: _toStringOrNull(json['sourceUrl']),
    );
  }

  final int itemIndex;
  final int? canonicalProductId;
  final int? requestedRetailerProductId;
  final String requestedName;
  final double? requestedQuantity;
  final String? requestedUnit;
  final int storeId;
  final String? storeExternalKey;
  final String? storeName;
  final String? retailerSlug;
  final int? matchedRetailerProductId;
  final String? matchedListingName;
  final String? normalizedSize;
  final double packsNeeded;
  final double? unitPackPriceMkd;
  final double lineTotalMkd;
  final bool isSubstitute;
  final String? substituteReason;
  final double? matchConfidence;
  final DateTime? publishedTs;
  final DateTime? fetchedTs;
  final String? sourceUrl;
}

class SingleStoreBasketResult {
  const SingleStoreBasketResult({
    required this.storeId,
    required this.retailerSlug,
    required this.retailerName,
    this.storeExternalKey,
    required this.storeName,
    this.city,
    required this.itemsCovered,
    required this.totalItemsRequested,
    required this.coverageRatio,
    required this.totalMkd,
    required this.savingsVsHighestCoveredSingleStoreMkd,
    required this.exactMatchesCount,
    required this.substitutesCount,
    required this.coveredItems,
    required this.missingItems,
  });

  factory SingleStoreBasketResult.fromJson(Map<String, dynamic> json) {
    return SingleStoreBasketResult(
      storeId: _toIntOrZero(json['storeId']),
      retailerSlug: _toStringOrNull(json['retailerSlug']) ?? '',
      retailerName: _toStringOrNull(json['retailerName']) ?? '',
      storeExternalKey: _toStringOrNull(json['storeExternalKey']),
      storeName: _toStringOrNull(json['storeName']) ?? '',
      city: _toStringOrNull(json['city']),
      itemsCovered: _toIntOrZero(json['itemsCovered']),
      totalItemsRequested: _toIntOrZero(json['totalItemsRequested']),
      coverageRatio: _toDoubleOrZero(json['coverageRatio']),
      totalMkd: _toDoubleOrZero(json['totalMkd']),
      savingsVsHighestCoveredSingleStoreMkd:
          _toDoubleOrZero(json['savingsVsHighestCoveredSingleStoreMkd']),
      exactMatchesCount: _toIntOrZero(json['exactMatchesCount']),
      substitutesCount: _toIntOrZero(json['substitutesCount']),
      coveredItems: _toList(json['coveredItems'], CoveredBasketItem.fromJson),
      missingItems: _toList(json['missingItems'], MissingBasketItem.fromJson),
    );
  }

  final int storeId;
  final String retailerSlug;
  final String retailerName;
  final String? storeExternalKey;
  final String storeName;
  final String? city;
  final int itemsCovered;
  final int totalItemsRequested;
  final double coverageRatio;
  final double totalMkd;
  final double savingsVsHighestCoveredSingleStoreMkd;
  final int exactMatchesCount;
  final int substitutesCount;
  final List<CoveredBasketItem> coveredItems;
  final List<MissingBasketItem> missingItems;
}

class StoreAllocation {
  const StoreAllocation({
    required this.storeId,
    required this.retailerSlug,
    required this.retailerName,
    this.storeExternalKey,
    required this.storeName,
    this.city,
    required this.subtotalMkd,
    required this.items,
  });

  factory StoreAllocation.fromJson(Map<String, dynamic> json) {
    return StoreAllocation(
      storeId: _toIntOrZero(json['storeId']),
      retailerSlug: _toStringOrNull(json['retailerSlug']) ?? '',
      retailerName: _toStringOrNull(json['retailerName']) ?? '',
      storeExternalKey: _toStringOrNull(json['storeExternalKey']),
      storeName: _toStringOrNull(json['storeName']) ?? '',
      city: _toStringOrNull(json['city']),
      subtotalMkd: _toDoubleOrZero(json['subtotalMkd']),
      items: _toList(json['items'], CoveredBasketItem.fromJson),
    );
  }

  final int storeId;
  final String retailerSlug;
  final String retailerName;
  final String? storeExternalKey;
  final String storeName;
  final String? city;
  final double subtotalMkd;
  final List<CoveredBasketItem> items;
}

class MultiStoreBasketPlan {
  const MultiStoreBasketPlan({
    required this.storesUsed,
    required this.itemsCovered,
    required this.totalItemsRequested,
    required this.coverageRatio,
    required this.totalMkd,
    required this.savingsVsBestSingleStoreMkd,
    required this.meetsMinSavingsThreshold,
    required this.recommendationReason,
    required this.storeAllocations,
    required this.missingItems,
  });

  factory MultiStoreBasketPlan.fromJson(Map<String, dynamic> json) {
    return MultiStoreBasketPlan(
      storesUsed: _toIntOrZero(json['storesUsed']),
      itemsCovered: _toIntOrZero(json['itemsCovered']),
      totalItemsRequested: _toIntOrZero(json['totalItemsRequested']),
      coverageRatio: _toDoubleOrZero(json['coverageRatio']),
      totalMkd: _toDoubleOrZero(json['totalMkd']),
      savingsVsBestSingleStoreMkd:
          _toDoubleOrZero(json['savingsVsBestSingleStoreMkd']),
      meetsMinSavingsThreshold: _toBool(json['meetsMinSavingsThreshold']),
      recommendationReason:
          _toStringOrNull(json['recommendationReason']) ?? 'unknown',
      storeAllocations: _toList(json['storeAllocations'], StoreAllocation.fromJson),
      missingItems: _toList(json['missingItems'], MissingBasketItem.fromJson),
    );
  }

  final int storesUsed;
  final int itemsCovered;
  final int totalItemsRequested;
  final double coverageRatio;
  final double totalMkd;
  final double savingsVsBestSingleStoreMkd;
  final bool meetsMinSavingsThreshold;
  final String recommendationReason;
  final List<StoreAllocation> storeAllocations;
  final List<MissingBasketItem> missingItems;
}

class BasketOptimization {
  const BasketOptimization({
    required this.totalItemsRequested,
    required this.allowSubstitutes,
    required this.inStockOnly,
    required this.maxStoresAllowed,
    required this.minSplitSavingsMkd,
    this.bestSingleStore,
    required this.singleStoreRankings,
    this.bestMultiStorePlan,
  });

  factory BasketOptimization.fromJson(Map<String, dynamic> json) {
    final bestSingle = json['bestSingleStore'];
    final bestMulti = json['bestMultiStorePlan'];
    return BasketOptimization(
      totalItemsRequested: _toIntOrZero(json['totalItemsRequested']),
      allowSubstitutes: _toBool(json['allowSubstitutes']),
      inStockOnly: _toBool(json['inStockOnly']),
      maxStoresAllowed: _toIntOrZero(json['maxStoresAllowed']),
      minSplitSavingsMkd: _toDoubleOrZero(json['minSplitSavingsMkd']),
      bestSingleStore: bestSingle is Map
          ? SingleStoreBasketResult.fromJson(_asMap(bestSingle))
          : null,
      singleStoreRankings:
          _toList(json['singleStoreRankings'], SingleStoreBasketResult.fromJson),
      bestMultiStorePlan: bestMulti is Map
          ? MultiStoreBasketPlan.fromJson(_asMap(bestMulti))
          : null,
    );
  }

  final int totalItemsRequested;
  final bool allowSubstitutes;
  final bool inStockOnly;
  final int maxStoresAllowed;
  final double minSplitSavingsMkd;
  final SingleStoreBasketResult? bestSingleStore;
  final List<SingleStoreBasketResult> singleStoreRankings;
  final MultiStoreBasketPlan? bestMultiStorePlan;
}
