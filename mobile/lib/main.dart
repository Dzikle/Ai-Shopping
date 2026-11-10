import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'l10n/app_localizations.dart';
import 'providers/app_state.dart';
import 'screens/main_shell.dart';
import 'services/api_client.dart';
import 'services/api_service.dart';
import 'services/assistant_api.dart';
import 'services/response_cache.dart';
import 'theme/app_colors.dart';
import 'theme/app_theme.dart';

/// Placeholder app icon shown until owner-approved branding exists.
class AiShoppingLogo extends StatelessWidget {
  const AiShoppingLogo({super.key, this.size = 28});

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

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  runApp(const AiShoppingRoot());
}

/// Bootstrap widget: resolves SharedPreferences before showing the app.
///
/// Kept as a widget (instead of async work in [main]) so widget and
/// integration tests can pump the real app graph unchanged.
class AiShoppingRoot extends StatefulWidget {
  const AiShoppingRoot({super.key});

  @override
  State<AiShoppingRoot> createState() => _AiShoppingRootState();
}

class _AiShoppingRootState extends State<AiShoppingRoot> {
  late final Future<SharedPreferences> _prefs = SharedPreferences.getInstance();
  late final ShoppingApi _api = _buildApi();
  // Dedicated transport for /api/v1/assistant/turn (same guest base URL).
  late final AssistantApi _assistantApi = HttpAssistantApi(service: ApiService());

  @override
  Widget build(BuildContext context) {
    return FutureBuilder<SharedPreferences>(
      future: _prefs,
      builder: (context, snapshot) {
        if (!snapshot.hasData) {
          return const MaterialApp(home: SizedBox.shrink());
        }
        return AppScope(
          state: AppState(snapshot.data!),
          api: _api,
          assistantApi: _assistantApi,
          child: const AiShoppingApp(),
        );
      },
    );
  }
}

/// Builds the production read-only API client.
///
/// The base URL can be overridden per build without code changes:
/// `flutter run --dart-define=API_BASE_URL=http://192.168.x.x:8000`
ShoppingApi _buildApi() {
  final service = ApiService();
  return HttpShoppingApi(
    service: service,
    cache: ResponseCacheFactory.forService(() => service.baseUrl),
  );
}

class AiShoppingApp extends StatelessWidget {
  const AiShoppingApp({super.key});

  @override
  Widget build(BuildContext context) {
    final appState = AppScope.stateOf(context);
    return MaterialApp(
      onGenerateTitle: (context) => AppLocalizations.of(context).t('app_name'),
      debugShowCheckedModeBanner: false,
      theme: AppTheme.light,
      darkTheme: AppTheme.dark,
      themeMode: appState.themeMode,
      locale: appState.locale,
      supportedLocales: AppLocalizations.supportedLocales,
      localizationsDelegates: const [
        AppLocalizations.delegate,
        GlobalMaterialLocalizations.delegate,
        GlobalWidgetsLocalizations.delegate,
        GlobalCupertinoLocalizations.delegate,
      ],
      home: const MainShell(),
    );
  }
}
