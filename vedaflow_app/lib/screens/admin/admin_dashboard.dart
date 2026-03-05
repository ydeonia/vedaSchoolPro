import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:percent_indicator/circular_percent_indicator.dart';
import '../../core/api_client.dart';
import '../../providers/auth_provider.dart';
import '../../providers/branding_provider.dart';
import '../../widgets/shimmer_loading.dart';
import '../../widgets/animated_card.dart';
import '../../widgets/stat_card.dart';
import '../../widgets/section_header.dart';

final adminDashboardProvider = FutureProvider<Map<String, dynamic>>((ref) async {
  final response = await api.get('/api/mobile/dashboard/admin');
  return response.data;
});

class AdminDashboard extends ConsumerWidget {
  const AdminDashboard({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final user = ref.watch(currentUserProvider);
    final dashboard = ref.watch(adminDashboardProvider);
    final branding = ref.watch(brandingProvider);
    final theme = Theme.of(context);

    return Scaffold(
      body: RefreshIndicator(
        onRefresh: () async => ref.invalidate(adminDashboardProvider),
        child: CustomScrollView(
          physics: const BouncingScrollPhysics(
            parent: AlwaysScrollableScrollPhysics(),
          ),
          slivers: [
            // ── App Bar ──
            SliverAppBar(
              expandedHeight: 160,
              floating: false,
              pinned: true,
              flexibleSpace: FlexibleSpaceBar(
                background: Container(
                  decoration: BoxDecoration(
                    gradient: LinearGradient(
                      begin: Alignment.topLeft,
                      end: Alignment.bottomRight,
                      colors: [
                        theme.colorScheme.primary,
                        theme.colorScheme.primary.withValues(alpha: 0.8),
                      ],
                    ),
                  ),
                  child: SafeArea(
                    child: Padding(
                      padding: const EdgeInsets.fromLTRB(20, 16, 20, 20),
                      child: Row(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          CircleAvatar(
                            radius: 26,
                            backgroundColor: Colors.white.withValues(alpha: 0.2),
                            child: const Icon(Icons.admin_panel_settings_rounded,
                                color: Colors.white, size: 28),
                          ),
                          const SizedBox(width: 14),
                          Expanded(
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              mainAxisSize: MainAxisSize.min,
                              children: [
                                Text(
                                  'Hi, ${user?.name.split(' ').first ?? 'Admin'}!',
                                  style: const TextStyle(
                                    color: Colors.white,
                                    fontSize: 18,
                                    fontWeight: FontWeight.w600,
                                  ),
                                ),
                                const SizedBox(height: 2),
                                Text(
                                  branding.valueOrNull?.schoolName ?? 'School Admin',
                                  style: TextStyle(
                                    color: Colors.white.withValues(alpha: 0.8),
                                    fontSize: 13,
                                  ),
                                ),
                              ],
                            ),
                          ),
                          // Quick action: Announcement
                          IconButton(
                            icon: Container(
                              padding: const EdgeInsets.all(8),
                              decoration: BoxDecoration(
                                color: Colors.white.withValues(alpha: 0.2),
                                borderRadius: BorderRadius.circular(10),
                              ),
                              child: const Icon(Icons.campaign_rounded,
                                  color: Colors.white, size: 20),
                            ),
                            onPressed: () => context.go('/admin/announcements'),
                          ),
                        ],
                      ),
                    ),
                  ),
                ),
              ),
            ),

            // ── Content ──
            SliverPadding(
              padding: const EdgeInsets.all(16),
              sliver: dashboard.when(
                data: (data) => _buildContent(context, data, ref),
                loading: () => SliverToBoxAdapter(
                  child: Column(
                    children: List.generate(
                      4,
                      (i) => const Padding(
                        padding: EdgeInsets.only(bottom: 12),
                        child: ShimmerCard(height: 100),
                      ),
                    ),
                  ),
                ),
                error: (_, __) => SliverToBoxAdapter(
                  child: Center(
                    child: Column(
                      children: [
                        const SizedBox(height: 60),
                        const Icon(Icons.cloud_off_rounded,
                            size: 56, color: Colors.grey),
                        const SizedBox(height: 12),
                        const Text('Could not load dashboard'),
                        OutlinedButton(
                          onPressed: () => ref.invalidate(adminDashboardProvider),
                          child: const Text('Retry'),
                        ),
                      ],
                    ),
                  ),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  SliverList _buildContent(
      BuildContext context, Map<String, dynamic> data, WidgetRef ref) {
    final theme = Theme.of(context);
    final stats = data['stats'] as Map<String, dynamic>? ?? {};
    final feeStats = data['fee_stats'] as Map<String, dynamic>? ?? {};
    final attendanceStats = data['attendance_stats'] as Map<String, dynamic>? ?? {};
    final pendingApprovals = data['pending_approvals'] as Map<String, dynamic>? ?? {};
    final recentAdmissions = data['recent_admissions'] as List? ?? [];
    final alerts = data['alerts'] as List? ?? [];

    return SliverList(
      delegate: SliverChildListDelegate([
        // ── Key Metrics ──
        GridView.count(
          crossAxisCount: 2,
          shrinkWrap: true,
          physics: const NeverScrollableScrollPhysics(),
          mainAxisSpacing: 12,
          crossAxisSpacing: 12,
          childAspectRatio: 1.4,
          children: [
            StatCard(
              icon: Icons.people_outlined,
              label: 'Total Students',
              value: '${stats['total_students'] ?? 0}',
              color: theme.colorScheme.primary,
              index: 0,
              onTap: () => context.go('/admin/students'),
            ),
            StatCard(
              icon: Icons.school_outlined,
              label: 'Total Teachers',
              value: '${stats['total_teachers'] ?? 0}',
              color: const Color(0xFF8B5CF6),
              index: 1,
              onTap: () => context.go('/admin/teachers'),
            ),
            StatCard(
              icon: Icons.account_balance_wallet_outlined,
              label: 'Fee Collected',
              value: '\u20B9${_formatAmount(feeStats['collected'] ?? 0)}',
              color: const Color(0xFF22C55E),
              index: 2,
              onTap: () => context.go('/admin/fees'),
            ),
            StatCard(
              icon: Icons.money_off_outlined,
              label: 'Fee Pending',
              value: '\u20B9${_formatAmount(feeStats['pending'] ?? 0)}',
              color: const Color(0xFFEF4444),
              index: 3,
              onTap: () => context.go('/admin/fees'),
            ),
          ],
        ),
        const SizedBox(height: 24),

        // ── Today's Attendance Overview ──
        const SectionHeader(title: "Today's Attendance"),
        AnimatedCard(
          index: 4,
          padding: const EdgeInsets.all(20),
          child: Row(
            mainAxisAlignment: MainAxisAlignment.spaceAround,
            children: [
              CircularPercentIndicator(
                radius: 40,
                lineWidth: 6,
                percent: ((attendanceStats['student_percentage'] ?? 0) / 100)
                    .clamp(0.0, 1.0)
                    .toDouble(),
                center: Text(
                  '${attendanceStats['student_percentage'] ?? 0}%',
                  style: const TextStyle(
                    fontSize: 14,
                    fontWeight: FontWeight.w700,
                  ),
                ),
                progressColor: const Color(0xFF22C55E),
                backgroundColor: const Color(0xFFE2E8F0),
                footer: const Padding(
                  padding: EdgeInsets.only(top: 8),
                  child: Text('Students',
                      style: TextStyle(fontSize: 11, fontWeight: FontWeight.w500)),
                ),
              ),
              CircularPercentIndicator(
                radius: 40,
                lineWidth: 6,
                percent: ((attendanceStats['teacher_percentage'] ?? 0) / 100)
                    .clamp(0.0, 1.0)
                    .toDouble(),
                center: Text(
                  '${attendanceStats['teacher_percentage'] ?? 0}%',
                  style: const TextStyle(
                    fontSize: 14,
                    fontWeight: FontWeight.w700,
                  ),
                ),
                progressColor: theme.colorScheme.primary,
                backgroundColor: const Color(0xFFE2E8F0),
                footer: const Padding(
                  padding: EdgeInsets.only(top: 8),
                  child: Text('Teachers',
                      style: TextStyle(fontSize: 11, fontWeight: FontWeight.w500)),
                ),
              ),
              Column(
                children: [
                  Text(
                    '${attendanceStats['students_present'] ?? 0}',
                    style: const TextStyle(
                      fontSize: 22,
                      fontWeight: FontWeight.w700,
                      color: Color(0xFF22C55E),
                    ),
                  ),
                  Text(
                    'of ${attendanceStats['total_students'] ?? 0}',
                    style: const TextStyle(fontSize: 11),
                  ),
                  const SizedBox(height: 4),
                  const Text('Present',
                      style: TextStyle(fontSize: 11, fontWeight: FontWeight.w500)),
                ],
              ),
            ],
          ),
        ),
        const SizedBox(height: 24),

        // ── Pending Approvals ──
        const SectionHeader(
          title: 'Pending Approvals',
          icon: Icons.pending_actions_outlined,
        ),
        AnimatedCard(
          index: 5,
          padding: const EdgeInsets.all(16),
          child: Column(
            children: [
              _approvalRow(
                context,
                Icons.event_note_outlined,
                'Leave Requests',
                pendingApprovals['leaves'] ?? 0,
                const Color(0xFFF59E0B),
                () => context.go('/admin/approvals'),
              ),
              const Divider(height: 20),
              _approvalRow(
                context,
                Icons.person_add_outlined,
                'New Admissions',
                pendingApprovals['admissions'] ?? 0,
                const Color(0xFF3B82F6),
                () => context.go('/admin/admissions'),
              ),
              const Divider(height: 20),
              _approvalRow(
                context,
                Icons.receipt_long_outlined,
                'Fee Waivers',
                pendingApprovals['fee_waivers'] ?? 0,
                const Color(0xFFEF4444),
                () => context.go('/admin/approvals'),
              ),
              const Divider(height: 20),
              _approvalRow(
                context,
                Icons.feedback_outlined,
                'Complaints',
                pendingApprovals['complaints'] ?? 0,
                const Color(0xFF8B5CF6),
                () => context.go('/admin/approvals'),
              ),
            ],
          ),
        ),
        const SizedBox(height: 24),

        // ── Quick Actions ──
        const SectionHeader(title: 'Quick Actions'),
        GridView.count(
          crossAxisCount: 4,
          shrinkWrap: true,
          physics: const NeverScrollableScrollPhysics(),
          mainAxisSpacing: 8,
          crossAxisSpacing: 8,
          childAspectRatio: 0.85,
          children: [
            QuickAction(
              icon: Icons.campaign_rounded,
              label: 'Announce',
              color: const Color(0xFFEF4444),
              onTap: () => context.go('/admin/announcements'),
              index: 0,
            ),
            QuickAction(
              icon: Icons.person_add_rounded,
              label: 'Add Student',
              color: const Color(0xFF4F46E5),
              onTap: () => context.go('/admin/add-student'),
              index: 1,
            ),
            QuickAction(
              icon: Icons.receipt_long_rounded,
              label: 'Collect Fee',
              color: const Color(0xFF22C55E),
              onTap: () => context.go('/admin/fees'),
              index: 2,
            ),
            QuickAction(
              icon: Icons.qr_code_scanner_rounded,
              label: 'QR Attend.',
              color: const Color(0xFF06B6D4),
              onTap: () => context.go('/admin/qr-attendance'),
              index: 3,
            ),
          ],
        ),
        const SizedBox(height: 24),

        // ── Fee Collection Summary ──
        const SectionHeader(title: 'Fee Collection'),
        AnimatedCard(
          index: 8,
          padding: const EdgeInsets.all(16),
          child: Column(
            children: [
              Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  _feeMetric('Total', '\u20B9${_formatAmount(feeStats['total'] ?? 0)}',
                      theme.textTheme.bodyLarge?.color ?? Colors.black),
                  _feeMetric('Collected',
                      '\u20B9${_formatAmount(feeStats['collected'] ?? 0)}',
                      const Color(0xFF22C55E)),
                  _feeMetric('Pending',
                      '\u20B9${_formatAmount(feeStats['pending'] ?? 0)}',
                      const Color(0xFFEF4444)),
                ],
              ),
              const SizedBox(height: 14),
              ClipRRect(
                borderRadius: BorderRadius.circular(6),
                child: LinearProgressIndicator(
                  value: ((feeStats['collected'] ?? 0) /
                          ((feeStats['total'] ?? 1) == 0 ? 1 : feeStats['total']))
                      .clamp(0.0, 1.0)
                      .toDouble(),
                  backgroundColor: const Color(0xFFE2E8F0),
                  valueColor:
                      AlwaysStoppedAnimation(theme.colorScheme.primary),
                  minHeight: 8,
                ),
              ),
              const SizedBox(height: 6),
              Text(
                '${(((feeStats['collected'] ?? 0) / ((feeStats['total'] ?? 1) == 0 ? 1 : feeStats['total'])) * 100).toStringAsFixed(1)}% collected',
                style: TextStyle(
                  fontSize: 12,
                  color: theme.textTheme.bodySmall?.color,
                ),
              ),
            ],
          ),
        ),
        const SizedBox(height: 24),

        // ── Recent Admissions ──
        if (recentAdmissions.isNotEmpty) ...[
          SectionHeader(
            title: 'Recent Admissions',
            actionText: 'View All',
            onAction: () => context.go('/admin/admissions'),
          ),
          ...recentAdmissions.take(5).toList().asMap().entries.map((entry) {
            final i = entry.key;
            final adm = entry.value as Map<String, dynamic>;
            return AnimatedCard(
              index: i + 9,
              padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
              child: Row(
                children: [
                  CircleAvatar(
                    radius: 18,
                    backgroundColor:
                        theme.colorScheme.primary.withValues(alpha: 0.1),
                    child: Text(
                      (adm['name'] ?? 'S').substring(0, 1).toUpperCase(),
                      style: TextStyle(
                        color: theme.colorScheme.primary,
                        fontWeight: FontWeight.w600,
                        fontSize: 14,
                      ),
                    ),
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          adm['name'] ?? '',
                          style: const TextStyle(
                            fontSize: 13,
                            fontWeight: FontWeight.w600,
                          ),
                        ),
                        Text(
                          'Class ${adm['class_name'] ?? ''} | ${adm['date'] ?? ''}',
                          style: TextStyle(
                            fontSize: 11,
                            color: theme.textTheme.bodySmall?.color,
                          ),
                        ),
                      ],
                    ),
                  ),
                  Container(
                    padding:
                        const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                    decoration: BoxDecoration(
                      color: const Color(0xFFF0FDF4),
                      borderRadius: BorderRadius.circular(6),
                    ),
                    child: const Text(
                      'NEW',
                      style: TextStyle(
                        fontSize: 9,
                        fontWeight: FontWeight.w700,
                        color: Color(0xFF22C55E),
                      ),
                    ),
                  ),
                ],
              ),
            );
          }),
        ],

        // ── System Alerts ──
        if (alerts.isNotEmpty) ...[
          const SizedBox(height: 24),
          const SectionHeader(
            title: 'System Alerts',
            icon: Icons.warning_amber_rounded,
          ),
          ...alerts.take(3).toList().asMap().entries.map((entry) {
            final i = entry.key;
            final alert = entry.value as Map<String, dynamic>;
            final isWarning = alert['type'] == 'warning';
            return AnimatedCard(
              index: i + 14,
              padding: const EdgeInsets.all(14),
              child: Row(
                children: [
                  Icon(
                    isWarning
                        ? Icons.warning_amber_rounded
                        : Icons.info_outline_rounded,
                    color: isWarning
                        ? const Color(0xFFF59E0B)
                        : const Color(0xFF3B82F6),
                    size: 22,
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: Text(
                      alert['message'] ?? '',
                      style: const TextStyle(fontSize: 13),
                    ),
                  ),
                ],
              ),
            );
          }),
        ],

        const SizedBox(height: 80),
      ]),
    );
  }

  Widget _approvalRow(BuildContext context, IconData icon, String label,
      int count, Color color, VoidCallback onTap) {
    return GestureDetector(
      onTap: onTap,
      child: Row(
        children: [
          Container(
            width: 36,
            height: 36,
            decoration: BoxDecoration(
              color: color.withValues(alpha: 0.1),
              borderRadius: BorderRadius.circular(8),
            ),
            child: Icon(icon, color: color, size: 18),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Text(label,
                style: const TextStyle(fontSize: 14, fontWeight: FontWeight.w500)),
          ),
          if (count > 0)
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
              decoration: BoxDecoration(
                color: color.withValues(alpha: 0.1),
                borderRadius: BorderRadius.circular(12),
              ),
              child: Text(
                '$count',
                style: TextStyle(
                  fontSize: 13,
                  fontWeight: FontWeight.w700,
                  color: color,
                ),
              ),
            )
          else
            Icon(Icons.check_circle_rounded,
                color: Colors.green.shade300, size: 20),
          const SizedBox(width: 4),
          Icon(Icons.chevron_right_rounded,
              size: 18, color: Theme.of(context).textTheme.bodySmall?.color),
        ],
      ),
    );
  }

  Widget _feeMetric(String label, String value, Color color) {
    return Column(
      children: [
        Text(
          value,
          style: TextStyle(
            fontSize: 16,
            fontWeight: FontWeight.w700,
            color: color,
          ),
        ),
        const SizedBox(height: 2),
        Text(label, style: const TextStyle(fontSize: 11, fontWeight: FontWeight.w500)),
      ],
    );
  }

  String _formatAmount(dynamic amount) {
    final num val = amount is num ? amount : 0;
    if (val >= 10000000) return '${(val / 10000000).toStringAsFixed(1)}Cr';
    if (val >= 100000) return '${(val / 100000).toStringAsFixed(1)}L';
    if (val >= 1000) return '${(val / 1000).toStringAsFixed(1)}K';
    return val.toStringAsFixed(0);
  }
}
