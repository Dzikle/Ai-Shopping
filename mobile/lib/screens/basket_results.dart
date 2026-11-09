import 'package:flutter/material.dart';

import '../l10n/app_localizations.dart';
import '../models/api_models.dart';
import '../theme/app_colors.dart';
import '../utils/formatters.dart';

/// Renders the server-computed optimization results (single-store + multi-store).
class BasketOptimizationResults extends StatelessWidget {
  const BasketOptimizationResults({super.key, required this.result});

  final BasketOptimization result;

  @override
  Widget build(BuildContext context) {
    final l = AppLocalizations.of(context);
    final theme = Theme.of(context);
    final isDark = theme.brightness == Brightness.dark;

    final best = result.bestSingleStore;
    final multi = result.bestMultiStorePlan;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          l.t('basket_results_title'),
          style: TextStyle(
            fontSize: 16,
            fontWeight: FontWeight.w700,
            color: isDark ? AppColors.darkText : AppColors.darkBlue,
          ),
        ),
        if (best != null) ...[
          const SizedBox(height: 8),
          _SectionCard(
            title: l.t('basket_best_single'),
            headline: '${l.t('basket_total')}: ${formatMkd(best.totalMkd)}',
            subtitle:
                '${best.storeName} (${best.retailerSlug}) · '
                '${l.t('basket_coverage_value', {
                  'covered': best.itemsCovered.toString(),
                  'total': best.totalItemsRequested.toString(),
                  'percent':
                      (best.coverageRatio * 100).round().toString(),
                })}',
            rows: [
              ...best.coveredItems.map((item) => _ResultRow(
                    leading: item.isSubstitute
                        ? l.t('basket_substitute')
                        : null,
                    title:
                        '${item.matchedListingName ?? item.requestedName} · ${item.storeName ?? ''}',
                    subtitle:
                        '${l.t('basket_packs_needed')}: ${formatNumber(item.packsNeeded, decimals: 0)} × ${formatMkd(item.unitPackPriceMkd ?? 0)} · ${l.t('basket_published')}: ${formatDateTime(item.publishedTs)}',
                    amount: formatMkd(item.lineTotalMkd),
                  )),
              ...best.missingItems.map((item) => _ResultRow(
                    leading: l.missingReason(item.reason),
                    title: item.requestedName,
                    subtitle: l.t('basket_missing_items'),
                    amount: '—',
                  )),
            ],
          ),
        ],
        if (result.singleStoreRankings.length > 1) ...[
          const SizedBox(height: 8),
          _SectionCard(
            title: l.t('basket_single_rankings'),
            headline: '',
            subtitle: '',
            rows: result.singleStoreRankings
                .take(6)
                .map((s) => _ResultRow(
                      title: '${s.storeName} (${s.retailerSlug})',
                      subtitle: l.t('basket_coverage_value', {
                        'covered': s.itemsCovered.toString(),
                        'total': s.totalItemsRequested.toString(),
                        'percent': (s.coverageRatio * 100).round().toString(),
                      }),
                      amount: formatMkd(s.totalMkd),
                    ))
                .toList(growable: false),
          ),
        ],
        if (multi != null) ...[
          const SizedBox(height: 8),
          _SectionCard(
            title: l.t('basket_multi_plan'),
            headline: '${l.t('basket_total')}: ${formatMkd(multi.totalMkd)}',
            subtitle:
                '${l.t('basket_stores_used')}: ${multi.storesUsed} · '
                '${l.t('basket_coverage_value', {
                  'covered': multi.itemsCovered.toString(),
                  'total': multi.totalItemsRequested.toString(),
                  'percent': (multi.coverageRatio * 100).round().toString(),
                })}',
            rows: [
              ...multi.storeAllocations.map(
                (a) => _ResultRow(
                  title: '${a.storeName} (${a.retailerSlug})',
                  subtitle: '${l.t('basket_subtotal')}: ${formatMkd(a.subtotalMkd)} · '
                      '${a.items.length} ${l.t('basket_items_covered')}',
                  amount: formatMkd(a.subtotalMkd),
                ),
              ),
              ...multi.missingItems.map(
                (item) => _ResultRow(
                  leading: l.missingReason(item.reason),
                  title: item.requestedName,
                  subtitle: l.t('basket_missing_items'),
                  amount: '—',
                ),
              ),
            ],
          ),
          const SizedBox(height: 6),
          Text(
            multi.storesUsed > 1
                ? (multi.meetsMinSavingsThreshold
                    ? l.t('basket_threshold_met')
                    : l.t('basket_threshold_not_met'))
                : l.t('basket_threshold_not_met'),
            style: TextStyle(
              fontSize: 11,
              color: theme.colorScheme.onSurface.withValues(alpha: 0.7),
            ),
          ),
        ],
        const SizedBox(height: 4),
        Text(
          l.t('basket_optimization_stale_note'),
          style: TextStyle(
            fontSize: 11,
            color: theme.colorScheme.onSurface.withValues(alpha: 0.5),
          ),
        ),
      ],
    );
  }
}

