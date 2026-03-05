import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:percent_indicator/circular_percent_indicator.dart';
import '../../core/api_client.dart';
import '../../providers/auth_provider.dart';
import '../../widgets/shimmer_loading.dart';
import '../../widgets/animated_card.dart';
import '../../widgets/section_header.dart';

final parentDashboardProvider =
    FutureProvider<Map<String, dynamic>>((ref) async {
  final response = await api.get('/api/mobile/dashboard/parent');
  return response.data;
});

class ParentDashboard extends ConsumerWidget {
  const ParentDashboard({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final user = ref.watch(currentUserProvider);
    final dashboard = ref.watch(parentDashboardProvider);
    final theme = Theme.of(context);

    return Scaffold(
      body: RefreshIndicator(
        onRefresh: () async => ref.invalidate(parentDashboardProvider),
        child: CustomScrollView(
          physics: const BouncingScrollPhysics(
            parent: AlwaysScrollableScrollPhysics(),
          ),
          slivers: [
            SliverAppBar(
              expandedHeight: 140,
              floating: false,
              pinned: true,
              flexibleSpace: FlexibleSpaceBar(
                background: Container(
                  decoration: BoxDecoration(
                    gradient: LinearGradient(
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
                        children: [
                          CircleAvatar(
                            radius: 24,
                            backgroundColor: Colors.white.withValues(alpha: 0.2),
                            child: Text(
                              (user?.name ?? 'P').substring(0, 1).toUpperCase(),
                              style: const TextStyle(
                                color: Colors.white,
                                fontSize: 20,
                                fontWeight: FontWeight.w600,
                              ),
                            ),
                          ),
                          const SizedBox(width: 14),
                          Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            mainAxisSize: MainAxisSize.min,
                            children: [
                              Text(
                                'Welcome, ${user?.name.split(' ').first ?? 'Parent'}',
                                style: const TextStyle(
                                  color: Colors.white,
                                  fontSize: 18,
                                  fontWeight: FontWeight.w600,
                                ),
                              ),
                              Text(
                                'Parent Dashboard',
                                style: TextStyle(
                                  color: Colors.white.withValues(alpha: 0.8),
                                  fontSize: 13,
                                ),
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
            SliverPadding(
              padding: const EdgeInsets.all(16),
              sliver: dashboard.when(
                data: (data) {
                  final children = data['children'] as List? ?? [];
                  return SliverList(
                    delegate: SliverChildListDelegate([
                      // ── Children Cards ──
                      ...children.asMap().entries.map((entry) {
                        final i = entry.key;
                        final child = entry.value as Map<String, dynamic>;
                        final att = child['attendance'] as Map<String, dynamic>? ?? {};
                        final fees = child['fees'] as Map<String, dynamic>? ?? {};

                        return AnimatedCard(
                          index: i,
                          padding: const EdgeInsets.all(16),
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              // Child header
                              Row(
                                children: [
                                  CircleAvatar(
                                    radius: 22,
                                    backgroundColor: theme.colorScheme.primary
                                        .withValues(alpha: 0.1),
                                    child: Text(
                                      (child['name'] ?? 'C').substring(0, 1),
                                      style: TextStyle(
                                        color: theme.colorScheme.primary,
                                        fontWeight: FontWeight.w600,
                                        fontSize: 18,
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
                                          child['name'] ?? '',
                                          style: const TextStyle(
                                            fontSize: 16,
                                            fontWeight: FontWeight.w600,
                                          ),
                                        ),
                                        Text(
                                          '${child['class_name'] ?? ''} ${child['section_name'] ?? ''} | ${child['registration_number'] ?? ''}',
                                          style: TextStyle(
                                            fontSize: 12,
                                            color: theme
                                                .textTheme.bodySmall?.color,
                                          ),
                                        ),
                                      ],
                                    ),
                                  ),
                                  CircularPercentIndicator(
                                    radius: 24,
                                    lineWidth: 4,
                                    percent: ((att['percentage'] ?? 0) / 100)
                                        .clamp(0.0, 1.0)
                                        .toDouble(),
                                    center: Text(
                                      '${att['percentage'] ?? 0}%',
                                      style: const TextStyle(
                                        fontSize: 10,
                                        fontWeight: FontWeight.w600,
                                      ),
                                    ),
                                    progressColor: theme.colorScheme.primary,
                                    backgroundColor: theme.colorScheme.primary
                                        .withValues(alpha: 0.15),
                                  ),
                                ],
                              ),
                              const SizedBox(height: 14),
                              const Divider(height: 1),
                              const SizedBox(height: 14),
                              // Stats row
                              Row(
                                mainAxisAlignment:
                                    MainAxisAlignment.spaceAround,
                                children: [
                                  _miniStat('Attendance',
                                      '${att['percentage'] ?? 0}%',
                                      const Color(0xFF22C55E)),
                                  _miniStat(
                                      'Fee Due',
                                      '\u20B9${fees['pending'] ?? 0}',
                                      (fees['pending'] ?? 0) > 0
                                          ? const Color(0xFFEF4444)
                                          : const Color(0xFF22C55E)),
                                  _miniStat(
                                      'Today',
                                      (att['today_status'] ?? 'N/A')
                                          .toString()
                                          .toUpperCase(),
                                      att['today_status'] == 'present'
                                          ? const Color(0xFF22C55E)
                                          : const Color(0xFFEF4444)),
                                ],
                              ),
                            ],
                          ),
                        );
                      }),
                      const SizedBox(height: 20),

                      // ── Announcements ──
                      if ((data['announcements'] as List?)?.isNotEmpty ==
                          true) ...[
                        const SectionHeader(
                          title: 'School Announcements',
                          icon: Icons.campaign_outlined,
                        ),
                        ...(data['announcements'] as List)
                            .take(3)
                            .toList()
                            .asMap()
                            .entries
                            .map((entry) {
                          final i = entry.key;
                          final ann = entry.value as Map<String, dynamic>;
                          return AnimatedCard(
                            index: i + children.length,
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
                },
                loading: () => SliverToBoxAdapter(
                  child: Column(
                    children: List.generate(
                      2,
                      (i) => const Padding(
                        padding: EdgeInsets.only(bottom: 12),
                        child: ShimmerCard(height: 160),
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
                          onPressed: () =>
                              ref.invalidate(parentDashboardProvider),
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

  Widget _miniStat(String label, String value, Color color) {
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
        Text(
          label,
          style: const TextStyle(fontSize: 11, fontWeight: FontWeight.w500),
        ),
      ],
    );
  }
}
