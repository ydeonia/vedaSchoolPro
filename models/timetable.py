import uuid
from datetime import datetime, timezone, time
from sqlalchemy import Column, String, Boolean, DateTime, Integer, ForeignKey, Time, Enum as SAEnum, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from database import Base
import enum


class DayOfWeek(str, enum.Enum):
    MONDAY = "monday"
    TUESDAY = "tuesday"
    WEDNESDAY = "wednesday"
    THURSDAY = "thursday"
    FRIDAY = "friday"
    SATURDAY = "saturday"


class PeriodType(str, enum.Enum):
    REGULAR = "regular"
    BREAK = "break"
    LUNCH = "lunch"
    ASSEMBLY = "assembly"
    EXTRA = "extra"


class PeriodDefinition(Base):
    """Defines the period timings for a branch (e.g., Period 1: 8:00-8:40)"""
    __tablename__ = "period_definitions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    branch_id = Column(UUID(as_uuid=True), ForeignKey("branches.id"), nullable=False, index=True)
    period_number = Column(Integer, nullable=False)  # 1, 2, 3...
    label = Column(String(50), nullable=False)  # "Period 1", "Lunch Break"
    start_time = Column(Time, nullable=False)
    end_time = Column(Time, nullable=False)
    period_type = Column(SAEnum(PeriodType), default=PeriodType.REGULAR)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.utcnow())

    __table_args__ = (
        UniqueConstraint('branch_id', 'period_number', name='uq_branch_period_number'),
    )

    # Relationships
    timetable_slots = relationship("TimetableSlot", back_populates="period_definition", cascade="all, delete-orphan")


class TimetableSlot(Base):
    """Assigns teacher+subject to a class+section+period+day"""
    __tablename__ = "timetable_slots"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    branch_id = Column(UUID(as_uuid=True), ForeignKey("branches.id"), nullable=False, index=True)
    academic_year_id = Column(UUID(as_uuid=True), ForeignKey("academic_years.id"), nullable=True)

    class_id = Column(UUID(as_uuid=True), ForeignKey("classes.id"), nullable=False, index=True)
    section_id = Column(UUID(as_uuid=True), ForeignKey("sections.id"), nullable=True)
    period_id = Column(UUID(as_uuid=True), ForeignKey("period_definitions.id"), nullable=False)
    day_of_week = Column(SAEnum(DayOfWeek), nullable=False)

    subject_id = Column(UUID(as_uuid=True), ForeignKey("subjects.id"), nullable=True)
    teacher_id = Column(UUID(as_uuid=True), ForeignKey("teachers.id"), nullable=True)

    room = Column(String(50), nullable=True)  # Optional room assignment
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.utcnow())

    __table_args__ = (
        UniqueConstraint('class_id', 'section_id', 'period_id', 'day_of_week',
                         name='uq_class_section_period_day'),
    )

    # Relationships
    period_definition = relationship("PeriodDefinition", back_populates="timetable_slots")
    class_ = relationship("Class")
    section = relationship("Section")
    subject = relationship("Subject")
    teacher = relationship("Teacher")