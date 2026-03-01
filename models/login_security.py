"""Login security models — track login attempts, ban IPs."""
import uuid
from datetime import datetime
from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID
from database import Base


class LoginAttempt(Base):
    __tablename__ = "login_attempts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String(255), nullable=True)
    ip_address = Column(String(50), nullable=True)
    user_agent = Column(Text, nullable=True)
    os = Column(String(100), nullable=True)
    browser = Column(String(100), nullable=True)
    device = Column(String(100), nullable=True)
    country = Column(String(100), nullable=True)
    success = Column(Boolean, default=False)
    failure_reason = Column(String(200), nullable=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.utcnow())


class BannedIP(Base):
    __tablename__ = "banned_ips"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ip_address = Column(String(50), nullable=False, unique=True)
    reason = Column(String(300), nullable=True)
    banned_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    banned_at = Column(DateTime, default=lambda: datetime.utcnow())
    expires_at = Column(DateTime, nullable=True)
    is_active = Column(Boolean, default=True)