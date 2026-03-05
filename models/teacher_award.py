import uuid
import enum
from datetime import datetime, date
from sqlalchemy import Column, String, Boolean, DateTime, Date, ForeignKey, Text, Integer, Numeric, Enum, Float, Time
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from database import Base


class TeacherAward(Base):
    """Monthly/annual teacher recognition & awards"""
    __tablename__ = "teacher_awards"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    branch_id = Column(UUID(as_uuid=True), ForeignKey("branches.id"), nullable=False, index=True)
    teacher_id = Column(UUID(as_uuid=True), ForeignKey("teachers.id"), nullable=False)
    award_type = Column(String(50), nullable=False)  # star_of_month, best_performance, innovation, punctuality, parent_choice
    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    month = Column(Integer, nullable=True)  # 1-12
    year = Column(Integer, nullable=False)
    prize_details = Column(String(300), nullable=True)  # "Certificate + ₹2000 voucher"
    nominated_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    criteria_data = Column(JSONB, nullable=True)  # auto-calculated metrics
    status = Column(String(20), default="nominated")  # nominated, approved, awarded, rejected
    awarded_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.utcnow())

    teacher = relationship("Teacher")
