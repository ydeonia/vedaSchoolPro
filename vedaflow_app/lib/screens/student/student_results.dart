import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../core/api_client.dart';
import '../../providers/auth_provider.dart';
import '../../widgets/shimmer_loading.dart';
import '../../widgets/animated_card.dart';
import '../../widgets/section_header.dart';

final resultsProvider =
    FutureProvider.family<Map<String, dynamic>, String>((ref, studentId) async {
  final response = await api.get('/api/mobile/results/student/$studentId');
  return response.data;
});

class StudentResults extends ConsumerWidget {
  const StudentResults({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final user = ref.watch(currentUserProvider);
    final studentId = user?.studentId ?? '';
    final results = ref.watch(resultsProvider(studentId));
    final theme = Theme.of(context);

    return Scaffold(
      appBar: AppBar(title: const Text('Results')),
      body: results.when(
        data: (data) {
          final exams = data['exams'] as List? ?? [];
          if (exams.isEmpty) {
            return Center(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Icon(Icons.assignment_outlined,
                      size: 56, color: theme.textTheme.bodySmall?.color),
                  const SizedBox(height: 12),
                  const Text('No results available yet'),
                ],
              ),
            );
          }

          return SingleChildScrollView(
            padding: const EdgeInsets.all(16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                // ── Overall Summary ──
                if (data['overall'] != null)
                  AnimatedCard(
                    index: 0,
                    padding: const EdgeInsets.all(20),
                    child: Row(
                      mainAxisAlignment: MainAxisAlignment.spaceAround,
                      children: [
                        _overviewItem(
                          'Average',
                          '${data['overall']['percentage'] ?? 0}%',
                          theme.colorScheme.primary,
                        ),
                        _overviewItem(
                          'Rank',
                          '#${data['overall']['rank'] ?? '-'}',
                          const Color(0xFF8B5CF6),
                        ),
                        _overviewItem(
                          'Grade',
                          data['overall']['grade'] ?? '-',
                          const Color(0xFF22C55E),
                        ),
                      ],
                    ),
                  ),
                const SizedBox(height: 20),

                // ── Exam-wise Results ──
                ...exams.asMap().entries.map((entry) {
                  final i = entry.key;
                  final exam = entry.value as Map<String, dynamic>;
                  final subjects = exam['subjects'] as List? ?? [];

                  return Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      SectionHeader(
                        title: exam['exam_name'] ?? 'Exam',
                        actionText: '${exam['percentage'] ?? 0}%',
                      ),
                      // Subject-wise bars
                      ...subjects.asMap().entries.map((sEntry) {
                        final j = sEntry.key;
                        final sub = sEntry.value as Map<String, dynamic>;
                        final pct = (sub['percentage'] ?? 0).toDouble();
                        return AnimatedCard(
                          index: i * 10 + j + 1,
                          padding: const EdgeInsets.symmetric(
                              horizontal: 14, vertical: 10),
                          child: Column(
                            children: [
                              Row(
                                children: [
                                  Expanded(
                                    child: Text(
                                      sub['subject_name'] ?? '',
                                      style: const TextStyle(
                                        fontSize: 13,
                                        fontWeight: FontWeight.w600,
                                      ),
                                    ),
                                  ),
                                  Text(
                                    '${sub['marks_obtained'] ?? 0}/${sub['total_marks'] ?? 100}',
                                    style: TextStyle(
                                      fontSize: 13,
                                      fontWeight: FontWeight.w600,
                                      color: pct >= 75
                                          ? const Color(0xFF22C55E)
                                          : pct >= 50
                                              ? const Color(0xFFF59E0B)
                                              : const Color(0xFFEF4444),
                                    ),
                                  ),
                                ],
                              ),
                              const SizedBox(height: 6),
                              ClipRRect(
                                borderRadius: BorderRadius.circular(4),
                                child: LinearProgressIndicator(
                                  value: (pct / 100).clamp(0.0, 1.0),
                                  backgroundColor: const Color(0xFFE2E8F0),
                                  valueColor: AlwaysStoppedAnimation(
                                    pct >= 75
                                        ? const Color(0xFF22C55E)
                                        : pct >= 50
                                            ? const Color(0xFFF59E0B)
                                            : const Color(0xFFEF4444),
                                  ),
                                  minHeight: 6,
                                ),
                              ),
                            ],
                          ),
                        );
                      }),
                      const SizedBox(height: 16),
                    ],
                  );
                }),
              ],
            ),
          );
        },
        loading: () => Padding(
          padding: const EdgeInsets.all(16),
          child: Column(
            children: [
              const ShimmerCard(height: 100),
              const SizedBox(height: 16),
              ShimmerList(itemCount: 5),
            ],
          ),
        ),
        error: (_, __) => Center(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Text('Could not load results'),
              OutlinedButton(
                onPressed: () => ref.invalidate(resultsProvider(studentId)),
                child: const Text('Retry'),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _overviewItem(String label, String value, Color color) {
    return Column(
      children: [
        Text(
          value,
          style: TextStyle(
            fontSize: 24,
            fontWeight: FontWeight.w700,
            color: color,
          ),
        ),
        Text(
          label,
          style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w500),
        ),
      ],
    );
  }
}
