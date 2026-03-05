import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../core/api_client.dart';
import '../../widgets/shimmer_loading.dart';
import '../../widgets/animated_card.dart';

final adminApprovalsProvider = FutureProvider<Map<String, dynamic>>((ref) async {
  final response = await api.get('/api/mobile/admin/pending-approvals');
  return response.data;
});

class AdminApprovals extends ConsumerWidget {
  const AdminApprovals({super.key});

  Future<void> _handleAction(WidgetRef ref, BuildContext context,
      String type, String id, String action) async {
    try {
      await api.post('/api/mobile/admin/$type/$id/$action');
      HapticFeedback.mediumImpact();
      ref.invalidate(adminApprovalsProvider);
      if (context.mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('${action == 'approve' ? 'Approved' : 'Rejected'} successfully'),
            backgroundColor:
                action == 'approve' ? const Color(0xFF22C55E) : const Color(0xFFEF4444),
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
    final approvals = ref.watch(adminApprovalsProvider);
    final theme = Theme.of(context);

    return Scaffold(
      appBar: AppBar(title: const Text('Approvals')),
      body: approvals.when(
        data: (data) {
          final leaves = data['leaves'] as List? ?? [];
          final admissions = data['admissions'] as List? ?? [];
          final feeWaivers = data['fee_waivers'] as List? ?? [];
          final complaints = data['complaints'] as List? ?? [];

          final allEmpty = leaves.isEmpty &&
              admissions.isEmpty &&
              feeWaivers.isEmpty &&
              complaints.isEmpty;

          if (allEmpty) {
            return Center(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Icon(Icons.check_circle_outline_rounded,
                      size: 64, color: theme.textTheme.bodySmall?.color),
                  const SizedBox(height: 16),
                  const Text(
                    'All caught up!',
                    style: TextStyle(fontSize: 18, fontWeight: FontWeight.w600),
                  ),
                  const SizedBox(height: 4),
                  Text(
                    'No pending approvals',
                    style: TextStyle(color: theme.textTheme.bodySmall?.color),
                  ),
                ],
              ),
            );
          }

          return DefaultTabController(
            length: 4,
            child: Column(
              children: [
                Container(
                  color: theme.colorScheme.primary,
                  child: TabBar(
                    indicatorColor: Colors.white,
                    labelColor: Colors.white,
                    unselectedLabelColor: Colors.white.withValues(alpha: 0.6),
                    tabs: [
                      Tab(text: 'Leaves (${leaves.length})'),
                      Tab(text: 'Admissions (${admissions.length})'),
                      Tab(text: 'Waivers (${feeWaivers.length})'),
                      Tab(text: 'Complaints (${complaints.length})'),
                    ],
                  ),
                ),
                Expanded(
                  child: TabBarView(
                    children: [
                      // ── Leaves Tab ──
                      _buildApprovalList(
                        context, ref, leaves, 'leave',
                        titleKey: 'student_name',
                        subtitleBuilder: (item) =>
                            '${item['from_date']} - ${item['to_date']} | ${item['reason'] ?? 'No reason'}',
                        icon: Icons.event_note_outlined,
                        color: const Color(0xFFF59E0B),
                      ),
                      // ── Admissions Tab ──
                      _buildApprovalList(
                        context, ref, admissions, 'admission',
                        titleKey: 'student_name',
                        subtitleBuilder: (item) =>
                            'Class ${item['class_name'] ?? ''} | ${item['parent_name'] ?? ''}',
                        icon: Icons.person_add_outlined,
                        color: const Color(0xFF3B82F6),
                      ),
                      // ── Fee Waivers Tab ──
                      _buildApprovalList(
                        context, ref, feeWaivers, 'fee-waiver',
                        titleKey: 'student_name',
                        subtitleBuilder: (item) =>
                            '\u20B9${item['amount'] ?? 0} waiver | ${item['reason'] ?? ''}',
                        icon: Icons.receipt_long_outlined,
                        color: const Color(0xFFEF4444),
                      ),
                      // ── Complaints Tab ──
                      _buildComplaintsList(context, ref, complaints),
                    ],
                  ),
                ),
              ],
            ),
          );
        },
        loading: () => Padding(
          padding: const EdgeInsets.all(16),
          child: ShimmerList(itemCount: 5),
        ),
        error: (_, __) => Center(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Text('Could not load approvals'),
              OutlinedButton(
                onPressed: () => ref.invalidate(adminApprovalsProvider),
                child: const Text('Retry'),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildApprovalList(
    BuildContext context,
    WidgetRef ref,
    List items,
    String type, {
    required String titleKey,
    required String Function(Map<String, dynamic>) subtitleBuilder,
    required IconData icon,
    required Color color,
  }) {
    if (items.isEmpty) {
      return Center(
        child: Text('No pending items',
            style: TextStyle(color: Theme.of(context).textTheme.bodySmall?.color)),
      );
    }

    return RefreshIndicator(
      onRefresh: () async => ref.invalidate(adminApprovalsProvider),
      child: ListView.builder(
        padding: const EdgeInsets.all(16),
        itemCount: items.length,
        itemBuilder: (ctx, i) {
          final item = items[i] as Map<String, dynamic>;
          return AnimatedCard(
            index: i,
            padding: const EdgeInsets.all(16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Container(
                      width: 40,
                      height: 40,
                      decoration: BoxDecoration(
                        color: color.withValues(alpha: 0.1),
                        borderRadius: BorderRadius.circular(10),
                      ),
                      child: Icon(icon, color: color, size: 20),
                    ),
                    const SizedBox(width: 12),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            item[titleKey] ?? '',
                            style: const TextStyle(
                              fontSize: 14,
                              fontWeight: FontWeight.w600,
                            ),
                          ),
                          Text(
                            subtitleBuilder(item),
                            style: TextStyle(
                              fontSize: 12,
                              color:
                                  Theme.of(context).textTheme.bodySmall?.color,
                            ),
                            maxLines: 2,
                            overflow: TextOverflow.ellipsis,
                          ),
                        ],
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 14),
                Row(
                  children: [
                    Expanded(
                      child: OutlinedButton(
                        onPressed: () => _handleAction(
                            ref, context, type, item['id'], 'reject'),
                        style: OutlinedButton.styleFrom(
                          side: const BorderSide(color: Color(0xFFEF4444)),
                        ),
                        child: const Text('Reject',
                            style: TextStyle(color: Color(0xFFEF4444))),
                      ),
                    ),
                    const SizedBox(width: 12),
                    Expanded(
                      child: ElevatedButton(
                        onPressed: () => _handleAction(
                            ref, context, type, item['id'], 'approve'),
                        style: ElevatedButton.styleFrom(
                          backgroundColor: const Color(0xFF22C55E),
                        ),
                        child: const Text('Approve'),
                      ),
                    ),
                  ],
                ),
              ],
            ),
          );
        },
      ),
    );
  }

  Widget _buildComplaintsList(
      BuildContext context, WidgetRef ref, List complaints) {
    if (complaints.isEmpty) {
      return Center(
        child: Text('No complaints',
            style: TextStyle(color: Theme.of(context).textTheme.bodySmall?.color)),
      );
    }

    return ListView.builder(
      padding: const EdgeInsets.all(16),
      itemCount: complaints.length,
      itemBuilder: (ctx, i) {
        final c = complaints[i] as Map<String, dynamic>;
        return AnimatedCard(
          index: i,
          padding: const EdgeInsets.all(14),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  const Icon(Icons.feedback_outlined,
                      color: Color(0xFF8B5CF6), size: 20),
                  const SizedBox(width: 8),
                  Expanded(
                    child: Text(
                      c['subject'] ?? 'Complaint',
                      style: const TextStyle(
                        fontSize: 14,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 6),
              Text(
                'From: ${c['name'] ?? ''} | ${c['date'] ?? ''}',
                style: TextStyle(
                  fontSize: 12,
                  color: Theme.of(context).textTheme.bodySmall?.color,
                ),
              ),
              if (c['message'] != null) ...[
                const SizedBox(height: 6),
                Text(
                  c['message'],
                  style: const TextStyle(fontSize: 13),
                  maxLines: 3,
                  overflow: TextOverflow.ellipsis,
                ),
              ],
            ],
          ),
        );
      },
    );
  }
}
