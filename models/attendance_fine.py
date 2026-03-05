import uuid
import enum
from datetime import datetime, date
from sqlalchemy import Column, String, Boolean, DateTime, Date, ForeignKey, Text, Integer, Numeric, Enum, Float, Time
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from database import Base


class AttendanceFineRule(Base):
    __tablename__ = "attendance_fine_rules"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    branch_id = Column(UUID(as_uuid=True), ForeignKey("branches.id"), nullable=False, index=True)
    rule_name = Column(String(200), nullable=False)  # "Daily absence fine"
    fine_type = Column(String(30), default="per_day")  # per_day, monthly_threshold
    fine_amount = Column(Float, default=50)  # ₹50 per absent day
    threshold_days = Column(Integer, nullable=True)  # null for per_day, or 5 for "after 5 absences"
    applicable_to = Column(String(20), default="all")  # all, class_specific
    applicable_classes = Column(JSONB, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.utcnow())


class AttendanceFine(Base):
    __tablename__ = "attendance_fines"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    branch_id = Column(UUID(as_uuid=True), ForeignKey("branches.id"), nullable=False, index=True)
    student_id = Column(UUID(as_uuid=True), ForeignKey("students.id"), nullable=False)
    rule_id = Column(UUID(as_uuid=True), ForeignKey("attendance_fine_rules.id"), nullable=True)
    month = Column(Integer, nullable=False)
    year = Column(Integer, nullable=False)
    absent_days = Column(Integer, default=0)
    fine_amount = Column(Float, default=0)
    status = Column(String(20), default="pending")  # pending, added_to_fee, waived, paid
    created_at = Column(DateTime, default=lambda: datetime.utcnow())
