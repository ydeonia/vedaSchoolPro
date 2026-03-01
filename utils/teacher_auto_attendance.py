"""
Auto-detect teacher attendance.
Called when:
1. Teacher marks student attendance → auto-present
2. Teacher marks period completed → auto-present
3. Teacher self check-in
"""
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from models.teacher_attendance import TeacherAttendance, TeacherAttendanceStatus, CheckInSource
from datetime import date, datetime
import uuid


async def auto_mark_teacher_present(
    db: AsyncSession,
    teacher_id: uuid.UUID,
    branch_id: uuid.UUID,
    source: CheckInSource,
    user_id: uuid.UUID = None,
):
    """Auto-mark teacher as present if not already marked for today"""
    today = date.today()
    now = datetime.utcnow().time()

    # Check existing
    result = await db.execute(
        select(TeacherAttendance).where(
            TeacherAttendance.teacher_id == teacher_id,
            TeacherAttendance.date == today,
        )
    )
    existing = result.scalar_one_or_none()

    if existing:
        # Already marked — don't overwrite admin manual or self check-in
        return existing

    # Create new auto attendance
    att = TeacherAttendance(
        branch_id=branch_id,
        teacher_id=teacher_id,
        date=today,
        status=TeacherAttendanceStatus.PRESENT,
        check_in_time=now,
        source=source,
        marked_by=user_id,
    )
    db.add(att)
    # Don't commit here — let the calling function commit
    return att
