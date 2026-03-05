import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../core/api_client.dart';
import '../../widgets/shimmer_loading.dart';
import '../../widgets/animated_card.dart';
import '../../widgets/section_header.dart';

final adminFeeProvider = FutureProvider<Map<String, dynamic>>((ref) async {
  final response = await api.get('/api/mobile/admin/fee-overview');
  return response.data;
});

class AdminFeeOverview extends ConsumerWidget {
  const AdminFeeOverview({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final fees = ref.watch(adminFeeProvider);
    final theme = Theme.of(context);

    return Scaffold(
      appBar: AppBar(title: const Text('Fee Overview')),
      body: fees.when(
        data: (data) {
          final summary = data['summary'] as Map<String, dynamic>? ?? {};
          final classWise = data['class_wise'] as List? ?? [];
          final recentPayments = data['recent_payments'] as List? ?? [];
          final defaulters = data['defaulters'] as List? ?? [];

          return RefreshIndicator(
            onRefresh: () async => ref.invalidate(adminFeeProvider),
            child: SingleChildScrollView(
              physics: const AlwaysScrollableScrollPhysics(),
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  // ── Summary ──
                  AnimatedCard(
                    index: 0,
                    padding: const EdgeInsets.all(20),
                    child: Column(
                      children: [
                        Row(
                          mainAxisAlignment: MainAxisAlignment.spaceAround,
                          children: [
                            _metric('Total', '\u20B9${_fmt(summary['total'] ?? 0)}',
                                theme.textTheme.bodyLarge?.color ?? Colors.black),
                            _metric('Collected', '\u20B9${_fmt(summary['collected'] ?? 0)}',
                                const Color(0xFF22C55E)),
                            _metric('Pending', '\u20B9${_fmt(summary['pending'] ?? 0)}',
                                const Color(0xFFEF4444)),
                          ],
                        ),
                        const SizedBox(height: 14),
                        ClipRRect(
                          borderRadius: BorderRadius.circular(6),
                          child: LinearProgressIndicator(
                            value: _pct(summary['collected'], summary['total']),
                            backgroundColor: const Color(0xFFE2E8F0),
                            valueColor:
                                AlwaysStoppedAnimation(theme.colorScheme.primary),
                            minHeight: 8,
                          ),
                        ),
                        const SizedBox(height: 8),
                        Row(
                          mainAxisAlignment: MainAxisAlignment.spaceBetween,
                          children: [
                            Text(
                              'Today: \u20B9${_fmt(summary['today_collection'] ?? 0)}',
                              style: TextStyle(
                                fontSize: 12,
                                color: theme.textTheme.bodySmall?.color,
                              ),
                            ),
                            Text(
                              'This Month: \u20B9${_fmt(summary['month_collection'] ?? 0)}',
                              style: TextStyle(
                                fontSize: 12,
                                color: theme.textTheme.bodySmall?.color,
                              ),
                            ),
                          ],
                        ),
                      ],
                    ),
                  ),
                  const SizedBox(height: 20),

                  // ── Class-wise Collection ──
                  if (classWise.isNotEmpty) ...[
                    const SectionHeader(title: 'Class-wise Collection'),
                    ...classWise.asMap().entries.map((entry) {
                      final i = entry.key;
                      final cls = entry.value as Map<String, dynamic>;
                      final pct = _pct(cls['collected'], cls['total']);
                      return AnimatedCard(
                        index: i + 1,
                        padding: const EdgeInsets.all(14),
                        child: Column(
                          children: [
                            Row(
                              children: [
                                Text(
                                  cls['class_name'] ?? '',
                                  style: const TextStyle(
                                    fontSize: 14,
                                    fontWeight: FontWeight.w600,
                                  ),
                                ),
                                const Spacer(),
                                Text(
                                  '${(pct * 100).toStringAsFixed(0)}%',
                                  style: TextStyle(
                                    fontSize: 13,
                                    fontWeight: FontWeight.w600,
                                    color: pct >= 0.75
                                        ? const Color(0xFF22C55E)
                                        : pct >= 0.5
                                            ? const Color(0xFFF59E0B)
                                            : const Color(0xFFEF4444),
                                  ),
                                ),
                              ],
                            ),
                            const SizedBox(height: 8),
                            ClipRRect(
                              borderRadius: BorderRadius.circular(4),
                              child: LinearProgressIndicator(
                                value: pct,
                                backgroundColor: const Color(0xFFE2E8F0),
                                valueColor: AlwaysStoppedAnimation(
                                  pct >= 0.75
                                      ? const Color(0xFF22C55E)
                                      : pct >= 0.5
                                          ? const Color(0xFFF59E0B)
                                          : const Color(0xFFEF4444),
                                ),
                                minHeight: 6,
                              ),
                            ),
                            const SizedBox(height: 6),
                            Row(
                              mainAxisAlignment: MainAxisAlignment.spaceBetween,
                              children: [
                                Text(
                                  'Collected: \u20B9${_fmt(cls['collected'] ?? 0)}',
                                  style: TextStyle(
                                    fontSize: 11,
                                    color: theme.textTheme.bodySmall?.color,
                                  ),
                                ),
                                Text(
                                  'Pending: \u20B9${_fmt(cls['pending'] ?? 0)}',
                                  style: TextStyle(
                                    fontSize: 11,
                                    color: theme.textTheme.bodySmall?.color,
                                  ),
                                ),
                              ],
                            ),
                          ],
                        ),
                      );
                    }),
                    const SizedBox(height: 20),
                  ],

                  // ── Top Defaulters ──
                  if (defaulters.isNotEmpty) ...[
                    const SectionHeader(
                      title: 'Top Defaulters',
                      icon: Icons.warning_amber_rounded,
                    ),
                    ...defaulters.take(5).toList().asMap().entries.map((entry) {
                      final i = entry.key;
                      final d = entry.value as Map<String, dynamic>;
                      return AnimatedCard(
                        index: i + classWise.length + 1,
                        padding: const EdgeInsets.symmetric(
                            horizontal: 14, vertical: 10),
                        child: Row(
                          children: [
                            CircleAvatar(
                              radius: 18,
                              backgroundColor: const Color(0xFFFEF2F2),
                              child: Text(
                                (d['name'] ?? 'S').substring(0, 1),
                                style: const TextStyle(
                                  color: Color(0xFFEF4444),
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
                                    d['name'] ?? '',
                                    style: const TextStyle(
                                      fontSize: 13,
                                      fontWeight: FontWeight.w600,
                                    ),
                                  ),
                                  Text(
                                    'Class ${d['class_name'] ?? ''}',
                                    style: TextStyle(
                                      fontSize: 11,
                                      color: theme.textTheme.bodySmall?.color,
                                    ),
                                  ),
                                ],
                              ),
                            ),
                            Text(
                              '\u20B9${_fmt(d['pending_amount'] ?? 0)}',
                              style: const TextStyle(
                                fontSize: 14,
                                fontWeight: FontWeight.w700,
                                color: Color(0xFFEF4444),
                              ),
                            ),
                          ],
                        ),
                      );
                    }),
                    const SizedBox(height: 20),
                  ],

                  // ── Recent Payments ──
                  if (recentPayments.isNotEmpty) ...[
                    const SectionHeader(title: 'Recent Payments'),
                    ...recentPayments.take(10).toList().asMap().entries.map((entry) {
                      final i = entry.key;
                      final p = entry.value as Map<String, dynamic>;
                      return AnimatedCard(
                        index: i + classWise.length + defaulters.length + 1,
                        padding: const EdgeInsets.symmetric(
                            horizontal: 14, vertical: 10),
                        child: Row(
                          children: [
                            Container(
                              width: 36,
                              height: 36,
                              decoration: BoxDecoration(
                                color: const Color(0xFFF0FDF4),
                                borderRadius: BorderRadius.circular(8),
                              ),
                              child: const Icon(Icons.receipt_long_outlined,
                                  color: Color(0xFF22C55E), size: 18),
                            ),
                            const SizedBox(width: 12),
                            Expanded(
                              child: Column(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                children: [
                                  Text(
                                    p['student_name'] ?? '',
                                    style: const TextStyle(
                                      fontSize: 13,
                                      fontWeight: FontWeight.w600,
                                    ),
                                  ),
                                  Text(
                                    '${p['method'] ?? 'Cash'} | ${p['time'] ?? ''}',
                                    style: TextStyle(
                                      fontSize: 11,
                                      color: theme.textTheme.bodySmall?.color,
                                    ),
                                  ),
                                ],
                              ),
                            ),
                            Text(
                              '\u20B9${p['amount'] ?? 0}',
                              style: const TextStyle(
                                fontSize: 14,
                                fontWeight: FontWeight.w700,
                                color: Color(0xFF22C55E),
                              ),
                            ),
                          ],
                        ),
                      );
                    }),
                  ],
                  const SizedBox(height: 40),
                ],
              ),
            ),
          );
        },
        loading: () => Padding(
          padding: const EdgeInsets.all(16),
          child: Column(
            children: [
              const ShimmerCard(height: 130),
              const SizedBox(height: 16),
              ShimmerList(itemCount: 5),
            ],
          ),
        ),
        error: (_, __) => Center(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Text('Could not load fee data'),
              OutlinedButton(
                onPressed: () => ref.invalidate(adminFeeProvider),
                child: const Text('Retry'),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _metric(String label, String value, Color color) {
    return Column(
      children: [
        Text(value,
            style: TextStyle(fontSize: 16, fontWeight: FontWeight.w700, color: color)),
        const SizedBox(height: 2),
        Text(label, style: const TextStyle(fontSize: 11, fontWeight: FontWeight.w500)),
      ],
    );
  }

  double _pct(dynamic collected, dynamic total) {
    final c = (collected is num ? collected : 0).toDouble();
    final t = (total is num ? total : 1).toDouble();
    return (c / (t == 0 ? 1 : t)).clamp(0.0, 1.0);
  }

  String _fmt(dynamic amount) {
    final num val = amount is num ? amount : 0;
    if (val >= 10000000) return '${(val / 10000000).toStringAsFixed(1)}Cr';
    if (val >= 100000) return '${(val / 100000).toStringAsFixed(1)}L';
    if (val >= 1000) return '${(val / 1000).toStringAsFixed(1)}K';
    return val.toStringAsFixed(0);
  }
}
