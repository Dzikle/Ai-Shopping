import 'dart:async';

import 'package:flutter/material.dart';

import '../l10n/app_localizations.dart';
import '../models/api_models.dart';
import '../services/api_service.dart';
import '../providers/app_state.dart';
import '../theme/app_colors.dart';
import '../utils/formatters.dart';
import '../widgets/error_view.dart';
import '../widgets/offer_card.dart';
import 'shopping_basket.dart';

/// Search tab with debounced query, filters and load-more pagination.
class SearchScreen extends StatefulWidget {
  const SearchScreen({super.key});

  @override
  State<SearchScreen> createState() => _SearchScreenState();
}

class _SearchScreenState extends State<SearchScreen> {
  static const _pageSize = 20;

  final _searchController = TextEditingController();
  final _searchFocus = FocusNode();
  Timer? _debounce;

  String _sort = 'price_asc';
  bool _inStockOnly = false;
  bool _promoOnly = false;
  String? _retailer;

  SearchPage<Offer>? _results;
  bool _loading = false;
  bool _loadingMore = false;
  bool _fromCache = false;
  DateTime? _cachedAt;
  String? _error;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) => _load());
  }

  @override
  void dispose() {
    _debounce?.cancel();
    _searchController.dispose();
    _searchFocus.dispose();
    super.dispose();
  }

  void _onQueryChanged(String value) {
    _debounce?.cancel();
    _debounce =
        Timer(const Duration(milliseconds: 400), () => _load());
  }

  Future<void> _load({bool loadMore = false}) async {
    if (!mounted) return;
    final page = loadMore ? (_results?.total != null ? (_results!.page + 1) : 0) : 0;
    if (loadMore) {
      setState(() => _loadingMore = true);
    } else {
      setState(() => _loading = true);
    }
    try {
      final api = AppScope.of(context).api;
      final result = await api.searchOffers(
        query: _searchController.text.trim(),
        retailer: _retailer,
        inStockOnly: _inStockOnly,
        promoOnly: _promoOnly,
        sort: _sort,
        page: page,
        size: _pageSize,
      );
      if (!mounted) return;
      setState(() {
        _results = loadMore && _results != null
            ? SearchPage<Offer>(
                sourceEngine: result.data.sourceEngine,
                total: result.data.total,
                page: page,
                size: result.data.size,
                items: [..._results!.items, ...result.data.items],
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

  bool get _hasLoadedOnce => _results != null || _error != null;
  bool get _queryIsEmpty => _searchController.text.trim().isEmpty;

  @override
  Widget build(BuildContext context) {
    final l = AppLocalizations.of(context);
    final theme = Theme.of(context);
    final isDark = theme.brightness == Brightness.dark;

    final hasQuery = !_queryIsEmpty;

    return RefreshIndicator(
      onRefresh: () => _load(),
      child: CustomScrollView(
        physics: const AlwaysScrollableScrollPhysics(),
        slivers: [
          SliverToBoxAdapter(
            child: Padding(
              padding: const EdgeInsets.fromLTRB(16, 12, 16, 8),
              child: TextField(
                controller: _searchController,
                focusNode: _searchFocus,
                onChanged: _onQueryChanged,
                textInputAction: TextInputAction.search,
                onSubmitted: (_) => _load(),
                decoration: InputDecoration(
                  hintText: l.t('search_hint'),
                  prefixIcon: const Icon(Icons.search),
                  suffixIcon: _queryIsEmpty
                      ? null
                      : IconButton(
                          icon: const Icon(Icons.clear),
                          onPressed: () {
                            _searchController.clear();
                            _load();
                          },
                        ),
                ),
              ),
            ),
          ),
          if (hasQuery &&
              _results?.queryUsed != null &&
              _results!.queryUsed!.isNotEmpty &&
              _results!.queryUsed != _searchController.text.trim())
            SliverToBoxAdapter(
              child: Padding(
                padding: const EdgeInsets.fromLTRB(16, 0, 16, 4),
                child: Text(
                  '${l.t('search_latin_note')} (${_results!.queryUsed})',
                  style: TextStyle(
                    fontSize: 11,
                    color: theme.colorScheme.onSurface.withValues(alpha: 0.55),
                  ),
                ),
              ),
            ),
          SliverToBoxAdapter(
            child: Padding(
              padding: const EdgeInsets.fromLTRB(16, 4, 16, 0),
              child: Row(
                children: [
                  Expanded(
                    child: SingleChildScrollView(
                      scrollDirection: Axis.horizontal,
                      child: Row(
                        children: [
                          FilterChip(
                            label: Text(l.t('search_in_stock_only')),
                            selected: _inStockOnly,
                            onSelected: (v) {
                              setState(() => _inStockOnly = v);
                              _load();
                            },
                          ),
                          const SizedBox(width: 8),
                          FilterChip(
                            label: Text(l.t('search_promo_only')),
                            selected: _promoOnly,
                            onSelected: (v) {
                              setState(() => _promoOnly = v);
                              _load();
                            },
                          ),
                        ],
                      ),
                    ),
                  ),
                  const SizedBox(width: 8),
                  DropdownButtonHideUnderline(
                    child: DropdownButton<String>(
                      value: _sort,
                      items: [
                        DropdownMenuItem(
                          value: 'price_asc',
                          child: Text(l.t('search_sort_price_asc'),
                              style: const TextStyle(fontSize: 12)),
                        ),
                        DropdownMenuItem(
                          value: 'price_desc',
                          child: Text(l.t('search_sort_price_desc'),
                              style: const TextStyle(fontSize: 12)),
                        ),
                      ],
                      onChanged: (value) {
                        setState(() => _sort = value ?? 'price_asc');
                        _load();
                      },
                    ),
                  ),
                ],
              ),
            ),
          ),
          SliverToBoxAdapter(child: const SizedBox(height: 8)),
          if (_fromCache && _cachedAt != null)
            SliverToBoxAdapter(
              child: Padding(
                padding: const EdgeInsets.fromLTRB(16, 0, 16, 6),
                child: Text(
                  '${l.t('common_offline_banner')} ${l.t('common_cached_at', {'ts': formatDateTime(_cachedAt!)})}',
                  style: TextStyle(
                    fontSize: 11,
                    color: isDark
                        ? AppColors.darkSecondary
                        : AppColors.lightSecondary,
                  ),
                ),
              ),
            ),
          if (_error != null && _results == null)
            SliverFillRemaining(
              hasScrollBody: false,
              child: ErrorView(
                message: l.t(_error!),
                onRetry: () => _load(),
              ),
            )
          else if (!hasQuery && !_hasLoadedOnce)
            SliverFillRemaining(
              hasScrollBody: false,
              child: _IdlePrompt(),
            )
          else if (_loading)
            const SliverFillRemaining(
              hasScrollBody: false,
              child: Center(child: CircularProgressIndicator()),
            )
          else if (_results == null || _results!.items.isEmpty)
            SliverFillRemaining(
              hasScrollBody: false,
              child: _NoResults(query: _results?.queryUsed ?? _searchController.text.trim()),
            )
          else ...[
            SliverPadding(
              padding: const EdgeInsets.symmetric(horizontal: 16),
              sliver: SliverList.separated(
                itemCount: _results!.items.length,
                separatorBuilder: (_, _) => const SizedBox(height: 10),
                itemBuilder: (context, index) {
                  final offer = _results!.items[index];
                  return OfferCard(
                    offer: offer,
                    onTap: () => showAddToBasketSheet(
                      context,
                      label: offer.hasVerifiedIdentity
                          ? (offer.canonicalName ?? offer.listingName)
                          : offer.listingName,
                      canonicalProductId: offer.canonicalProductId,
                    ),
                    trailing: IconButton(
                      tooltip: l.t('offer_add_to_basket'),
                      icon: const Icon(Icons.add_shopping_cart,
                          size: 20, color: AppColors.primaryOrange),
                      onPressed: () => showAddToBasketSheet(
                        context,
                        label: offer.hasVerifiedIdentity
                            ? (offer.canonicalName ?? offer.listingName)
                            : offer.listingName,
                        canonicalProductId: offer.canonicalProductId,
                      ),
                    ),
                  );
                },
              ),
            ),
            if (_results!.hasMore)
              SliverToBoxAdapter(
                child: Padding(
                  padding: const EdgeInsets.symmetric(vertical: 16),
                  child: Center(
                    child: _loadingMore
                        ? const CircularProgressIndicator()
                        : OutlinedButton(
                            onPressed: () => _load(loadMore: true),
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

class _IdlePrompt extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    final l = AppLocalizations.of(context);
    final theme = Theme.of(context);
    return Center(
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 40),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Icon(Icons.search, size: 56, color: AppColors.lightSecondary),
            const SizedBox(height: 12),
            Text(
              l.t('search_empty_title'),
              style: TextStyle(
                fontSize: 16,
                fontWeight: FontWeight.w700,
                color: theme.colorScheme.onSurface,
              ),
            ),
            const SizedBox(height: 6),
            Text(
              l.t('search_empty_body'),
              textAlign: TextAlign.center,
              style: TextStyle(
                fontSize: 13,
                color: theme.colorScheme.onSurface.withValues(alpha: 0.65),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _NoResults extends StatelessWidget {
  const _NoResults({required this.query});

  final String query;

  @override
  Widget build(BuildContext context) {
    final l = AppLocalizations.of(context);
    final theme = Theme.of(context);
    return Center(
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 36),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Icon(Icons.search_off,
                size: 56, color: AppColors.lightSecondary),
            const SizedBox(height: 12),
            Text(
              l.t('search_no_results_title'),
              style: TextStyle(
                fontSize: 16,
                fontWeight: FontWeight.w700,
                color: theme.colorScheme.onSurface,
              ),
            ),
            const SizedBox(height: 6),
            Text(
              l.t('search_no_results_body', {'query': query}),
              textAlign: TextAlign.center,
              style: TextStyle(
                fontSize: 13,
                color: theme.colorScheme.onSurface.withValues(alpha: 0.65),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
