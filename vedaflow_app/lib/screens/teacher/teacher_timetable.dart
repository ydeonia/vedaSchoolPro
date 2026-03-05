import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../core/api_client.dart';
import '../../widgets/shimmer_loading.dart';
import '../../widgets/animated_card.dart';

final teacherTimetableProvider = FutureProvider<Map<String, dynamic>>((ref) async {
  final response = await api.get('/api/mobile/timetable');
  return response.data;
});

class TeacherTimetable extends ConsumerWidget {
  const TeacherTimetable({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final timetable = ref.watch(teacherTimetableProvider);
    final theme = Theme.of(context);

    return Scaffold(
      appBar: AppBar(title: const Text('My Timetable')),
      body: timetable.when(
        data: (data) {
          final days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];
          final schedule = data['schedule'] as Map<String, dynamic>? ?? {};

          return DefaultTabController(
            length: days.length,
            initialIndex: (DateTime.now().weekday - 1).clamp(0, 5),
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
                    tabs: days.map((d) => Tab(text: d.substring(0, 3))).toList(),
                  ),
                ),
                Expanded(
                  child: TabBarView(
                    children: days.map((day) {
                      final periods =
                          (schedule[day.toLowerCase()] as List?) ?? [];
                      if (periods.isEmpty) {
                        return Center(
                          child: Column(
                            mainAxisSize: MainAxisSize.min,
                            children: [
                              Icon(Icons.weekend_outlined,
                                  size: 56,
                                  color: theme.textTheme.bodySmall?.color),
                              const SizedBox(height: 12),
                              const Text('No classes today'),
                            ],
                          ),
                        );
                      }
                      return ListView.builder(
                        padding: const EdgeInsets.all(16),
                        itemCount: periods.length,
                        itemBuilder: (ctx, i) {
                          final p = periods[i] as Map<String, dynamic>;
                          return AnimatedCard(
                            index: i,
                            padding: const EdgeInsets.all(14),
                            child: Row(
                              children: [
                                Container(
                                  width: 44,
                                  height: 44,
                                  decoration: BoxDecoration(
                                    color: theme.colorScheme.primary
                                        .withValues(alpha: 0.1),
                                    borderRadius: BorderRadius.circular(12),
                                  ),
                                  child: Center(
                                    child: Text(
                                      'P${p['period_number'] ?? i + 1}',
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
                                        p['subject_name'] ?? 'Free',
                                        style: const TextStyle(
                                          fontSize: 14,
                                          fontWeight: FontWeight.w600,
                                        ),
                                      ),
                                      Text(
                                        'Class ${p['class_name'] ?? ''} - ${p['section_name'] ?? ''}',
                                        style: TextStyle(
                                          fontSize: 12,
                                          color: theme
                                              .textTheme.bodySmall?.color,
                                        ),
                                      ),
                                    ],
                                  ),
                                ),
                                Column(
                                  crossAxisAlignment: CrossAxisAlignment.end,
                                  children: [
                                    Text(
                                      p['start_time'] ?? '',
                                      style: TextStyle(
                                        fontSize: 12,
                                        fontWeight: FontWeight.w600,
                                        color: theme
                                            .textTheme.bodySmall?.color,
                                      ),
                                    ),
                                    Text(
                                      p['end_time'] ?? '',
                                      style: TextStyle(
                                        fontSize: 11,
                                        color: theme
                                            .textTheme.bodySmall?.color,
                                      ),
                                    ),
                                  ],
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
          child: ShimmerList(itemCount: 6),
        ),
        error: (_, __) => Center(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Text('Could not load timetable'),
              OutlinedButton(
                onPressed: () => ref.invalidate(teacherTimetableProvider),
                child: const Text('Retry'),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
