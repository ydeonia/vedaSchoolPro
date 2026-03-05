import uuid
import enum
from datetime import datetime
from sqlalchemy import Column, String, DateTime, ForeignKey, Text, Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
from database import Base


class PhotoApprovalStatus(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class PhotoChangeRequest(Base):
    """When a student/teacher/staff uploads a new photo, it goes through admin approval."""
    __tablename__ = "photo_change_requests"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    branch_id = Column(UUID(as_uuid=True), ForeignKey("branches.id"), nullable=False, index=True)
    entity_type = Column(String(20), nullable=False)  # 'student', 'teacher', 'employee'
    entity_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    requested_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)

    current_photo_url = Column(String(500), nullable=True)
    new_photo_url = Column(String(500), nullable=False)

    status = Column(SAEnum(PhotoApprovalStatus), default=PhotoApprovalStatus.PENDING)
    reviewed_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    reviewed_at = Column(DateTime, nullable=True)
    rejection_reason = Column(Text, nullable=True)

    created_at = Column(DateTime, default=lambda: datetime.utcnow())
