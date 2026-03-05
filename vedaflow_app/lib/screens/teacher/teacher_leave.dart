import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../core/api_client.dart';
import '../../widgets/shimmer_loading.dart';
import '../../widgets/animated_card.dart';

/// Fetches pending leave requests for this teacher's class.
final pendingLeavesProvider = FutureProvider<List>((ref) async {
  final response = await api.get('/api/mobile/teacher/pending-leaves');
  return response.data['leaves'] ?? [];
});

class TeacherLeave extends ConsumerWidget {
  const TeacherLeave({super.key});

  Future<void> _handleLeaveAction(
      WidgetRef ref, BuildContext context, String leaveId, String action) async {
    try {
      await api.post('/api/mobile/teacher/leave/$leaveId/$action');
      HapticFeedback.mediumImpact();
      ref.invalidate(pendingLeavesProvider);
      if (context.mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text(
                'Leave ${action == 'approve' ? 'approved' : 'rejected'}'),
            backgroundColor: action == 'approve'
                ? const Color(0xFF22C55E)
                : const Color(0xFFEF4444),
          ),
        );
      }
    } catch (_) {
      if (context.mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text('Action failed'),
            backgroundColor: Color(0xFFEF4444),
          ),
        );
      }
    }
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final leaves = ref.watch(pendingLeavesProvider);
    final theme = Theme.of(context);

    return Scaffold(
      appBar: AppBar(title: const Text('Leave Requests')),
      body: leaves.when(
        data: (items) {
          if (items.isEmpty) {
            return Center(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Icon(Icons.event_available_rounded,
                      size: 56, color: theme.textTheme.bodySmall?.color),
                  const SizedBox(height: 12),
                  const Text('No pending leave requests'),
                ],
              ),
            );
          }

          return RefreshIndicator(
            onRefresh: () async => ref.invalidate(pendingLeavesProvider),
            child: ListView.builder(
              padding: const EdgeInsets.all(16),
              itemCount: items.length,
              itemBuilder: (ctx, i) {
                final leave = items[i] as Map<String, dynamic>;
                final status = leave['teacher_status'] ?? 'pending';

                return AnimatedCard(
                  index: i,
                  padding: const EdgeInsets.all(16),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Row(
                        children: [
                          CircleAvatar(
                            radius: 20,
                            backgroundColor:
                                theme.colorScheme.primary.withValues(alpha: 0.1),
                            child: Text(
                              (leave['student_name'] ?? 'S')
                                  .substring(0, 1)
                                  .toUpperCase(),
                              style: TextStyle(
                                color: theme.colorScheme.primary,
                                fontWeight: FontWeight.w600,
                              ),
                            ),
                          ),
                          const SizedBox(width: 12),
                          Expanded(
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Text(
                                  leave['student_name'] ?? '',
                                  style: const TextStyle(
                                    fontSize: 15,
                                    fontWeight: FontWeight.w600,
                                  ),
                                ),
                                Text(
                                  '${leave['class_name'] ?? ''} ${leave['section_name'] ?? ''}',
                                  style: TextStyle(
                                    fontSize: 12,
                                    color: theme.textTheme.bodySmall?.color,
                                  ),
                                ),
                              ],
                            ),
                          ),
                          Container(
                            padding: const EdgeInsets.symmetric(
                                horizontal: 8, vertical: 3),
                            decoration: BoxDecoration(
                              color: status == 'pending'
                                  ? const Color(0xFFFEF3C7)
                                  : status == 'approved'
                                      ? const Color(0xFFF0FDF4)
                                      : const Color(0xFFFEF2F2),
                              borderRadius: BorderRadius.circular(6),
                            ),
                            child: Text(
                              status.toUpperCase(),
                              style: TextStyle(
                                fontSize: 10,
                                fontWeight: FontWeight.w700,
                                color: status == 'pending'
                                    ? const Color(0xFFF59E0B)
                                    : status == 'approved'
                                        ? const Color(0xFF22C55E)
                                        : const Color(0xFFEF4444),
                              ),
                            ),
                          ),
                        ],
                      ),
                      const SizedBox(height: 12),
                      Container(
                        padding: const EdgeInsets.all(12),
                        decoration: BoxDecoration(
                          color: const Color(0xFFF8FAFC),
                          borderRadius: BorderRadius.circular(10),
                        ),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Row(
                              children: [
                                const Icon(Icons.calendar_today_outlined,
                                    size: 14, color: Color(0xFF64748B)),
                                const SizedBox(width: 6),
                                Text(
                                  '${leave['from_date']} — ${leave['to_date']}',
                                  style: const TextStyle(
                                    fontSize: 13,
                                    fontWeight: FontWeight.w500,
                                  ),
                                ),
                                const Spacer(),
                                Text(
                                  '${leave['total_days'] ?? 1} day(s)',
                                  style: TextStyle(
                                    fontSize: 12,
                                    color: theme.textTheme.bodySmall?.color,
                                  ),
                                ),
                              ],
                            ),
                            const SizedBox(height: 6),
                            Row(
                              children: [
                                const Icon(Icons.description_outlined,
                                    size: 14, color: Color(0xFF64748B)),
                                const SizedBox(width: 6),
                                Expanded(
                                  child: Text(
                                    leave['reason'] ?? 'No reason given',
                                    style: TextStyle(
                                      fontSize: 13,
                                      color: theme.textTheme.bodySmall?.color,
                                    ),
                                  ),
                                ),
                              ],
                            ),
                          ],
                        ),
                      ),
                      if (status == 'pending') ...[
                        const SizedBox(height: 14),
                        Row(
                          children: [
                            Expanded(
                              child: OutlinedButton.icon(
                                onPressed: () => _handleLeaveAction(
                                    ref, context, leave['id'], 'reject'),
                                icon: const Icon(Icons.close_rounded,
                                    size: 18, color: Color(0xFFEF4444)),
                                label: const Text('Reject',
                                    style: TextStyle(color: Color(0xFFEF4444))),
                                style: OutlinedButton.styleFrom(
                                  side: const BorderSide(
                                      color: Color(0xFFEF4444)),
                                ),
                              ),
                            ),
                            const SizedBox(width: 12),
                            Expanded(
                              child: ElevatedButton.icon(
                                onPressed: () => _handleLeaveAction(
                                    ref, context, leave['id'], 'approve'),
                                icon: const Icon(Icons.check_rounded,
                                    size: 18),
                                label: const Text('Approve'),
                                style: ElevatedButton.styleFrom(
                                  backgroundColor: const Color(0xFF22C55E),
                                ),
                              ),
                            ),
                          ],
                        ),
                      ],
                    ],
                  ),
                );
              },
            ),
          );
        },
        loading: () => Padding(
          padding: const EdgeInsets.all(16),
          child: ShimmerList(itemCount: 4),
        ),
        error: (_, __) => Center(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Text('Could not load leave requests'),
              OutlinedButton(
                onPressed: () => ref.invalidate(pendingLeavesProvider),
                child: const Text('Retry'),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
