import uuid
import enum
from datetime import datetime, date
from sqlalchemy import Column, String, Boolean, DateTime, Date, ForeignKey, Text, Integer, Numeric, Enum, Float, Time
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from database import Base


class LeaveReasonType(str, enum.Enum):
    MEDICAL = "medical"
    FAMILY = "family"
    PERSONAL = "personal"
    RELIGIOUS = "religious"
    EMERGENCY = "emergency"
    OTHER = "other"

class ApprovalStatus(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"

class StudentLeave(Base):
    __tablename__ = "student_leaves"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    branch_id = Column(UUID(as_uuid=True), ForeignKey("branches.id"), nullable=False, index=True)
    student_id = Column(UUID(as_uuid=True), ForeignKey("students.id"), nullable=False, index=True)
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    reason_type = Column(Enum(LeaveReasonType), nullable=False)
    reason_text = Column(String(500), nullable=True)
    total_days = Column(Integer, default=1)
    parent_status = Column(Enum(ApprovalStatus), default=ApprovalStatus.PENDING)
    parent_comment = Column(String(300), nullable=True)
    parent_approved_at = Column(DateTime, nullable=True)
    parent_approved_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    teacher_status = Column(Enum(ApprovalStatus), default=ApprovalStatus.PENDING)
    teacher_comment = Column(String(300), nullable=True)
    teacher_approved_at = Column(DateTime, nullable=True)
    teacher_approved_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    has_exam_conflict = Column(Boolean, default=False)
    conflict_details = Column(String(500), nullable=True)
    has_event_conflict = Column(Boolean, default=False)
    event_conflict_details = Column(String(500), nullable=True)
    applied_by = Column(String(20), default="student")
    is_cancelled = Column(Boolean, default=False)
    created_at = Column(DateTime, default=lambda: datetime.utcnow())
    updated_at = Column(DateTime, default=lambda: datetime.utcnow(), onupdate=lambda: datetime.utcnow())
