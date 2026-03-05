import uuid
from datetime import datetime, timezone, time
from sqlalchemy import Column, String, Boolean, DateTime, Integer, ForeignKey, Time, Date, Text, Float, Enum as SAEnum, UniqueConstraint
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


class SubstitutionStatus(str, enum.Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


# ═══════════════════════════════════════════════════════════
# BELL SCHEDULE TEMPLATES
# ═══════════════════════════════════════════════════════════

class BellScheduleTemplate(Base):
    """Named bell schedule template (e.g. 'Primary Standard', 'Senior Standard', 'Half-Day Saturday')"""
    __tablename__ = "bell_schedule_templates"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    branch_id = Column(UUID(as_uuid=True), ForeignKey("branches.id"), nullable=False, index=True)
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    is_default = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.utcnow())

    __table_args__ = (
        UniqueConstraint('branch_id', 'name', name='uq_branch_template_name'),
    )

    # Relationships
    periods = relationship("PeriodDefinition", back_populates="template", cascade="all, delete-orphan")
    assignments = relationship("ClassScheduleAssignment", back_populates="template")


class ClassScheduleAssignment(Base):
    """Assigns a bell schedule template to a class (optionally per day-of-week for overrides like Saturday half-day)"""
    __tablename__ = "class_schedule_assignments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    branch_id = Column(UUID(as_uuid=True), ForeignKey("branches.id"), nullable=False, index=True)
    class_id = Column(UUID(as_uuid=True), ForeignKey("classes.id"), nullable=False)
    section_id = Column(UUID(as_uuid=True), ForeignKey("sections.id"), nullable=True)
    template_id = Column(UUID(as_uuid=True), ForeignKey("bell_schedule_templates.id"), nullable=False)
    day_of_week = Column(SAEnum(DayOfWeek), nullable=True)  # NULL = all days
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.utcnow())

    __table_args__ = (
        UniqueConstraint('class_id', 'section_id', 'day_of_week', name='uq_class_section_day_assignment'),
    )

    template = relationship("BellScheduleTemplate", back_populates="assignments")
    class_ = relationship("Class")
    section = relationship("Section")

# ═══════════════════════════════════════════════════════════
# PERIOD DEFINITIONS (Modified — now belongs to a template)
# ═══════════════════════════════════════════════════════════

class PeriodDefinition(Base):
    """Defines the period timings for a template (e.g., Period 1: 8:00-8:40)"""
    __tablename__ = "period_definitions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    branch_id = Column(UUID(as_uuid=True), ForeignKey("branches.id"), nullable=False, index=True)
    template_id = Column(UUID(as_uuid=True), ForeignKey("bell_schedule_templates.id"), nullable=True, index=True)
    period_number = Column(Integer, nullable=False)  # 1, 2, 3...
    label = Column(String(50), nullable=False)  # "Period 1", "Lunch Break"
    start_time = Column(Time, nullable=False)
    end_time = Column(Time, nullable=False)
    period_type = Column(SAEnum(PeriodType), default=PeriodType.REGULAR)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.utcnow())

    __table_args__ = (
        UniqueConstraint('template_id', 'period_number', name='uq_template_period_number'),
    )

    # Relationships
    template = relationship("BellScheduleTemplate", back_populates="periods")
    timetable_slots = relationship("TimetableSlot", back_populates="period_definition", cascade="all, delete-orphan")


# ═══════════════════════════════════════════════════════════
# TIMETABLE SLOTS
# ═══════════════════════════════════════════════════════════

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

# ═══════════════════════════════════════════════════════════
# SUBJECT HOURS CONFIG
# ═══════════════════════════════════════════════════════════

class SubjectHoursConfig(Base):
    """Configures expected periods per week for each subject in a class"""
    __tablename__ = "subject_hours_config"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    branch_id = Column(UUID(as_uuid=True), ForeignKey("branches.id"), nullable=False, index=True)
    class_id = Column(UUID(as_uuid=True), ForeignKey("classes.id"), nullable=False)
    subject_id = Column(UUID(as_uuid=True), ForeignKey("subjects.id"), nullable=False)
    periods_per_week = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, default=lambda: datetime.utcnow())

    __table_args__ = (
        UniqueConstraint('branch_id', 'class_id', 'subject_id', name='uq_branch_class_subject_hours'),
    )

    class_ = relationship("Class")
    subject = relationship("Subject")


# ═══════════════════════════════════════════════════════════
# SUBSTITUTION MANAGEMENT
# ═══════════════════════════════════════════════════════════

class Substitution(Base):
    """Tracks teacher substitutions for absent teachers"""
    __tablename__ = "substitutions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    branch_id = Column(UUID(as_uuid=True), ForeignKey("branches.id"), nullable=False, index=True)
    date = Column(Date, nullable=False, index=True)
    timetable_slot_id = Column(UUID(as_uuid=True), ForeignKey("timetable_slots.id"), nullable=False)
    original_teacher_id = Column(UUID(as_uuid=True), ForeignKey("teachers.id"), nullable=False)
    substitute_teacher_id = Column(UUID(as_uuid=True), ForeignKey("teachers.id"), nullable=False)
    reason = Column(String(255), nullable=True)
    status = Column(SAEnum(SubstitutionStatus), default=SubstitutionStatus.PENDING)
    assigned_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.utcnow())

    timetable_slot = relationship("TimetableSlot")
    original_teacher = relationship("Teacher", foreign_keys=[original_teacher_id])
    substitute_teacher = relationship("Teacher", foreign_keys=[substitute_teacher_id])
