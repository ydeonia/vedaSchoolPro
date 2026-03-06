"""
VedaFlow Coupon & Discount System — Promo codes for plan subscriptions.
Supports percentage and flat discounts, usage limits, plan eligibility, and bulk generation.
"""

import uuid
import enum
from datetime import datetime
from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey, Text, Integer, Numeric, JSON, Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from database import Base


class DiscountType(str, enum.Enum):
    PERCENTAGE = "percentage"
    FLAT = "flat"               # Fixed INR amount off


class Coupon(Base):
    __tablename__ = "coupons"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    code = Column(String(50), unique=True, nullable=False, index=True)    # e.g. "LAUNCH20", "SCHOOL50"
    description = Column(String(300), nullable=True)

    discount_type = Column(
        SAEnum(DiscountType, values_callable=lambda x: [e.value for e in x]),
        default=DiscountType.PERCENTAGE,
    )
    discount_value = Column(Numeric(10, 2), nullable=False)               # 20 for 20%, or 500 for Rs.500 off
    max_discount_amount = Column(Numeric(10, 2), nullable=True)           # Cap for percentage (e.g. max Rs.2000)
    min_plan_amount = Column(Numeric(10, 2), default=0)                   # Minimum plan price to apply

    applicable_plans = Column(JSON, nullable=True)                        # list of plan_id strings, null = all
    applicable_tiers = Column(JSON, nullable=True)                        # ["growth","pro"], null = all

    max_uses = Column(Integer, default=100)                               # Total redemptions allowed
    max_uses_per_branch = Column(Integer, default=1)                      # Per branch limit
    used_count = Column(Integer, default=0)

    valid_from = Column(DateTime, nullable=False)
    valid_until = Column(DateTime, nullable=False)

    is_active = Column(Boolean, default=True)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.utcnow())
    updated_at = Column(DateTime, default=lambda: datetime.utcnow(), onupdate=lambda: datetime.utcnow())

    # Relationships
    redemptions = relationship("CouponRedemption", back_populates="coupon", cascade="all, delete-orphan")


class CouponRedemption(Base):
    __tablename__ = "coupon_redemptions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    coupon_id = Column(UUID(as_uuid=True), ForeignKey("coupons.id"), nullable=False, index=True)
    branch_id = Column(UUID(as_uuid=True), ForeignKey("branches.id"), nullable=False)
    subscription_id = Column(UUID(as_uuid=True), ForeignKey("school_subscriptions.id"), nullable=True)
    payment_id = Column(UUID(as_uuid=True), ForeignKey("payment_history.id"), nullable=True)

    original_amount = Column(Numeric(10, 2), nullable=False)
    discount_applied = Column(Numeric(10, 2), nullable=False)
    final_amount = Column(Numeric(10, 2), nullable=False)

    redeemed_at = Column(DateTime, default=lambda: datetime.utcnow())
    redeemed_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)

    # Relationships
    coupon = relationship("Coupon", back_populates="redemptions")
