import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime, ForeignKey, Text, Boolean, Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from database import Base
import enum


class NotificationType(str, enum.Enum):
    ATTENDANCE = "attendance"
    FEE_REMINDER = "fee_reminder"
    FEE_RECEIVED = "fee_received"
    RESULT_PUBLISHED = "result_published"
    ANNOUNCEMENT = "announcement"
    MESSAGE = "message"
    ADMISSION = "admission"
    TRANSPORT = "transport"
    HOSTEL = "hostel"
    ACK = "ack"
    ALERT = "alert"
    ONLINE_CLASS = "online_class"


class NotificationChannel(str, enum.Enum):
    IN_APP = "in_app"
    EMAIL = "email"
    SMS = "sms"
    WHATSAPP = "whatsapp"
    TATHAASTU = "tathaastu"


class Notification(Base):
    __tablename__ = "notifications"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    branch_id = Column(UUID(as_uuid=True), ForeignKey("branches.id"), nullable=False, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)  # recipient
    type = Column(SAEnum(NotificationType), nullable=False)
    title = Column(String(255), nullable=False)
    message = Column(Text, nullable=False)
    channel = Column(SAEnum(NotificationChannel), default=NotificationChannel.IN_APP)
    priority = Column(String(20), default="normal")  # low, normal, high, urgent
    action_url = Column(String(500), nullable=True)  # "Pay now" → /fees, "View" → /results
    action_label = Column(String(50), nullable=True)  # "Pay Now", "View Results", "Acknowledge"
    is_read = Column(Boolean, default=False)
    sent_at = Column(DateTime, nullable=True)
    read_at = Column(DateTime, nullable=True)
    # Admission notification fields
    notification_type = Column(String(50), nullable=True)  # admission, transport, hostel, ack
    reference_id = Column(String(100), nullable=True)  # student_id or other entity
    requires_ack = Column(Boolean, default=False)
    acknowledged = Column(Boolean, default=False)
    acknowledged_at = Column(DateTime, nullable=True)
    acknowledged_by = Column(UUID(as_uuid=True), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.utcnow())


class AnnouncementPriority(str, enum.Enum):
    NORMAL = "normal"
    IMPORTANT = "important"
    URGENT = "urgent"
    EMERGENCY = "emergency"


class Announcement(Base):
    __tablename__ = "announcements"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    branch_id = Column(UUID(as_uuid=True), ForeignKey("branches.id"), nullable=False, index=True)
    title = Column(String(255), nullable=False)
    content = Column(Text, nullable=False)
    priority = Column(SAEnum(AnnouncementPriority), default=AnnouncementPriority.NORMAL)
    target_role = Column(String(50), nullable=True)  # all, teacher, student, parent
    target_class_id = Column(UUID(as_uuid=True), ForeignKey("classes.id"), nullable=True)
    attachment_url = Column(String(500), nullable=True)
    is_pinned = Column(Boolean, default=False)
    is_emergency = Column(Boolean, default=False)  # overrides quiet hours
    published_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    publish_date = Column(DateTime, default=lambda: datetime.utcnow())
    expiry_date = Column(DateTime, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.utcnow())