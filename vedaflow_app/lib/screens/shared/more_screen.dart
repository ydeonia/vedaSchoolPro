import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import '../../providers/auth_provider.dart';
import '../../widgets/animated_card.dart';

/// "More" screen — grid of all features accessible from bottom nav.
class MoreScreen extends ConsumerWidget {
  const MoreScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final role = ref.watch(currentRoleProvider) ?? 'student';
    final theme = Theme.of(context);

    final items = _itemsForRole(role);

    return Scaffold(
      appBar: AppBar(title: const Text('More')),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // ── Profile card ──
            AnimatedCard(
              index: 0,
              onTap: () {
                final prefix = role == 'teacher' ? '/teacher' : role == 'parent' ? '/parent' : '/student';
                context.go('$prefix/profile');
              },
              padding: const EdgeInsets.all(16),
              child: Row(
                children: [
                  CircleAvatar(
                    radius: 24,
                    backgroundColor:
                        theme.colorScheme.primary.withValues(alpha: 0.1),
                    child: Icon(Icons.person_outline_rounded,
                        color: theme.colorScheme.primary, size: 26),
                  ),
                  const SizedBox(width: 14),
                  const Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          'My Profile',
                          style: TextStyle(
                              fontSize: 15, fontWeight: FontWeight.w600),
                        ),
                        Text(
                          'View and edit your profile',
                          style: TextStyle(fontSize: 12, color: Colors.grey),
                        ),
                      ],
                    ),
                  ),
                  Icon(Icons.chevron_right_rounded,
                      color: theme.textTheme.bodySmall?.color),
                ],
              ),
            ),
            const SizedBox(height: 20),

            // ── Menu Grid ──
            GridView.builder(
              shrinkWrap: true,
              physics: const NeverScrollableScrollPhysics(),
              gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(
                crossAxisCount: 3,
                mainAxisSpacing: 12,
                crossAxisSpacing: 12,
                childAspectRatio: 0.9,
              ),
              itemCount: items.length,
              itemBuilder: (ctx, i) {
                final item = items[i];
                return AnimatedCard(
                  index: i + 1,
                  onTap: () {
                    HapticFeedback.selectionClick();
                    if (item['route'] != null) {
                      context.go(item['route'] as String);
                    }
                  },
                  padding:
                      const EdgeInsets.symmetric(vertical: 16, horizontal: 8),
                  child: Column(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      Container(
                        width: 44,
                        height: 44,
                        decoration: BoxDecoration(
                          color: (item['color'] as Color).withValues(alpha: 0.12),
                          borderRadius: BorderRadius.circular(12),
                        ),
                        child: Icon(
                          item['icon'] as IconData,
                          color: item['color'] as Color,
                          size: 22,
                        ),
                      ),
                      const SizedBox(height: 8),
                      Text(
                        item['label'] as String,
                        textAlign: TextAlign.center,
                        maxLines: 2,
                        overflow: TextOverflow.ellipsis,
                        style: const TextStyle(
                          fontSize: 11,
                          fontWeight: FontWeight.w500,
                        ),
                      ),
                    ],
                  ),
                );
              },
            ),
          ],
        ),
      ),
    );
  }

  List<Map<String, dynamic>> _itemsForRole(String role) {
    if (role == 'teacher') {
      return [
        {'icon': Icons.schedule_rounded, 'label': 'Timetable', 'color': const Color(0xFF4F46E5), 'route': '/teacher/timetable'},
        {'icon': Icons.people_outline, 'label': 'Students', 'color': const Color(0xFF06B6D4), 'route': '/teacher/students'},
        {'icon': Icons.event_note_outlined, 'label': 'Leave\nRequests', 'color': const Color(0xFFF59E0B), 'route': '/teacher/leave'},
        {'icon': Icons.fact_check_outlined, 'label': 'Attendance', 'color': const Color(0xFF22C55E), 'route': '/teacher/attendance'},
        {'icon': Icons.book_outlined, 'label': 'Homework', 'color': const Color(0xFFEC4899), 'route': null},
        {'icon': Icons.assignment_outlined, 'label': 'Exams', 'color': const Color(0xFF8B5CF6), 'route': null},
        {'icon': Icons.library_books_outlined, 'label': 'Library', 'color': const Color(0xFF78716C), 'route': null},
        {'icon': Icons.settings_outlined, 'label': 'Settings', 'color': const Color(0xFF64748B), 'route': null},
      ];
    } else if (role == 'parent') {
      return [
        {'icon': Icons.person_outline, 'label': 'My Children', 'color': const Color(0xFF4F46E5), 'route': '/parent'},
        {'icon': Icons.account_balance_wallet_outlined, 'label': 'Fees', 'color': const Color(0xFFEF4444), 'route': null},
        {'icon': Icons.directions_bus_outlined, 'label': 'Transport', 'color': const Color(0xFF22C55E), 'route': null},
        {'icon': Icons.feedback_outlined, 'label': 'Complaints', 'color': const Color(0xFFF59E0B), 'route': null},
        {'icon': Icons.settings_outlined, 'label': 'Settings', 'color': const Color(0xFF64748B), 'route': null},
      ];
    }
    // Student
    return [
      {'icon': Icons.schedule_rounded, 'label': 'Timetable', 'color': const Color(0xFF4F46E5), 'route': '/student/timetable'},
      {'icon': Icons.check_circle_outline, 'label': 'Attendance', 'color': const Color(0xFF22C55E), 'route': '/student/attendance'},
      {'icon': Icons.book_outlined, 'label': 'Homework', 'color': const Color(0xFFF59E0B), 'route': '/student/homework'},
      {'icon': Icons.leaderboard_outlined, 'label': 'Results', 'color': const Color(0xFF8B5CF6), 'route': '/student/results'},
      {'icon': Icons.event_note_outlined, 'label': 'Leave', 'color': const Color(0xFF06B6D4), 'route': '/student/leave'},
      {'icon': Icons.library_books_outlined, 'label': 'Library', 'color': const Color(0xFF78716C), 'route': null},
      {'icon': Icons.directions_bus_outlined, 'label': 'Transport', 'color': const Color(0xFFEC4899), 'route': null},
      {'icon': Icons.feedback_outlined, 'label': 'Complaints', 'color': const Color(0xFFEF4444), 'route': null},
      {'icon': Icons.settings_outlined, 'label': 'Settings', 'color': const Color(0xFF64748B), 'route': null},
    ];
  }
}
