import 'package:flutter/material.dart';

import '../l10n/app_localizations.dart';
import '../models/api_models.dart';
import '../services/api_service.dart';
import '../providers/app_state.dart';
import '../theme/app_colors.dart';
import '../utils/formatters.dart';
import '../widgets/compare_tile.dart';
import '../widgets/error_view.dart';
import 'comparison_detail_screen.dart';

/// Compare tab: verified cross-retailer product matches.
class CompareScreen extends StatefulWidget {
  const CompareScreen({super.key});

  @override
  State<CompareScreen> createState() => _CompareScreenState();
}

class _CompareScreenState extends State<CompareScreen> {
  final _searchController = TextEditingController();
  SearchPage<CanonicalComparison>? _page;
  bool _loading = false;
  String? _error;
  bool _fromCache = false;
  DateTime? _cachedAt;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) => _load());
  }

  @override
  void dispose() {
    _searchController.dispose();
    super.dispose();
  }

  Future<void> _load({String? query}) async {
    if (!mounted) return;
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final api = AppScope.of(context).api;
      final result = await api.compareProducts(query: query, size: 25);
      if (!mounted) return;
      setState(() {
        _page = result.data;
        _loading = false;
        _fromCache = result.fromCache;
        _cachedAt = result.cachedAt;
      });
    } on ApiServiceException catch (error) {
      if (!mounted) return;
      setState(() {
        _loading = false;
        _error = _errorKey(error);
      });
    }
  }

  String _errorKey(ApiServiceException error) {
    switch (error.kind) {
      case ApiServiceErrorKind.network:
        return 'error_network';
      case ApiServiceErrorKind.notFound:
        return 'error_not_found';
      case ApiServiceErrorKind.server:
        return 'error_server';
    }
  }

  void _openDetail(CanonicalComparison comparison) {
    Navigator.of(context).push(
      MaterialPageRoute<void>(
        builder: (_) =>
            ComparisonDetailScreen(comparisonId: comparison.canonicalProductId),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final l = AppLocalizations.of(context);
    final theme = Theme.of(context);
    final isDark = theme.brightness == Brightness.dark;

    final showEmptyState =
        !_loading && _error == null && (_page == null || _page!.items.isEmpty);
    final showResults = !_loading && _error == null && _page != null;

    return RefreshIndicator(
      onRefresh: () => _load(query: _searchController.text.trim()),
      child: CustomScrollView(
        physics: const AlwaysScrollableScrollPhysics(),
        slivers: [
          SliverToBoxAdapter(
            child: Padding(
              padding: const EdgeInsets.fromLTRB(16, 16, 16, 4),
              child: Text(
                l.t('compare_title'),
                style: TextStyle(
                  fontSize: 22,
                  fontWeight: FontWeight.w700,
                  color: isDark ? AppColors.darkText : AppColors.darkBlue,
                ),
              ),
            ),
          ),
          SliverToBoxAdapter(
            child: Padding(
              padding: const EdgeInsets.fromLTRB(16, 0, 16, 8),
              child: Text(
                l.t('compare_subtitle'),
                style: TextStyle(
                  fontSize: 13,
                  color: theme.colorScheme.onSurface.withValues(alpha: 0.6),
                ),
              ),
            ),
          ),
          SliverToBoxAdapter(
            child: Padding(
              padding: const EdgeInsets.fromLTRB(16, 4, 16, 8),
              child: TextField(
                controller: _searchController,
                textInputAction: TextInputAction.search,
                onSubmitted: (value) => _load(query: value.trim()),
                decoration: InputDecoration(
                  prefixIcon: const Icon(Icons.compare_arrows_outlined, size: 20),
                  suffixIcon: _searchController.text.isEmpty
                      ? null
                      : IconButton(
                          icon: const Icon(Icons.clear, size: 18),
                          onPressed: () {
                            _searchController.clear();
                            _load();
                          },
                        ),
                  hintText: l.t('compare_search_hint'),
                ),
              ),
            ),
          ),
          if (_fromCache && _cachedAt != null)
            SliverToBoxAdapter(child: _OfflineBanner(cachedAt: _cachedAt!)),
          if (_error != null)
            SliverFillRemaining(
              hasScrollBody: false,
              child: ErrorView(
                message: l.t(_error!),
                onRetry: () => _load(query: _searchController.text.trim()),
              ),
            )
          else if (_loading)
            const SliverFillRemaining(
              hasScrollBody: false,
              child: Center(child: CircularProgressIndicator()),
            )
          else if (showEmptyState)
            SliverFillRemaining(
              hasScrollBody: false,
              child: _CompareEmptyState(queryUsed: _page?.queryUsed),
            )
          else if (showResults)
            SliverPadding(
              padding: const EdgeInsets.fromLTRB(16, 8, 16, 24),
              sliver: SliverList.separated(
                itemCount: _page!.items.length,
                separatorBuilder: (_, _) => const SizedBox(height: 10),
                itemBuilder: (context, index) {
                  final comparison = _page!.items[index];
                  return CompareTile(
                    comparison: comparison,
                    retailerLabel: (slug) => slug,
                    onOpen: () => _openDetail(comparison),
                  );
                },
              ),
            ),
          SliverToBoxAdapter(
            child: Padding(
              padding: const EdgeInsets.fromLTRB(16, 0, 16, 24),
              child: Text(
                l.t('compare_verified_note'),
                style: TextStyle(
                  fontSize: 11,
                  color: theme.colorScheme.onSurface.withValues(alpha: 0.5),
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _OfflineBanner extends StatelessWidget {
  const _OfflineBanner({required this.cachedAt});

  final DateTime cachedAt;

  @override
  Widget build(BuildContext context) {
    final l = AppLocalizations.of(context);
    final isDark = Theme.of(context).brightness == Brightness.dark;
    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 0, 16, 8),
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
        decoration: BoxDecoration(
          color: isDark ? AppColors.badgeBgDark : AppColors.badgeBgLight,
          borderRadius: BorderRadius.circular(8),
        ),
        child: Text(
          '${l.t('common_offline_banner')} ${l.t('common_cached_at', {'ts': formatDateTime(cachedAt)})}',
          style: TextStyle(
            fontSize: 12,
            color: isDark ? AppColors.darkText : AppColors.darkBlue,
          ),
        ),
      ),
    );
  }
}

class _CompareEmptyState extends StatelessWidget {
  const _CompareEmptyState({this.queryUsed});

  final String? queryUsed;

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
              Icons.rule,
              size: 56,
              color: AppColors.lightSecondary,
            ),
            const SizedBox(height: 12),
            Text(
              l.t('compare_empty_title'),
              style: TextStyle(
                fontSize: 16,
                fontWeight: FontWeight.w700,
                color: theme.colorScheme.onSurface,
              ),
            ),
            const SizedBox(height: 6),
            Text(
              queryUsed == null || queryUsed!.isEmpty
                  ? l.t('compare_empty_body')
                  : l.t('search_no_results_body', {'query': queryUsed!}),
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
