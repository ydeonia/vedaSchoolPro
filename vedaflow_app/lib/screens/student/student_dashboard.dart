import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:cached_network_image/cached_network_image.dart';
import 'package:percent_indicator/circular_percent_indicator.dart';
import '../../core/api_client.dart';
import '../../core/config.dart';
import '../../providers/auth_provider.dart';
import '../../providers/branding_provider.dart';
import '../../widgets/shimmer_loading.dart';
import '../../widgets/animated_card.dart';
import '../../widgets/stat_card.dart';
import '../../widgets/section_header.dart';

/// Fetches student dashboard data from API.
final studentDashboardProvider = FutureProvider<Map<String, dynamic>>((ref) async {
  final response = await api.get('/api/mobile/dashboard/student');
  return response.data;
});

class StudentDashboard extends ConsumerWidget {
  const StudentDashboard({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final user = ref.watch(currentUserProvider);
    final dashboard = ref.watch(studentDashboardProvider);
    final branding = ref.watch(brandingProvider);
    final theme = Theme.of(context);

    return Scaffold(
      body: RefreshIndicator(
        onRefresh: () async {
          ref.invalidate(studentDashboardProvider);
        },
        child: CustomScrollView(
          physics: const BouncingScrollPhysics(
            parent: AlwaysScrollableScrollPhysics(),
          ),
          slivers: [
            // ── App Bar with student info ──
            SliverAppBar(
              expandedHeight: 180,
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
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Row(
                            children: [
                              // Student photo
                              Container(
                                width: 52,
                                height: 52,
                                decoration: BoxDecoration(
                                  shape: BoxShape.circle,
                                  border: Border.all(
                                      color: Colors.white.withValues(alpha: 0.3),
                                      width: 2),
                                ),
                                child: CircleAvatar(
                                  radius: 24,
                                  backgroundColor:
                                      Colors.white.withValues(alpha: 0.2),
                                  child: user?.photoUrl != null
                                      ? ClipOval(
                                          child: CachedNetworkImage(
                                            imageUrl:
                                                '${AppConfig.apiBaseUrl}${user!.photoUrl}',
                                            fit: BoxFit.cover,
                                            width: 48,
                                            height: 48,
                                          ),
                                        )
                                      : Text(
                                          (user?.name ?? 'S')
                                              .substring(0, 1)
                                              .toUpperCase(),
                                          style: const TextStyle(
                                            color: Colors.white,
                                            fontSize: 22,
                                            fontWeight: FontWeight.w600,
                                          ),
                                        ),
                                ),
                              ),
                              const SizedBox(width: 14),
                              Expanded(
                                child: Column(
                                  crossAxisAlignment: CrossAxisAlignment.start,
                                  children: [
                                    Text(
                                      'Hi, ${user?.name.split(' ').first ?? 'Student'}!',
                                      style: const TextStyle(
                                        color: Colors.white,
                                        fontSize: 20,
                                        fontWeight: FontWeight.w600,
                                      ),
                                    ),
                                    const SizedBox(height: 2),
                                    Text(
                                      '${user?.className ?? ''} ${user?.sectionName ?? ''} | ${user?.registrationNumber ?? ''}',
                                      style: TextStyle(
                                        color: Colors.white.withValues(alpha: 0.85),
                                        fontSize: 13,
                                      ),
                                    ),
                                  ],
                                ),
                              ),
                              // School logo
                              branding.when(
                                data: (b) => b.logoUrl.isNotEmpty
                                    ? Container(
                                        width: 40,
                                        height: 40,
                                        decoration: BoxDecoration(
                                          color: Colors.white,
                                          borderRadius:
                                              BorderRadius.circular(10),
                                        ),
                                        child: ClipRRect(
                                          borderRadius:
                                              BorderRadius.circular(10),
                                          child: CachedNetworkImage(
                                            imageUrl:
                                                '${AppConfig.apiBaseUrl}${b.logoUrl}',
                                            fit: BoxFit.cover,
                                          ),
                                        ),
                                      )
                                    : const SizedBox(),
                                loading: () => const SizedBox(),
                                error: (_, __) => const SizedBox(),
                              ),
                            ],
                          ),
                        ],
                      ),
                    ),
                  ),
                ),
              ),
            ),

