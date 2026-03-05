import uuid
import enum
from datetime import datetime, date
from sqlalchemy import Column, String, Boolean, DateTime, Date, ForeignKey, Text, Integer, Numeric, Enum, Float, Time
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from database import Base


class AdmissionStatus(str, enum.Enum):
    INQUIRY = "inquiry"
    APPLIED = "applied"
    DOCUMENT_PENDING = "document_pending"
    INTERVIEW = "interview"
    ADMITTED = "admitted"
    ENROLLED = "enrolled"
    REJECTED = "rejected"
    WITHDRAWN = "withdrawn"


class Admission(Base):
    __tablename__ = "admissions"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    branch_id = Column(UUID(as_uuid=True), ForeignKey("branches.id"), nullable=False, index=True)
    academic_year = Column(String(20), nullable=True)  # 2025-26

    # Student info
    student_name = Column(String(200), nullable=False)
    date_of_birth = Column(Date, nullable=True)
    gender = Column(String(10), nullable=True)
    blood_group = Column(String(5), nullable=True)
    applying_for_class = Column(String(50), nullable=True)
    previous_school = Column(String(300), nullable=True)

    # Parent info
    father_name = Column(String(200), nullable=True)
    father_phone = Column(String(15), nullable=True)
    father_email = Column(String(200), nullable=True)
    father_occupation = Column(String(200), nullable=True)
    mother_name = Column(String(200), nullable=True)
    mother_phone = Column(String(15), nullable=True)
    address = Column(Text, nullable=True)

    # Process
    status = Column(Enum(AdmissionStatus), default=AdmissionStatus.INQUIRY, index=True)
    enquiry_date = Column(Date, default=date.today)
    application_date = Column(Date, nullable=True)
    interview_date = Column(Date, nullable=True)
    interview_notes = Column(Text, nullable=True)
    approval_date = Column(Date, nullable=True)
    enrollment_date = Column(Date, nullable=True)
    rejection_reason = Column(Text, nullable=True)

    # Fees
    registration_fee_paid = Column(Boolean, default=False)
    admission_fee_paid = Column(Boolean, default=False)

    # Documents
    birth_certificate = Column(Boolean, default=False)
    transfer_certificate = Column(Boolean, default=False)
    previous_marksheet = Column(Boolean, default=False)
    aadhaar_copy = Column(Boolean, default=False)
    photos = Column(Boolean, default=False)

    # Link to student record after enrollment
    student_id = Column(UUID(as_uuid=True), ForeignKey("students.id"), nullable=True)

    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.utcnow())
    updated_at = Column(DateTime, default=lambda: datetime.utcnow(), onupdate=lambda: datetime.utcnow())
