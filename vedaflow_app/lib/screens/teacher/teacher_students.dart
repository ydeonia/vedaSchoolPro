import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../core/api_client.dart';
import '../../widgets/shimmer_loading.dart';
import '../../widgets/animated_card.dart';

final myStudentsProvider = FutureProvider<Map<String, dynamic>>((ref) async {
  final response = await api.get('/api/mobile/teacher/my-students');
  return response.data;
});

class TeacherStudents extends ConsumerWidget {
  const TeacherStudents({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final data = ref.watch(myStudentsProvider);
    final theme = Theme.of(context);

    return Scaffold(
      appBar: AppBar(title: const Text('My Students')),
      body: data.when(
        data: (result) {
          final classes = result['classes'] as List? ?? [];
          if (classes.isEmpty) {
            return const Center(child: Text('No classes assigned'));
          }

          return DefaultTabController(
            length: classes.length,
            child: Column(
              children: [
                Container(
                  color: theme.colorScheme.primary,
                  child: TabBar(
                    isScrollable: true,
                    indicatorColor: Colors.white,
                    labelColor: Colors.white,
                    unselectedLabelColor: Colors.white.withValues(alpha: 0.6),
                    tabAlignment: TabAlignment.start,
                    tabs: classes.map((c) {
                      final cl = c as Map<String, dynamic>;
                      return Tab(
                        text: '${cl['class_name']} ${cl['section_name']}',
                      );
                    }).toList(),
                  ),
                ),
                Expanded(
                  child: TabBarView(
                    children: classes.map((c) {
                      final cl = c as Map<String, dynamic>;
                      final students = cl['students'] as List? ?? [];

                      return ListView.builder(
                        padding: const EdgeInsets.all(16),
                        itemCount: students.length,
                        itemBuilder: (ctx, i) {
                          final s = students[i] as Map<String, dynamic>;
                          return AnimatedCard(
                            index: i,
                            padding: const EdgeInsets.symmetric(
                                horizontal: 14, vertical: 12),
                            child: Row(
                              children: [
                                Container(
                                  width: 40,
                                  height: 40,
                                  decoration: BoxDecoration(
                                    color: theme.colorScheme.primary
                                        .withValues(alpha: 0.1),
                                    borderRadius: BorderRadius.circular(10),
                                  ),
                                  child: Center(
                                    child: Text(
                                      '${s['roll_number'] ?? i + 1}',
                                      style: TextStyle(
                                        fontWeight: FontWeight.w700,
                                        color: theme.colorScheme.primary,
                                        fontSize: 13,
                                      ),
                                    ),
                                  ),
                                ),
                                const SizedBox(width: 12),
                                Expanded(
                                  child: Column(
                                    crossAxisAlignment:
                                        CrossAxisAlignment.start,
                                    children: [
                                      Text(
                                        s['name'] ?? '',
                                        style: const TextStyle(
                                          fontSize: 14,
                                          fontWeight: FontWeight.w600,
                                        ),
                                      ),
                                      Text(
                                        s['registration_number'] ?? '',
                                        style: TextStyle(
                                          fontSize: 12,
                                          color: theme
                                              .textTheme.bodySmall?.color,
                                        ),
                                      ),
                                    ],
                                  ),
                                ),
                                // Attendance % badge
                                if (s['attendance_percentage'] != null)
                                  Container(
                                    padding: const EdgeInsets.symmetric(
                                        horizontal: 8, vertical: 4),
                                    decoration: BoxDecoration(
                                      color:
                                          (s['attendance_percentage'] ?? 0) >= 75
                                              ? const Color(0xFFF0FDF4)
                                              : const Color(0xFFFEF2F2),
                                      borderRadius: BorderRadius.circular(6),
                                    ),
                                    child: Text(
                                      '${s['attendance_percentage']}%',
                                      style: TextStyle(
                                        fontSize: 12,
                                        fontWeight: FontWeight.w600,
                                        color: (s['attendance_percentage'] ??
                                                    0) >=
                                                75
                                            ? const Color(0xFF22C55E)
                                            : const Color(0xFFEF4444),
                                      ),
                                    ),
                                  ),
                              ],
                            ),
                          );
                        },
                      );
                    }).toList(),
                  ),
                ),
              ],
            ),
          );
        },
        loading: () => Padding(
          padding: const EdgeInsets.all(16),
          child: ShimmerList(itemCount: 8),
        ),
        error: (_, __) => Center(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Text('Could not load students'),
              OutlinedButton(
                onPressed: () => ref.invalidate(myStudentsProvider),
                child: const Text('Retry'),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
