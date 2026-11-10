import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';

import '../l10n/app_localizations.dart';
import '../models/api_models.dart';
import '../services/api_service.dart';
import '../providers/app_state.dart';
import '../theme/app_colors.dart';
import '../utils/formatters.dart';
import 'product_detail_screen.dart';

/// Detail screen for a verified canonical product: offers per retailer plus
/// (optionally) price history.
class ComparisonDetailScreen extends StatefulWidget {
  const ComparisonDetailScreen({super.key, required this.comparisonId});

  final int comparisonId;

  @override
  State<ComparisonDetailScreen> createState() => _ComparisonDetailScreenState();
}

class _ComparisonDetailScreenState extends State<ComparisonDetailScreen> {
  CanonicalComparison? _comparison;
  ProductHistory? _history;
  bool _loading = true;
  String? _error;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) => _load());
  }

  Future<void> _load() async {
    if (!mounted) return;
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final api = AppScope.of(context).api;
      final pages = await api.compareProducts(size: 100, page: 0);
      final match = pages.data.items
          .where((c) => c.canonicalProductId == widget.comparisonId)
          .firstOrNull;
      if (!mounted) return;
      if (match == null) {
        setState(() {
          _loading = false;
          _error = 'compare_error';
        });
        return;
      }
      ProductHistory? history;
      try {
        final historyResult = await api.fetchHistory(widget.comparisonId);
        history = historyResult.data;
      } on ApiServiceException {
        history = null;
      }
      if (!mounted) return;
      setState(() {
        _comparison = match;
        _history = history;
        _loading = false;
      });
    } on ApiServiceException catch (error) {
      if (!mounted) return;
      setState(() {
        _loading = false;
        _error = switch (error.kind) {
          ApiServiceErrorKind.network => 'error_network',
          ApiServiceErrorKind.notFound => 'error_not_found',
          ApiServiceErrorKind.server => 'error_server',
        };
      });
    }
  }

  Future<void> _addOfferToBasket(ComparisonOffer offer) async {
    final state = AppScope.stateOf(context);
    await state.addBasketItem(BasketItem(
      localId: AppState.newLocalId(),
      label: offer.listingName,
      canonicalProductId: widget.comparisonId,
      quantity: 1,
      unit: 'pack',
    ));
    if (!mounted) return;
    final l = AppLocalizations.of(context);
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text(l.t('offer_added_to_basket'))),
    );
  }

  @override
  Widget build(BuildContext context) {
    final l = AppLocalizations.of(context);
    final theme = Theme.of(context);
    final isDark = theme.brightness == Brightness.dark;

    if (_loading) {
      return Scaffold(
        appBar: AppBar(title: Text(l.t('compare_loading'))),
        body: const Center(child: CircularProgressIndicator()),
      );
    }
    if (_error != null || _comparison == null) {
      return Scaffold(
        appBar: AppBar(title: Text(l.t('compare_detail_title'))),
        body: Center(
          child: Text(l.t(_error ?? 'compare_error')),
        ),
      );
    }

    final comparison = _comparison!;
    final historyObservations = _history?.newestFirst ?? const <PriceObservation>[];

    return Scaffold(
      appBar: AppBar(
        title: Text(
          l.t('compare_detail_title'),
          style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w700),
        ),
      ),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          Container(
            padding: const EdgeInsets.all(12),
            decoration: BoxDecoration(
              color: isDark ? AppColors.badgeBgDark : AppColors.badgeBgLight,
              borderRadius: BorderRadius.circular(10),
            ),
            child: Row(
              children: [
                const Icon(Icons.verified_outlined,
                    size: 18, color: Color(0xFF1E7C4A)),
                const SizedBox(width: 8),
                Expanded(
                  child: Text(
                    l.t('compare_verified_note'),
                    style: TextStyle(
                      fontSize: 12,
                      color: isDark ? AppColors.darkText : AppColors.darkBlue,
                    ),
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(height: 12),
          Text(
            comparison.canonicalName,
            style: TextStyle(
              fontSize: 20,
              fontWeight: FontWeight.w700,
              color: isDark ? AppColors.darkText : AppColors.darkBlue,
            ),
          ),
          if (comparison.normalizedSize != null) ...[
            const SizedBox(height: 4),
            Text(
              comparison.normalizedSize!,
              style: TextStyle(
                fontSize: 13,
                color: theme.colorScheme.onSurface.withValues(alpha: 0.65),
              ),
            ),
          ],
          const SizedBox(height: 12),
          Row(
            children: [
              _MetricBox(
                label: l.t('compare_cheapest'),
                value: formatMkd(comparison.cheapestMkd),
              ),
              const SizedBox(width: 10),
              _MetricBox(
                label: l.t('compare_highest'),
                value: formatMkd(comparison.highestMkd),
              ),
              const SizedBox(width: 10),
              _MetricBox(
                label: l.t('compare_spread'),
                value: formatMkd(comparison.spreadMkd),
              ),
            ],
          ),
          const SizedBox(height: 8),
          Text(
            l.t('detail_published', {
              'ts': formatDateTime(comparison.latestPublishedTs),
            }),
            style: TextStyle(
              fontSize: 12,
              color: theme.colorScheme.onSurface.withValues(alpha: 0.6),
            ),
          ),
          const SizedBox(height: 16),
          Text(
            l.t('compare_offers_title'),
            style: TextStyle(
              fontSize: 15,
              fontWeight: FontWeight.w700,
              color: isDark ? AppColors.darkText : AppColors.darkBlue,
            ),
          ),          const SizedBox(height: 8),
          ...comparison.offers.map(
            (offer) => Card(
              margin: const EdgeInsets.only(bottom: 8),
              elevation: 1,
              color: isDark ? AppColors.darkSurface : Colors.white,
              shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(10),
              ),
              child: Padding(
                padding: const EdgeInsets.all(12),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        Expanded(
                          child: Text(
                            '${offer.retailerSlug} · ${offer.listingName}',
                            style: TextStyle(
                              fontSize: 13,
                              fontWeight: FontWeight.w600,
                              color: theme.colorScheme.onSurface,
                            ),
                          ),
                        ),
                        Text(
                          formatMkd(offer.minPrice),
                          style: const TextStyle(
                            fontSize: 15,
                            fontWeight: FontWeight.w700,
                            color: AppColors.primaryOrange,
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: 4),
                    Text(
                      '${l.t('offer_store')}: ${l.t('compare_stores', {
                            'count': offer.storeCount.toString(),
                          })} · ${l.t('common_published')}: ${formatDateTime(offer.latestPublishedTs)}',
                      style: TextStyle(
                        fontSize: 11,
                        color:
                            theme.colorScheme.onSurface.withValues(alpha: 0.6),
                      ),
                    ),
                    const SizedBox(height: 8),
                    Row(
                      children: [
                        TextButton.icon(
                          onPressed: () => _addOfferToBasket(offer),
                          icon: const Icon(Icons.add_shopping_cart, size: 16),
                          label: Text(l.t('compare_add_offer')),
                        ),
                        const SizedBox(width: 8),
                        if (offer.sourceUrl != null)
                          TextButton.icon(
                            onPressed: () async {
                              final messenger = ScaffoldMessenger.of(context);
                              final uri = Uri.tryParse(offer.sourceUrl!);
                              if (uri == null || !await launchUrl(uri)) {
                                messenger.showSnackBar(SnackBar(
                                  content: Text(l.t('offer_source_error')),
                                ));
                              }
                            },
                            icon: const Icon(Icons.open_in_new, size: 16),
                            label: Text(l.t('offer_source')),
                          ),
                      ],
                    ),
                  ],
                ),
              ),
            ),
          ),
          const SizedBox(height: 12),
          Text(
            l.t('compare_history_title'),
            style: TextStyle(
              fontSize: 15,
              fontWeight: FontWeight.w700,
              color: isDark ? AppColors.darkText : AppColors.darkBlue,
            ),
          ),
          const SizedBox(height: 4),
          if (historyObservations.isEmpty)
            Padding(
              padding: const EdgeInsets.symmetric(vertical: 8),
              child: Text(
                l.t('compare_history_empty'),
                style: TextStyle(
                  fontSize: 13,
                  color: theme.colorScheme.onSurface.withValues(alpha: 0.65),
                ),
              ),
            )
          else ...[
            ...historyObservations.take(20).map(
                  (obs) => ListTile(
                    contentPadding: EdgeInsets.zero,
                    dense: true,
                    title: Text(
                      '${obs.retailerSlug} · ${obs.storeName}',
                      style: TextStyle(
                        fontSize: 13,
                        color: theme.colorScheme.onSurface,
                      ),
                    ),
                    subtitle: Text(
                      l.t('common_published') +
                          ': ${formatDateTime(obs.publishedTs)}',
                      style: TextStyle(
                        fontSize: 11,
                        color:
                            theme.colorScheme.onSurface.withValues(alpha: 0.6),
                      ),
                    ),
                    trailing: Text(
                      formatMkd(obs.priceCurrent),
                      style: const TextStyle(
                        fontSize: 14,
                        fontWeight: FontWeight.w700,
                        color: AppColors.primaryOrange,
                      ),
                    ),
                  ),
                ),
            Padding(
              padding: const EdgeInsets.only(top: 4),
              child: Text(
                l.t('compare_history_note'),
                style: TextStyle(
                  fontSize: 11,
                  color: theme.colorScheme.onSurface.withValues(alpha: 0.5),
                ),
              ),
            ),
            const SizedBox(height: 8),
            Center(
              child: TextButton.icon(
                onPressed: () {
                  Navigator.of(context).push(
                    MaterialPageRoute<void>(
                      builder: (_) => ProductDetailScreen(
                        canonicalProductId: comparison.canonicalProductId,
                        title: comparison.canonicalName,
                      ),
                    ),
                  );
                },
                icon: const Icon(Icons.history, size: 16),
                label: Text(l.t('offer_view_history')),
              ),
            ),
          ],
          const SizedBox(height: 16),
          Text(
            l.t('basket_server_totals_note'),
            style: TextStyle(
              fontSize: 11,
              color: theme.colorScheme.onSurface.withValues(alpha: 0.5),
            ),
          ),
        ],
      ),
    );
  }
}

class _MetricBox extends StatelessWidget {
  const _MetricBox({required this.label, required this.value});

  final String label;
  final String value;
  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Expanded(
      child: Container(
        padding: const EdgeInsets.all(8),
        decoration: BoxDecoration(
          color: theme.brightness == Brightness.dark
              ? AppColors.darkSurface
              : AppColors.lightSurface,
          borderRadius: BorderRadius.circular(8),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              label,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: TextStyle(
                fontSize: 10,
                color: theme.colorScheme.onSurface.withValues(alpha: 0.6),
              ),
            ),
            const SizedBox(height: 2),
            FittedBox(
              fit: BoxFit.scaleDown,
              child: Text(
                value,
                style: const TextStyle(
                  fontSize: 14,
                  fontWeight: FontWeight.w700,
                  color: AppColors.primaryOrange,
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
