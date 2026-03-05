import uuid
import enum
from datetime import datetime, date
from sqlalchemy import Column, String, Boolean, DateTime, Date, ForeignKey, Text, Integer, Numeric, Enum, Float, Time
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from database import Base


class Homework(Base):
    __tablename__ = "homework"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    branch_id = Column(UUID(as_uuid=True), ForeignKey("branches.id"), nullable=False, index=True)
    teacher_id = Column(UUID(as_uuid=True), ForeignKey("teachers.id"), nullable=False)
    class_id = Column(UUID(as_uuid=True), ForeignKey("classes.id"), nullable=False)
    section_id = Column(UUID(as_uuid=True), ForeignKey("sections.id"), nullable=True)
    subject_id = Column(UUID(as_uuid=True), ForeignKey("subjects.id"), nullable=False)
    title = Column(String(300), nullable=False)
    description = Column(Text, nullable=True)
    attachment_url = Column(String(500), nullable=True)
    assigned_date = Column(Date, default=date.today)
    due_date = Column(Date, nullable=False)
    max_marks = Column(Integer, nullable=True)
    is_graded = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.utcnow())


class HomeworkSubmission(Base):
    __tablename__ = "homework_submissions"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    homework_id = Column(UUID(as_uuid=True), ForeignKey("homework.id"), nullable=False, index=True)
    student_id = Column(UUID(as_uuid=True), ForeignKey("students.id"), nullable=False)
    content = Column(Text, nullable=True)
    attachment_url = Column(String(500), nullable=True)
    submitted_at = Column(DateTime, default=lambda: datetime.utcnow())
    marks_obtained = Column(Integer, nullable=True)
    teacher_remarks = Column(Text, nullable=True)
    graded_at = Column(DateTime, nullable=True)
    status = Column(String(20), default="submitted")  # submitted, graded, late, missing
