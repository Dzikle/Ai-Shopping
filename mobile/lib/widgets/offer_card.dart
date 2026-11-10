import 'package:flutter/material.dart';

import '../models/api_models.dart';
import '../theme/app_colors.dart';
import '../utils/formatters.dart';
import 'product_placeholder.dart';

/// Offer card used on Home, Search and comparison add-to-basket flows.
class OfferCard extends StatelessWidget {
  const OfferCard({
    super.key,
    required this.offer,
    required this.onTap,
    this.trailing,
    this.dense = false,
  });

  final Offer offer;
  final VoidCallback onTap;

  /// Optional trailing widget (e.g. add-to-basket button).
  final Widget? trailing;

  final bool dense;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final isDark = theme.brightness == Brightness.dark;

    return Card(
      elevation: 1.5,
      shadowColor: Colors.black,
      color: isDark ? AppColors.darkSurface : Colors.white,
      margin: EdgeInsets.zero,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
      child: InkWell(
        borderRadius: BorderRadius.circular(12),
        onTap: onTap,
        child: Padding(
          padding: const EdgeInsets.all(12),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const ProductPlaceholder(size: 64),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      offer.listingName,
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                      style: TextStyle(
                        fontSize: 14,
                        fontWeight: FontWeight.w600,
                        color: theme.colorScheme.onSurface,
                        height: 1.25,
                      ),
                    ),
                    const SizedBox(height: 4),
                    Row(
                      children: [
                        Flexible(
                          child: Text(
                            [
                              if (offer.retailerName != null &&
                                  offer.retailerName!.isNotEmpty)
                                offer.retailerName!,
                              if (offer.storeName != null &&
                                  offer.storeName!.isNotEmpty &&
                                  offer.storeName != offer.retailerName)
                                offer.storeName!,
                            ].join(' · '),
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                            style: TextStyle(
                              fontSize: 12,
                              color: theme.colorScheme.onSurface
                                  .withValues(alpha: 0.65),
                            ),
                          ),
                        ),
                        if (offer.hasVerifiedIdentity) ...[
                          const SizedBox(width: 6),
                          const _VerifiedBadge(compact: true),
                        ],
                      ],
                    ),
                    const SizedBox(height: 6),
                    Row(
                      crossAxisAlignment: CrossAxisAlignment.baseline,
                      textBaseline: TextBaseline.alphabetic,
                      children: [
                        Text(
                          formatMkd(offer.priceCurrent),
                          style: const TextStyle(
                            fontSize: 16,
                            fontWeight: FontWeight.w700,
                            color: AppColors.primaryOrange,
                          ),
                        ),
                        if ((offer.regularPrice ?? offer.priceCurrent) >
                            offer.priceCurrent + 0.001) ...[
                          const SizedBox(width: 8),
                          Text(
                            formatMkd(offer.regularPrice ?? offer.priceCurrent),
                            style: TextStyle(
                              fontSize: 12,
                              color: theme.colorScheme.onSurface
                                  .withValues(alpha: 0.5),
                              decoration: TextDecoration.lineThrough,
                            ),
                          ),
                        ],
                        if (offer.discountPct != null) ...[
                          const SizedBox(width: 8),
                          _DiscountBadge(pct: offer.discountPct!),
                        ],
                      ],
                    ),
                    if (!dense && offer.isAvailabilityUnknown) ...[
                      const SizedBox(height: 4),
                      Text(
                        '•',
                        style: TextStyle(
                          fontSize: 11,
                          color:
                              theme.colorScheme.onSurface.withValues(alpha: 0.45),
                        ),
                      ),
                    ],
                  ],
                ),
              ),
              if (trailing != null) ...[
                const SizedBox(width: 8),
                trailing!,
              ],
            ],
          ),
        ),
      ),
    );
  }
}

class _DiscountBadge extends StatelessWidget {
  const _DiscountBadge({required this.pct});

  final double pct;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
      decoration: BoxDecoration(
        color: AppColors.primaryOrange,
        borderRadius: BorderRadius.circular(10),
      ),
      child: Text(
        '-${formatNumber(pct, decimals: 0)}%',
        style: const TextStyle(
          fontSize: 10,
          fontWeight: FontWeight.w700,
          color: Colors.white,
        ),
      ),
    );
  }
}

/// Small green check used to mark offers linked to a verified canonical product.
class _VerifiedBadge extends StatelessWidget {
  const _VerifiedBadge({required this.compact});

  final bool compact;

  @override
  Widget build(BuildContext context) {
    return Tooltip(
      message: compact ? '✓' : null,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 5, vertical: 1),
        decoration: BoxDecoration(
          color: const Color(0xFFE7F3EC),
          borderRadius: BorderRadius.circular(8),
        ),
        child: const Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(Icons.verified_outlined, size: 12, color: Color(0xFF1E7C4A)),
          ],
        ),
      ),
    );
  }
}
