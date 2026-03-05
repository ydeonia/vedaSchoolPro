import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:intl/intl.dart';
import '../../core/api_client.dart';
import '../../widgets/shimmer_loading.dart';
import '../../widgets/animated_card.dart';

final leaveListProvider = FutureProvider<List>((ref) async {
  final response = await api.get('/api/mobile/student/leaves');
  return response.data['leaves'] ?? [];
});

class StudentLeave extends ConsumerStatefulWidget {
  const StudentLeave({super.key});

  @override
  ConsumerState<StudentLeave> createState() => _StudentLeaveState();
}

class _StudentLeaveState extends ConsumerState<StudentLeave> {
  bool _showForm = false;
  final _reasonCtrl = TextEditingController();
  String _leaveType = 'sick';
  DateTime? _fromDate;
  DateTime? _toDate;
  bool _submitting = false;

  @override
  void dispose() {
    _reasonCtrl.dispose();
    super.dispose();
  }

  Future<void> _pickDate(bool isFrom) async {
    final picked = await showDatePicker(
      context: context,
      initialDate: DateTime.now(),
      firstDate: DateTime.now(),
      lastDate: DateTime.now().add(const Duration(days: 60)),
    );
    if (picked != null) {
      setState(() {
        if (isFrom) {
          _fromDate = picked;
          if (_toDate != null && _toDate!.isBefore(picked)) {
            _toDate = picked;
          }
        } else {
          _toDate = picked;
        }
      });
    }
  }

