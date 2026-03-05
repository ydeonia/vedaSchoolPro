import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../core/api_client.dart';
import '../../widgets/shimmer_loading.dart';
import '../../widgets/animated_card.dart';

/// Selected class/section for attendance.
final selectedClassProvider = StateProvider<String?>((ref) => null);
final selectedSectionProvider = StateProvider<String?>((ref) => null);

/// Fetch classes assigned to this teacher.
final teacherClassesProvider = FutureProvider<List>((ref) async {
  final response = await api.get('/api/mobile/teacher/classes');
  return response.data['classes'] ?? [];
});

/// Fetch students for selected class/section.
final classStudentsProvider =
    FutureProvider.family<List, String>((ref, key) async {
  final parts = key.split('_');
  final response = await api.get('/api/mobile/teacher/students', params: {
    'class_id': parts[0],
    'section_id': parts[1],
  });
  return response.data['students'] ?? [];
});

class TeacherAttendanceMark extends ConsumerStatefulWidget {
  const TeacherAttendanceMark({super.key});

  @override
  ConsumerState<TeacherAttendanceMark> createState() =>
      _TeacherAttendanceMarkState();
}

class _TeacherAttendanceMarkState extends ConsumerState<TeacherAttendanceMark> {
  // student_id -> status
  final Map<String, String> _attendance = {};
  bool _saving = false;

