import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Boolean, DateTime, Integer, Date, ForeignKey, Text, Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from database import Base
import enum


class Gender(str, enum.Enum):
    MALE = "male"
    FEMALE = "female"
    OTHER = "other"


class AdmissionStatus(str, enum.Enum):
    INQUIRY = "inquiry"
    APPLIED = "applied"
    ADMITTED = "admitted"
    REJECTED = "rejected"
    WITHDRAWN = "withdrawn"
    TC_ISSUED = "tc_issued"
    LEFT = "left"


class Student(Base):
    __tablename__ = "students"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True, unique=True)
    branch_id = Column(UUID(as_uuid=True), ForeignKey("branches.id"), nullable=False, index=True)
    class_id = Column(UUID(as_uuid=True), ForeignKey("classes.id"), nullable=True)
    section_id = Column(UUID(as_uuid=True), ForeignKey("sections.id"), nullable=True)
    academic_year_id = Column(UUID(as_uuid=True), ForeignKey("academic_years.id"), nullable=True)

    # Admission details
    admission_number = Column(String(50), nullable=True, index=True)
    admission_date = Column(Date, nullable=True)
    admission_status = Column(SAEnum(AdmissionStatus), default=AdmissionStatus.ADMITTED)
    roll_number = Column(String(20), nullable=True)

    # Personal details
    first_name = Column(String(100), nullable=False)
    last_name = Column(String(100), nullable=True)
    date_of_birth = Column(Date, nullable=True)
    gender = Column(SAEnum(Gender), nullable=True)
    blood_group = Column(String(5), nullable=True)
    aadhaar_number = Column(String(12), nullable=True)
    photo_url = Column(String(500), nullable=True)

    # Parent/Guardian details
    father_name = Column(String(200), nullable=True)
    father_phone = Column(String(15), nullable=True)
    father_email = Column(String(255), nullable=True)
    father_occupation = Column(String(100), nullable=True)
    mother_name = Column(String(200), nullable=True)
    mother_phone = Column(String(15), nullable=True)
    mother_email = Column(String(255), nullable=True)
    guardian_name = Column(String(200), nullable=True)
    guardian_phone = Column(String(15), nullable=True)

    # Address
    address = Column(Text, nullable=True)
    city = Column(String(100), nullable=True)
    state = Column(String(100), nullable=True)
    pincode = Column(String(10), nullable=True)

    # Transport
    uses_transport = Column(Boolean, default=False)
    transport_route = Column(String(100), nullable=True)

    # Medical
    medical_conditions = Column(Text, nullable=True)
    emergency_contact = Column(String(15), nullable=True)

    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.utcnow())
    updated_at = Column(DateTime, default=lambda: datetime.utcnow(), onupdate=lambda: datetime.utcnow())

    # Relationships
    user = relationship("User", back_populates="student_profile")
    branch = relationship("Branch", back_populates="students")
    class_ = relationship("Class", back_populates="students")
    section = relationship("Section", back_populates="students")
    academic_year = relationship("AcademicYear", back_populates="students")
    attendance_records = relationship("Attendance", back_populates="student")
    marks = relationship("Marks", back_populates="student")
    fee_records = relationship("FeeRecord", back_populates="student")
    documents = relationship("StudentDocument", back_populates="student", cascade="all, delete-orphan")
    activities = relationship("StudentActivity", back_populates="student")

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name or ''}".strip()


class StudentDocument(Base):
    __tablename__ = "student_documents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    student_id = Column(UUID(as_uuid=True), ForeignKey("students.id"), nullable=False)
    doc_type = Column(String(50), nullable=False)  # birth_cert, tc, marksheet, aadhaar, photo
    doc_name = Column(String(255), nullable=False)
    file_url = Column(String(500), nullable=False)
    uploaded_at = Column(DateTime, default=lambda: datetime.utcnow())

    student = relationship("Student", back_populates="documents")