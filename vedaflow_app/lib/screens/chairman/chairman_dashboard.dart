import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:percent_indicator/circular_percent_indicator.dart';
import '../../core/api_client.dart';
import '../../providers/auth_provider.dart';
import '../../widgets/shimmer_loading.dart';
import '../../widgets/animated_card.dart';
import '../../widgets/stat_card.dart';
import '../../widgets/section_header.dart';

final chairmanDashboardProvider =
    FutureProvider<Map<String, dynamic>>((ref) async {
  final response = await api.get('/api/mobile/dashboard/chairman');
  return response.data;
});

class ChairmanDashboard extends ConsumerWidget {
  const ChairmanDashboard({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final user = ref.watch(currentUserProvider);
    final dashboard = ref.watch(chairmanDashboardProvider);

    return Scaffold(
      body: RefreshIndicator(
        onRefresh: () async => ref.invalidate(chairmanDashboardProvider),
        child: CustomScrollView(
          physics: const BouncingScrollPhysics(
            parent: AlwaysScrollableScrollPhysics(),
          ),
          slivers: [
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
                        const Color(0xFF1E293B),
                        const Color(0xFF334155),
                      ],
                    ),
                  ),
                  child: SafeArea(
                    child: Padding(
                      padding: const EdgeInsets.fromLTRB(20, 16, 20, 20),
                      child: Row(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Container(
                            width: 52,
                            height: 52,
                            decoration: BoxDecoration(
                              color: Colors.white.withValues(alpha: 0.15),
                              borderRadius: BorderRadius.circular(14),
                            ),
                            child: const Icon(Icons.business_rounded,
                                color: Colors.white, size: 28),
                          ),
                          const SizedBox(width: 14),
                          Expanded(
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              mainAxisSize: MainAxisSize.min,
                              children: [
                                Text(
                                  'Welcome, ${user?.name.split(' ').first ?? 'Chairman'}',
                                  style: const TextStyle(
                                    color: Colors.white,
                                    fontSize: 18,
                                    fontWeight: FontWeight.w600,
                                  ),
                                ),
                                const SizedBox(height: 2),
                                Text(
                                  'Organization Overview',
                                  style: TextStyle(
                                    color: Colors.white.withValues(alpha: 0.7),
                                    fontSize: 13,
                                  ),
                                ),
                              ],
                            ),
                          ),
                        ],
                      ),
                    ),
                  ),
                ),
              ),
            ),

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
                        const Text('Could not load data'),
                        OutlinedButton(
                          onPressed: () =>
                              ref.invalidate(chairmanDashboardProvider),
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
    final orgStats = data['organization'] as Map<String, dynamic>? ?? {};
    final branches = data['branches'] as List? ?? [];
    final financeSummary = data['finance_summary'] as Map<String, dynamic>? ?? {};
    final alerts = data['alerts'] as List? ?? [];

    return SliverList(
      delegate: SliverChildListDelegate([
        // ── Organization Stats ──
        GridView.count(
          crossAxisCount: 2,
          shrinkWrap: true,
          physics: const NeverScrollableScrollPhysics(),
          mainAxisSpacing: 12,
          crossAxisSpacing: 12,
          childAspectRatio: 1.4,
          children: [
            StatCard(
              icon: Icons.business_outlined,
              label: 'Branches',
              value: '${orgStats['total_branches'] ?? 0}',
              color: const Color(0xFF4F46E5),
              index: 0,
            ),
            StatCard(
              icon: Icons.people_outlined,
              label: 'Total Students',
              value: '${orgStats['total_students'] ?? 0}',
              color: const Color(0xFF06B6D4),
              index: 1,
            ),
            StatCard(
              icon: Icons.school_outlined,
              label: 'Total Staff',
              value: '${orgStats['total_staff'] ?? 0}',
              color: const Color(0xFF8B5CF6),
              index: 2,
            ),
            StatCard(
              icon: Icons.account_balance_wallet_outlined,
              label: 'Revenue',
              value: '\u20B9${_fmt(financeSummary['total_revenue'] ?? 0)}',
              color: const Color(0xFF22C55E),
              index: 3,
              onTap: () => context.go('/chairman/finances'),
            ),
          ],
        ),
        const SizedBox(height: 24),

        // ── Finance Overview ──
        const SectionHeader(
          title: 'Financial Summary',
          icon: Icons.account_balance_outlined,
        ),
        AnimatedCard(
          index: 4,
          padding: const EdgeInsets.all(20),
          child: Column(
            children: [
              Row(
                mainAxisAlignment: MainAxisAlignment.spaceAround,
                children: [
                  _financeMetric('Revenue',
                      '\u20B9${_fmt(financeSummary['total_revenue'] ?? 0)}',
                      const Color(0xFF22C55E)),
                  _financeMetric('Collected',
                      '\u20B9${_fmt(financeSummary['collected'] ?? 0)}',
                      const Color(0xFF3B82F6)),
                  _financeMetric('Pending',
                      '\u20B9${_fmt(financeSummary['pending'] ?? 0)}',
                      const Color(0xFFEF4444)),
                ],
              ),
              const SizedBox(height: 16),
              Row(
                mainAxisAlignment: MainAxisAlignment.spaceAround,
                children: [
                  _financeMetric('Expenses',
                      '\u20B9${_fmt(financeSummary['expenses'] ?? 0)}',
                      const Color(0xFFF59E0B)),
                  _financeMetric('Net Profit',
                      '\u20B9${_fmt(financeSummary['profit'] ?? 0)}',
                      (financeSummary['profit'] ?? 0) >= 0
                          ? const Color(0xFF22C55E)
                          : const Color(0xFFEF4444)),
                  _financeMetric('Collection %',
                      '${financeSummary['collection_percentage'] ?? 0}%',
                      theme.colorScheme.primary),
                ],
              ),
            ],
          ),
        ),
        const SizedBox(height: 24),

        // ── Branch-wise Performance ──
        if (branches.isNotEmpty) ...[
          const SectionHeader(title: 'Branch Performance'),
          ...branches.asMap().entries.map((entry) {
            final i = entry.key;
            final branch = entry.value as Map<String, dynamic>;
            final collectionPct = ((branch['collection_percentage'] ?? 0) / 100)
                .clamp(0.0, 1.0)
                .toDouble();
            final attendancePct = ((branch['attendance_percentage'] ?? 0) / 100)
                .clamp(0.0, 1.0)
                .toDouble();

            return AnimatedCard(
              index: i + 5,
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
                          color: theme.colorScheme.primary.withValues(alpha: 0.1),
                          borderRadius: BorderRadius.circular(10),
                        ),
                        child: Icon(Icons.location_city_rounded,
                            color: theme.colorScheme.primary, size: 20),
                      ),
                      const SizedBox(width: 12),
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(
                              branch['name'] ?? '',
                              style: const TextStyle(
                                fontSize: 15,
                                fontWeight: FontWeight.w600,
                              ),
                            ),
                            Text(
                              '${branch['students'] ?? 0} students | ${branch['teachers'] ?? 0} staff',
                              style: TextStyle(
                                fontSize: 12,
                                color: theme.textTheme.bodySmall?.color,
                              ),
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
                        child: Column(
                          children: [
                            CircularPercentIndicator(
                              radius: 28,
                              lineWidth: 5,
                              percent: collectionPct,
                              center: Text(
                                '${branch['collection_percentage'] ?? 0}%',
                                style: const TextStyle(
                                    fontSize: 10, fontWeight: FontWeight.w600),
                              ),
                              progressColor: const Color(0xFF22C55E),
                              backgroundColor: const Color(0xFFE2E8F0),
                            ),
                            const SizedBox(height: 4),
                            const Text('Fee',
                                style: TextStyle(
                                    fontSize: 10, fontWeight: FontWeight.w500)),
                          ],
                        ),
                      ),
                      Expanded(
                        child: Column(
                          children: [
                            CircularPercentIndicator(
                              radius: 28,
                              lineWidth: 5,
                              percent: attendancePct,
                              center: Text(
                                '${branch['attendance_percentage'] ?? 0}%',
                                style: const TextStyle(
                                    fontSize: 10, fontWeight: FontWeight.w600),
                              ),
                              progressColor: const Color(0xFF3B82F6),
                              backgroundColor: const Color(0xFFE2E8F0),
                            ),
                            const SizedBox(height: 4),
                            const Text('Attendance',
                                style: TextStyle(
                                    fontSize: 10, fontWeight: FontWeight.w500)),
                          ],
                        ),
                      ),
                      Expanded(
                        child: Column(
                          children: [
                            Text(
                              '\u20B9${_fmt(branch['revenue'] ?? 0)}',
                              style: const TextStyle(
                                fontSize: 16,
                                fontWeight: FontWeight.w700,
                                color: Color(0xFF22C55E),
                              ),
                            ),
                            const SizedBox(height: 4),
                            const Text('Revenue',
                                style: TextStyle(
                                    fontSize: 10, fontWeight: FontWeight.w500)),
                          ],
                        ),
                      ),
                    ],
                  ),
                ],
              ),
            );
          }),
          const SizedBox(height: 24),
        ],

        // ── Alerts ──
        if (alerts.isNotEmpty) ...[
          const SectionHeader(
            title: 'Alerts & Notices',
            icon: Icons.warning_amber_rounded,
          ),
          ...alerts.take(5).toList().asMap().entries.map((entry) {
            final i = entry.key;
            final alert = entry.value as Map<String, dynamic>;
            final isWarning = alert['severity'] == 'warning' ||
                alert['severity'] == 'critical';
            return AnimatedCard(
              index: i + branches.length + 5,
              padding: const EdgeInsets.all(14),
              child: Row(
                children: [
                  Icon(
                    isWarning
                        ? Icons.warning_amber_rounded
                        : Icons.info_outline_rounded,
                    color: isWarning
                        ? const Color(0xFFEF4444)
                        : const Color(0xFF3B82F6),
                    size: 22,
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          alert['title'] ?? '',
                          style: const TextStyle(
                            fontSize: 13,
                            fontWeight: FontWeight.w600,
                          ),
                        ),
                        if (alert['message'] != null)
                          Text(
                            alert['message'],
                            style: TextStyle(
                              fontSize: 12,
                              color: theme.textTheme.bodySmall?.color,
                            ),
                            maxLines: 2,
                            overflow: TextOverflow.ellipsis,
                          ),
                      ],
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

  Widget _financeMetric(String label, String value, Color color) {
    return Column(
      children: [
        Text(
          value,
          style: TextStyle(
            fontSize: 15,
            fontWeight: FontWeight.w700,
            color: color,
          ),
        ),
        const SizedBox(height: 2),
        Text(label, style: const TextStyle(fontSize: 10, fontWeight: FontWeight.w500)),
      ],
    );
  }

  String _fmt(dynamic amount) {
    final num val = amount is num ? amount : 0;
    if (val >= 10000000) return '${(val / 10000000).toStringAsFixed(1)}Cr';
    if (val >= 100000) return '${(val / 100000).toStringAsFixed(1)}L';
    if (val >= 1000) return '${(val / 1000).toStringAsFixed(1)}K';
    return val.toStringAsFixed(0);
  }
}
