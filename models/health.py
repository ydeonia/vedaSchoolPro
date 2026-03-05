import uuid
import enum
from datetime import datetime, date
from sqlalchemy import Column, String, Boolean, DateTime, Date, ForeignKey, Text, Integer, Numeric, Enum, Float, Time
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from database import Base


class StudentHealth(Base):
    __tablename__ = "student_health"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    student_id = Column(UUID(as_uuid=True), ForeignKey("students.id"), nullable=False, unique=True)
    branch_id = Column(UUID(as_uuid=True), ForeignKey("branches.id"), nullable=False)
    blood_group = Column(String(5), nullable=True)
    height_cm = Column(Float, nullable=True)
    weight_kg = Column(Float, nullable=True)
    bmi = Column(Float, nullable=True)
    vision_left = Column(String(20), nullable=True)
    vision_right = Column(String(20), nullable=True)
    wears_glasses = Column(Boolean, default=False)
    allergies = Column(Text, nullable=True)
    chronic_conditions = Column(Text, nullable=True)
    medications = Column(Text, nullable=True)
    disabilities = Column(Text, nullable=True)
    vaccinations = Column(Text, nullable=True)
    emergency_contact_1 = Column(String(200), nullable=True)
    emergency_contact_2 = Column(String(200), nullable=True)
    family_doctor = Column(String(200), nullable=True)
    doctor_phone = Column(String(15), nullable=True)
    insurance_id = Column(String(100), nullable=True)
    last_checkup_date = Column(Date, nullable=True)
    checkup_notes = Column(Text, nullable=True)
    updated_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.utcnow())
    updated_at = Column(DateTime, default=lambda: datetime.utcnow(), onupdate=lambda: datetime.utcnow())
