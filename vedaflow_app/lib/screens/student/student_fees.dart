import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../core/api_client.dart';
import '../../providers/auth_provider.dart';
import '../../widgets/shimmer_loading.dart';
import '../../widgets/animated_card.dart';
import '../../widgets/section_header.dart';

final studentFeesProvider =
    FutureProvider.family<Map<String, dynamic>, String>((ref, studentId) async {
  final response = await api.get('/api/mobile/fees/student/$studentId');
  return response.data;
});

class StudentFees extends ConsumerWidget {
  const StudentFees({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final user = ref.watch(currentUserProvider);
    final studentId = user?.studentId ?? '';
    final fees = ref.watch(studentFeesProvider(studentId));
    final theme = Theme.of(context);

    return Scaffold(
      appBar: AppBar(title: const Text('Fee Details')),
      body: fees.when(
        data: (data) {
          final summary = data['summary'] as Map<String, dynamic>? ?? {};
          final items = data['fee_items'] as List? ?? [];
          final payments = data['recent_payments'] as List? ?? [];

          return RefreshIndicator(
            onRefresh: () async =>
                ref.invalidate(studentFeesProvider(studentId)),
            child: SingleChildScrollView(
              physics: const AlwaysScrollableScrollPhysics(),
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  // ── Fee Summary Card ──
                  AnimatedCard(
                    index: 0,
                    padding: const EdgeInsets.all(20),
                    child: Column(
                      children: [
                        Row(
                          mainAxisAlignment: MainAxisAlignment.spaceBetween,
                          children: [
                            _feeItem('Total Fee', '\u20B9${summary['total'] ?? 0}',
                                theme.textTheme.bodyLarge?.color ?? Colors.black),
                            _feeItem('Paid', '\u20B9${summary['paid'] ?? 0}',
                                const Color(0xFF22C55E)),
                            _feeItem('Due', '\u20B9${summary['pending'] ?? 0}',
                                (summary['pending'] ?? 0) > 0
                                    ? const Color(0xFFEF4444)
                                    : const Color(0xFF22C55E)),
                          ],
                        ),
                        if ((summary['pending'] ?? 0) > 0) ...[
                          const SizedBox(height: 16),
                          // Due progress bar
                          ClipRRect(
                            borderRadius: BorderRadius.circular(6),
                            child: LinearProgressIndicator(
                              value: ((summary['paid'] ?? 0) /
                                      (summary['total'] ?? 1))
                                  .clamp(0.0, 1.0)
                                  .toDouble(),
                              backgroundColor: const Color(0xFFE2E8F0),
                              valueColor: AlwaysStoppedAnimation(
                                  theme.colorScheme.primary),
                              minHeight: 8,
                            ),
                          ),
                          const SizedBox(height: 8),
                          Text(
                            '${(((summary['paid'] ?? 0) / (summary['total'] ?? 1)) * 100).toStringAsFixed(0)}% paid',
                            style: TextStyle(
                              fontSize: 12,
                              color: theme.textTheme.bodySmall?.color,
                            ),
                          ),
                        ],
                      ],
                    ),
                  ),
                  const SizedBox(height: 20),

                  // ── Pending Fee Items ──
                  if (items.isNotEmpty) ...[
                    const SectionHeader(title: 'Fee Breakdown'),
                    ...items.asMap().entries.map((entry) {
                      final i = entry.key;
                      final item = entry.value as Map<String, dynamic>;
                      final isPaid = item['status'] == 'paid';
                      return AnimatedCard(
                        index: i + 1,
                        padding: const EdgeInsets.all(14),
                        child: Row(
                          children: [
                            Container(
                              width: 40,
                              height: 40,
                              decoration: BoxDecoration(
                                color: isPaid
                                    ? const Color(0xFFF0FDF4)
                                    : const Color(0xFFFEF2F2),
                                borderRadius: BorderRadius.circular(10),
                              ),
                              child: Icon(
                                isPaid
                                    ? Icons.check_circle_rounded
                                    : Icons.pending_rounded,
                                color: isPaid
                                    ? const Color(0xFF22C55E)
                                    : const Color(0xFFEF4444),
                                size: 22,
                              ),
                            ),
                            const SizedBox(width: 12),
                            Expanded(
                              child: Column(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                children: [
                                  Text(
                                    item['fee_type'] ?? 'Fee',
                                    style: const TextStyle(
                                      fontSize: 14,
                                      fontWeight: FontWeight.w600,
                                    ),
                                  ),
                                  if (item['due_date'] != null)
                                    Text(
                                      'Due: ${item['due_date']}',
                                      style: TextStyle(
                                        fontSize: 11,
                                        color:
                                            theme.textTheme.bodySmall?.color,
                                      ),
                                    ),
                                ],
                              ),
                            ),
                            Text(
                              '\u20B9${item['amount'] ?? 0}',
                              style: TextStyle(
                                fontSize: 15,
                                fontWeight: FontWeight.w700,
                                color: isPaid
                                    ? const Color(0xFF22C55E)
                                    : const Color(0xFFEF4444),
                              ),
                            ),
                          ],
                        ),
                      );
                    }),
                    const SizedBox(height: 20),
                  ],

                  // ── Recent Payments ──
                  if (payments.isNotEmpty) ...[
                    const SectionHeader(title: 'Recent Payments'),
                    ...payments.take(5).toList().asMap().entries.map((entry) {
                      final i = entry.key;
                      final pay = entry.value as Map<String, dynamic>;
                      return AnimatedCard(
                        index: i + items.length + 1,
                        padding: const EdgeInsets.symmetric(
                            horizontal: 14, vertical: 12),
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
                                    '\u20B9${pay['amount']} via ${pay['method'] ?? 'Cash'}',
                                    style: const TextStyle(
                                      fontSize: 13,
                                      fontWeight: FontWeight.w600,
                                    ),
                                  ),
                                  Text(
                                    pay['date'] ?? '',
                                    style: TextStyle(
                                      fontSize: 11,
                                      color: theme.textTheme.bodySmall?.color,
                                    ),
                                  ),
                                ],
                              ),
                            ),
                            if (pay['receipt_number'] != null)
                              Text(
                                '#${pay['receipt_number']}',
                                style: TextStyle(
                                  fontSize: 11,
                                  color: theme.textTheme.bodySmall?.color,
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
              ShimmerList(itemCount: 4),
            ],
          ),
        ),
        error: (_, __) => Center(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Icon(Icons.error_outline, size: 48, color: Colors.grey),
              const SizedBox(height: 12),
              const Text('Could not load fee details'),
              OutlinedButton(
                onPressed: () =>
                    ref.invalidate(studentFeesProvider(studentId)),
                child: const Text('Retry'),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _feeItem(String label, String value, Color color) {
    return Column(
      children: [
        Text(
          value,
          style: TextStyle(
            fontSize: 18,
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
