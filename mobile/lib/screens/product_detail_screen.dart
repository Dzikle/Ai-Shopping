import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';

import '../l10n/app_localizations.dart';
import '../models/api_models.dart';
import '../services/api_service.dart';
import '../providers/app_state.dart';
import '../theme/app_colors.dart';
import '../utils/formatters.dart';
import '../widgets/error_view.dart';
import '../widgets/product_placeholder.dart';

/// Offer detail: verified comparison (if canonical identity exists) plus raw
/// price observations without comparison (if not).
class ProductDetailScreen extends StatefulWidget {
  const ProductDetailScreen({
    super.key,
    required this.canonicalProductId,
    required this.title,
    this.heroOffer,
  });

  final int canonicalProductId;
  final String title;
  final Offer? heroOffer;

  @override
  State<ProductDetailScreen> createState() => _ProductDetailScreenState();
}

class _ProductDetailScreenState extends State<ProductDetailScreen> {
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
      final result = await api.fetchHistory(widget.canonicalProductId);
      if (!mounted) return;
      setState(() {
        _history = result.data;
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

  Future<void> _addToBasket() async {
    final offer = widget.heroOffer;
    final l = AppLocalizations.of(context);
    final state = AppScope.stateOf(context);
    await state.addBasketItem(BasketItem(
      localId: AppState.newLocalId(),
      label: offer?.listingName ?? widget.title,
      canonicalProductId: widget.canonicalProductId,
      quantity: 1,
      unit: 'pack',
    ));
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text(l.t('add_to_basket_added'))),
    );
  }

  @override
  Widget build(BuildContext context) {
    final l = AppLocalizations.of(context);
    final theme = Theme.of(context);
    final isDark = theme.brightness == Brightness.dark;
    final hero = widget.heroOffer;

    return Scaffold(
      appBar: AppBar(
        title: Text(
          l.t('offer_details_title'),
          style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w700),
        ),
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : _error != null
              ? ErrorView(
                  message: l.t(_error!),
                  onRetry: _load,
                )
              : RefreshIndicator(
                  onRefresh: _load,
                  child: ListView(
                    physics: const AlwaysScrollableScrollPhysics(),
                    padding: const EdgeInsets.all(16),
                    children: [
                      Center(
                        child: ProductPlaceholder(size: 130),
                      ),
                      const SizedBox(height: 12),
                      Text(
                        widget.title,
                        textAlign: TextAlign.center,
                        style: TextStyle(
                          fontSize: 18,
                          fontWeight: FontWeight.w700,
                          color: isDark ? AppColors.darkText : AppColors.darkBlue,
                        ),
                      ),
                      if (hero != null) ...[
                        const SizedBox(height: 4),
                        Center(
                          child: Text(
                            '${hero.retailerSlug} · ${hero.storeName ?? ''} · ${formatMkd(hero.priceCurrent)}',
                            style: TextStyle(
                              fontSize: 13,
                              color: theme.colorScheme.onSurface
                                  .withValues(alpha: 0.7),
                            ),
                          ),
                        ),
                      ],
                      const SizedBox(height: 12),
                      Center(
                        child: FilledButton.icon(
                          onPressed: _addToBasket,
                          icon: const Icon(Icons.add_shopping_cart, size: 18),
                          label: Text(l.t('offer_add_to_basket')),
                        ),
                      ),
                      const SizedBox(height: 20),
                      Text(
                        l.t('compare_history_title'),
                        style: TextStyle(
                          fontSize: 15,
                          fontWeight: FontWeight.w700,
                          color: isDark ? AppColors.darkText : AppColors.darkBlue,
                        ),
                      ),
                      const SizedBox(height: 4),
                      if (_history == null ||
                          _history!.observations.isEmpty)
                        Padding(
                          padding: const EdgeInsets.symmetric(vertical: 8),
                          child: Text(
                            l.t('compare_history_empty'),
                            style: TextStyle(
                              fontSize: 13,
                              color: theme.colorScheme.onSurface
                                  .withValues(alpha: 0.65),
                            ),
                          ),
                        )
                      else ...[
                        ..._history!.newestFirst.map(
                          (obs) => Card(
                            margin: const EdgeInsets.only(bottom: 8),
                            elevation: 1,
                            color: isDark
                                ? AppColors.darkSurface
                                : Colors.white,
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
                                          '${obs.retailerSlug} · ${obs.storeName}',
                                          style: TextStyle(
                                            fontSize: 13,
                                            fontWeight: FontWeight.w600,
                                            color: theme.colorScheme.onSurface,
                                          ),
                                        ),
                                      ),
                                      Text(
                                        formatMkd(obs.priceCurrent),
                                        style: const TextStyle(
                                          fontSize: 15,
                                          fontWeight: FontWeight.w700,
                                          color: AppColors.primaryOrange,
                                        ),
                                      ),
                                    ],
                                  ),
                                  const SizedBox(height: 4),
                                  Wrap(
                                    spacing: 12,
                                    runSpacing: 4,
                                    children: [
                                      Text(
                                        '${l.t('common_published')}: ${formatDateTime(obs.publishedTs)}',
                                        style: TextStyle(
                                          fontSize: 11,
                                          color: theme.colorScheme.onSurface
                                              .withValues(alpha: 0.6),
                                        ),
                                      ),
                                      if (obs.discountPct != null)
                                        Text(
                                          '${l.t('offer_discount_price')}: ${formatMkd(obs.discountPrice ?? obs.priceCurrent)} (-${formatNumber(obs.discountPct!, decimals: 0)}%)',
                                          style: TextStyle(
                                            fontSize: 11,
                                            color: theme.colorScheme.onSurface
                                                .withValues(alpha: 0.6),
                                          ),
                                        ),
                                      Text(
                                        l.availability(obs.availability),
                                        style: TextStyle(
                                          fontSize: 11,
                                          color: theme.colorScheme.onSurface
                                              .withValues(alpha: 0.6),
                                        ),
                                      ),
                                    ],
                                  ),
                                  if (obs.sourceUrl != null) ...[
                                    const SizedBox(height: 6),
                                    TextButton.icon(
                                      style: TextButton.styleFrom(
                                        visualDensity: VisualDensity.compact,
                                      ),
                                      onPressed: () async {
                                        final messenger =
                                            ScaffoldMessenger.of(context);
                                        final uri =
                                            Uri.tryParse(obs.sourceUrl!);
                                        if (uri == null ||
                                            !await launchUrl(uri,
                                                mode: LaunchMode
                                                    .externalApplication)) {
                                          messenger.showSnackBar(SnackBar(
                                            content: Text(
                                                l.t('offer_source_error')),
                                          ));
                                        }
                                      },
                                      icon: const Icon(Icons.open_in_new,
                                          size: 14),
                                      label: Text(
                                        l.t('offer_source'),
                                        style: const TextStyle(fontSize: 12),
                                      ),
                                    ),
                                  ],
                                ],
                              ),
                            ),
                          ),
                        ),
                        Padding(
                          padding: const EdgeInsets.symmetric(vertical: 6),
                          child: Text(
                            l.t('compare_history_note'),
                            style: TextStyle(
                              fontSize: 11,
                              color: theme.colorScheme.onSurface
                                  .withValues(alpha: 0.5),
                            ),
                          ),
                        ),
                      ],
                      const SizedBox(height: 8),
                      Text(
                        l.t('basket_server_totals_note'),
                        style: TextStyle(
                          fontSize: 11,
                          color:
                              theme.colorScheme.onSurface.withValues(alpha: 0.5),
                        ),
                      ),
                    ],
                  ),
                ),
    );
  }
}
