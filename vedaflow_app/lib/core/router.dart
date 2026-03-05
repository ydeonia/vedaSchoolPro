import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import '../core/storage.dart';
import '../screens/auth/login_screen.dart';
import '../screens/auth/profile_select_screen.dart';
import '../screens/student/student_shell.dart';
import '../screens/student/student_dashboard.dart';
import '../screens/student/student_timetable.dart';
import '../screens/student/student_attendance.dart';
import '../screens/student/student_fees.dart';
import '../screens/student/student_homework.dart';
import '../screens/student/student_results.dart';
import '../screens/student/student_leave.dart';
import '../screens/teacher/teacher_shell.dart';
import '../screens/teacher/teacher_dashboard.dart';
import '../screens/teacher/teacher_attendance_mark.dart';
import '../screens/teacher/teacher_timetable.dart';
import '../screens/teacher/teacher_students.dart';
import '../screens/teacher/teacher_leave.dart';
import '../screens/parent/parent_shell.dart';
import '../screens/parent/parent_dashboard.dart';
import '../screens/admin/admin_shell.dart';
import '../screens/admin/admin_dashboard.dart';
import '../screens/admin/admin_approvals.dart';
import '../screens/admin/admin_fee_overview.dart';
import '../screens/chairman/chairman_shell.dart';
import '../screens/chairman/chairman_dashboard.dart';
import '../screens/staff/staff_shell.dart';
import '../screens/staff/staff_dashboard.dart';
import '../screens/staff/staff_leave.dart';
import '../screens/shared/chat_screen.dart';
import '../screens/shared/notifications_screen.dart';
import '../screens/shared/profile_screen.dart';
import '../screens/shared/more_screen.dart';

final GlobalKey<NavigatorState> _rootNavigatorKey = GlobalKey<NavigatorState>();

