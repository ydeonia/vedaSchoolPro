import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../core/api_client.dart';
import '../core/storage.dart';

/// User profile data after login.
class UserProfile {
  final String id;
  final String name;
  final String email;
  final String role;
  final String? photoUrl;
  final String? studentId;
  final String? teacherId;
  final String? className;
  final String? sectionName;
  final String? registrationNumber;
  final List<RoleProfile> profiles;

  UserProfile({
    required this.id,
    required this.name,
    required this.email,
    required this.role,
    this.photoUrl,
    this.studentId,
    this.teacherId,
    this.className,
    this.sectionName,
    this.registrationNumber,
    this.profiles = const [],
  });

  factory UserProfile.fromJson(Map<String, dynamic> json) => UserProfile(
        id: json['id'] ?? '',
        name: json['name'] ?? '',
        email: json['email'] ?? '',
        role: json['role'] ?? 'student',
        photoUrl: json['photo_url'],
        studentId: json['student_id'],
        teacherId: json['teacher_id'],
        className: json['class_name'],
        sectionName: json['section_name'],
        registrationNumber: json['registration_number'],
        profiles: (json['profiles'] as List?)
                ?.map((p) => RoleProfile.fromJson(p))
                .toList() ??
            [],
      );
}

class RoleProfile {
  final String id;
  final String role;
  final String label;
  final String? photoUrl;

  RoleProfile({
    required this.id,
    required this.role,
    required this.label,
    this.photoUrl,
  });

  factory RoleProfile.fromJson(Map<String, dynamic> json) => RoleProfile(
        id: json['id'] ?? '',
        role: json['role'] ?? '',
        label: json['label'] ?? '',
        photoUrl: json['photo_url'],
      );
}

/// Auth state.
enum AuthStatus { initial, loading, authenticated, unauthenticated, error }

class AuthState {
  final AuthStatus status;
  final UserProfile? user;
  final String? errorMessage;
  final List<RoleProfile> availableProfiles;

  AuthState({
    this.status = AuthStatus.initial,
    this.user,
    this.errorMessage,
    this.availableProfiles = const [],
  });

  AuthState copyWith({
    AuthStatus? status,
    UserProfile? user,
    String? errorMessage,
    List<RoleProfile>? availableProfiles,
  }) =>
      AuthState(
        status: status ?? this.status,
        user: user ?? this.user,
        errorMessage: errorMessage ?? this.errorMessage,
        availableProfiles: availableProfiles ?? this.availableProfiles,
      );
}

class AuthNotifier extends StateNotifier<AuthState> {
  AuthNotifier() : super(AuthState()) {
    _checkSavedAuth();
  }

  /// Check if user has saved auth tokens on app start.
  Future<void> _checkSavedAuth() async {
    if (LocalStorage.accessToken != null) {
      try {
        final response = await api.get('/api/mobile/profile');
        if (response.statusCode == 200) {
          final user = UserProfile.fromJson(response.data);
          LocalStorage.userProfile = response.data;
          LocalStorage.activeRole = user.role;
          state = AuthState(
            status: AuthStatus.authenticated,
            user: user,
          );
          return;
        }
      } catch (_) {}
    }
    state = AuthState(status: AuthStatus.unauthenticated);
  }

  /// Login with ID (registration#, phone, email) and password.
  Future<void> login(String loginId, String password) async {
    state = state.copyWith(status: AuthStatus.loading);
    try {
      final response = await api.post('/api/mobile/auth/login', data: {
        'login_id': loginId,
        'password': password,
      });

      if (response.statusCode == 200) {
        final data = response.data;
        LocalStorage.accessToken = data['access_token'];
        LocalStorage.refreshToken = data['refresh_token'];

        // Check if multiple profiles available
        final profiles = (data['profiles'] as List?)
                ?.map((p) => RoleProfile.fromJson(p))
                .toList() ??
            [];

        if (profiles.length > 1) {
          // Multiple roles — go to profile selection
          state = AuthState(
            status: AuthStatus.unauthenticated,
            availableProfiles: profiles,
          );
          return;
        }

        // Single role — auto-select
        if (profiles.isNotEmpty) {
          await selectProfile(profiles.first.id);
        } else {
          final user = UserProfile.fromJson(data['user'] ?? data);
          LocalStorage.userProfile = data['user'] ?? data;
          LocalStorage.activeRole = user.role;
          state = AuthState(
            status: AuthStatus.authenticated,
            user: user,
          );
        }
      }
    } catch (e) {
      String msg = 'Login failed. Please check your credentials.';
      if (e is DioException) {
        if (e.response?.statusCode == 401) {
          msg = 'Invalid ID or password.';
        } else if (e.response?.statusCode == 403) {
          msg = 'Account is deactivated. Contact your school.';
        } else if (e.type == DioExceptionType.connectionTimeout ||
            e.type == DioExceptionType.connectionError) {
          msg = 'No internet connection. Please try again.';
        }
      }
      state = AuthState(
        status: AuthStatus.error,
        errorMessage: msg,
      );
    }
  }

  /// Select a specific role profile (for multi-role users).
  Future<void> selectProfile(String profileId) async {
    state = state.copyWith(status: AuthStatus.loading);
    try {
      final response = await api.post(
        '/api/mobile/auth/select-profile',
        data: {'profile_id': profileId},
      );
      if (response.statusCode == 200) {
        final data = response.data;
        if (data['access_token'] != null) {
          LocalStorage.accessToken = data['access_token'];
        }
        LocalStorage.activeProfileId = profileId;
        final user = UserProfile.fromJson(data['user'] ?? data);
        LocalStorage.userProfile = data['user'] ?? data;
        LocalStorage.activeRole = user.role;
        state = AuthState(
          status: AuthStatus.authenticated,
          user: user,
        );
      }
    } catch (e) {
      state = AuthState(
        status: AuthStatus.error,
        errorMessage: 'Failed to select profile.',
      );
    }
  }

  /// Logout — clear tokens and navigate to login.
  Future<void> logout() async {
    try {
      await api.post('/api/mobile/auth/logout');
    } catch (_) {}
    await LocalStorage.clearAuth();
    state = AuthState(status: AuthStatus.unauthenticated);
  }
}

final authProvider = StateNotifierProvider<AuthNotifier, AuthState>((ref) {
  return AuthNotifier();
});

/// Quick access to current user.
final currentUserProvider = Provider<UserProfile?>((ref) {
  return ref.watch(authProvider).user;
});

/// Quick access to current role.
final currentRoleProvider = Provider<String?>((ref) {
  return ref.watch(authProvider).user?.role ?? LocalStorage.activeRole;
});
