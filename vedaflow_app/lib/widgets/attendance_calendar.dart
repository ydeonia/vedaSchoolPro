import 'package:flutter/material.dart';
import 'package:intl/intl.dart';

/// Attendance day data.
class AttendanceDay {
  final int day;
  final String? status; // present, absent, late, half_day, excused, holiday
  final bool isWeekend;
  final String? checkIn;
  final String? checkOut;
  final String? remarks;

  AttendanceDay({
    required this.day,
    this.status,
    this.isWeekend = false,
    this.checkIn,
    this.checkOut,
    this.remarks,
  });

  factory AttendanceDay.fromJson(Map<String, dynamic> json) => AttendanceDay(
        day: json['day'],
        status: json['status'],
        isWeekend: json['is_weekend'] ?? false,
        checkIn: json['check_in'],
        checkOut: json['check_out'],
        remarks: json['remarks'],
      );
}

/// Color-coded attendance calendar widget with tap-to-see-details.
class AttendanceCalendar extends StatefulWidget {
  final int month;
  final int year;
  final List<AttendanceDay> days;
  final Map<String, int> summary;
  final Function(int month, int year)? onMonthChanged;

  const AttendanceCalendar({
    super.key,
    required this.month,
    required this.year,
    required this.days,
    this.summary = const {},
    this.onMonthChanged,
  });

  @override
  State<AttendanceCalendar> createState() => _AttendanceCalendarState();
}

class _AttendanceCalendarState extends State<AttendanceCalendar> {
  AttendanceDay? _selectedDay;

  Color _statusColor(String? status, bool isWeekend) {
    if (isWeekend) return const Color(0xFFF3F4F6);
    switch (status) {
      case 'present':
        return const Color(0xFF22C55E);
      case 'absent':
        return const Color(0xFFEF4444);
      case 'late':
        return const Color(0xFFF59E0B);
      case 'half_day':
        return const Color(0xFFF59E0B);
      case 'excused':
        return const Color(0xFF3B82F6);
      case 'holiday':
        return const Color(0xFFE5E7EB);
      default:
        return Colors.transparent;
    }
  }