  Future<void> _saveAttendance() async {
    if (_attendance.isEmpty) return;
    setState(() => _saving = true);
    try {
      final classId = ref.read(selectedClassProvider);
      final sectionId = ref.read(selectedSectionProvider);
      await api.post('/api/mobile/attendance/save', data: {
        'class_id': classId,
        'section_id': sectionId,
        'date': DateTime.now().toIso8601String().split('T')[0],
        'attendance': _attendance.entries
            .map((e) => {'student_id': e.key, 'status': e.value})
            .toList(),
      });
      HapticFeedback.mediumImpact();
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text('Attendance saved successfully!'),
            backgroundColor: Color(0xFF22C55E),
          ),
        );
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text('Failed to save attendance'),
            backgroundColor: Color(0xFFEF4444),
          ),
        );
      }
    } finally {
      setState(() => _saving = false);
    }
  }

  Color _statusColor(String status) {
    switch (status) {
      case 'present':
        return const Color(0xFF22C55E);
      case 'absent':
        return const Color(0xFFEF4444);
      case 'late':
        return const Color(0xFFF59E0B);
      default:
        return Colors.grey;
    }
  }

  @override
  Widget build(BuildContext context) {
    final classes = ref.watch(teacherClassesProvider);
    final classId = ref.watch(selectedClassProvider);
    final sectionId = ref.watch(selectedSectionProvider);
    final theme = Theme.of(context);

    return Scaffold(
      appBar: AppBar(
        title: const Text('Mark Attendance'),
        actions: [
          if (_attendance.isNotEmpty)
            TextButton.icon(
              onPressed: _saving ? null : _saveAttendance,
              icon: _saving
                  ? const SizedBox(
                      width: 16,
                      height: 16,
                      child: CircularProgressIndicator(
                          strokeWidth: 2, color: Colors.white),
                    )
                  : const Icon(Icons.save_rounded, color: Colors.white),
              label: Text(
                'Save',
                style: TextStyle(
                  color: Colors.white.withValues(alpha: _saving ? 0.5 : 1.0),
                ),
              ),
            ),
        ],
      ),
      body: Column(
        children: [
          // ── Class/Section Selector ──
          Container(
            padding: const EdgeInsets.all(16),
            color: theme.colorScheme.primary.withValues(alpha: 0.04),
            child: classes.when(
              data: (classList) {
                // Extract unique classes
                final classOptions = <Map<String, dynamic>>[];
                final sectionOptions = <Map<String, dynamic>>[];
                for (final c in classList) {
                  final cm = c as Map<String, dynamic>;
                  if (!classOptions.any((x) => x['class_id'] == cm['class_id'])) {
                    classOptions.add(cm);
                  }
                }
                if (classId != null) {
                  for (final c in classList) {
                    final cm = c as Map<String, dynamic>;
                    if (cm['class_id'] == classId) sectionOptions.add(cm);
                  }
                }

                return Row(
                  children: [
                    Expanded(
                      child: DropdownButtonFormField<String>(
                        value: classId,
                        decoration:
                            const InputDecoration(labelText: 'Class'),
                        items: classOptions
                            .map((c) => DropdownMenuItem(
                                  value: c['class_id'] as String,
                                  child: Text(c['class_name'] ?? ''),
                                ))
                            .toList(),
                        onChanged: (v) {
                          ref.read(selectedClassProvider.notifier).state = v;
                          ref.read(selectedSectionProvider.notifier).state =
                              null;
                          _attendance.clear();
                        },
                      ),
                    ),
                    const SizedBox(width: 12),
                    Expanded(
                      child: DropdownButtonFormField<String>(
                        value: sectionId,
                        decoration:
                            const InputDecoration(labelText: 'Section'),
                        items: sectionOptions
                            .map((c) => DropdownMenuItem(
                                  value: c['section_id'] as String,
                                  child: Text(c['section_name'] ?? ''),
                                ))
                            .toList(),
                        onChanged: (v) {
                          ref.read(selectedSectionProvider.notifier).state = v;
                          _attendance.clear();
                        },
                      ),
                    ),
                  ],
                );
              },
              loading: () => const ShimmerLoading(height: 48),
              error: (_, __) => const Text('Failed to load classes'),
            ),
          ),

          // ── Student List ──
          Expanded(
            child: classId != null && sectionId != null
                ? ref.watch(classStudentsProvider('${classId}_$sectionId')).when(
                      data: (students) {
                        if (students.isEmpty) {
                          return const Center(
                              child: Text('No students in this section'));
                        }

                        // Mark all present by default
                        for (final s in students) {
                          final sid = s['id'] as String;
                          _attendance.putIfAbsent(sid, () => 'present');
                        }

                        return Column(
                          children: [
                            // Bulk actions
                            Padding(
                              padding: const EdgeInsets.symmetric(
                                  horizontal: 16, vertical: 8),
                              child: Row(
                                children: [
                                  Text(
                                    '${students.length} students',
                                    style: const TextStyle(
                                        fontWeight: FontWeight.w600),
                                  ),
                                  const Spacer(),
                                  TextButton(
                                    onPressed: () {
                                      setState(() {
                                        for (final s in students) {
                                          _attendance[s['id']] = 'present';
                                        }
                                      });
                                    },
                                    child: const Text('All Present',
                                        style: TextStyle(fontSize: 12)),
                                  ),
                                ],
                              ),
                            ),
                            Expanded(
                              child: ListView.builder(
                                padding:
                                    const EdgeInsets.symmetric(horizontal: 16),
                                itemCount: students.length,
                                itemBuilder: (ctx, i) {
                                  final student =
                                      students[i] as Map<String, dynamic>;
                                  final sid = student['id'] as String;
                                  final status =
                                      _attendance[sid] ?? 'present';

                                  return AnimatedCard(
                                    index: i,
                                    padding: const EdgeInsets.symmetric(
                                        horizontal: 12, vertical: 10),
                                    child: Row(
                                      children: [
                                        // Roll number
                                        Container(
                                          width: 32,
                                          height: 32,
                                          decoration: BoxDecoration(
                                            color: theme.colorScheme.primary
                                                .withValues(alpha: 0.1),
                                            borderRadius:
                                                BorderRadius.circular(8),
                                          ),
                                          child: Center(
                                            child: Text(
                                              '${student['roll_number'] ?? i + 1}',
                                              style: TextStyle(
                                                fontSize: 12,
                                                fontWeight: FontWeight.w600,
                                                color: theme
                                                    .colorScheme.primary,
                                              ),
                                            ),
                                          ),
                                        ),
                                        const SizedBox(width: 12),
                                        Expanded(
                                          child: Text(
                                            student['name'] ?? '',
                                            style: const TextStyle(
                                              fontSize: 14,
                                              fontWeight: FontWeight.w500,
                                            ),
                                          ),
                                        ),
                                        // Status buttons
                                        _statusBtn(sid, 'P', 'present',
                                            status == 'present'),
                                        const SizedBox(width: 4),
                                        _statusBtn(sid, 'A', 'absent',
                                            status == 'absent'),
                                        const SizedBox(width: 4),
                                        _statusBtn(sid, 'L', 'late',
                                            status == 'late'),
                                      ],
                                    ),
                                  );
                                },
                              ),
                            ),
                          ],
                        );
                      },
                      loading: () => Padding(
                        padding: const EdgeInsets.all(16),
                        child: ShimmerList(itemCount: 8),
                      ),
                      error: (_, __) =>
                          const Center(child: Text('Failed to load students')),
                    )
                : Center(
                    child: Column(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Icon(Icons.touch_app_outlined,
                            size: 56,
                            color: theme.textTheme.bodySmall?.color),
                        const SizedBox(height: 12),
                        const Text('Select a class and section'),
                      ],
                    ),
                  ),
          ),
        ],
      ),
    );
  }

  Widget _statusBtn(
      String studentId, String label, String status, bool active) {
    final color = _statusColor(status);
    return GestureDetector(
      onTap: () {
        HapticFeedback.selectionClick();
        setState(() => _attendance[studentId] = status);
      },
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 200),
        width: 36,
        height: 36,
        decoration: BoxDecoration(
          color: active ? color : color.withValues(alpha: 0.08),
          borderRadius: BorderRadius.circular(8),
          border: Border.all(
            color: active ? color : color.withValues(alpha: 0.3),
            width: active ? 2 : 1,
          ),
        ),
        child: Center(
          child: Text(
            label,
            style: TextStyle(
              fontSize: 13,
              fontWeight: FontWeight.w700,
              color: active ? Colors.white : color,
            ),
          ),
        ),
      ),
    );
  }
}
