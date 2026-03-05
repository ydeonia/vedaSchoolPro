import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Boolean, DateTime, Text, ForeignKey, Enum as SAEnum, Integer
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from database import Base
import enum


class BoardType(str, enum.Enum):
    CBSE = "cbse"
    ICSE = "icse"
    STATE = "state"
    IB = "ib"
    IGCSE = "igcse"
    OTHER = "other"


class Branch(Base):
    __tablename__ = "branches"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    code = Column(String(50), nullable=True)  # e.g., "DPS-GZB-01"
    subdomain = Column(String(63), nullable=True, unique=True, index=True)  # e.g., "goenkajammu", "conventgwalior"
    board_type = Column(SAEnum(BoardType), default=BoardType.CBSE)

    # Contact info
    email = Column(String(255), nullable=True)
    phone = Column(String(15), nullable=True)
    address = Column(Text, nullable=True)
    city = Column(String(100), nullable=True)
    state = Column(String(100), nullable=True)
    pincode = Column(String(10), nullable=True)

    # School details
    principal_name = Column(String(200), nullable=True)
    established_year = Column(Integer, nullable=True)
    logo_url = Column(String(500), nullable=True)
    motto = Column(String(300), nullable=True)  # School motto/tagline
    tagline = Column(String(300), nullable=True)  # Additional tagline
    accreditation = Column(String(300), nullable=True)  # CBSE/ICSE affiliation number
    landline = Column(String(20), nullable=True)  # School landline
    website_url = Column(String(300), nullable=True)
    affiliation_number = Column(String(100), nullable=True)
    principal_signature_url = Column(String(500), nullable=True)
    school_stamp_url = Column(String(500), nullable=True)

    # Internationalization
    timezone = Column(String(50), default="Asia/Kolkata")
    currency = Column(String(10), default="INR")
    language = Column(String(20), default="English")

    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.utcnow())
    updated_at = Column(DateTime, default=lambda: datetime.utcnow(), onupdate=lambda: datetime.utcnow())

    # Relationships
    organization = relationship("Organization", back_populates="branches")
    users = relationship("User", back_populates="branch")
    settings = relationship("BranchSettings", back_populates="branch", uselist=False, cascade="all, delete-orphan")
    payment_config = relationship("PaymentGatewayConfig", back_populates="branch", uselist=False, cascade="all, delete-orphan")
    communication_config = relationship("CommunicationConfig", back_populates="branch", uselist=False, cascade="all, delete-orphan")
    academic_years = relationship("AcademicYear", back_populates="branch", cascade="all, delete-orphan")
    classes = relationship("Class", back_populates="branch", cascade="all, delete-orphan")
    students = relationship("Student", back_populates="branch")
    teachers = relationship("Teacher", back_populates="branch")


class BranchSettings(Base):
    __tablename__ = "branch_settings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    branch_id = Column(UUID(as_uuid=True), ForeignKey("branches.id"), unique=True, nullable=False)

    # Academic settings
    grading_system = Column(String(50), default="percentage")  # percentage, grade, cgpa
    attendance_type = Column(String(50), default="daily")  # daily, period_wise
    min_attendance_percent = Column(Integer, default=75)

    # Fee settings
    fee_reminder_days = Column(JSONB, default=[7, 3, 1])  # remind X days before due
    late_fee_percentage = Column(Integer, default=0)
    late_fee_after_days = Column(Integer, default=15)

    # Notification preferences
    notify_attendance_parent = Column(Boolean, default=True)
    notify_fee_reminder = Column(Boolean, default=True)
    notify_result_published = Column(Boolean, default=True)

    # UI customization
    theme_color = Column(String(7), default="#4F46E5")  # primary color
    language = Column(String(10), default="en")  # en, hi, ta, mr, etc.
    timezone = Column(String(50), default="Asia/Kolkata")  # IANA timezone

    # Custom data (ID card design, SMS config, etc.)
    custom_data = Column(JSONB, default={})  # {"id_card_design": {...}, "sms_config": {...}}

    branch = relationship("Branch", back_populates="settings")


