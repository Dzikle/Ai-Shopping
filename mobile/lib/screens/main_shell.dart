import 'package:flutter/material.dart';

import '../l10n/app_localizations.dart';
import '../theme/app_colors.dart';
import '../widgets/app_logo.dart';
import 'basket_screen.dart';
import 'compare_screen.dart';
import 'home_screen.dart';
import 'search_screen.dart';
import 'settings_screen.dart';

/// Bottom navigation shell: Home / Search / Compare / Basket / Settings.
class MainShell extends StatefulWidget {
  const MainShell({super.key});

  @override
  State<MainShell> createState() => _MainShellState();
}

class _MainShellState extends State<MainShell> {
  int _index = 0;

  @override
  Widget build(BuildContext context) {
    final l = AppLocalizations.of(context);
    final isDark = Theme.of(context).brightness == Brightness.dark;

    final screens = [
      const HomeScreen(),
      const SearchScreen(),
      const CompareScreen(),
      const BasketScreen(),
      const SettingsScreen(),
    ];

    return Scaffold(
      appBar: AppBar(
        automaticallyImplyLeading: false,
        title: Row(
          children: [
            const AppLogo(size: 26),
            const SizedBox(width: 8),
            Text(
              l.t('app_name'),
              style: TextStyle(
                fontSize: 17,
                fontWeight: FontWeight.w700,
                color: isDark ? AppColors.primaryOrange : AppColors.darkBlue,
              ),
            ),
          ],
        ),
        bottom: PreferredSize(
          preferredSize: const Size.fromHeight(1),
          child: Divider(
            height: 1,
            color: isDark ? AppColors.darkBorder : AppColors.lightBorder,
          ),
        ),
      ),
      body: IndexedStack(index: _index, children: screens),
      bottomNavigationBar: BottomNavigationBar(
        type: BottomNavigationBarType.fixed,
        currentIndex: _index,
        onTap: (i) => setState(() => _index = i),
        items: [
          BottomNavigationBarItem(
            icon: const Icon(Icons.home_outlined),
            activeIcon: const Icon(Icons.home),
            label: l.t('nav_home'),
          ),
          BottomNavigationBarItem(
            icon: const Icon(Icons.search_outlined),
            activeIcon: const Icon(Icons.search),
            label: l.t('nav_search'),
          ),
          BottomNavigationBarItem(
            icon: const Icon(Icons.compare_arrows_outlined),
            activeIcon: const Icon(Icons.compare_arrows),
            label: l.t('compare_title'),
          ),
          BottomNavigationBarItem(
            icon: const Icon(Icons.shopping_basket_outlined),
            activeIcon: const Icon(Icons.shopping_basket),
            label: l.t('nav_basket'),
          ),
          BottomNavigationBarItem(
            icon: const Icon(Icons.settings_outlined),
            activeIcon: const Icon(Icons.settings),
            label: l.t('nav_settings'),
          ),
        ],
      ),
    );
  }
}
