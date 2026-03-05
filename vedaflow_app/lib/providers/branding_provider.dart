import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../core/api_client.dart';
import '../core/config.dart';
import '../core/storage.dart';

/// School branding data (logo, color, name) — fetched from API, cached locally.
class BrandingData {
  final String themeColor;
  final String logoUrl;
  final String schoolName;
  final String motto;
  final String language;

  BrandingData({
    required this.themeColor,
    required this.logoUrl,
    required this.schoolName,
    required this.motto,
    required this.language,
  });

  factory BrandingData.fromJson(Map<String, dynamic> json) => BrandingData(
        themeColor: json['theme_color'] ?? AppConfig.defaultThemeColor,
        logoUrl: json['logo_url'] ?? '',
        schoolName: json['school_name'] ?? AppConfig.schoolName,
        motto: json['motto'] ?? '',
        language: json['language'] ?? 'en',
      );

  /// Load from local cache (for instant display before API response).
  factory BrandingData.fromCache() => BrandingData(
        themeColor:
            LocalStorage.cachedThemeColor ?? AppConfig.defaultThemeColor,
        logoUrl: LocalStorage.cachedLogoUrl ?? '',
        schoolName: LocalStorage.cachedSchoolName ?? AppConfig.schoolName,
        motto: LocalStorage.cachedMotto ?? '',
        language: 'en',
      );
}

/// Fetches branding from API and caches it. Falls back to cache if offline.
final brandingProvider = FutureProvider<BrandingData>((ref) async {
  // Return cached immediately, then update in background
  try {
    final response = await api.get('/api/school/branding');
    if (response.statusCode == 200) {
      final data = BrandingData.fromJson(response.data);
      // Cache for next launch
      LocalStorage.cachedThemeColor = data.themeColor;
      LocalStorage.cachedLogoUrl = data.logoUrl;
      LocalStorage.cachedSchoolName = data.schoolName;
      LocalStorage.cachedMotto = data.motto;
      return data;
    }
  } catch (_) {
    // Offline — use cached values
  }
  return BrandingData.fromCache();
});
