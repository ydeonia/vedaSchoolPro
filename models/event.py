import uuid
import enum
from datetime import datetime, date
from sqlalchemy import Column, String, Boolean, DateTime, Date, ForeignKey, Text, Integer, Numeric, Enum, Float, Time
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from database import Base


class EventType(str, enum.Enum):
    HOLIDAY = "holiday"
    EXAM = "exam"
    EVENT = "event"
    PTM = "ptm"
    SPORTS = "sports"
    CULTURAL = "cultural"
    DEADLINE = "deadline"
    OTHER = "other"

class SchoolEvent(Base):
    __tablename__ = "school_events"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    branch_id = Column(UUID(as_uuid=True), ForeignKey("branches.id"), nullable=False, index=True)
    title = Column(String(300), nullable=False)
    description = Column(Text, nullable=True)
    event_type = Column(Enum(EventType), default=EventType.EVENT)
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=True)
    start_time = Column(Time, nullable=True)
    end_time = Column(Time, nullable=True)
    is_holiday = Column(Boolean, default=False)
    is_all_day = Column(Boolean, default=True)
    applies_to_classes = Column(Text, nullable=True)
    color = Column(String(7), default="#3B82F6")
    location = Column(String(300), nullable=True)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.utcnow())
