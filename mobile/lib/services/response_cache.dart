import 'dart:convert';

import 'package:shared_preferences/shared_preferences.dart';

/// Small SharedPreferences-backed JSON response cache.
///
/// Used only to keep the app useful when the API is unreachable; every cached
/// payload is shown with an explicit offline banner and its cache timestamp.
abstract class KeyValueCache {
  Future<void> put(String key, Object? json);
  CachedResponse? read(String key);
  Future<void> clear();
}

class ResponseCache implements KeyValueCache {
  ResponseCache(this.prefs);

  static const _prefix = 'api_cache:';
  static const _tsPrefix = 'api_cache_ts:';

  final SharedPreferences prefs;

  @override
  Future<void> put(String key, Object? json) async {
    final encoded = jsonEncode(json);
    await prefs.setString('$_prefix$key', encoded);
    await prefs.setString(
      '$_tsPrefix$key',
      DateTime.now().toUtc().toIso8601String(),
    );
  }

  @override
  CachedResponse? read(String key) {
    final encoded = prefs.getString('$_prefix$key');
    if (encoded == null) return null;
    try {
      final decoded = jsonDecode(encoded);
      final stamp = prefs.getString('$_tsPrefix$key');
      return CachedResponse(
        data: decoded,
        storedAt: stamp == null ? null : DateTime.tryParse(stamp),
      );
    } catch (_) {
      return null;
    }
  }

  @override
  Future<void> clear() async {
    for (final key in prefs.getKeys().toList(growable: false)) {
      if (key.startsWith(_prefix) || key.startsWith(_tsPrefix)) {
        await prefs.remove(key);
      }
    }
  }
}

class CachedResponse {
  const CachedResponse({required this.data, this.storedAt});

  final Object? data;
  final DateTime? storedAt;
}

/// Builds a cache lazy-bound to SharedPreferences so `main.dart` does not need
/// an async bootstrap before constructing the API client.
class ResponseCacheFactory {
  const ResponseCacheFactory._();

  /// Namespaces cache keys per API base URL so switching environments does not
  /// serve payloads cached from another backend.
  static KeyValueCache forService(String Function() baseUrlGetter) {
    return _LazyCache(() {
      final key = baseUrlGetter().replaceAll(RegExp(r'[^a-zA-Z0-9]'), '_');
      return key;
    });
  }
}

class _LazyCache implements KeyValueCache {
  _LazyCache(this._namespace);

  final String Function() _namespace;
  final Map<String, ResponseCache> _resolved = {};

  Future<ResponseCache> _load() async {
    final ns = _namespace();
    final existing = _resolved[ns];
    if (existing != null) return existing;
    final created = ResponseCache(await SharedPreferences.getInstance());
    _resolved[ns] = created;
    return created;
  }

  ResponseCache? get _syncDelegate => _resolved[_namespace()];

  String _key(String key) => '${_namespace()}:$key';

  @override
  Future<void> put(String key, Object? json) async {
    final delegate = await _load();
    await delegate.put(_key(key), json);
  }

  @override
  CachedResponse? read(String key) => _syncDelegate?.read(_key(key));

  @override
  Future<void> clear() async {
    final delegate = _syncDelegate;
    if (delegate != null) await delegate.clear();
  }
}
