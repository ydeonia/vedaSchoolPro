import uuid
from datetime import datetime, timezone, date, timezone
from sqlalchemy import Column, String, DateTime, Date, ForeignKey, Text, Boolean, Integer, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from database import Base


class PeriodLog(Base):
    """Tracks when a teacher completes a period — what topic was covered"""
    __tablename__ = "period_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    branch_id = Column(UUID(as_uuid=True), ForeignKey("branches.id"), nullable=False, index=True)

    teacher_id = Column(UUID(as_uuid=True), ForeignKey("teachers.id"), nullable=False, index=True)
    timetable_slot_id = Column(UUID(as_uuid=True), ForeignKey("timetable_slots.id"), nullable=True)
    class_id = Column(UUID(as_uuid=True), ForeignKey("classes.id"), nullable=False)
    section_id = Column(UUID(as_uuid=True), ForeignKey("sections.id"), nullable=True)
    subject_id = Column(UUID(as_uuid=True), ForeignKey("subjects.id"), nullable=False)
    period_definition_id = Column(UUID(as_uuid=True), ForeignKey("period_definitions.id"), nullable=True)

    date = Column(Date, nullable=False, index=True, default=date.today)
    status = Column(String(20), default="completed")  # completed, substitution, cancelled

    # What was taught
    syllabus_id = Column(UUID(as_uuid=True), ForeignKey("syllabus.id"), nullable=True)
    topic_covered = Column(String(500), nullable=True)
    remarks = Column(Text, nullable=True)

    # Homework assigned
    homework = Column(Text, nullable=True)

    completed_at = Column(DateTime, default=lambda: datetime.utcnow())
    created_at = Column(DateTime, default=lambda: datetime.utcnow())

    __table_args__ = (
        UniqueConstraint('teacher_id', 'period_definition_id', 'date',
                         name='uq_teacher_period_date'),
    )

    # Relationships
    teacher = relationship("Teacher")
    class_ = relationship("Class")
    section = relationship("Section")
    subject = relationship("Subject")
    syllabus_entry = relationship("Syllabus")
    period_definition = relationship("PeriodDefinition")