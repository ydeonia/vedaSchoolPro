import uuid
import enum
from datetime import datetime, date
from sqlalchemy import Column, String, Boolean, DateTime, Date, ForeignKey, Text, Integer, Numeric, Enum, Float, Time
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from database import Base


class DiaryEntryType(str, enum.Enum):
    POSITIVE = "positive"
    CONCERN = "concern"
    INFORMATIONAL = "informational"
    HOMEWORK_NOTE = "homework_note"

class DailyDiary(Base):
    __tablename__ = "daily_diary"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    branch_id = Column(UUID(as_uuid=True), ForeignKey("branches.id"), nullable=False, index=True)
    teacher_id = Column(UUID(as_uuid=True), ForeignKey("teachers.id"), nullable=False)
    student_id = Column(UUID(as_uuid=True), ForeignKey("students.id"), nullable=True)
    class_id = Column(UUID(as_uuid=True), ForeignKey("classes.id"), nullable=True)
    section_id = Column(UUID(as_uuid=True), ForeignKey("sections.id"), nullable=True)
    entry_date = Column(Date, nullable=False)
    entry_type = Column(Enum(DiaryEntryType), default=DiaryEntryType.INFORMATIONAL)
    content = Column(Text, nullable=False)
    is_visible_to_parent = Column(Boolean, default=True)
    parent_acknowledged = Column(Boolean, default=False)
    parent_acknowledged_at = Column(DateTime, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.utcnow())