class PaymentGatewayConfig(Base):
    """Each school configures their OWN payment gateway — inspired by best-in-class SaaS UX"""
    __tablename__ = "payment_gateway_configs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    branch_id = Column(UUID(as_uuid=True), ForeignKey("branches.id"), unique=True, nullable=False)

    # Master toggles
    online_payments_enabled = Column(Boolean, default=False)
    test_mode = Column(Boolean, default=False)  # sandbox mode
    selected_gateway = Column(String(50), default="manual")  # razorpay, payu, cashfree, phonepe, stripe, manual

    # Razorpay
    razorpay_enabled = Column(Boolean, default=False)
    razorpay_key_id = Column(String(255), nullable=True)
    razorpay_key_secret = Column(String(255), nullable=True)
    razorpay_webhook_secret = Column(String(255), nullable=True)

    # PayU
    payu_enabled = Column(Boolean, default=False)
    payu_merchant_key = Column(String(255), nullable=True)
    payu_merchant_salt = Column(String(255), nullable=True)

    # Cashfree
    cashfree_enabled = Column(Boolean, default=False)
    cashfree_app_id = Column(String(255), nullable=True)
    cashfree_secret_key = Column(String(255), nullable=True)

    # PhonePe PG
    phonepe_enabled = Column(Boolean, default=False)
    phonepe_merchant_id = Column(String(255), nullable=True)
    phonepe_salt_key = Column(String(255), nullable=True)
    phonepe_salt_index = Column(Integer, nullable=True)

    # Stripe (International)
    stripe_enabled = Column(Boolean, default=False)
    stripe_publishable_key = Column(String(255), nullable=True)
    stripe_secret_key = Column(String(255), nullable=True)

    # Accepted payment methods (for online gateway)
    accept_upi = Column(Boolean, default=True)
    accept_cards = Column(Boolean, default=True)
    accept_netbanking = Column(Boolean, default=True)
    accept_wallets = Column(Boolean, default=False)
    accept_emi = Column(Boolean, default=False)

    # Direct UPI (shown on invoice/receipt)
    upi_enabled = Column(Boolean, default=False)
    upi_id = Column(String(255), nullable=True)  # school@ybl, school@paytm
    upi_display_name = Column(String(255), nullable=True)
    upi_qr_url = Column(String(500), nullable=True)  # custom QR code image URL
    show_upi_on_invoice = Column(Boolean, default=True)

    # Bank Account (shown on invoice/receipt)
    bank_transfer_enabled = Column(Boolean, default=False)
    bank_name = Column(String(255), nullable=True)
    account_number = Column(String(50), nullable=True)
    ifsc_code = Column(String(20), nullable=True)
    account_holder = Column(String(255), nullable=True)
    bank_branch = Column(String(255), nullable=True)
    account_type = Column(String(50), default="current")  # current, savings
    show_bank_on_invoice = Column(Boolean, default=True)

    # WhatsApp for payment links
    whatsapp_number = Column(String(20), nullable=True)  # 91XXXXXXXXXX

    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.utcnow())

    branch = relationship("Branch", back_populates="payment_config")


class CommunicationConfig(Base):
    """Each school configures their own communication channels"""
    __tablename__ = "communication_configs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    branch_id = Column(UUID(as_uuid=True), ForeignKey("branches.id"), unique=True, nullable=False)

    # Email (SMTP)
    email_enabled = Column(Boolean, default=False)
    smtp_host = Column(String(255), nullable=True)
    smtp_port = Column(Integer, nullable=True)
    smtp_username = Column(String(255), nullable=True)
    smtp_password = Column(String(255), nullable=True)
    from_email = Column(String(255), nullable=True)

    # SMS
    sms_enabled = Column(Boolean, default=False)
    sms_provider = Column(String(50), nullable=True)  # msg91, twilio, msgclub, textlocal
    sms_api_key = Column(String(255), nullable=True)
    sms_sender_id = Column(String(20), nullable=True)
    sms_route_id = Column(String(10), nullable=True, default="8")  # MsgClub route: 1=Trans, 2=Promo, 8=OTP

    # WhatsApp Business
    whatsapp_enabled = Column(Boolean, default=False)
    whatsapp_api_token = Column(String(500), nullable=True)
    whatsapp_phone_id = Column(String(50), nullable=True)

    # TathaAstu (future integration)
    tathaastu_enabled = Column(Boolean, default=False)
    tathaastu_api_key = Column(String(255), nullable=True)
    tathaastu_school_id = Column(String(100), nullable=True)

    # Trust-First Boundaries
    quiet_hours_enabled = Column(Boolean, default=True)
    quiet_start = Column(String(5), default="20:00")  # 8 PM
    quiet_end = Column(String(5), default="07:00")  # 7 AM
    allow_emergency_override = Column(Boolean, default=True)
    parent_teacher_chat_enabled = Column(Boolean, default=False)  # OFF by default (PO principle)
    admin_moderated_messages = Column(Boolean, default=True)

    created_at = Column(DateTime, default=lambda: datetime.utcnow())

    branch = relationship("Branch", back_populates="communication_config")


class PlatformConfig(Base):
    """Platform-wide configuration (single row) — Super Admin settings.
    Stores SMTP, SMS, general settings as a flexible JSON blob."""
    __tablename__ = "platform_configs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    config = Column(JSONB, nullable=True, default=dict)
    updated_at = Column(DateTime, default=lambda: datetime.utcnow(), onupdate=lambda: datetime.utcnow())