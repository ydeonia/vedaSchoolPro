import uuid
import enum
from datetime import datetime, date
from sqlalchemy import Column, String, Boolean, DateTime, Date, ForeignKey, Text, Integer, Numeric, Enum, Float, Time
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from database import Base


class BoardResult(Base):
    """Track board exam results (CBSE/ICSE/State) — class 10 & 12"""
    __tablename__ = "board_results"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    branch_id = Column(UUID(as_uuid=True), ForeignKey("branches.id"), nullable=False, index=True)
    academic_year = Column(String(20), nullable=False)  # "2025-26"
    board = Column(String(20), nullable=False)  # cbse, icse, state
    class_level = Column(String(5), nullable=False)  # "10" or "12"
    student_id = Column(UUID(as_uuid=True), ForeignKey("students.id"), nullable=True)
    student_name = Column(String(200), nullable=False)  # stored separately for alumni
    roll_number = Column(String(50), nullable=True)
    total_marks = Column(Float, nullable=True)
    max_marks = Column(Float, nullable=True)
    percentage = Column(Float, nullable=True)
    grade = Column(String(10), nullable=True)
    result_status = Column(String(20), default="pass")  # pass, fail, compartment, absent
    subject_wise = Column(JSONB, nullable=True)  # [{"subject":"Math","marks":95,"max":100,"grade":"A1"}]
    rank_in_school = Column(Integer, nullable=True)
    is_distinction = Column(Boolean, default=False)  # 90%+
    is_merit = Column(Boolean, default=False)  # School topper / board merit
    created_at = Column(DateTime, default=lambda: datetime.utcnow())
