import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Boolean, DateTime, Date, ForeignKey, Text, Integer
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from database import Base


class Teacher(Base):
    __tablename__ = "teachers"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True, unique=True)
    branch_id = Column(UUID(as_uuid=True), ForeignKey("branches.id"), nullable=False, index=True)

    employee_id = Column(String(50), nullable=True, index=True)
    first_name = Column(String(100), nullable=False)
    last_name = Column(String(100), nullable=True)
    phone = Column(String(15), nullable=True)
    email = Column(String(255), nullable=True)
    photo_url = Column(String(500), nullable=True)

    # Professional details
    qualification = Column(String(200), nullable=True)
    specialization = Column(String(200), nullable=True)
    experience_years = Column(Integer, default=0)
    joining_date = Column(Date, nullable=True)
    designation = Column(String(100), nullable=True)  # PGT, TGT, PRT, etc.
    signature_url = Column(String(500), nullable=True)

    # Address
    address = Column(Text, nullable=True)

    is_class_teacher = Column(Boolean, default=False)
    class_teacher_of = Column(UUID(as_uuid=True), ForeignKey("sections.id"), nullable=True)

    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.utcnow())
    updated_at = Column(DateTime, default=lambda: datetime.utcnow(), onupdate=lambda: datetime.utcnow())

    # Relationships
    user = relationship("User", back_populates="teacher_profile")
    branch = relationship("Branch", back_populates="teachers")
    class_subjects = relationship("ClassSubject", back_populates="teacher")

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name or ''}".strip()