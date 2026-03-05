import uuid
import enum
from datetime import datetime, date
from sqlalchemy import Column, String, Boolean, DateTime, Date, ForeignKey, Text, Integer, Numeric, Enum, Float, Time
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from database import Base


class StudentPromotion(Base):
    """Track student promotions/demotions between classes"""
    __tablename__ = "student_promotions"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    branch_id = Column(UUID(as_uuid=True), ForeignKey("branches.id"), nullable=False, index=True)
    student_id = Column(UUID(as_uuid=True), ForeignKey("students.id"), nullable=False)
    from_class_id = Column(UUID(as_uuid=True), ForeignKey("classes.id"), nullable=False)
    to_class_id = Column(UUID(as_uuid=True), ForeignKey("classes.id"), nullable=True)  # null = TC/Dropout
    from_section_id = Column(UUID(as_uuid=True), ForeignKey("sections.id"), nullable=True)
    to_section_id = Column(UUID(as_uuid=True), ForeignKey("sections.id"), nullable=True)
    academic_year_from = Column(String(20), nullable=False)  # "2024-25"
    academic_year_to = Column(String(20), nullable=False)  # "2025-26"
    action = Column(String(20), default="promoted")  # promoted, detained, tc_issued, dropout
    remarks = Column(Text, nullable=True)
    promoted_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    promoted_at = Column(DateTime, default=lambda: datetime.utcnow())