            // ── Dashboard Content ──
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
                error: (err, _) => SliverToBoxAdapter(
                  child: Center(
                    child: Column(
                      children: [
                        const SizedBox(height: 60),
                        Icon(Icons.cloud_off_rounded,
                            size: 56, color: theme.textTheme.bodySmall?.color),
                        const SizedBox(height: 16),
                        const Text('Could not load dashboard'),
                        const SizedBox(height: 12),
                        OutlinedButton(
                          onPressed: () =>
                              ref.invalidate(studentDashboardProvider),
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
    final attendance = data['attendance'] as Map<String, dynamic>? ?? {};
    final fees = data['fees'] as Map<String, dynamic>? ?? {};
    final timetable = data['today_timetable'] as List? ?? [];
    final homework = data['pending_homework'] as List? ?? [];
    final announcements = data['announcements'] as List? ?? [];

    return SliverList(
      delegate: SliverChildListDelegate([
        // ── Quick Stats ──
        GridView.count(
          crossAxisCount: 2,
          shrinkWrap: true,
          physics: const NeverScrollableScrollPhysics(),
          mainAxisSpacing: 12,
          crossAxisSpacing: 12,
          childAspectRatio: 1.4,
          children: [
            StatCard(
              icon: Icons.check_circle_outline_rounded,
              label: 'Attendance',
              value: '${attendance['percentage'] ?? 0}%',
              color: theme.colorScheme.primary,
              index: 0,
              onTap: () => context.go('/student/attendance'),
            ),
            StatCard(
              icon: Icons.account_balance_wallet_outlined,
              label: 'Fee Due',
              value: '\u20B9${fees['pending_amount'] ?? 0}',
              color: (fees['pending_amount'] ?? 0) > 0
                  ? const Color(0xFFEF4444)
                  : const Color(0xFF22C55E),
              index: 1,
              onTap: () => context.go('/student/fees'),
            ),
            StatCard(
              icon: Icons.assignment_outlined,
              label: 'Homework',
              value: '${homework.length}',
              color: const Color(0xFFF59E0B),
              index: 2,
              onTap: () => context.go('/student/homework'),
            ),
            StatCard(
              icon: Icons.emoji_events_outlined,
              label: 'Results',
              value: data['last_exam_rank'] ?? '-',
              color: const Color(0xFF8B5CF6),
              index: 3,
              onTap: () => context.go('/student/results'),
            ),
          ],
        ),
        const SizedBox(height: 24),

        // ── Today's Attendance Status ──
        if (attendance['today_status'] != null)
          FadeInWidget(
            delay: const Duration(milliseconds: 200),
            child: Container(
              padding: const EdgeInsets.all(16),
              decoration: BoxDecoration(
                color: attendance['today_status'] == 'present'
                    ? const Color(0xFFF0FDF4)
                    : attendance['today_status'] == 'absent'
                        ? const Color(0xFFFEF2F2)
                        : const Color(0xFFFFFBEB),
                borderRadius: BorderRadius.circular(14),
                border: Border.all(
                  color: attendance['today_status'] == 'present'
                      ? const Color(0xFFBBF7D0)
                      : attendance['today_status'] == 'absent'
                          ? const Color(0xFFFECACA)
                          : const Color(0xFFFDE68A),
                ),
              ),
              child: Row(
                children: [
                  Icon(
                    attendance['today_status'] == 'present'
                        ? Icons.check_circle_rounded
                        : attendance['today_status'] == 'absent'
                            ? Icons.cancel_rounded
                            : Icons.access_time_rounded,
                    color: attendance['today_status'] == 'present'
                        ? const Color(0xFF22C55E)
                        : attendance['today_status'] == 'absent'
                            ? const Color(0xFFEF4444)
                            : const Color(0xFFF59E0B),
                    size: 28,
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          'Today: ${(attendance['today_status'] as String).toUpperCase()}',
                          style: const TextStyle(
                            fontSize: 14,
                            fontWeight: FontWeight.w600,
                          ),
                        ),
                        if (attendance['check_in_time'] != null)
                          Text(
                            'Check-in: ${attendance['check_in_time']}',
                            style: TextStyle(
                              fontSize: 12,
                              color: theme.textTheme.bodySmall?.color,
                            ),
                          ),
                      ],
                    ),
                  ),
                  // Attendance percentage ring
                  CircularPercentIndicator(
                    radius: 24,
                    lineWidth: 4,
                    percent: ((attendance['percentage'] ?? 0) / 100)
                        .clamp(0.0, 1.0)
                        .toDouble(),
                    center: Text(
                      '${attendance['percentage'] ?? 0}%',
                      style: const TextStyle(
                          fontSize: 10, fontWeight: FontWeight.w600),
                    ),
                    progressColor: theme.colorScheme.primary,
                    backgroundColor: theme.colorScheme.primary.withValues(alpha: 0.15),
                  ),
                ],
              ),
            ),
          ),
        const SizedBox(height: 24),

        // ── Quick Actions Grid ──
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
              icon: Icons.schedule_rounded,
              label: 'Timetable',
              color: const Color(0xFF4F46E5),
              onTap: () => context.go('/student/timetable'),
              index: 0,
            ),
            QuickAction(
              icon: Icons.book_outlined,
              label: 'Homework',
              color: const Color(0xFFF59E0B),
              onTap: () => context.go('/student/homework'),
              index: 1,
            ),
            QuickAction(
              icon: Icons.event_note_outlined,
              label: 'Leave',
              color: const Color(0xFF06B6D4),
              onTap: () => context.go('/student/leave'),
              index: 2,
            ),
            QuickAction(
              icon: Icons.leaderboard_outlined,
              label: 'Results',
              color: const Color(0xFF8B5CF6),
              onTap: () => context.go('/student/results'),
              index: 3,
            ),
          ],
        ),
        const SizedBox(height: 24),

        // ── Today's Timetable ──
        if (timetable.isNotEmpty) ...[
          const SectionHeader(
            title: "Today's Classes",
            actionText: 'Full Timetable',
          ),
          ...timetable.asMap().entries.map((entry) {
            final i = entry.key;
            final period = entry.value as Map<String, dynamic>;
            return AnimatedCard(
              index: i,
              padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
              child: Row(
                children: [
                  Container(
                    width: 44,
                    height: 44,
                    decoration: BoxDecoration(
                      color: theme.colorScheme.primary.withValues(alpha: 0.1),
                      borderRadius: BorderRadius.circular(12),
                    ),
                    child: Center(
                      child: Text(
                        'P${period['period_number'] ?? i + 1}',
                        style: TextStyle(
                          fontSize: 13,
                          fontWeight: FontWeight.w700,
                          color: theme.colorScheme.primary,
                        ),
                      ),
                    ),
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          period['subject_name'] ?? 'Free',
                          style: const TextStyle(
                            fontSize: 14,
                            fontWeight: FontWeight.w600,
                          ),
                        ),
                        Text(
                          period['teacher_name'] ?? '',
                          style: TextStyle(
                            fontSize: 12,
                            color: theme.textTheme.bodySmall?.color,
                          ),
                        ),
                      ],
                    ),
                  ),
                  Text(
                    '${period['start_time'] ?? ''} - ${period['end_time'] ?? ''}',
                    style: TextStyle(
                      fontSize: 11,
                      color: theme.textTheme.bodySmall?.color,
                    ),
                  ),
                ],
              ),
            );
          }),
          const SizedBox(height: 24),
        ],

        // ── Recent Announcements ──
        if (announcements.isNotEmpty) ...[
          const SectionHeader(
            title: 'Announcements',
            icon: Icons.campaign_outlined,
          ),
          ...announcements.take(3).toList().asMap().entries.map((entry) {
            final i = entry.key;
            final ann = entry.value as Map<String, dynamic>;
            return AnimatedCard(
              index: i,
              padding: const EdgeInsets.all(14),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      Container(
                        padding: const EdgeInsets.symmetric(
                            horizontal: 8, vertical: 3),
                        decoration: BoxDecoration(
                          color: theme.colorScheme.primary.withValues(alpha: 0.1),
                          borderRadius: BorderRadius.circular(6),
                        ),
                        child: Text(
                          ann['priority'] ?? 'Info',
                          style: TextStyle(
                            fontSize: 10,
                            fontWeight: FontWeight.w600,
                            color: theme.colorScheme.primary,
                          ),
                        ),
                      ),
                      const Spacer(),
                      Text(
                        ann['date'] ?? '',
                        style: TextStyle(
                          fontSize: 11,
                          color: theme.textTheme.bodySmall?.color,
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 8),
                  Text(
                    ann['title'] ?? '',
                    style: const TextStyle(
                      fontSize: 14,
                      fontWeight: FontWeight.w600,
                    ),
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
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

        const SizedBox(height: 80), // Bottom spacing for FAB
      ]),
    );
  }
}
