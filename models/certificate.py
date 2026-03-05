import uuid
import enum
from datetime import datetime, date
from sqlalchemy import Column, String, Boolean, DateTime, Date, ForeignKey, Text, Integer, Numeric, Enum, Float, Time
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from database import Base


class CertificateType(str, enum.Enum):
    TRANSFER = "TRANSFER"
    BONAFIDE = "BONAFIDE"
    CHARACTER = "CHARACTER"
    STUDY = "STUDY"
    CONDUCT = "CONDUCT"


class Certificate(Base):
    __tablename__ = "certificates"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    branch_id = Column(UUID(as_uuid=True), ForeignKey("branches.id"), nullable=False, index=True)
    student_id = Column(UUID(as_uuid=True), ForeignKey("students.id"), nullable=False)
    cert_type = Column(Enum(CertificateType), nullable=False)
    certificate_number = Column(String(50), nullable=True)
    issue_date = Column(Date, default=date.today)
    content = Column(Text, nullable=True)  # Custom fields stored as JSON
    reason = Column(String(300), nullable=True)  # Reason for TC
    destination_school = Column(String(300), nullable=True)
    conduct = Column(String(100), default="Good")
    generated_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    is_issued = Column(Boolean, default=False)
    created_at = Column(DateTime, default=lambda: datetime.utcnow())
