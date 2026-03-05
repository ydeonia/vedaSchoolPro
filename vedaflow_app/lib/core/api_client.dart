import 'package:dio/dio.dart';
import 'package:flutter/foundation.dart';
import '../core/config.dart';
import '../core/storage.dart';

/// Singleton API client with auth interceptors, retry logic, and offline support.
class ApiClient {
  static final ApiClient _instance = ApiClient._internal();
  factory ApiClient() => _instance;

  late final Dio dio;

  ApiClient._internal() {
    dio = Dio(BaseOptions(
      baseUrl: AppConfig.apiBaseUrl,
      connectTimeout: const Duration(seconds: 15),
      receiveTimeout: const Duration(seconds: 30),
      headers: {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
        'X-App-Version': '1.0.0',
        'X-Platform': 'mobile',
      },
    ));

    // ── Auth Interceptor ──
    dio.interceptors.add(InterceptorsWrapper(
      onRequest: (options, handler) {
        final token = LocalStorage.accessToken;
        if (token != null) {
          options.headers['Authorization'] = 'Bearer $token';
        }
        return handler.next(options);
      },
      onError: (error, handler) async {
        if (error.response?.statusCode == 401) {
          // Try refresh token
          final refreshed = await _refreshToken();
          if (refreshed) {
            // Retry original request with new token
            final opts = error.requestOptions;
            opts.headers['Authorization'] =
                'Bearer ${LocalStorage.accessToken}';
            try {
              final response = await dio.fetch(opts);
              return handler.resolve(response);
            } catch (e) {
              return handler.next(error);
            }
          }
        }
        return handler.next(error);
      },
    ));

    // ── Logging (debug only) ──
    if (kDebugMode) {
      dio.interceptors.add(LogInterceptor(
        requestBody: true,
        responseBody: true,
        logPrint: (log) => debugPrint('[API] $log'),
      ));
    }
  }

  /// Refresh the access token using the refresh token.
  Future<bool> _refreshToken() async {
    final refreshToken = LocalStorage.refreshToken;
    if (refreshToken == null) return false;
    try {
      final response = await Dio(BaseOptions(
        baseUrl: AppConfig.apiBaseUrl,
      )).post('/api/mobile/auth/refresh', data: {
        'refresh_token': refreshToken,
      });
      if (response.statusCode == 200) {
        LocalStorage.accessToken = response.data['access_token'];
        if (response.data['refresh_token'] != null) {
          LocalStorage.refreshToken = response.data['refresh_token'];
        }
        return true;
      }
    } catch (_) {}
    return false;
  }

  // ── Convenience Methods ──

  Future<Response> get(String path, {Map<String, dynamic>? params}) =>
      dio.get(path, queryParameters: params);

  Future<Response> post(String path, {dynamic data}) =>
      dio.post(path, data: data);

  Future<Response> put(String path, {dynamic data}) =>
      dio.put(path, data: data);

  Future<Response> delete(String path) => dio.delete(path);

  Future<Response> upload(String path, FormData formData) =>
      dio.post(path, data: formData);
}

/// Global API client accessor.
final api = ApiClient();
