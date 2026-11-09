import 'package:flutter/material.dart';

import '../l10n/app_localizations.dart';
import '../models/api_models.dart';
import '../providers/app_state.dart';
import '../services/api_service.dart';
import '../theme/app_colors.dart';
import '../utils/formatters.dart';
import '../widgets/offer_card.dart';
import '../widgets/error_view.dart';
import 'comparison_detail_screen.dart';

/// Home screen: freshness banner, promo offers, latest offers, retailer chips.
class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key});

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  static const _pageSize = 25;

  String? _selectedRetailer;
  bool _promoOnly = false;

  SearchPage<Offer>? _offers;
  FreshnessReport? _freshness;
  List<Store> _stores = const [];
  List<String> _retailers = const [];

  bool _loading = true;
  bool _loadingMore = false;
  bool _fromCache = false;
  DateTime? _cachedAt;
  String? _error;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) => _bootstrap());
  }

  Future<void> _bootstrap() async {
    if (!mounted) return;
    setState(() => _loading = true);
    final api = AppScope.of(context).api;
    try {
      final storesResult = await api.fetchStores();
      if (!mounted) return;
      final retailers = storesResult.data
          .map((s) => s.retailerSlug)
          .toSet()
          .toList()
        ..sort();
      setState(() {
        _stores = storesResult.data;
        _retailers = retailers;
        _fromCache = storesResult.fromCache;
        _cachedAt = storesResult.cachedAt;
      });
    } on ApiServiceException {
      // Freshness and offers render their own error states.
    }
    await _loadOffers();
    await _loadFreshness();
  }

  Future<void> _loadOffers({bool loadMore = false}) async {
    if (!mounted) return;
    final page = loadMore ? (_offers?.page ?? 0) + 1 : 0;
    if (loadMore) {
      setState(() => _loadingMore = true);
    } else {
      setState(() => _loading = true);
    }
    try {
      final api = AppScope.of(context).api;
      final result = await api.searchOffers(
        retailer: _selectedRetailer,
        promoOnly: _promoOnly,
        page: page,
        size: _pageSize,
      );
      if (!mounted) return;
      setState(() {
        _offers = loadMore && _offers != null
            ? SearchPage<Offer>(
                sourceEngine: result.data.sourceEngine,
                total: result.data.total,
                page: page,
                size: result.data.size,
                items: [..._offers!.items, ...result.data.items],
              )
            : result.data;
        _loading = false;
        _loadingMore = false;
        _error = null;
        _fromCache = result.fromCache;
        _cachedAt = result.cachedAt;
      });
    } on ApiServiceException catch (error) {
      if (!mounted) return;
      setState(() {
        _loading = false;
        _loadingMore = false;
        _error = switch (error.kind) {
          ApiServiceErrorKind.network => 'error_network',
          ApiServiceErrorKind.notFound => 'error_not_found',
          ApiServiceErrorKind.server => 'error_server',
        };
      });
    }
  }

  Future<void> _loadFreshness() async {
    try {
      final api = AppScope.of(context).api;
      final result = await api.fetchFreshness();
      if (!mounted) return;
      setState(() => _freshness = result.data);
    } on ApiServiceException {
      if (!mounted) return;
      setState(() => _freshness = null);
    }
  }

  Future<void> _openOffer(Offer offer) async {
    if (offer.canonicalProductId == null) {
      // Without verified identity we cannot show comparison; show details only.
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(
        content: Text(AppLocalizations.of(context)
            .t('offer_missing_canonical')),
      ));
      return;
    }
    await Navigator.of(context).push(
      MaterialPageRoute<void>(
        builder: (_) => ComparisonDetailScreen(
          comparisonId: offer.canonicalProductId!,
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final l = AppLocalizations.of(context);
    final theme = Theme.of(context);
    final isDark = theme.brightness == Brightness.dark;

    return RefreshIndicator(
      onRefresh: () => _bootstrap(),
      child: CustomScrollView(
        physics: const AlwaysScrollableScrollPhysics(),
        slivers: [
          const SliverToBoxAdapter(child: SizedBox(height: 8)),
          if (_freshness != null)
            SliverToBoxAdapter(
              child: _FreshnessCard(report: _freshness!),
            ),
          SliverToBoxAdapter(
            child: Padding(
              padding: const EdgeInsets.fromLTRB(16, 12, 16, 4),
              child: Text(
                l.t('home_browse_retailers'),
                style: TextStyle(
                  fontSize: 15,
                  fontWeight: FontWeight.w700,
                  color: isDark ? AppColors.darkText : AppColors.darkBlue,
                ),
              ),
            ),
          ),
          SliverToBoxAdapter(
            child: SizedBox(
              height: 40,
              child: ListView.separated(
                scrollDirection: Axis.horizontal,
                padding: const EdgeInsets.symmetric(horizontal: 16),
                itemCount: _retailers.length + 1,
                separatorBuilder: (_, _) => const SizedBox(width: 8),
                itemBuilder: (context, index) {
                  if (index == 0) {
                    return _RetailerChip(
                      label: l.t('common_all'),
                      selected: _selectedRetailer == null,
                      onTap: () {
                        setState(() {
                          _selectedRetailer = null;
                          _offers = null;
                        });
                        _loadOffers();
                      },
                    );
                  }
                  final slug = _retailers[index - 1];
                  final storeCount = _stores
                      .where((s) => s.retailerSlug == slug)
                      .length;
                  return _RetailerChip(
                    label: storeCount > 0
                        ? '$slug (${l.t('home_retailer_stores', {'count': storeCount.toString()})})'
                        : slug,
                    selected: _selectedRetailer == slug,
                    onTap: () {
                      setState(() {
                        _selectedRetailer = _selectedRetailer == slug ? null : slug;
                        _offers = null;
                      });
                      _loadOffers();
                    },
                  );
                },
              ),
            ),
          ),
          SliverToBoxAdapter(
            child: Padding(
              padding: const EdgeInsets.fromLTRB(16, 8, 16, 8),
              child: Row(
                children: [
                  Expanded(
                    child: Text(
                      _promoOnly
                          ? l.t('home_promotions')
                          : l.t('home_latest_offers'),
                      style: TextStyle(
                        fontSize: 15,
                        fontWeight: FontWeight.w700,
                        color: isDark ? AppColors.darkText : AppColors.darkBlue,
                      ),
                    ),
                  ),
                  FilterChip(
                    label: Text(l.t('home_filters_title') + ': ' + l.t('home_promotions')),
                    selected: _promoOnly,
                    onSelected: (value) {
                      setState(() {
                        _promoOnly = value;
                        _offers = null;
                      });
                      _loadOffers();
                    },
                  ),
                ],
              ),
            ),
          ),
          if (_fromCache && _cachedAt != null)
            SliverToBoxAdapter(child: _OfflineNotice(cachedAt: _cachedAt!)),
          if (_error != null && _offers == null)
            SliverFillRemaining(
              hasScrollBody: false,
              child: ErrorView(
                message: l.t(_error!),
                onRetry: () {
                  _loadOffers();
                  _loadFreshness();
                },
              ),
            )
          else if (_loading)
            const SliverFillRemaining(
              hasScrollBody: false,
              child: Center(child: CircularProgressIndicator()),
            )
          else if (_offers == null || _offers!.items.isEmpty)
            SliverFillRemaining(
              hasScrollBody: false,
              child: _EmptyOffers(promoOnly: _promoOnly),
            )
          else ...[
            SliverPadding(
              padding: const EdgeInsets.symmetric(horizontal: 16),
              sliver: SliverList.separated(
                itemCount: _offers!.items.length,
                separatorBuilder: (_, _) => const SizedBox(height: 10),
                itemBuilder: (context, index) {
                  final offer = _offers!.items[index];
                  return OfferCard(
                    offer: offer,
                    onTap: () => _openOffer(offer),
                  );
                },
              ),
            ),
            if (_offers != null && _offers!.hasMore)
              SliverToBoxAdapter(
                child: Padding(
                  padding: const EdgeInsets.symmetric(vertical: 16),
                  child: Center(
                    child: _loadingMore
                        ? const CircularProgressIndicator()
                        : OutlinedButton(
                            onPressed: () => _loadOffers(loadMore: true),
                            child: Text(l.t('search_load_more')),
                          ),
                  ),
                ),
              ),
          ],
          const SliverToBoxAdapter(child: SizedBox(height: 24)),
        ],
      ),
    );
  }
}

class _RetailerChip extends StatelessWidget {
  const _RetailerChip({
    required this.label,
    required this.selected,
    required this.onTap,
  });

  final String label;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 4),
      child: GestureDetector(
        onTap: onTap,
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 7),
          decoration: BoxDecoration(
            color: selected
                ? AppColors.primaryOrange
                : isDark
                    ? AppColors.darkSurface
                    : AppColors.lightSurface,
            borderRadius: BorderRadius.circular(16),
            border: Border.all(
              color: selected
                  ? AppColors.primaryOrange
                  : isDark
                      ? AppColors.darkBorder
                      : AppColors.lightBorder,
            ),
          ),
          child: Text(
            label,
            style: TextStyle(
              fontSize: 12,
              fontWeight: FontWeight.w600,
              color: selected
                  ? Colors.white
                  : isDark
                      ? AppColors.darkText
                      : AppColors.darkBlue,
            ),
          ),
        ),
      ),
    );
  }
}

