import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../core/api_client.dart';
import '../../widgets/shimmer_loading.dart';
import '../../widgets/animated_card.dart';

final notificationsProvider = FutureProvider<List>((ref) async {
  final response = await api.get('/api/mobile/notifications');
  return response.data['notifications'] ?? [];
});

class NotificationsScreen extends ConsumerWidget {
  const NotificationsScreen({super.key});

  IconData _typeIcon(String? type) {
    switch (type) {
      case 'attendance':
        return Icons.check_circle_outline;
      case 'fee':
        return Icons.account_balance_wallet_outlined;
      case 'exam':
        return Icons.assignment_outlined;
      case 'homework':
        return Icons.book_outlined;
      case 'leave':
        return Icons.event_note_outlined;
      case 'announcement':
        return Icons.campaign_outlined;
      default:
        return Icons.notifications_outlined;
    }
  }

  Color _typeColor(String? type) {
    switch (type) {
      case 'attendance':
        return const Color(0xFF22C55E);
      case 'fee':
        return const Color(0xFFEF4444);
      case 'exam':
        return const Color(0xFF8B5CF6);
      case 'homework':
        return const Color(0xFFF59E0B);
      case 'leave':
        return const Color(0xFF06B6D4);
      case 'announcement':
        return const Color(0xFF4F46E5);
      default:
        return const Color(0xFF64748B);
    }
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final notifications = ref.watch(notificationsProvider);
    final theme = Theme.of(context);

    return Scaffold(
      appBar: AppBar(
        title: const Text('Notifications'),
        actions: [
          TextButton(
            onPressed: () async {
              try {
                await api.post('/api/mobile/notifications/mark-all-read');
                ref.invalidate(notificationsProvider);
              } catch (_) {}
            },
            child: const Text(
              'Mark all read',
              style: TextStyle(color: Colors.white, fontSize: 12),
            ),
          ),
        ],
      ),
      body: notifications.when(
        data: (items) {
          if (items.isEmpty) {
            return Center(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Icon(Icons.notifications_off_outlined,
                      size: 56, color: theme.textTheme.bodySmall?.color),
                  const SizedBox(height: 12),
                  const Text('No notifications'),
                ],
              ),
            );
          }

          return RefreshIndicator(
            onRefresh: () async => ref.invalidate(notificationsProvider),
            child: ListView.builder(
              padding: const EdgeInsets.all(16),
              itemCount: items.length,
              itemBuilder: (ctx, i) {
                final n = items[i] as Map<String, dynamic>;
                final isRead = n['is_read'] == true;
                final type = n['type'] as String?;

                return AnimatedCard(
                  index: i,
                  padding:
                      const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
                  child: Row(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Container(
                        width: 40,
                        height: 40,
                        decoration: BoxDecoration(
                          color: _typeColor(type).withValues(alpha: 0.1),
                          borderRadius: BorderRadius.circular(10),
                        ),
                        child:
                            Icon(_typeIcon(type), color: _typeColor(type), size: 20),
                      ),
                      const SizedBox(width: 12),
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Row(
                              children: [
                                Expanded(
                                  child: Text(
                                    n['title'] ?? '',
                                    style: TextStyle(
                                      fontSize: 14,
                                      fontWeight:
                                          isRead ? FontWeight.w500 : FontWeight.w600,
                                    ),
                                    maxLines: 1,
                                    overflow: TextOverflow.ellipsis,
                                  ),
                                ),
                                if (!isRead)
                                  Container(
                                    width: 8,
                                    height: 8,
                                    decoration: BoxDecoration(
                                      color: theme.colorScheme.primary,
                                      shape: BoxShape.circle,
                                    ),
                                  ),
                              ],
                            ),
                            const SizedBox(height: 4),
                            Text(
                              n['message'] ?? '',
                              style: TextStyle(
                                fontSize: 13,
                                color: theme.textTheme.bodySmall?.color,
                              ),
                              maxLines: 2,
                              overflow: TextOverflow.ellipsis,
                            ),
                            const SizedBox(height: 4),
                            Text(
                              n['time_ago'] ?? '',
                              style: TextStyle(
                                fontSize: 11,
                                color: theme.textTheme.bodySmall?.color,
                              ),
                            ),
                          ],
                        ),
                      ),
                    ],
                  ),
                );
              },
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
              const Text('Could not load notifications'),
              OutlinedButton(
                onPressed: () => ref.invalidate(notificationsProvider),
                child: const Text('Retry'),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
