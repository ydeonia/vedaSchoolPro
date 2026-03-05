import 'package:hive_flutter/hive_flutter.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// Local storage for offline-first caching and auth tokens.
class LocalStorage {
  static late Box _authBox;
  static late Box _cacheBox;
  static late Box _brandingBox;
  static late SharedPreferences _prefs;

  static Future<void> init() async {
    _authBox = await Hive.openBox('auth');
    _cacheBox = await Hive.openBox('cache');
    _brandingBox = await Hive.openBox('branding');
    _prefs = await SharedPreferences.getInstance();
  }

  // ── Auth Token ──
  static String? get accessToken => _authBox.get('access_token');
  static set accessToken(String? v) => _authBox.put('access_token', v);

  static String? get refreshToken => _authBox.get('refresh_token');
  static set refreshToken(String? v) => _authBox.put('refresh_token', v);

  static Map? get userProfile => _authBox.get('user_profile');
  static set userProfile(Map? v) => _authBox.put('user_profile', v);

  static String? get activeRole => _authBox.get('active_role');
  static set activeRole(String? v) => _authBox.put('active_role', v);

  static String? get activeProfileId => _authBox.get('active_profile_id');
  static set activeProfileId(String? v) => _authBox.put('active_profile_id', v);

  // ── Branding (dynamic theme from API) ──
  static String? get cachedThemeColor => _brandingBox.get('theme_color');
  static set cachedThemeColor(String? v) => _brandingBox.put('theme_color', v);

  static String? get cachedLogoUrl => _brandingBox.get('logo_url');
  static set cachedLogoUrl(String? v) => _brandingBox.put('logo_url', v);

  static String? get cachedSchoolName => _brandingBox.get('school_name');
  static set cachedSchoolName(String? v) => _brandingBox.put('school_name', v);

  static String? get cachedMotto => _brandingBox.get('motto');
  static set cachedMotto(String? v) => _brandingBox.put('motto', v);

  // ── Offline Cache ──
  static dynamic getCached(String key) => _cacheBox.get(key);
  static Future<void> setCache(String key, dynamic value) =>
      _cacheBox.put(key, value);
  static Future<void> clearCache() => _cacheBox.clear();

  // ── Preferences ──
  static bool get rememberMe => _prefs.getBool('remember_me') ?? false;
  static set rememberMe(bool v) => _prefs.setBool('remember_me', v);

  static bool get biometricEnabled => _prefs.getBool('biometric') ?? false;
  static set biometricEnabled(bool v) => _prefs.setBool('biometric', v);

  static String? get savedLoginId => _prefs.getString('saved_login_id');
  static set savedLoginId(String? v) {
    if (v != null) _prefs.setString('saved_login_id', v);
    else _prefs.remove('saved_login_id');
  }

  // ── Clear on Logout ──
  static Future<void> clearAuth() async {
    await _authBox.clear();
    // Keep branding and cache — they're school-level, not user-level
  }

  static Future<void> clearAll() async {
    await _authBox.clear();
    await _cacheBox.clear();
    await _brandingBox.clear();
    await _prefs.clear();
  }
}
