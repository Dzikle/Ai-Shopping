import 'package:flutter/material.dart';

import '../l10n/app_localizations.dart';
import '../models/api_models.dart';
import '../theme/app_colors.dart';
import '../utils/formatters.dart';

/// Shows verified cross-retailer comparison data.
///
/// Only offers grouped by a verified canonical product (ADR-0003) are compared;
/// the widget never invents groupings and explicitly reports the source engine
/// and publication timestamps.
class CompareTile extends StatelessWidget {
  const CompareTile({
    super.key,
    required this.comparison,
    required this.retailerLabel,
    required this.onOpen,
  });

  final CanonicalComparison comparison;
  final String Function(String slug) retailerLabel;
  final VoidCallback onOpen;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final isDark = theme.brightness == Brightness.dark;
    final l = AppLocalizations.of(context);

    return Card(
      elevation: 1.5,
      shadowColor: Colors.black,
      margin: EdgeInsets.zero,
      color: isDark ? AppColors.darkSurface : Colors.white,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
      child: InkWell(
        borderRadius: BorderRadius.circular(12),
        onTap: onOpen,
        child: Padding(
          padding: const EdgeInsets.all(12),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Expanded(
                    child: Text(
                      comparison.canonicalName,
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                      style: TextStyle(
                        fontSize: 14,
                        fontWeight: FontWeight.w600,
                        color: theme.colorScheme.onSurface,
                        height: 1.25,
                      ),
                    ),
                  ),
                  const SizedBox(width: 8),
                  Container(
                    padding:
                        const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                    decoration: BoxDecoration(
                      color: AppColors.primaryOrange.withValues(alpha: 0.12),
                      borderRadius: BorderRadius.circular(10),
                    ),
                    child: Text(
                      l.t('compare_retailers', {
                        'count': comparison.retailerSlugs.length.toString(),
                      }),
                      style: const TextStyle(
                        fontSize: 10,
                        fontWeight: FontWeight.w600,
                        color: AppColors.primaryOrange,
                      ),
                    ),
                  ),
                ],
              ),
              if (comparison.normalizedSize != null) ...[
                const SizedBox(height: 3),
                Text(
                  comparison.normalizedSize!,
                  style: TextStyle(
                    fontSize: 12,
                    color: theme.colorScheme.onSurface.withValues(alpha: 0.6),
                  ),
                ),
              ],
              const SizedBox(height: 8),
              Text(
                l.t('compare_cheapest'),
                style: TextStyle(
                  fontSize: 11,
                  color: theme.colorScheme.onSurface.withValues(alpha: 0.55),
                ),
              ),
              Text(
                formatMkd(comparison.cheapestMkd),
                style: const TextStyle(
                  fontSize: 17,
                  fontWeight: FontWeight.w700,
                  color: AppColors.primaryOrange,
                ),
              ),
              if (comparison.highestMkd > comparison.cheapestMkd) ...[
                const SizedBox(height: 2),
                Text(
                  '${l.t('compare_highest')}: ${formatMkd(comparison.highestMkd)}',
                  style: TextStyle(
                    fontSize: 12,
                    color: theme.colorScheme.onSurface.withValues(alpha: 0.6),
                  ),
                ),
              ],
              const SizedBox(height: 6),
              Text(
                comparison.offers
                    .map((o) => retailerLabel(o.retailerSlug))
                    .toSet()
                    .join(' · '),
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: TextStyle(
                  fontSize: 12,
                  color: theme.colorScheme.onSurface.withValues(alpha: 0.65),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