final appRouter = GoRouter(
  navigatorKey: _rootNavigatorKey,
  initialLocation: '/',
  redirect: (context, state) {
    final loggedIn = LocalStorage.accessToken != null;
    final isAuthRoute = state.matchedLocation.startsWith('/auth');

    if (!loggedIn && !isAuthRoute) return '/auth/login';
    if (loggedIn && isAuthRoute) {
      final role = LocalStorage.activeRole;
      return _homeForRole(role);
    }
    return null;
  },
  routes: [
    // ── Auth Routes ──
    GoRoute(
      path: '/auth/login',
      builder: (ctx, state) => const LoginScreen(),
    ),
    GoRoute(
      path: '/auth/select-profile',
      builder: (ctx, state) => const ProfileSelectScreen(),
    ),

    // ── Student Shell (bottom nav) ──
    ShellRoute(
      builder: (ctx, state, child) => StudentShell(child: child),
      routes: [
        GoRoute(
          path: '/student',
          builder: (ctx, state) => const StudentDashboard(),
        ),
        GoRoute(
          path: '/student/timetable',
          builder: (ctx, state) => const StudentTimetable(),
        ),
        GoRoute(
          path: '/student/attendance',
          builder: (ctx, state) => const StudentAttendance(),
        ),
        GoRoute(
          path: '/student/fees',
          builder: (ctx, state) => const StudentFees(),
        ),
        GoRoute(
          path: '/student/homework',
          builder: (ctx, state) => const StudentHomework(),
        ),
        GoRoute(
          path: '/student/results',
          builder: (ctx, state) => const StudentResults(),
        ),
        GoRoute(
          path: '/student/leave',
          builder: (ctx, state) => const StudentLeave(),
        ),
        GoRoute(
          path: '/student/chat',
          builder: (ctx, state) => const ChatScreen(),
        ),
        GoRoute(
          path: '/student/notifications',
          builder: (ctx, state) => const NotificationsScreen(),
        ),
        GoRoute(
          path: '/student/profile',
          builder: (ctx, state) => const ProfileScreen(),
        ),
        GoRoute(
          path: '/student/more',
          builder: (ctx, state) => const MoreScreen(),
        ),
      ],
    ),

    // ── Teacher Shell (bottom nav) ──
    ShellRoute(
      builder: (ctx, state, child) => TeacherShell(child: child),
      routes: [
        GoRoute(
          path: '/teacher',
          builder: (ctx, state) => const TeacherDashboard(),
        ),
        GoRoute(
          path: '/teacher/attendance',
          builder: (ctx, state) => const TeacherAttendanceMark(),
        ),
        GoRoute(
          path: '/teacher/timetable',
          builder: (ctx, state) => const TeacherTimetable(),
        ),
        GoRoute(
          path: '/teacher/students',
          builder: (ctx, state) => const TeacherStudents(),
        ),
        GoRoute(
          path: '/teacher/leave',
          builder: (ctx, state) => const TeacherLeave(),
        ),
        GoRoute(
          path: '/teacher/chat',
          builder: (ctx, state) => const ChatScreen(),
        ),
        GoRoute(
          path: '/teacher/notifications',
          builder: (ctx, state) => const NotificationsScreen(),
        ),
        GoRoute(
          path: '/teacher/profile',
          builder: (ctx, state) => const ProfileScreen(),
        ),
        GoRoute(
          path: '/teacher/more',
          builder: (ctx, state) => const MoreScreen(),
        ),
      ],
    ),

    // ── Parent Shell (bottom nav) ──
    ShellRoute(
      builder: (ctx, state, child) => ParentShell(child: child),
      routes: [
        GoRoute(
          path: '/parent',
          builder: (ctx, state) => const ParentDashboard(),
        ),
        GoRoute(
          path: '/parent/chat',
          builder: (ctx, state) => const ChatScreen(),
        ),
        GoRoute(
          path: '/parent/notifications',
          builder: (ctx, state) => const NotificationsScreen(),
        ),
        GoRoute(
          path: '/parent/profile',
          builder: (ctx, state) => const ProfileScreen(),
        ),
        GoRoute(
          path: '/parent/more',
          builder: (ctx, state) => const MoreScreen(),
        ),
      ],
    ),

    // ── Admin Shell (bottom nav) ──
    ShellRoute(
      builder: (ctx, state, child) => AdminShell(child: child),
      routes: [
        GoRoute(
          path: '/admin',
          builder: (ctx, state) => const AdminDashboard(),
        ),
        GoRoute(
          path: '/admin/approvals',
          builder: (ctx, state) => const AdminApprovals(),
        ),
        GoRoute(
          path: '/admin/fees',
          builder: (ctx, state) => const AdminFeeOverview(),
        ),
        GoRoute(
          path: '/admin/chat',
          builder: (ctx, state) => const ChatScreen(),
        ),
        GoRoute(
          path: '/admin/notifications',
          builder: (ctx, state) => const NotificationsScreen(),
        ),
        GoRoute(
          path: '/admin/profile',
          builder: (ctx, state) => const ProfileScreen(),
        ),
        GoRoute(
          path: '/admin/more',
          builder: (ctx, state) => const MoreScreen(),
        ),
      ],
    ),

    // ── Staff Shell (non-teaching staff) ──
    ShellRoute(
      builder: (ctx, state, child) => StaffShell(child: child),
      routes: [
        GoRoute(
          path: '/staff',
          builder: (ctx, state) => const StaffDashboard(),
        ),
        GoRoute(
          path: '/staff/leave',
          builder: (ctx, state) => const StaffLeave(),
        ),
        GoRoute(
          path: '/staff/notifications',
          builder: (ctx, state) => const NotificationsScreen(),
        ),
        GoRoute(
          path: '/staff/profile',
          builder: (ctx, state) => const ProfileScreen(),
        ),
        GoRoute(
          path: '/staff/more',
          builder: (ctx, state) => const MoreScreen(),
        ),
      ],
    ),

    // ── Chairman Shell (bottom nav) ──
    ShellRoute(
      builder: (ctx, state, child) => ChairmanShell(child: child),
      routes: [
        GoRoute(
          path: '/chairman',
          builder: (ctx, state) => const ChairmanDashboard(),
        ),
        GoRoute(
          path: '/chairman/finances',
          builder: (ctx, state) => const AdminFeeOverview(), // Reuse fee view
        ),
        GoRoute(
          path: '/chairman/notifications',
          builder: (ctx, state) => const NotificationsScreen(),
        ),
        GoRoute(
          path: '/chairman/profile',
          builder: (ctx, state) => const ProfileScreen(),
        ),
        GoRoute(
          path: '/chairman/more',
          builder: (ctx, state) => const MoreScreen(),
        ),
      ],
    ),
  ],
);

String _homeForRole(String? role) {
  switch (role) {
    // ── Teaching Staff ──
    case 'teacher':
    case 'hod':           // Head of Department → teacher dashboard + dept view
      return '/teacher';

    // ── Admin Roles ──
    case 'school_admin':
    case 'principal':     // Principal = full admin access
    case 'vice_principal': // VP = admin with limited finance view
      return '/admin';

    // ── Chairman / Trust ──
    case 'chairman':
    case 'trust_member':
      return '/chairman';

    // ── Parent ──
    case 'parent':
      return '/parent';

    // ── Non-Teaching Staff ──
    case 'staff':
    case 'accountant':
    case 'clerk':
    case 'librarian':
    case 'lab_assistant':
    case 'peon':
    case 'driver':
    case 'security':
    case 'non_teaching':
      return '/staff';

    // ── Default = Student ──
    default:
      return '/student';
  }
}
