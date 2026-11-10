import 'package:flutter/material.dart';

import '../l10n/app_localizations.dart';
import '../providers/app_state.dart';

/// Settings tab: language, theme, about/disclaimer. No auth, no accounts.
class SettingsScreen extends StatelessWidget {
  const SettingsScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final l = AppLocalizations.of(context);
    final theme = Theme.of(context);
    final state = AppScope.stateOf(context);

    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        _SectionHeader(l.t('app_name')),
        ListTile(
          leading: const Icon(Icons.language),
          title: Text(l.t('settings_language')),
          trailing: DropdownButton<Locale>(
            value: state.locale,
            items: [
              DropdownMenuItem(
                value: const Locale('mk'),
                child: Text(l.t('settings_language_mk')),
              ),
              DropdownMenuItem(
                value: const Locale('en'),
                child: Text(l.t('settings_language_en')),
              ),
            ],
            onChanged: (locale) {
              if (locale != null) state.setLocale(locale);
            },
          ),
        ),
        ListTile(
          leading: const Icon(Icons.brightness_6_outlined),
          title: Text(l.t('settings_theme')),
          trailing: SegmentedButton<ThemeMode>(
            segments: [
              ButtonSegment(
                value: ThemeMode.system,
                icon: const Icon(Icons.settings_suggest_outlined, size: 16),
              ),
              ButtonSegment(
                value: ThemeMode.light,
                icon: const Icon(Icons.light_mode_outlined, size: 16),
              ),
              ButtonSegment(
                value: ThemeMode.dark,
                icon: const Icon(Icons.dark_mode_outlined, size: 16),
              ),
            ],
            selected: {state.themeMode},
            onSelectionChanged: (mode) => state.setThemeMode(mode.first),
          ),
        ),
        const SizedBox(height: 8),
        _SectionHeader(l.t('settings_about')),
        ListTile(
          leading: const Icon(Icons.info_outline),
          title: Text(l.t('app_name')),
          subtitle: Text(l.t('settings_guest_body')),
        ),
        ListTile(
          leading: const Icon(Icons.gavel_outlined),
          title: Text(l.t('settings_attribution')),
          subtitle: Text(l.t('settings_attribution_body')),
        ),
        ListTile(
          leading: const Icon(Icons.warning_amber_outlined),
          title: Text(l.t('settings_disclaimer_title')),
          subtitle: Text(l.t('settings_disclaimer_body')),
        ),
        const SizedBox(height: 8),
        Padding(
          padding: const EdgeInsets.all(8),
          child: Text(
            l.t('settings_version') + ': 1.0.0+1',
            style: TextStyle(
              fontSize: 12,
              color: theme.colorScheme.onSurface.withValues(alpha: 0.6),
            ),
          ),
        ),
      ],
    );
  }
}

class _SectionHeader extends StatelessWidget {
  const _SectionHeader(this.title);

  final String title;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(8, 8, 8, 4),
      child: Text(
        title.toUpperCase(),
        style: TextStyle(
          fontSize: 11,
          fontWeight: FontWeight.w700,
          color: Theme.of(context).colorScheme.onSurface.withValues(alpha: 0.5),
        ),
      ),
    );
  }
}