class _FreshnessCard extends StatelessWidget {
  const _FreshnessCard({required this.report});

  final FreshnessReport report;

  @override
  Widget build(BuildContext context) {
    final l = AppLocalizations.of(context);
    final theme = Theme.of(context);
    final isDark = theme.brightness == Brightness.dark;
    final statusColor = switch (report.status.toUpperCase()) {
      'UP' || 'OK' || 'HEALTHY' => const Color(0xFF1E7C4A),
      'DEGRADED' => AppColors.primaryOrange,
      _ => const Color(0xFFB3261E),
    };

    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 16),
      child: Container(
        padding: const EdgeInsets.all(12),
        decoration: BoxDecoration(
          color: isDark ? AppColors.darkSurface : AppColors.lightSurface,
          borderRadius: BorderRadius.circular(10),
          border: Border.all(
            color: isDark ? AppColors.darkBorder : AppColors.lightBorder,
          ),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Icon(
                  report.hasStaleData
                      ? Icons.schedule
                      : Icons.verified_outlined,
                  size: 18,
                  color: statusColor,
                ),
                const SizedBox(width: 8),
                Expanded(
                  child: Text(
                    l.freshnessStatus(report.status),
                    style: TextStyle(
                      fontSize: 13,
                      fontWeight: FontWeight.w700,
                      color: isDark ? AppColors.darkText : AppColors.darkBlue,
                    ),
                  ),
                ),
                Text(
                  l.t('home_freshness_checked', {
                    'ts': formatDateTime(report.checkedAt),
                  }),
                  style: TextStyle(
                    fontSize: 11,
                    color: theme.colorScheme.onSurface.withValues(alpha: 0.6),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 6),
            Text(
              '${l.t('home_freshness_offers', {'count': report.totalOffers.toString()})} · '
              '${l.t('home_freshness_stores', {'count': report.totalPopulatedStores.toString()})} · '
              '${l.t('home_freshness_stale', {'count': report.totalStaleStores.toString()})}',
              style: TextStyle(
                fontSize: 12,
                color: theme.colorScheme.onSurface.withValues(alpha: 0.7),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _OfflineNotice extends StatelessWidget {
  const _OfflineNotice({required this.cachedAt});

  final DateTime cachedAt;

  @override
  Widget build(BuildContext context) {
    final l = AppLocalizations.of(context);
    final isDark = Theme.of(context).brightness == Brightness.dark;
    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 4, 16, 4),
      child: Text(
        '${l.t('common_offline_banner')} '
        '${l.t('common_cached_at', {'ts': formatDateTime(cachedAt)})}',
        style: TextStyle(
          fontSize: 11,
          color: isDark ? AppColors.darkSecondary : AppColors.lightSecondary,
        ),
      ),
    );
  }
}

class _EmptyOffers extends StatelessWidget {
  const _EmptyOffers({required this.promoOnly});

  final bool promoOnly;

  @override
  Widget build(BuildContext context) {
    final l = AppLocalizations.of(context);
    final theme = Theme.of(context);
    return Center(
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 32),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Icon(
              Icons.shopping_basket_outlined,
              size: 48,
              color: AppColors.lightSecondary,
            ),
            const SizedBox(height: 12),
            Text(
              promoOnly ? l.t('home_promotions_empty') : l.t('home_offers_empty'),
              textAlign: TextAlign.center,
              style: TextStyle(
                fontSize: 14,
                color: theme.colorScheme.onSurface.withValues(alpha: 0.7),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