  String _statusEmoji(String? status) {
    switch (status) {
      case 'present':
        return 'Present';
      case 'absent':
        return 'Absent';
      case 'late':
        return 'Late';
      case 'half_day':
        return 'Half Day';
      case 'excused':
        return 'Excused';
      case 'holiday':
        return 'Holiday';
      default:
        return 'No Record';
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final monthName = DateFormat.MMMM().format(DateTime(widget.year, widget.month));
    final firstDay = DateTime(widget.year, widget.month, 1);
    final startWeekday = (firstDay.weekday % 7); // 0=Sun, adjust to Mon start
    final daysInMonth = DateTime(widget.year, widget.month + 1, 0).day;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        // ── Summary bar ──
        if (widget.summary.isNotEmpty)
          Container(
            padding: const EdgeInsets.all(12),
            margin: const EdgeInsets.only(bottom: 12),
            decoration: BoxDecoration(
              color: theme.colorScheme.primary.withValues(alpha: 0.06),
              borderRadius: BorderRadius.circular(12),
            ),
            child: Row(
              mainAxisAlignment: MainAxisAlignment.spaceAround,
              children: [
                _summaryItem('Present', widget.summary['present'] ?? 0, const Color(0xFF22C55E)),
                _summaryItem('Absent', widget.summary['absent'] ?? 0, const Color(0xFFEF4444)),
                _summaryItem('Late', widget.summary['late'] ?? 0, const Color(0xFFF59E0B)),
                _summaryItem(
                  'Att %',
                  (widget.summary['percentage'] ?? 0),
                  theme.colorScheme.primary,
                  isPercent: true,
                ),
              ],
            ),
          ),

        // ── Month navigator ──
        Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            IconButton(
              icon: const Icon(Icons.chevron_left),
              onPressed: () {
                int m = widget.month - 1;
                int y = widget.year;
                if (m < 1) { m = 12; y--; }
                widget.onMonthChanged?.call(m, y);
              },
            ),
            Text(
              '$monthName ${widget.year}',
              style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w600),
            ),
            IconButton(
              icon: const Icon(Icons.chevron_right),
              onPressed: () {
                int m = widget.month + 1;
                int y = widget.year;
                if (m > 12) { m = 1; y++; }
                widget.onMonthChanged?.call(m, y);
              },
            ),
          ],
        ),
        const SizedBox(height: 8),

        // ── Weekday headers ──
        Row(
          children: ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
              .map((d) => Expanded(
                    child: Center(
                      child: Text(
                        d,
                        style: TextStyle(
                          fontSize: 11,
                          fontWeight: FontWeight.w600,
                          color: theme.textTheme.bodySmall?.color,
                        ),
                      ),
                    ),
                  ))
              .toList(),
        ),
        const SizedBox(height: 4),

        // ── Calendar grid ──
        GridView.builder(
          shrinkWrap: true,
          physics: const NeverScrollableScrollPhysics(),
          gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(
            crossAxisCount: 7,
            mainAxisSpacing: 4,
            crossAxisSpacing: 4,
          ),
          itemCount: startWeekday - 1 + daysInMonth, // Mon=1 offset
          itemBuilder: (ctx, i) {
            final offset = (firstDay.weekday - 1) % 7; // Mon=0
            if (i < offset) return const SizedBox();
            final dayNum = i - offset + 1;
            if (dayNum > daysInMonth) return const SizedBox();

            final dayData = widget.days.firstWhere(
              (d) => d.day == dayNum,
              orElse: () => AttendanceDay(day: dayNum),
            );
            final color = _statusColor(dayData.status, dayData.isWeekend);
            final isSelected = _selectedDay?.day == dayNum;

            return GestureDetector(
              onTap: () => setState(() => _selectedDay = dayData),
              child: AnimatedContainer(
                duration: const Duration(milliseconds: 200),
                decoration: BoxDecoration(
                  color: dayData.status != null || dayData.isWeekend
                      ? color.withValues(alpha: 0.2)
                      : null,
                  borderRadius: BorderRadius.circular(8),
                  border: isSelected
                      ? Border.all(color: theme.colorScheme.primary, width: 2)
                      : null,
                ),
                child: Center(
                  child: Text(
                    '$dayNum',
                    style: TextStyle(
                      fontSize: 13,
                      fontWeight:
                          isSelected ? FontWeight.w700 : FontWeight.w500,
                      color: dayData.isWeekend
                          ? Colors.grey
                          : dayData.status != null
                              ? color
                              : null,
                    ),
                  ),
                ),
              ),
            );
          },
        ),

        // ── Day detail panel ──
        if (_selectedDay != null)
          AnimatedContainer(
            duration: const Duration(milliseconds: 300),
            curve: Curves.easeOutCubic,
            margin: const EdgeInsets.only(top: 12),
            padding: const EdgeInsets.all(14),
            decoration: BoxDecoration(
              color: theme.colorScheme.primary.withValues(alpha: 0.04),
              borderRadius: BorderRadius.circular(12),
              border: Border.all(
                color: theme.colorScheme.primary.withValues(alpha: 0.15),
              ),
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  DateFormat('EEEE, d MMMM yyyy').format(
                    DateTime(widget.year, widget.month, _selectedDay!.day),
                  ),
                  style: const TextStyle(
                      fontSize: 14, fontWeight: FontWeight.w600),
                ),
                const SizedBox(height: 8),
                Row(
                  children: [
                    Container(
                      padding: const EdgeInsets.symmetric(
                          horizontal: 10, vertical: 4),
                      decoration: BoxDecoration(
                        color: _statusColor(
                                _selectedDay!.status, _selectedDay!.isWeekend)
                            .withValues(alpha: 0.15),
                        borderRadius: BorderRadius.circular(6),
                      ),
                      child: Text(
                        _statusEmoji(_selectedDay!.status),
                        style: TextStyle(
                          fontSize: 12,
                          fontWeight: FontWeight.w600,
                          color: _statusColor(
                              _selectedDay!.status, _selectedDay!.isWeekend),
                        ),
                      ),
                    ),
                  ],
                ),
                if (_selectedDay!.checkIn != null ||
                    _selectedDay!.checkOut != null) ...[
                  const SizedBox(height: 8),
                  Row(
                    children: [
                      if (_selectedDay!.checkIn != null)
                        _timeChip('In: ${_selectedDay!.checkIn}',
                            const Color(0xFF22C55E)),
                      if (_selectedDay!.checkIn != null &&
                          _selectedDay!.checkOut != null)
                        const SizedBox(width: 12),
                      if (_selectedDay!.checkOut != null)
                        _timeChip('Out: ${_selectedDay!.checkOut}',
                            const Color(0xFFEF4444)),
                    ],
                  ),
                ],
                if (_selectedDay!.remarks != null) ...[
                  const SizedBox(height: 6),
                  Text(
                    'Remarks: ${_selectedDay!.remarks}',
                    style: TextStyle(
                      fontSize: 12,
                      color: theme.textTheme.bodySmall?.color,
                    ),
                  ),
                ],
              ],
            ),
          ),

        // ── Legend ──
        const SizedBox(height: 12),
        Wrap(
          spacing: 12,
          runSpacing: 4,
          children: [
            _legendItem('Present', const Color(0xFF22C55E)),
            _legendItem('Absent', const Color(0xFFEF4444)),
            _legendItem('Late', const Color(0xFFF59E0B)),
            _legendItem('Excused', const Color(0xFF3B82F6)),
            _legendItem('Holiday', const Color(0xFFE5E7EB)),
          ],
        ),
      ],
    );
  }

  Widget _summaryItem(String label, int value, Color color,
      {bool isPercent = false}) {
    return Column(
      children: [
        Text(
          isPercent ? '$value%' : '$value',
          style: TextStyle(
            fontSize: 18,
            fontWeight: FontWeight.w700,
            color: color,
          ),
        ),
        Text(
          label,
          style: const TextStyle(fontSize: 10, fontWeight: FontWeight.w500),
        ),
      ],
    );
  }

  Widget _timeChip(String text, Color color) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.1),
        borderRadius: BorderRadius.circular(6),
      ),
      child: Text(
        text,
        style: TextStyle(fontSize: 11, fontWeight: FontWeight.w600, color: color),
      ),
    );
  }

  Widget _legendItem(String label, Color color) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Container(
          width: 10,
          height: 10,
          decoration: BoxDecoration(
            color: color.withValues(alpha: 0.3),
            borderRadius: BorderRadius.circular(3),
          ),
        ),
        const SizedBox(width: 4),
        Text(label, style: const TextStyle(fontSize: 10)),
      ],
    );
  }
}
