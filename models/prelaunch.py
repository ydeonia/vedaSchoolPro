"""Pre-Launch Models — Audit, Messaging, Complaints, Plans"""
import uuid
import enum
from datetime import datetime, timezone
from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey, Text, Integer, Numeric, Enum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from database import Base


# ─── AUDIT LOG ─────────────────────────────────────────────
class AuditAction(str, enum.Enum):
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"
    LOGIN = "login"
    LOGOUT = "logout"
    EXPORT = "export"
    PAYMENT = "payment"
    PUBLISH = "publish"
    APPROVE = "approve"
    REJECT = "reject"


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    branch_id = Column(UUID(as_uuid=True), ForeignKey("branches.id"), nullable=True, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True, index=True)
    user_name = Column(String(200), nullable=True)
    user_role = Column(String(50), nullable=True)

    action = Column(Enum(AuditAction), nullable=False, index=True)
    entity_type = Column(String(100), nullable=False, index=True)  # student, fee, exam, attendance...
    entity_id = Column(String(100), nullable=True)
    description = Column(Text, nullable=False)
    details = Column(Text, nullable=True)  # JSON details of changes
    ip_address = Column(String(50), nullable=True)

    created_at = Column(DateTime, default=lambda: datetime.utcnow(), index=True)