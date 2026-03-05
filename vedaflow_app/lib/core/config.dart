import 'package:flutter/foundation.dart';

/// School-specific configuration.
/// Build-time defaults come from school_config.json (baked by build_school.py).
/// Runtime overrides come from GET /api/school/branding on every app launch.
class AppConfig {
  static String schoolId = 'default';
  static String schoolName = 'VedaSchoolPro';
  static String logoUrl = '';
  static String defaultThemeColor = '#4F46E5'; // Indigo
  static String motto = '';
  static String language = 'en';
  static String packageId = 'com.vedaschoolpro.app';

  /// API base URL:
  /// - Debug (emulator): http://10.0.2.2:8000 (Android emulator → host localhost)
  /// - Debug (real device on same WiFi): http://192.168.x.x:8000
  /// - Production: https://app.vedaschoolpro.com
  static String get apiBaseUrl {
    if (kDebugMode) {
      // Android emulator maps 10.0.2.2 → host machine's localhost
      return 'http://10.0.2.2:8000';
    }
    return 'https://app.vedaschoolpro.com';
  }

  /// Load build-time config from bundled JSON asset.
  static Future<void> load() async {
    // In white-label builds, build_school.py replaces these values.
    // For dev/default builds, we use the defaults above.
    // Runtime branding is fetched separately via BrandingProvider.
  }
}
