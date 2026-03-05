import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../core/api_client.dart';
import '../../providers/auth_provider.dart';
import '../../widgets/shimmer_loading.dart';
import '../../widgets/attendance_calendar.dart';

/// State for selected month/year.
final attendanceMonthProvider = StateProvider<int>((ref) => DateTime.now().month);
final attendanceYearProvider = StateProvider<int>((ref) => DateTime.now().year);

/// Fetches attendance calendar data.
final studentAttendanceProvider =
    FutureProvider.family<Map<String, dynamic>, String>((ref, params) async {
  final month = ref.watch(attendanceMonthProvider);
  final year = ref.watch(attendanceYearProvider);
  final response = await api.get(
    '/api/mobile/attendance/student/$params',
    params: {'month': month, 'year': year},
  );
  return response.data;
});

class StudentAttendance extends ConsumerWidget {
  const StudentAttendance({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final user = ref.watch(currentUserProvider);
    final studentId = user?.studentId ?? '';
    final month = ref.watch(attendanceMonthProvider);
    final year = ref.watch(attendanceYearProvider);
    final attendance = ref.watch(studentAttendanceProvider(studentId));

    return Scaffold(
      appBar: AppBar(title: const Text('Attendance')),
      body: attendance.when(
        data: (data) {
          final days = (data['days'] as List?)
                  ?.map((d) => AttendanceDay.fromJson(d))
                  .toList() ??
              [];
          final summary = Map<String, int>.from(data['summary'] ?? {});

          return SingleChildScrollView(
            padding: const EdgeInsets.all(16),
            child: AttendanceCalendar(
              month: month,
              year: year,
              days: days,
              summary: summary,
              onMonthChanged: (m, y) {
                ref.read(attendanceMonthProvider.notifier).state = m;
                ref.read(attendanceYearProvider.notifier).state = y;
              },
            ),
          );
        },
        loading: () => const Center(child: ShimmerCard(height: 400)),
        error: (err, _) => Center(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Icon(Icons.error_outline, size: 48, color: Colors.grey),
              const SizedBox(height: 12),
              const Text('Could not load attendance'),
              const SizedBox(height: 8),
              OutlinedButton(
                onPressed: () =>
                    ref.invalidate(studentAttendanceProvider(studentId)),
                child: const Text('Retry'),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
