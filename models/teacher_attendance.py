import uuid
from datetime import datetime, timezone, date, timezone
from sqlalchemy import Column, String, DateTime, Date, ForeignKey, Text, Boolean, Integer, Time, Enum as SAEnum, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from database import Base
import enum


class TeacherAttendanceStatus(str, enum.Enum):
    PRESENT = "present"
    ABSENT = "absent"
    LATE = "late"
    HALF_DAY = "half_day"
    ON_LEAVE = "on_leave"


class CheckInSource(str, enum.Enum):
    AUTO_STUDENT_ATTENDANCE = "auto_student_attendance"  # Auto: teacher marked student attendance
    AUTO_PERIOD_LOG = "auto_period_log"  # Auto: teacher marked period completed
    SELF_CHECKIN = "self_checkin"  # Teacher tapped check-in
    ADMIN_MANUAL = "admin_manual"  # Admin marked manually


class TeacherAttendance(Base):
    """Daily attendance record for teachers — one per teacher per day"""
    __tablename__ = "teacher_attendance"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    branch_id = Column(UUID(as_uuid=True), ForeignKey("branches.id"), nullable=False, index=True)
    teacher_id = Column(UUID(as_uuid=True), ForeignKey("teachers.id"), nullable=False, index=True)
    date = Column(Date, nullable=False, index=True, default=date.today)
    status = Column(SAEnum(TeacherAttendanceStatus), default=TeacherAttendanceStatus.PRESENT)
    check_in_time = Column(Time, nullable=True)
    check_out_time = Column(Time, nullable=True)
    source = Column(SAEnum(CheckInSource), default=CheckInSource.SELF_CHECKIN)
    remarks = Column(Text, nullable=True)
    marked_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.utcnow())
    updated_at = Column(DateTime, default=lambda: datetime.utcnow(), onupdate=lambda: datetime.utcnow())

    __table_args__ = (
        UniqueConstraint('teacher_id', 'date', name='uq_teacher_date_attendance'),
    )

    teacher = relationship("Teacher")


class LeaveType(str, enum.Enum):
    CASUAL = "casual"
    SICK = "sick"
    EARNED = "earned"
    MATERNITY = "maternity"
    PATERNITY = "paternity"
    COMPENSATORY = "compensatory"
    UNPAID = "unpaid"
    OTHER = "other"


class LeaveStatus(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    CANCELLED = "cancelled"


class LeaveRequest(Base):
    """Leave applications from teachers"""
    __tablename__ = "leave_requests"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    branch_id = Column(UUID(as_uuid=True), ForeignKey("branches.id"), nullable=False, index=True)
    teacher_id = Column(UUID(as_uuid=True), ForeignKey("teachers.id"), nullable=False, index=True)

    leave_type = Column(SAEnum(LeaveType), nullable=False)
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    reason = Column(Text, nullable=False)
    status = Column(SAEnum(LeaveStatus, values_callable=lambda x: [e.value for e in x]), default=LeaveStatus.PENDING)

    # Approval
    reviewed_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    reviewed_at = Column(DateTime, nullable=True)
    admin_remarks = Column(Text, nullable=True)

    # On-behalf tracking
    applied_on_behalf_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    on_behalf_name = Column(String(200), nullable=True)  # Cached name of person who raised it

    created_at = Column(DateTime, default=lambda: datetime.utcnow())
    updated_at = Column(DateTime, default=lambda: datetime.utcnow(), onupdate=lambda: datetime.utcnow())

    teacher = relationship("Teacher")