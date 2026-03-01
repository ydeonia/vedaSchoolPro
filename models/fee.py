import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime, Date, ForeignKey, Float, Integer, Boolean, Text, Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from database import Base
import enum


class FeeFrequency(str, enum.Enum):
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    HALF_YEARLY = "half_yearly"
    ANNUALLY = "annually"
    ONE_TIME = "one_time"


class PaymentStatus(str, enum.Enum):
    PENDING = "pending"
    PAID = "paid"
    PARTIAL = "partial"
    OVERDUE = "overdue"
    WAIVED = "waived"


class PaymentMode(str, enum.Enum):
    CASH = "cash"
    UPI = "upi"
    BANK_TRANSFER = "bank_transfer"
    RAZORPAY = "razorpay"
    PHONEPE = "phonepe"
    CHEQUE = "cheque"
    OTHER = "other"


class FeeStructure(Base):
    __tablename__ = "fee_structures"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    branch_id = Column(UUID(as_uuid=True), ForeignKey("branches.id"), nullable=False, index=True)
    class_id = Column(UUID(as_uuid=True), ForeignKey("classes.id"), nullable=True)
    academic_year_id = Column(UUID(as_uuid=True), ForeignKey("academic_years.id"), nullable=True)

    fee_name = Column(String(100), nullable=False)  # "Tuition Fee", "Transport", "Lab Fee"
    amount = Column(Float, nullable=False)
    frequency = Column(SAEnum(FeeFrequency), default=FeeFrequency.MONTHLY)
    due_day = Column(Integer, default=10)  # day of month when fee is due
    description = Column(Text, nullable=True)
    is_mandatory = Column(Boolean, default=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.utcnow())

    class_ = relationship("Class", back_populates="fee_structures")
    fee_records = relationship("FeeRecord", back_populates="fee_structure")


class FeeRecord(Base):
    __tablename__ = "fee_records"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    student_id = Column(UUID(as_uuid=True), ForeignKey("students.id"), nullable=False, index=True)
    fee_structure_id = Column(UUID(as_uuid=True), ForeignKey("fee_structures.id"), nullable=False)
    branch_id = Column(UUID(as_uuid=True), ForeignKey("branches.id"), nullable=False, index=True)

    amount_due = Column(Float, nullable=False)
    amount_paid = Column(Float, default=0)
    discount = Column(Float, default=0)
    late_fee = Column(Float, default=0)
    due_date = Column(Date, nullable=False)
    payment_date = Column(Date, nullable=True)
    payment_mode = Column(SAEnum(PaymentMode), nullable=True)
    transaction_id = Column(String(100), nullable=True)
    receipt_number = Column(String(50), nullable=True)
    status = Column(SAEnum(PaymentStatus), default=PaymentStatus.PENDING)
    remarks = Column(Text, nullable=True)

    created_at = Column(DateTime, default=lambda: datetime.utcnow())
    updated_at = Column(DateTime, default=lambda: datetime.utcnow(), onupdate=lambda: datetime.utcnow())

    student = relationship("Student", back_populates="fee_records")
    fee_structure = relationship("FeeStructure", back_populates="fee_records")