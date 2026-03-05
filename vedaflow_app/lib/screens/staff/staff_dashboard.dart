import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:intl/intl.dart';
import '../../core/api_client.dart';
import '../../providers/auth_provider.dart';
import '../../providers/branding_provider.dart';
import '../../widgets/shimmer_loading.dart';
import '../../widgets/animated_card.dart';
import '../../widgets/stat_card.dart';
import '../../widgets/section_header.dart';

final staffDashboardProvider = FutureProvider<Map<String, dynamic>>((ref) async {
  final response = await api.get('/api/mobile/dashboard/staff');
  return response.data;
});

class StaffDashboard extends ConsumerWidget {
  const StaffDashboard({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final user = ref.watch(currentUserProvider);
    final dashboard = ref.watch(staffDashboardProvider);
    final branding = ref.watch(brandingProvider);
    final theme = Theme.of(context);

    return Scaffold(
      body: RefreshIndicator(
        onRefresh: () async => ref.invalidate(staffDashboardProvider),
        child: CustomScrollView(
          physics: const BouncingScrollPhysics(
            parent: AlwaysScrollableScrollPhysics(),
          ),
          slivers: [
            SliverAppBar(
              expandedHeight: 150,
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
                        theme.colorScheme.primary.withValues(alpha: 0.85),
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
                            child: Text(
                              (user?.name ?? 'S').substring(0, 1).toUpperCase(),
                              style: const TextStyle(
                                color: Colors.white,
                                fontSize: 22,
                                fontWeight: FontWeight.w600,
                              ),
                            ),
                          ),
                          const SizedBox(width: 14),
                          Expanded(
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              mainAxisSize: MainAxisSize.min,
                              children: [
                                Text(
                                  'Hi, ${user?.name.split(' ').first ?? 'Staff'}!',
                                  style: const TextStyle(
                                    color: Colors.white,
                                    fontSize: 18,
                                    fontWeight: FontWeight.w600,
                                  ),
                                ),
                                const SizedBox(height: 2),
                                Text(
                                  branding.valueOrNull?.schoolName ?? '',
                                  style: TextStyle(
                                    color: Colors.white.withValues(alpha: 0.8),
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
                      3,
                      (i) => const Padding(
                        padding: EdgeInsets.only(bottom: 12),
                        child: ShimmerCard(height: 80),
                      ),
                    ),
                  ),
                ),
                error: (_, __) => SliverToBoxAdapter(
                  child: Center(
                    child: Column(
                      children: [
                        const SizedBox(height: 60),
                        const Text('Could not load dashboard'),
                        OutlinedButton(
                          onPressed: () => ref.invalidate(staffDashboardProvider),
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
    final attendance = data['my_attendance'] as Map<String, dynamic>? ?? {};
    final leaveBalance = data['leave_balance'] as Map<String, dynamic>? ?? {};
    final salary = data['salary'] as Map<String, dynamic>? ?? {};
    final announcements = data['announcements'] as List? ?? [];

    return SliverList(
      delegate: SliverChildListDelegate([
        // ── Today's Attendance Status ──
        AnimatedCard(
          index: 0,
          padding: const EdgeInsets.all(16),
          child: Row(
            children: [
              Container(
                width: 50,
                height: 50,
                decoration: BoxDecoration(
                  color: attendance['today_status'] == 'present'
                      ? const Color(0xFFF0FDF4)
                      : attendance['today_status'] == 'absent'
                          ? const Color(0xFFFEF2F2)
                          : const Color(0xFFF8FAFC),
                  borderRadius: BorderRadius.circular(14),
                ),
                child: Icon(
                  attendance['today_status'] == 'present'
                      ? Icons.check_circle_rounded
                      : attendance['today_status'] == 'absent'
                          ? Icons.cancel_rounded
                          : Icons.access_time_rounded,
                  color: attendance['today_status'] == 'present'
                      ? const Color(0xFF22C55E)
                      : attendance['today_status'] == 'absent'
                          ? const Color(0xFFEF4444)
                          : const Color(0xFF64748B),
                  size: 28,
                ),
              ),
              const SizedBox(width: 14),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      'Today: ${(attendance['today_status'] ?? 'Not Marked').toString().toUpperCase()}',
                      style: const TextStyle(
                        fontSize: 15,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                    if (attendance['check_in'] != null)
                      Text(
                        'In: ${attendance['check_in']}${attendance['check_out'] != null ? ' | Out: ${attendance['check_out']}' : ''}',
                        style: TextStyle(
                          fontSize: 12,
                          color: theme.textTheme.bodySmall?.color,
                        ),
                      ),
                  ],
                ),
              ),
              Column(
                children: [
                  Text(
                    '${attendance['percentage'] ?? 0}%',
                    style: TextStyle(
                      fontSize: 20,
                      fontWeight: FontWeight.w700,
                      color: theme.colorScheme.primary,
                    ),
                  ),
                  Text(
                    'This Month',
                    style: TextStyle(
                      fontSize: 10,
                      color: theme.textTheme.bodySmall?.color,
                    ),
                  ),
                ],
              ),
            ],
          ),
        ),
        const SizedBox(height: 16),

        // ── Quick Stats ──
        GridView.count(
          crossAxisCount: 2,
          shrinkWrap: true,
          physics: const NeverScrollableScrollPhysics(),
          mainAxisSpacing: 12,
          crossAxisSpacing: 12,
          childAspectRatio: 1.5,
          children: [
            StatCard(
              icon: Icons.event_available_outlined,
              label: 'Present Days',
              value: '${attendance['present_days'] ?? 0}',
              color: const Color(0xFF22C55E),
              index: 1,
            ),
            StatCard(
              icon: Icons.event_busy_outlined,
              label: 'Absent Days',
              value: '${attendance['absent_days'] ?? 0}',
              color: const Color(0xFFEF4444),
              index: 2,
            ),
          ],
        ),
        const SizedBox(height: 24),

        // ── Leave Balance ──
        const SectionHeader(
          title: 'Leave Balance',
          icon: Icons.event_note_outlined,
        ),
        AnimatedCard(
          index: 3,
          padding: const EdgeInsets.all(16),
          child: Row(
            mainAxisAlignment: MainAxisAlignment.spaceAround,
            children: [
              _leaveBalanceItem('Casual', leaveBalance['casual_remaining'] ?? 0,
                  leaveBalance['casual_total'] ?? 12, const Color(0xFF3B82F6)),
              _leaveBalanceItem('Sick', leaveBalance['sick_remaining'] ?? 0,
                  leaveBalance['sick_total'] ?? 12, const Color(0xFFF59E0B)),
              _leaveBalanceItem('Earned', leaveBalance['earned_remaining'] ?? 0,
                  leaveBalance['earned_total'] ?? 15, const Color(0xFF22C55E)),
            ],
          ),
        ),
        const SizedBox(height: 24),

        // ── Salary Info ──
        if (salary.isNotEmpty) ...[
          const SectionHeader(
            title: 'Salary',
            icon: Icons.account_balance_wallet_outlined,
          ),
          AnimatedCard(
            index: 4,
            padding: const EdgeInsets.all(16),
            child: Column(
              children: [
                Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          'Last Credited',
                          style: TextStyle(
                            fontSize: 12,
                            color: theme.textTheme.bodySmall?.color,
                          ),
                        ),
                        Text(
                          '\u20B9${salary['last_amount'] ?? 0}',
                          style: const TextStyle(
                            fontSize: 22,
                            fontWeight: FontWeight.w700,
                            color: Color(0xFF22C55E),
                          ),
                        ),
                      ],
                    ),
                    Column(
                      crossAxisAlignment: CrossAxisAlignment.end,
                      children: [
                        Text(
                          'Month',
                          style: TextStyle(
                            fontSize: 12,
                            color: theme.textTheme.bodySmall?.color,
                          ),
                        ),
                        Text(
                          salary['month'] ?? DateFormat('MMMM yyyy').format(DateTime.now()),
                          style: const TextStyle(
                            fontSize: 14,
                            fontWeight: FontWeight.w600,
                          ),
                        ),
                      ],
                    ),
                  ],
                ),
                if (salary['credited_date'] != null) ...[
                  const SizedBox(height: 8),
                  Row(
                    children: [
                      Icon(Icons.calendar_today_outlined,
                          size: 14, color: theme.textTheme.bodySmall?.color),
                      const SizedBox(width: 6),
                      Text(
                        'Credited on ${salary['credited_date']}',
                        style: TextStyle(
                          fontSize: 12,
                          color: theme.textTheme.bodySmall?.color,
                        ),
                      ),
                    ],
                  ),
                ],
              ],
            ),
          ),
          const SizedBox(height: 24),
        ],

        // ── Announcements ──
        if (announcements.isNotEmpty) ...[
          const SectionHeader(
            title: 'Announcements',
            icon: Icons.campaign_outlined,
          ),
          ...announcements.take(3).toList().asMap().entries.map((entry) {
            final i = entry.key;
            final ann = entry.value as Map<String, dynamic>;
            return AnimatedCard(
              index: i + 5,
              padding: const EdgeInsets.all(14),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    ann['title'] ?? '',
                    style: const TextStyle(
                      fontSize: 14,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                  if (ann['message'] != null) ...[
                    const SizedBox(height: 4),
                    Text(
                      ann['message'],
                      style: TextStyle(
                        fontSize: 12,
                        color: theme.textTheme.bodySmall?.color,
                      ),
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                    ),
                  ],
                ],
              ),
            );
          }),
        ],

        const SizedBox(height: 80),
      ]),
    );
  }

  Widget _leaveBalanceItem(String type, int remaining, int total, Color color) {
    return Column(
      children: [
        Stack(
          alignment: Alignment.center,
          children: [
            SizedBox(
              width: 52,
              height: 52,
              child: CircularProgressIndicator(
                value: total > 0 ? (remaining / total).clamp(0.0, 1.0) : 0,
                strokeWidth: 5,
                backgroundColor: const Color(0xFFE2E8F0),
                valueColor: AlwaysStoppedAnimation(color),
              ),
            ),
            Text(
              '$remaining',
              style: TextStyle(
                fontSize: 16,
                fontWeight: FontWeight.w700,
                color: color,
              ),
            ),
          ],
        ),
        const SizedBox(height: 6),
        Text(
          type,
          style: const TextStyle(fontSize: 11, fontWeight: FontWeight.w500),
        ),
        Text(
          'of $total',
          style: const TextStyle(fontSize: 10, color: Color(0xFF94A3B8)),
        ),
      ],
    );
  }
}
