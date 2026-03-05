import uuid
import enum
from datetime import datetime, date
from sqlalchemy import Column, String, Boolean, DateTime, Date, ForeignKey, Text, Integer, Numeric, Enum, Float, Time
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from database import Base


class StudentRole(Base):
    """Head Boy, Head Girl, House Captain, Class Monitor, etc."""
    __tablename__ = "student_roles"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    branch_id = Column(UUID(as_uuid=True), ForeignKey("branches.id"), nullable=False, index=True)
    student_id = Column(UUID(as_uuid=True), ForeignKey("students.id"), nullable=False)
    role_type = Column(String(50), nullable=False)  # head_boy, head_girl, house_captain, class_monitor, sports_captain, prefect, vice_captain
    title = Column(String(200), nullable=False)  # "Head Boy", "House Captain - Red House"
    house_id = Column(UUID(as_uuid=True), ForeignKey("houses.id"), nullable=True)  # for house-specific roles
    class_id = Column(UUID(as_uuid=True), ForeignKey("classes.id"), nullable=True)  # for class-specific roles
    academic_year = Column(String(20), nullable=True)
    awarded_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.utcnow())