  Future<void> _submitLeave() async {
    if (_fromDate == null || _toDate == null || _reasonCtrl.text.trim().isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Please fill all fields')),
      );
      return;
    }
    setState(() => _submitting = true);
    try {
      await api.post('/api/mobile/student/leave/apply', data: {
        'leave_type': _leaveType,
        'from_date': DateFormat('yyyy-MM-dd').format(_fromDate!),
        'to_date': DateFormat('yyyy-MM-dd').format(_toDate!),
        'reason': _reasonCtrl.text.trim(),
      });
      HapticFeedback.mediumImpact();
      ref.invalidate(leaveListProvider);
      setState(() {
        _showForm = false;
        _reasonCtrl.clear();
        _fromDate = null;
        _toDate = null;
      });
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text('Leave applied! Waiting for teacher approval.'),
            backgroundColor: Color(0xFF22C55E),
          ),
        );
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text('Failed to apply leave'),
            backgroundColor: Color(0xFFEF4444),
          ),
        );
      }
    } finally {
      setState(() => _submitting = false);
    }
  }

  Color _statusColor(String status) {
    switch (status) {
      case 'approved':
        return const Color(0xFF22C55E);
      case 'rejected':
        return const Color(0xFFEF4444);
      default:
        return const Color(0xFFF59E0B);
    }
  }

  @override
  Widget build(BuildContext context) {
    final leaves = ref.watch(leaveListProvider);
    final theme = Theme.of(context);
    final fmt = DateFormat('dd MMM');

    return Scaffold(
      appBar: AppBar(title: const Text('Leave')),
      floatingActionButton: FloatingActionButton.extended(
        onPressed: () => setState(() => _showForm = !_showForm),
        icon: Icon(_showForm ? Icons.close : Icons.add),
        label: Text(_showForm ? 'Cancel' : 'Apply Leave'),
      ),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // ── Apply Leave Form ──
            if (_showForm)
              AnimatedCard(
                index: 0,
                padding: const EdgeInsets.all(20),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Text(
                      'Apply for Leave',
                      style:
                          TextStyle(fontSize: 16, fontWeight: FontWeight.w600),
                    ),
                    const SizedBox(height: 16),
                    // Leave type
                    DropdownButtonFormField<String>(
                      value: _leaveType,
                      decoration:
                          const InputDecoration(labelText: 'Leave Type'),
                      items: const [
                        DropdownMenuItem(
                            value: 'sick', child: Text('Sick Leave')),
                        DropdownMenuItem(
                            value: 'casual', child: Text('Casual Leave')),
                        DropdownMenuItem(
                            value: 'family', child: Text('Family Emergency')),
                        DropdownMenuItem(
                            value: 'other', child: Text('Other')),
                      ],
                      onChanged: (v) => setState(() => _leaveType = v!),
                    ),
                    const SizedBox(height: 12),
                    // Date pickers
                    Row(
                      children: [
                        Expanded(
                          child: GestureDetector(
                            onTap: () => _pickDate(true),
                            child: InputDecorator(
                              decoration:
                                  const InputDecoration(labelText: 'From'),
                              child: Text(
                                _fromDate != null
                                    ? fmt.format(_fromDate!)
                                    : 'Select',
                                style: TextStyle(
                                  color: _fromDate != null
                                      ? null
                                      : theme.textTheme.bodySmall?.color,
                                ),
                              ),
                            ),
                          ),
                        ),
                        const SizedBox(width: 12),
                        Expanded(
                          child: GestureDetector(
                            onTap: () => _pickDate(false),
                            child: InputDecorator(
                              decoration:
                                  const InputDecoration(labelText: 'To'),
                              child: Text(
                                _toDate != null
                                    ? fmt.format(_toDate!)
                                    : 'Select',
                                style: TextStyle(
                                  color: _toDate != null
                                      ? null
                                      : theme.textTheme.bodySmall?.color,
                                ),
                              ),
                            ),
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: 12),
                    TextFormField(
                      controller: _reasonCtrl,
                      maxLines: 3,
                      decoration: const InputDecoration(
                        labelText: 'Reason',
                        hintText: 'Explain reason for leave...',
                      ),
                    ),
                    const SizedBox(height: 16),
                    SizedBox(
                      width: double.infinity,
                      child: ElevatedButton(
                        onPressed: _submitting ? null : _submitLeave,
                        child: _submitting
                            ? const SizedBox(
                                width: 20,
                                height: 20,
                                child: CircularProgressIndicator(
                                    strokeWidth: 2, color: Colors.white),
                              )
                            : const Text('Submit'),
                      ),
                    ),
                  ],
                ),
              ),
            if (_showForm) const SizedBox(height: 20),

            // ── Leave History ──
            const Text(
              'Leave History',
              style: TextStyle(fontSize: 16, fontWeight: FontWeight.w600),
            ),
            const SizedBox(height: 12),
            leaves.when(
              data: (items) {
                if (items.isEmpty) {
                  return Center(
                    child: Padding(
                      padding: const EdgeInsets.all(40),
                      child: Text(
                        'No leave applications yet',
                        style: TextStyle(
                            color: theme.textTheme.bodySmall?.color),
                      ),
                    ),
                  );
                }
                return Column(
                  children: items.asMap().entries.map((entry) {
                    final i = entry.key;
                    final leave = entry.value as Map<String, dynamic>;
                    return AnimatedCard(
                      index: i + 1,
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
                                  color: _statusColor(
                                          leave['teacher_status'] ?? 'pending')
                                      .withValues(alpha: 0.12),
                                  borderRadius: BorderRadius.circular(6),
                                ),
                                child: Text(
                                  (leave['teacher_status'] ?? 'pending')
                                      .toUpperCase(),
                                  style: TextStyle(
                                    fontSize: 10,
                                    fontWeight: FontWeight.w700,
                                    color: _statusColor(
                                        leave['teacher_status'] ?? 'pending'),
                                  ),
                                ),
                              ),
                              const Spacer(),
                              Text(
                                '${leave['from_date']} - ${leave['to_date']}',
                                style: TextStyle(
                                  fontSize: 12,
                                  color: theme.textTheme.bodySmall?.color,
                                ),
                              ),
                            ],
                          ),
                          const SizedBox(height: 8),
                          Text(
                            '${(leave['leave_type'] ?? '').toString().replaceAll('_', ' ')} Leave',
                            style: const TextStyle(
                              fontSize: 14,
                              fontWeight: FontWeight.w600,
                            ),
                          ),
                          if (leave['reason'] != null) ...[
                            const SizedBox(height: 4),
                            Text(
                              leave['reason'],
                              style: TextStyle(
                                fontSize: 13,
                                color: theme.textTheme.bodySmall?.color,
                              ),
                              maxLines: 2,
                              overflow: TextOverflow.ellipsis,
                            ),
                          ],
                        ],
                      ),
                    );
                  }).toList(),
                );
              },
              loading: () => ShimmerList(itemCount: 3),
              error: (_, __) => const Text('Failed to load leaves'),
            ),
            const SizedBox(height: 80),
          ],
        ),
      ),
    );
  }
}
