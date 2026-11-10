import 'package:flutter/material.dart';

import '../theme/app_colors.dart';

/// Placeholder brand mark for AI Shopping until final branding is approved.
class AppLogo extends StatelessWidget {
  const AppLogo({super.key, this.size = 28});

  final double size;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: size,
      height: size,
      decoration: BoxDecoration(
        color: AppColors.primaryOrange,
        borderRadius: BorderRadius.circular(size * 0.28),
      ),
      child: Icon(
        Icons.shopping_basket_rounded,
        size: size * 0.6,
        color: Colors.white,
      ),
    );
  }
}
