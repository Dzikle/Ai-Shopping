import 'package:flutter/material.dart';

import '../l10n/app_localizations.dart';

/// Options form preceeding the optimize button on the Basket screen.
class BasketOptionsCard extends StatelessWidget {
  const BasketOptionsCard({
    super.key,
    required this.cityController,
    required this.allowSubstitutes,
    required this.onAllowSubstitutes,
    required this.inStockOnly,
    required this.onInStockOnly,
    required this.maxStores,
    required this.onMaxStores,
    required this.minSplitSavings,
    required this.onMinSplitSavings,
  });

  final TextEditingController cityController;
  final bool allowSubstitutes;
  final ValueChanged<bool> onAllowSubstitutes;
  final bool inStockOnly;
  final ValueChanged<bool> onInStockOnly;
  final int maxStores;
  final ValueChanged<int> onMaxStores;
  final double minSplitSavings;
  final ValueChanged<double> onMinSplitSavings;

  @override
  Widget build(BuildContext context) {
    final l = AppLocalizations.of(context);
    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: Theme.of(context).colorScheme.surface.withValues(alpha: 0.4),
        borderRadius: BorderRadius.circular(10),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            l.t('basket_options_title'),
            style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w700),
          ),
          const SizedBox(height: 8),
          TextField(
            controller: cityController,
            decoration: InputDecoration(
              labelText: l.t('basket_city'),
              isDense: true,
            ),
          ),
          const SizedBox(height: 8),
          Row(
            children: [
              Expanded(child: Text(l.t('basket_max_stores'))),
              SegmentedButton<int>(
                segments: [1, 2, 3]
                    .map((v) => ButtonSegment(value: v, label: Text('$v')))
                    .toList(growable: false),
                selected: {maxStores},
                onSelectionChanged: (selection) =>
                    onMaxStores(selection.first),
              ),
            ],
          ),
          const SizedBox(height: 8),
          Row(
            children: [
              Expanded(
                child: Text(l.t('basket_in_stock_only')),
              ),
              Switch(value: inStockOnly, onChanged: onInStockOnly),
            ],
          ),
          Row(
            children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(l.t('basket_allow_substitutes')),
                    Text(
                      l.t('basket_allow_substitutes_note'),
                      style: TextStyle(
                        fontSize: 11,
                        color: Theme.of(context)
                            .colorScheme
                            .onSurface
                            .withValues(alpha: 0.6),
                      ),
                    ),
                  ],
                ),
              ),
              Switch(value: allowSubstitutes, onChanged: onAllowSubstitutes),
            ],
          ),
          const SizedBox(height: 4),
          TextFormField(
            initialValue: minSplitSavings.toString(),
            keyboardType:
                const TextInputType.numberWithOptions(decimal: true),
            decoration: InputDecoration(
              labelText: l.t('basket_min_split_savings'),
              isDense: true,
            ),
            onChanged: (value) {
              final parsed = double.tryParse(value.replaceFirst(',', '.'));
              if (parsed != null && parsed >= 0) onMinSplitSavings(parsed);
            },
          ),
          const SizedBox(height: 6),
          Text(
            l.t('basket_optimize_hint'),
            style: TextStyle(
              fontSize: 11,
              color: Theme.of(context)
                  .colorScheme
                  .onSurface
                  .withValues(alpha: 0.55),
            ),
          ),
        ],
      ),
    );
  }
}
