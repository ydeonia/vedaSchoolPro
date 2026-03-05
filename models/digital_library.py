import uuid
import enum
from datetime import datetime, date
from sqlalchemy import Column, String, Boolean, DateTime, Date, ForeignKey, Text, Integer, Numeric, Enum, Float, Time
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from database import Base


class DigitalContent(Base):
    """Magazines, Textbooks, Study Material uploaded by admin/teachers"""
    __tablename__ = "digital_contents"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    branch_id = Column(UUID(as_uuid=True), ForeignKey("branches.id"), nullable=False, index=True)
    title = Column(String(300), nullable=False)
    description = Column(Text, nullable=True)
    content_type = Column(String(50), nullable=False)  # magazine, textbook, notes, worksheet, circular
    file_url = Column(String(500), nullable=False)
    file_size_kb = Column(Integer, default=0)
    thumbnail_url = Column(String(500), nullable=True)
    subject_id = Column(UUID(as_uuid=True), ForeignKey("subjects.id"), nullable=True)
    class_id = Column(UUID(as_uuid=True), ForeignKey("classes.id"), nullable=True)
    uploaded_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    visibility = Column(String(30), default="students_parents")  # students_parents, students_only, teachers_only, all
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.utcnow())


class ContentView(Base):
    """Track who viewed what — drill-down analytics"""
    __tablename__ = "content_views"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    content_id = Column(UUID(as_uuid=True), ForeignKey("digital_contents.id"), nullable=False, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    student_id = Column(UUID(as_uuid=True), ForeignKey("students.id"), nullable=True)
    viewed_at = Column(DateTime, default=lambda: datetime.utcnow())
    duration_seconds = Column(Integer, default=0)  # how long they viewed