class _SectionCard extends StatelessWidget {
  const _SectionCard({
    required this.title,
    required this.headline,
    required this.subtitle,
    required this.rows,
  });

  final String title;
  final String headline;
  final String subtitle;
  final List<_ResultRow> rows;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final isDark = theme.brightness == Brightness.dark;
    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: isDark ? AppColors.darkSurface : Colors.white,
        borderRadius: BorderRadius.circular(10),
        border: Border.all(
          color: isDark ? AppColors.darkBorder : AppColors.lightBorder,
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(title,
              style: const TextStyle(
                  fontSize: 13, fontWeight: FontWeight.w700)),
          if (headline.isNotEmpty) ...[
            const SizedBox(height: 4),
            Text(
              headline,
              style: const TextStyle(
                fontSize: 16,
                fontWeight: FontWeight.w700,
                color: AppColors.primaryOrange,
              ),
            ),
          ],
          if (subtitle.isNotEmpty) ...[
            const SizedBox(height: 2),
            Text(
              subtitle,
              style: TextStyle(
                fontSize: 12,
                color: theme.colorScheme.onSurface.withValues(alpha: 0.65),
              ),
            ),
          ],
          const SizedBox(height: 8),
          ...rows.map((row) => Padding(
                padding: const EdgeInsets.symmetric(vertical: 4),
                child: row,
              )),
        ],
      ),
    );
  }
}

class _ResultRow extends StatelessWidget {
  const _ResultRow({
    required this.title,
    required this.subtitle,
    required this.amount,
    this.leading,
  });

  final String title;
  final String subtitle;
  final String amount;
  final String? leading;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Wrap(
                spacing: 6,
                runSpacing: 2,
                children: [
                  Text(
                    title,
                    style: TextStyle(
                      fontSize: 13,
                      color: theme.colorScheme.onSurface,
                    ),
                  ),
                  if (leading != null)
                    Container(
                      padding: const EdgeInsets.symmetric(
                          horizontal: 6, vertical: 1),
                      decoration: BoxDecoration(
                        color: AppColors.primaryOrange.withValues(alpha: 0.15),
                        borderRadius: BorderRadius.circular(8),
                      ),
                      child: Text(
                        leading!,
                        style: const TextStyle(
                          fontSize: 10,
                          color: AppColors.primaryOrange,
                          fontWeight: FontWeight.w600,
                        ),
                      ),
                    ),
                ],
              ),
              Text(
                subtitle,
                style: TextStyle(
                  fontSize: 11,
                  color: theme.colorScheme.onSurface.withValues(alpha: 0.6),
                ),
              ),
            ],
          ),
        ),
        const SizedBox(width: 8),
        Text(
          amount,
          style: const TextStyle(
            fontSize: 13,
            fontWeight: FontWeight.w700,
            color: AppColors.primaryOrange,
          ),
        ),
      ],
    );
  }
}
