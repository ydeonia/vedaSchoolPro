import uuid
import enum
from datetime import datetime, date
from sqlalchemy import Column, String, Boolean, DateTime, Date, ForeignKey, Text, Integer, Numeric, Enum, Float, Time
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from database import Base


class AchievementCategory(str, enum.Enum):
    ACADEMIC = "academic"
    SPORTS = "sports"
    DISCIPLINE = "discipline"
    ATTENDANCE = "attendance"
    EXTRACURRICULAR = "extracurricular"
    LEADERSHIP = "leadership"
    CREATIVITY = "creativity"
    COMMUNITY = "community"

class StudentAchievement(Base):
    __tablename__ = "student_achievements"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    branch_id = Column(UUID(as_uuid=True), ForeignKey("branches.id"), nullable=False, index=True)
    student_id = Column(UUID(as_uuid=True), ForeignKey("students.id"), nullable=False, index=True)
    title = Column(String(300), nullable=False)
    description = Column(Text, nullable=True)
    category = Column(Enum(AchievementCategory), nullable=False)
    badge_icon = Column(String(10), default="🏆")
    awarded_date = Column(Date, nullable=False)
    awarded_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    is_visible_to_parent = Column(Boolean, default=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.utcnow())
