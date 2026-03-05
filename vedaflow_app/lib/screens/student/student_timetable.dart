import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../core/api_client.dart';
import '../../widgets/shimmer_loading.dart';
import '../../widgets/animated_card.dart';

final timetableProvider = FutureProvider<Map<String, dynamic>>((ref) async {
  final response = await api.get('/api/mobile/timetable');
  return response.data;
});

class StudentTimetable extends ConsumerWidget {
  const StudentTimetable({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final timetable = ref.watch(timetableProvider);
    final theme = Theme.of(context);

    return Scaffold(
      appBar: AppBar(title: const Text('Timetable')),
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
                              const Text('No classes scheduled'),
                            ],
                          ),
                        );
                      }
                      return ListView.builder(
                        padding: const EdgeInsets.all(16),
                        itemCount: periods.length,
                        itemBuilder: (ctx, i) {
                          final p = periods[i] as Map<String, dynamic>;
                          final isBreak = p['is_break'] == true;
                          return AnimatedCard(
                            index: i,
                            padding: const EdgeInsets.all(14),
                            child: Row(
                              children: [
                                // Period number
                                Container(
                                  width: 44,
                                  height: 44,
                                  decoration: BoxDecoration(
                                    color: isBreak
                                        ? const Color(0xFFFEF3C7)
                                        : theme.colorScheme.primary
                                            .withValues(alpha: 0.1),
                                    borderRadius: BorderRadius.circular(12),
                                  ),
                                  child: Center(
                                    child: isBreak
                                        ? const Icon(Icons.coffee_rounded,
                                            color: Color(0xFFF59E0B), size: 22)
                                        : Text(
                                            'P${p['period_number'] ?? i + 1}',
                                            style: TextStyle(
                                              fontWeight: FontWeight.w700,
                                              color:
                                                  theme.colorScheme.primary,
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
                                        isBreak
                                            ? (p['label'] ?? 'Break')
                                            : (p['subject_name'] ?? 'Free'),
                                        style: TextStyle(
                                          fontSize: 14,
                                          fontWeight: FontWeight.w600,
                                          fontStyle: isBreak
                                              ? FontStyle.italic
                                              : FontStyle.normal,
                                        ),
                                      ),
                                      if (!isBreak &&
                                          p['teacher_name'] != null)
                                        Text(
                                          p['teacher_name'],
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
                                        color: theme.textTheme.bodySmall?.color,
                                      ),
                                    ),
                                    Text(
                                      p['end_time'] ?? '',
                                      style: TextStyle(
                                        fontSize: 11,
                                        color: theme.textTheme.bodySmall?.color,
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
        error: (err, _) => Center(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Icon(Icons.error_outline, size: 48, color: Colors.grey),
              const SizedBox(height: 12),
              const Text('Could not load timetable'),
              const SizedBox(height: 8),
              OutlinedButton(
                onPressed: () => ref.invalidate(timetableProvider),
                child: const Text('Retry'),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
