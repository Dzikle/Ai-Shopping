import 'package:flutter/material.dart';

import '../l10n/app_localizations.dart';
import '../models/api_models.dart';
import '../services/api_service.dart';
import '../providers/app_state.dart';
import '../theme/app_colors.dart';
import '../utils/formatters.dart';
import '../widgets/error_view.dart';
import 'basket_options.dart';
import 'basket_results.dart';
import 'shopping_basket.dart';

/// Basket tab: local editing + server-side deterministic optimization.
class BasketScreen extends StatefulWidget {
  const BasketScreen({super.key});

  @override
  State<BasketScreen> createState() => _BasketScreenState();
}

class _BasketScreenState extends State<BasketScreen> {
  final _cityController = TextEditingController();
  bool _allowSubstitutes = false;
  bool _inStockOnly = true;
  int _maxStores = 2;
  double _minSplitSavings = 0;

  BasketOptimization? _result;
  bool _optimizing = false;
  String? _error;

  @override
  void dispose() {
    _cityController.dispose();
    super.dispose();
  }

  Future<void> _optimize() async {
    final state = AppScope.stateOf(context);
    if (state.basketIsEmpty) return;
    setState(() {
      _optimizing = true;
      _error = null;
    });
    try {
      final api = AppScope.of(context).api;
      final result = await api.optimizeBasket(BasketOptimizeRequest(
        items: state.basketItems,
        city: _cityController.text.trim().isEmpty
            ? null
            : _cityController.text.trim(),
        maxStores: _maxStores,
        minSplitSavingsMkd: _minSplitSavings,
        allowSubstitutes: _allowSubstitutes,
        inStockOnly: _inStockOnly,
      ));
      if (!mounted) return;
      setState(() {
        _result = result;
        _optimizing = false;
      });
    } on ApiServiceException {
      if (!mounted) return;
      setState(() {
        _optimizing = false;
        _error = 'basket_optimize_failed';
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final l = AppLocalizations.of(context);
    final theme = Theme.of(context);
    final isDark = theme.brightness == Brightness.dark;
    final state = AppScope.stateOf(context);

    if (state.basketIsEmpty) {
      return _EmptyBasket();
    }

    return ListenableBuilder(
      listenable: state,
      builder: (context, _) => RefreshIndicator(
        onRefresh: _optimize,
        child: ListView(
          physics: const AlwaysScrollableScrollPhysics(),
          padding: const EdgeInsets.all(16),
          children: [
            Row(
              children: [
                Expanded(
                  child: Text(
                    l.t('basket_title'),
                    style: TextStyle(
                      fontSize: 20,
                      fontWeight: FontWeight.w700,
                      color: isDark ? AppColors.darkText : AppColors.darkBlue,
                    ),
                  ),
                ),
                IconButton(
                  tooltip: l.t('basket_clear'),
                  icon: const Icon(Icons.delete_outline),
                  onPressed: () async {
                    final confirmed = await showDialog<bool>(
                      context: context,
                      builder: (dialogContext) => AlertDialog(
                        title: Text(l.t('basket_clear')),
                        content: Text(l.t('basket_clear_confirm')),
                        actions: [
                          TextButton(
                            onPressed: () => Navigator.pop(dialogContext, false),
                            child: Text(l.t('common_cancel')),
                          ),
                          TextButton(
                            onPressed: () => Navigator.pop(dialogContext, true),
                            child: Text(l.t('common_yes')),
                          ),
                        ],
                      ),
                    );
                    if (confirmed == true && mounted) {
                      await state.clearBasket();
                    }
                  },
                ),
              ],
            ),
            Text(
              l.t('basket_items_count', {'count': state.basketCount.toString()}),
              style: TextStyle(
                fontSize: 13,
                color: theme.colorScheme.onSurface.withValues(alpha: 0.6),
              ),
            ),
            const SizedBox(height: 12),
            ...state.basketItems.map(
              (item) => Card(
                margin: const EdgeInsets.only(bottom: 8),
                elevation: 1,
                color: isDark ? AppColors.darkSurface : Colors.white,
                shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(10),
                ),
                child: Padding(
                  padding: const EdgeInsets.symmetric(
                      horizontal: 12, vertical: 10),
                  child: Row(
                    children: [
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(
                              item.label,
                              maxLines: 2,
                              overflow: TextOverflow.ellipsis,
                              style: TextStyle(
                                fontSize: 13,
                                fontWeight: FontWeight.w600,
                                color: theme.colorScheme.onSurface,
                              ),
                            ),
                            const SizedBox(height: 2),
                            Text(
                              '${formatQuantity(item.quantity)} ${l.unit(item.unit)}',
                              style: TextStyle(
                                fontSize: 12,
                                color: theme.colorScheme.onSurface
                                    .withValues(alpha: 0.65),
                              ),
                            ),
                          ],
                        ),
                      ),
                      IconButton(
                        tooltip: l.t('basket_edit_item'),
                        icon: const Icon(Icons.edit_outlined, size: 18),
                        onPressed: () => showAddToBasketSheet(
                          context,
                          label: item.label,
                          canonicalProductId: item.canonicalProductId,
                          sourceUnit: item.unit,
                        ).then((_) {
                          // Replaced item handling: simplify by removing+adding
                        }),
                      ),
                      IconButton(
                        tooltip: l.t('basket_remove_item'),
                        icon: const Icon(Icons.close, size: 18),
                        onPressed: () => state.removeBasketItem(item.localId),
                      ),
                    ],
                  ),
                ),
              ),
            ),
            const SizedBox(height: 8),
            BasketOptionsCard(
              cityController: _cityController,
              allowSubstitutes: _allowSubstitutes,
              onAllowSubstitutes: (v) =>
                  setState(() => _allowSubstitutes = v),
              inStockOnly: _inStockOnly,
              onInStockOnly: (v) => setState(() => _inStockOnly = v),
              maxStores: _maxStores,
              onMaxStores: (v) => setState(() => _maxStores = v),
              minSplitSavings: _minSplitSavings,
              onMinSplitSavings: (v) => setState(() => _minSplitSavings = v),
            ),
            const SizedBox(height: 12),
            SizedBox(
              width: double.infinity,
              child: FilledButton.icon(
                onPressed: _optimizing ? null : _optimize,
                icon: _optimizing
                    ? const SizedBox(
                        width: 18,
                        height: 18,
                        child: CircularProgressIndicator(strokeWidth: 2),
                      )
                    : const Icon(Icons.calculate_outlined),
                label: Text(
                  _optimizing
                      ? l.t('basket_optimizing')
                      : l.t('basket_optimize'),
                ),
              ),
            ),
            if (_error != null) ...[
              const SizedBox(height: 8),
              ErrorView(
                message: l.t(_error!),
                onRetry: _optimize,
              ),
            ],
            if (_result != null) ...[
              const SizedBox(height: 16),
              BasketOptimizationResults(result: _result!),
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
      ),
    );
  }
}

class _EmptyBasket extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    final l = AppLocalizations.of(context);
    final theme = Theme.of(context);
    return Center(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          const Icon(
            Icons.shopping_basket_outlined,
            size: 64,
            color: AppColors.lightSecondary,
          ),
          const SizedBox(height: 12),
          Text(
            l.t('basket_empty_title'),
            style: TextStyle(
              fontSize: 16,
              fontWeight: FontWeight.w700,
              color: theme.colorScheme.onSurface,
            ),
          ),
          const SizedBox(height: 6),
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 40),
            child: Text(
              l.t('basket_empty_body'),
              textAlign: TextAlign.center,
              style: TextStyle(
                fontSize: 13,
                color: theme.colorScheme.onSurface.withValues(alpha: 0.65),
              ),
            ),
          ),
          const SizedBox(height: 16),
          FilledButton(
            onPressed: () {},
            child: Text(l.t('basket_empty_cta')),
          ),
        ],
      ),
    );
  }
}
