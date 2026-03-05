import uuid
import enum
from datetime import datetime, date
from sqlalchemy import Column, String, Boolean, DateTime, Date, ForeignKey, Text, Integer, Numeric, Enum, Float, Time
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from database import Base


class AccountTransaction(Base):
    __tablename__ = "account_transactions"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    branch_id = Column(UUID(as_uuid=True), ForeignKey("branches.id"), nullable=False, index=True)
    transaction_type = Column(String(20), nullable=False)  # income, expense
    category = Column(String(100), nullable=False)  # fee_collection, salary, utilities, maintenance, transport, misc
    description = Column(Text, nullable=True)
    amount = Column(Float, nullable=False)
    transaction_date = Column(Date, nullable=False)
    payment_mode = Column(String(30), nullable=True)  # cash, bank, upi, cheque
    reference_number = Column(String(100), nullable=True)
    receipt_url = Column(String(500), nullable=True)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.utcnow())


class SmsLog(Base):
    """Track SMS sent via gateway"""
    __tablename__ = "sms_logs"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    branch_id = Column(UUID(as_uuid=True), ForeignKey("branches.id"), nullable=False, index=True)
    phone_number = Column(String(15), nullable=False)
    message = Column(Text, nullable=False)
    sms_type = Column(String(50), nullable=True)  # fee_reminder, attendance_alert, announcement, otp
    status = Column(String(20), default="sent")  # sent, delivered, failed
    provider = Column(String(30), nullable=True)  # msg91, twilio, textlocal
    provider_id = Column(String(200), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.utcnow())
