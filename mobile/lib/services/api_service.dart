import 'dart:async';
import 'dart:convert';

import 'package:http/http.dart' as http;

/// Base URL of the AI Shopping FastAPI backend (no trailing slash).
///
/// Defaults to the Android emulator alias for a host machine dev server
/// (10.0.2.2 = host loopback inside the Android emulator).
String get apiBaseUrl =>
    const String.fromEnvironment('API_BASE_URL', defaultValue: 'http://10.0.2.2:8000');

const _requestTimeout = Duration(seconds: 15);

/// Guest-first HTTP transport for the read-only FastAPI catalog + basket API.
///
/// No authentication headers are sent (M12 contract: public read-only browsing;
/// admin/review/metrics endpoints are never called from the mobile client).
class ApiService {
  ApiService({http.Client? client, String? baseUrl})
      : _client = client ?? http.Client(),
        _baseUrlOverride = baseUrl;

  final http.Client _client;
  final String? _baseUrlOverride;

  String get baseUrl => _baseUrlOverride ?? apiBaseUrl;

  Future<dynamic> get(String path, {Map<String, String?>? params}) async {
    final queryParams = <String, String>{};
    if (params != null) {
      for (final e in params.entries) {
        if (e.value != null && e.value!.isNotEmpty) {
          queryParams[e.key] = e.value!;
        }
      }
    }
    final uri = Uri.parse('$baseUrl$path').replace(
      queryParameters: queryParams.isNotEmpty ? queryParams : null,
    );
    try {
      final response = await _client.get(uri).timeout(_requestTimeout);
      return _decode(response, uri);
    } on TimeoutException {
      throw ApiServiceException.network('timeout', path);
    } on http.ClientException catch (e) {
      throw ApiServiceException.network(e.message, path);
    }
  }

  Future<dynamic> post(String path, {Map<String, dynamic>? body}) async {
    final uri = Uri.parse('$baseUrl$path');
    final headers = {'Content-Type': 'application/json'};
    try {
      final response = await _client
          .post(uri, headers: headers, body: body != null ? jsonEncode(body) : null)
          .timeout(_requestTimeout);
      return _decode(response, uri);
    } on TimeoutException {
      throw ApiServiceException.network('timeout', path);
    } on http.ClientException catch (e) {
      throw ApiServiceException.network(e.message, path);
    }
  }

  dynamic _decode(http.Response response, Uri uri) {
    if (response.statusCode >= 200 && response.statusCode < 300) {
      final body = utf8.decode(response.bodyBytes);
      return body.isEmpty ? null : jsonDecode(body);
    }
    String? detail;
    try {
      final decoded = jsonDecode(utf8.decode(response.bodyBytes));
      if (decoded is Map) detail = decoded['error'] as String?;
    } catch (_) {}
    throw ApiServiceException.http(response.statusCode, uri.path, detail);
  }
}

/// Typed failure surfaced to the UI as error / network / empty states.
class ApiServiceException implements Exception {
  ApiServiceException.http(int statusCode, String path, String? detail)
      : kind = _kindForStatus(statusCode),
        statusCode = statusCode,
        path = path,
        message = detail;

  ApiServiceException.network(String message, String path)
      : kind = ApiServiceErrorKind.network,
        statusCode = null,
        path = path,
        message = message;

  final ApiServiceErrorKind kind;
  final int? statusCode;
  final String path;
  final String? message;

  static ApiServiceErrorKind _kindForStatus(int code) {
    if (code == 400 || code == 404 || code == 409) {
      return ApiServiceErrorKind.notFound;
    }
    return ApiServiceErrorKind.server;
  }

  @override
  String toString() =>
      'ApiServiceException(kind=$kind, status=$statusCode, path=$path, message=$message)';
}

enum ApiServiceErrorKind { network, notFound, server }
