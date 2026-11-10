import 'package:flutter/material.dart';

import '../theme/app_colors.dart';

/// Neutral product placeholder.
///
/// The catalog API has no product image URLs; the app must never invent them,
/// so every product uses this non-photographic placeholder.
class ProductPlaceholder extends StatelessWidget {
  const ProductPlaceholder({super.key, this.size = 56});

  final double size;

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    return Container(
      width: size,
      height: size,
      decoration: BoxDecoration(
        color: isDark ? AppColors.darkSurface : AppColors.lightSurface,
        borderRadius: BorderRadius.circular(10),
        border: Border.all(
          color: isDark ? AppColors.darkBorder : AppColors.lightBorder,
        ),
      ),
      child: Icon(
        Icons.shopping_basket_outlined,
        size: size * 0.45,
        color: isDark ? AppColors.darkSecondary : AppColors.lightSecondary,
      ),
    );
  }
}
