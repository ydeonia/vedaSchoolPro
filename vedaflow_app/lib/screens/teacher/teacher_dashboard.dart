import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:cached_network_image/cached_network_image.dart';
import '../../core/api_client.dart';
import '../../core/config.dart';
import '../../providers/auth_provider.dart';
import '../../providers/branding_provider.dart';
import '../../widgets/shimmer_loading.dart';
import '../../widgets/animated_card.dart';
import '../../widgets/stat_card.dart';
import '../../widgets/section_header.dart';

final teacherDashboardProvider = FutureProvider<Map<String, dynamic>>((ref) async {
  final response = await api.get('/api/mobile/dashboard/teacher');
  return response.data;
});

class TeacherDashboard extends ConsumerWidget {
  const TeacherDashboard({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final user = ref.watch(currentUserProvider);
    final dashboard = ref.watch(teacherDashboardProvider);
    final branding = ref.watch(brandingProvider);
    final theme = Theme.of(context);

    return Scaffold(
      body: RefreshIndicator(
        onRefresh: () async => ref.invalidate(teacherDashboardProvider),
        child: CustomScrollView(
          physics: const BouncingScrollPhysics(
            parent: AlwaysScrollableScrollPhysics(),
          ),
          slivers: [
            // ── Header ──
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
                            child: user?.photoUrl != null
                                ? ClipOval(
                                    child: CachedNetworkImage(
                                      imageUrl:
                                          '${AppConfig.apiBaseUrl}${user!.photoUrl}',
                                      width: 48,
                                      height: 48,
                                      fit: BoxFit.cover,
                                    ),
                                  )
                                : Text(
                                    (user?.name ?? 'T').substring(0, 1).toUpperCase(),
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
                                  'Good ${_greeting()}, ${user?.name.split(' ').first ?? 'Teacher'}!',
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

            // ── Dashboard Content ──
            SliverPadding(
              padding: const EdgeInsets.all(16),
              sliver: dashboard.when(
                data: (data) => _buildContent(context, data),
                loading: () => SliverToBoxAdapter(
                  child: Column(
                    children: List.generate(
                      3,
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
                          onPressed: () =>
                              ref.invalidate(teacherDashboardProvider),
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

  String _greeting() {
    final hour = DateTime.now().hour;
    if (hour < 12) return 'Morning';
    if (hour < 17) return 'Afternoon';
    return 'Evening';
  }

  SliverList _buildContent(BuildContext context, Map<String, dynamic> data) {
    final theme = Theme.of(context);
    final attendance = data['my_attendance'] as Map<String, dynamic>? ?? {};
    final classes = data['my_classes'] as List? ?? [];
    final pendingLeaves = data['pending_leaves'] as List? ?? [];
    final timetable = data['today_timetable'] as List? ?? [];

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
              icon: Icons.groups_outlined,
              label: 'My Classes',
              value: '${classes.length}',
              color: theme.colorScheme.primary,
              index: 0,
              onTap: () => context.go('/teacher/students'),
            ),
            StatCard(
              icon: Icons.check_circle_outline,
              label: 'My Attendance',
              value: '${attendance['percentage'] ?? 0}%',
              color: const Color(0xFF22C55E),
              index: 1,
            ),
            StatCard(
              icon: Icons.event_note_outlined,
              label: 'Pending Leaves',
              value: '${pendingLeaves.length}',
              color: const Color(0xFFF59E0B),
              index: 2,
              onTap: () => context.go('/teacher/leave'),
            ),
            StatCard(
              icon: Icons.schedule_outlined,
              label: 'Classes Today',
              value: '${timetable.length}',
              color: const Color(0xFF8B5CF6),
              index: 3,
              onTap: () => context.go('/teacher/timetable'),
            ),
          ],
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
              icon: Icons.fact_check_rounded,
              label: 'Mark\nAttendance',
              color: const Color(0xFF22C55E),
              onTap: () => context.go('/teacher/attendance'),
              index: 0,
            ),
            QuickAction(
              icon: Icons.schedule_rounded,
              label: 'Timetable',
              color: const Color(0xFF4F46E5),
              onTap: () => context.go('/teacher/timetable'),
              index: 1,
            ),
            QuickAction(
              icon: Icons.people_outline_rounded,
              label: 'Students',
              color: const Color(0xFF06B6D4),
              onTap: () => context.go('/teacher/students'),
              index: 2,
            ),
            QuickAction(
              icon: Icons.event_note_outlined,
              label: 'Leave\nRequests',
              color: const Color(0xFFF59E0B),
              onTap: () => context.go('/teacher/leave'),
              index: 3,
            ),
          ],
        ),
        const SizedBox(height: 24),

        // ── Today's Schedule ──
        if (timetable.isNotEmpty) ...[
          const SectionHeader(title: "Today's Schedule"),
          ...timetable.asMap().entries.map((entry) {
            final i = entry.key;
            final p = entry.value as Map<String, dynamic>;
            return AnimatedCard(
              index: i + 4,
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
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          '${p['subject_name'] ?? 'Free'} — ${p['class_name'] ?? ''} ${p['section_name'] ?? ''}',
                          style: const TextStyle(
                            fontSize: 14,
                            fontWeight: FontWeight.w600,
                          ),
                        ),
                        Text(
                          '${p['start_time'] ?? ''} - ${p['end_time'] ?? ''}',
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
            );
          }),
          const SizedBox(height: 24),
        ],

        // ── Pending Leave Requests ──
        if (pendingLeaves.isNotEmpty) ...[
          SectionHeader(
            title: 'Pending Leave Requests',
            actionText: 'See All',
            onAction: () => context.go('/teacher/leave'),
          ),
          ...pendingLeaves.take(3).toList().asMap().entries.map((entry) {
            final i = entry.key;
            final leave = entry.value as Map<String, dynamic>;
            return AnimatedCard(
              index: i + timetable.length + 4,
              padding: const EdgeInsets.all(14),
              child: Row(
                children: [
                  CircleAvatar(
                    radius: 20,
                    backgroundColor:
                        theme.colorScheme.primary.withValues(alpha: 0.1),
                    child: Text(
                      (leave['student_name'] ?? 'S').substring(0, 1),
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
                            fontSize: 14,
                            fontWeight: FontWeight.w600,
                          ),
                        ),
                        Text(
                          '${leave['from_date']} - ${leave['to_date']} | ${leave['reason'] ?? ''}',
                          style: TextStyle(
                            fontSize: 12,
                            color: theme.textTheme.bodySmall?.color,
                          ),
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                        ),
                      ],
                    ),
                  ),
                  Container(
                    padding:
                        const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                    decoration: BoxDecoration(
                      color: const Color(0xFFFEF3C7),
                      borderRadius: BorderRadius.circular(6),
                    ),
                    child: const Text(
                      'PENDING',
                      style: TextStyle(
                        fontSize: 9,
                        fontWeight: FontWeight.w700,
                        color: Color(0xFFF59E0B),
                      ),
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
}
