import uuid
import enum
from datetime import datetime, date
from sqlalchemy import Column, String, Boolean, DateTime, Date, ForeignKey, Text, Integer, Numeric, Enum, Float, Time
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from database import Base


class RemarkCategory(str, enum.Enum):
    STRENGTH = "strength"
    CONCERN = "concern"
    SUGGESTION = "suggestion"

class RemarkTag(Base):
    """Pre-defined skill tags that teachers can tap to quickly give feedback.
    Subject-specific: 'Algebra weak', 'Grammar excellent', 'Handwriting poor' etc."""
    __tablename__ = "remark_tags"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    branch_id = Column(UUID(as_uuid=True), ForeignKey("branches.id"), nullable=True)  # NULL = global default
    subject_name = Column(String(100), nullable=False)  # 'Mathematics', 'English', 'General'
    tag_text = Column(String(200), nullable=False)       # 'Weak in Algebra'
    category = Column(Enum(RemarkCategory), nullable=False)  # strength/concern/suggestion
    icon = Column(String(10), default="📝")              # emoji for display
    sort_order = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)

class StudentRemark(Base):
    """Teacher feedback per student, per subject, per exam (or general).
    Combines quick tags + optional free text."""
    __tablename__ = "student_remarks"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    branch_id = Column(UUID(as_uuid=True), ForeignKey("branches.id"), nullable=False, index=True)
    student_id = Column(UUID(as_uuid=True), ForeignKey("students.id"), nullable=False, index=True)
    teacher_id = Column(UUID(as_uuid=True), ForeignKey("teachers.id"), nullable=False)
    subject_id = Column(UUID(as_uuid=True), ForeignKey("subjects.id"), nullable=True)  # NULL = general remark
    exam_id = Column(UUID(as_uuid=True), ForeignKey("exams.id"), nullable=True)        # NULL = anytime remark
    tags = Column(Text, nullable=True)          # JSON array of tag IDs: ["uuid1","uuid2"]
    tag_texts = Column(Text, nullable=True)     # Denormalized: ["Algebra weak","Needs practice"]
    custom_remark = Column(String(500), nullable=True)  # Teacher's own words (optional)
    category = Column(Enum(RemarkCategory), default=RemarkCategory.SUGGESTION)
    is_visible_to_parent = Column(Boolean, default=True)
    is_visible_to_student = Column(Boolean, default=True)
    parent_acknowledged = Column(Boolean, default=False)
    parent_acknowledged_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.utcnow())
    updated_at = Column(DateTime, default=lambda: datetime.utcnow(), onupdate=lambda: datetime.utcnow())
