"""
Payment Transactions & Donations — Sprint 26
Tracks all online payments across gateways + donation management.
"""
import uuid
import enum
from datetime import datetime
from sqlalchemy import Column, String, DateTime, Date, ForeignKey, Float, Integer, Boolean, Text, Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from database import Base


class PaymentGateway(str, enum.Enum):
    RAZORPAY = "razorpay"
    PHONEPE = "phonepe"
    PAYTM = "paytm"
    CASHFREE = "cashfree"
    STRIPE = "stripe"
    UPI_DIRECT = "upi_direct"
    BANK_TRANSFER = "bank_transfer"
    CASH = "cash"


class TransactionStatus(str, enum.Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    SUCCESS = "success"
    FAILED = "failed"
    REFUNDED = "refunded"
    PARTIALLY_REFUNDED = "partially_refunded"
    EXPIRED = "expired"


class PaymentPurpose(str, enum.Enum):
    FEE = "fee"
    FINE = "fine"
    DONATION = "donation"
    TRANSPORT = "transport"
    HOSTEL = "hostel"
    ADMISSION = "admission"
    OTHER = "other"


class DonationPurpose(str, enum.Enum):
    INFRASTRUCTURE = "infrastructure"
    SCHOLARSHIP = "scholarship"
    GENERAL = "general"
    EVENT = "event"
    BUILDING = "building"
    SPORTS = "sports"
    LIBRARY = "library"
    OTHER = "other"


class PaymentTransaction(Base):
    """Every online payment goes through this table — unified across all gateways."""
    __tablename__ = "payment_transactions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    branch_id = Column(UUID(as_uuid=True), ForeignKey("branches.id"), nullable=False, index=True)
    student_id = Column(UUID(as_uuid=True), ForeignKey("students.id"), nullable=True)
    fee_record_id = Column(UUID(as_uuid=True), ForeignKey("fee_records.id"), nullable=True)

    # Amount
    amount = Column(Float, nullable=False)
    currency = Column(String(5), default="INR")

    # Gateway info
    gateway = Column(String(30), nullable=False)  # razorpay/phonepe/paytm/cashfree/stripe
    gateway_order_id = Column(String(200), nullable=True, index=True)  # Razorpay order_id, PhonePe txnId
    gateway_payment_id = Column(String(200), nullable=True)  # Razorpay payment_id
    gateway_signature = Column(String(500), nullable=True)  # For verification

    # Status
    status = Column(String(20), default="pending", index=True)
    purpose = Column(String(20), default="fee")  # fee/fine/donation/transport/hostel/admission/other
    description = Column(Text, nullable=True)

    # Payment Link
    payment_link = Column(String(500), nullable=True)
    payment_link_short = Column(String(100), nullable=True)
    payment_link_id = Column(String(100), nullable=True, index=True)
    link_expiry = Column(DateTime, nullable=True)

    # Refund
    refund_id = Column(String(200), nullable=True)
    refund_amount = Column(Float, nullable=True)
    refund_status = Column(String(20), nullable=True)

    # Payer info (for non-student payments like donations)
    payer_name = Column(String(200), nullable=True)
    payer_phone = Column(String(20), nullable=True)
    payer_email = Column(String(200), nullable=True)

    # Receipt
    receipt_number = Column(String(50), nullable=True)

    # Gateway-specific metadata
    gateway_metadata = Column("metadata", JSONB, default={})

    created_at = Column(DateTime, default=lambda: datetime.utcnow())
    completed_at = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, default=lambda: datetime.utcnow(), onupdate=lambda: datetime.utcnow())


class Donation(Base):
    """Donation records — linked to payment transactions."""
    __tablename__ = "donations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    branch_id = Column(UUID(as_uuid=True), ForeignKey("branches.id"), nullable=False, index=True)

    # Donor info
    donor_name = Column(String(200), nullable=False)
    donor_phone = Column(String(20), nullable=True)
    donor_email = Column(String(200), nullable=True)
    donor_pan = Column(String(20), nullable=True)  # For 80G tax receipt
    donor_address = Column(Text, nullable=True)

    # Amount & purpose
    amount = Column(Float, nullable=False)
    purpose = Column(String(50), default="general")
    student_id = Column(UUID(as_uuid=True), ForeignKey("students.id"), nullable=True)  # Optional link to admission

    # Payment
    payment_txn_id = Column(UUID(as_uuid=True), ForeignKey("payment_transactions.id"), nullable=True)
    payment_mode = Column(String(30), nullable=True)  # online/cash/cheque/bank_transfer

    # Receipt & tax
    receipt_number = Column(String(50), nullable=True)
    status = Column(String(20), default="pending")  # pending/completed/refunded
    tax_receipt_sent = Column(Boolean, default=False)
    tax_receipt_number = Column(String(50), nullable=True)  # 80G receipt number

    # Other
    message = Column(Text, nullable=True)
    is_anonymous = Column(Boolean, default=False)
    academic_year = Column(String(20), nullable=True)

    created_at = Column(DateTime, default=lambda: datetime.utcnow())
    updated_at = Column(DateTime, default=lambda: datetime.utcnow(), onupdate=lambda: datetime.utcnow())


class NotificationLog(Base):
    """Track every notification sent — WhatsApp, SMS, Email delivery status."""
    __tablename__ = "notification_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    notification_id = Column(UUID(as_uuid=True), ForeignKey("notifications.id"), nullable=True)
    branch_id = Column(UUID(as_uuid=True), ForeignKey("branches.id"), nullable=True, index=True)

    channel = Column(String(20), nullable=False)  # whatsapp/sms/email/tathaastu
    provider = Column(String(30), nullable=True)  # msg91/interakt/brevo/twilio
    recipient = Column(String(200), nullable=True)  # phone number or email
    template_id = Column(String(100), nullable=True)  # DLT template or WhatsApp template

    status = Column(String(20), default="queued", index=True)  # queued/sent/delivered/failed/read
    provider_message_id = Column(String(200), nullable=True)
    error_message = Column(Text, nullable=True)
    cost = Column(Float, default=0)  # SMS/WhatsApp cost tracking

    sent_at = Column(DateTime, nullable=True)
    delivered_at = Column(DateTime, nullable=True)
    read_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.utcnow())