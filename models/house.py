import uuid
import enum
from datetime import datetime, date
from sqlalchemy import Column, String, Boolean, DateTime, Date, ForeignKey, Text, Integer, Numeric, Enum, Float, Time
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from database import Base


class House(Base):
    __tablename__ = "houses"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    branch_id = Column(UUID(as_uuid=True), ForeignKey("branches.id"), nullable=False, index=True)
    name = Column(String(100), nullable=False)  # "Red House", "Blue House"
    color = Column(String(7), default="#DC2626")  # hex color
    tagline = Column(String(300), nullable=True)  # "Courage and Strength"
    logo_url = Column(String(500), nullable=True)
    house_master_id = Column(UUID(as_uuid=True), ForeignKey("teachers.id"), nullable=True)  # teacher incharge
    points = Column(Integer, default=0)  # house points for competitions
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.utcnow())


class StudentHouse(Base):
    """Tag students to houses"""
    __tablename__ = "student_houses"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    student_id = Column(UUID(as_uuid=True), ForeignKey("students.id"), nullable=False, index=True)
    house_id = Column(UUID(as_uuid=True), ForeignKey("houses.id"), nullable=False)
    academic_year = Column(String(20), nullable=True)  # "2025-26"
    assigned_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    assigned_at = Column(DateTime, default=lambda: datetime.utcnow())
