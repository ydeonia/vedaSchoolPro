"""
VedaFlow Plans & Subscription System
======================================

PLANS:
  Starter (₹999/mo)  — Small schools (up to 300 students)
  Growth  (₹2499/mo) — Growing schools (up to 1000 students)  
  Pro     (₹4999/mo) — Large schools (up to 3000 students)
  Enterprise (Custom) — School chains / 3000+ students

BILLING:
  Monthly or Yearly (20% discount on yearly)
  Auto-deactivate on expiry (grace period: 7 days)
  
FEATURE GATES:
  Each plan enables/disables specific modules
  School admin sees plan status on their dashboard
"""

import uuid
import enum
from datetime import datetime
from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey, Text, Integer, Numeric, Enum as SAEnum, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from database import Base


class PlanTier(str, enum.Enum):
    FREE = "free"
    TRIAL = "trial"
    STARTER = "starter"
    GROWTH = "growth"
    PRO = "pro"
    ENTERPRISE = "enterprise"


class BillingCycle(str, enum.Enum):
    MONTHLY = "monthly"
    YEARLY = "yearly"


class SubscriptionStatus(str, enum.Enum):
    TRIAL = "trial"
    ACTIVE = "active"
    GRACE = "grace"        # Expired but within 7-day grace
    EXPIRED = "expired"     # Past grace — school deactivated
    CANCELLED = "cancelled"


# ═══════════════════════════════════════════════════════════
# PLAN — What features each tier gets
# ═══════════════════════════════════════════════════════════

class Plan(Base):
    __tablename__ = "plans"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(100), nullable=False)                  # "Starter", "Growth", "Pro", "Enterprise"
    tier = Column(SAEnum(PlanTier, values_callable=lambda x: [e.value for e in x]), nullable=False)
    tagline = Column(String(300), nullable=True)                # "Perfect for small schools"

    # Pricing (INR)
    price_monthly = Column(Numeric(10, 2), default=0)
    price_yearly = Column(Numeric(10, 2), default=0)            # Per year (not per month)

    # Limits
    max_students = Column(Integer, default=100)
    max_teachers = Column(Integer, default=10)
    max_branches = Column(Integer, default=1)
    max_storage_gb = Column(Integer, default=5)

    # Communication
    sms_credits_monthly = Column(Integer, default=0)            # Free SMS per month
    whatsapp_enabled = Column(Boolean, default=False)
    email_notifications = Column(Boolean, default=True)

    # Features — JSON list of enabled module keys
    # Example: ["student_admission","attendance","fees","exams","results","timetable"]
    enabled_modules = Column(JSON, nullable=True)

    # Extras
    custom_branding = Column(Boolean, default=False)            # School logo on reports
    priority_support = Column(Boolean, default=False)
    api_access = Column(Boolean, default=False)
    data_export = Column(Boolean, default=True)
    advanced_analytics = Column(Boolean, default=False)
    backup_frequency = Column(String(50), default="weekly")     # daily, weekly
    parent_app = Column(Boolean, default=True)                  # Parent mobile app access
    teacher_app = Column(Boolean, default=True)
    online_fee_payment = Column(Boolean, default=False)         # Razorpay/Paytm integration
    id_card_generator = Column(Boolean, default=False)
    transport_module = Column(Boolean, default=False)
    hostel_module = Column(Boolean, default=False)
    library_module = Column(Boolean, default=False)
    hr_payroll = Column(Boolean, default=False)
    messaging_system = Column(Boolean, default=True)
    complaints_system = Column(Boolean, default=False)

    # Late fee config (per-plan)
    late_fee_type = Column(String(20), default="percentage")    # "percentage" or "flat"
    late_fee_value = Column(Numeric(10, 2), default=5)          # 5% or Rs.500 flat
    late_fee_grace_days = Column(Integer, default=7)            # Days after due before late fee kicks in

    is_active = Column(Boolean, default=True)
    display_order = Column(Integer, default=0)
    created_at = Column(DateTime, default=lambda: datetime.utcnow())


# ═══════════════════════════════════════════════════════════
# SUBSCRIPTION — Links a school branch to a plan
# ═══════════════════════════════════════════════════════════

class SchoolSubscription(Base):
    __tablename__ = "school_subscriptions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False)
    branch_id = Column(UUID(as_uuid=True), ForeignKey("branches.id"), nullable=False, unique=True)
    plan_id = Column(UUID(as_uuid=True), ForeignKey("plans.id"), nullable=False)

    status = Column(SAEnum(SubscriptionStatus, values_callable=lambda x: [e.value for e in x]), default=SubscriptionStatus.TRIAL, index=True)
    billing_cycle = Column(SAEnum(BillingCycle, values_callable=lambda x: [e.value for e in x]), default=BillingCycle.MONTHLY)

    # Trial
    trial_started_at = Column(DateTime, nullable=True)
    trial_ends_at = Column(DateTime, nullable=True)

    # Active subscription dates
    current_period_start = Column(DateTime, nullable=True)
    current_period_end = Column(DateTime, nullable=True)
    grace_period_end = Column(DateTime, nullable=True)      # 7 days after expiry

    # Payment
    last_payment_amount = Column(Numeric(10, 2), nullable=True)
    last_payment_date = Column(DateTime, nullable=True)
    last_payment_ref = Column(String(200), nullable=True)   # Razorpay/manual reference
    next_payment_due = Column(DateTime, nullable=True)

    # Auto-deactivation
    auto_deactivated = Column(Boolean, default=False)
    deactivated_at = Column(DateTime, nullable=True)
    deactivation_reason = Column(String(300), nullable=True)

    # Usage tracking
    current_student_count = Column(Integer, default=0)
    current_teacher_count = Column(Integer, default=0)
    storage_used_mb = Column(Integer, default=0)

    # Late fee tracking
    late_fee_amount = Column(Numeric(10, 2), default=0)
    late_fee_applied_at = Column(DateTime, nullable=True)
    late_fee_waived = Column(Boolean, default=False)
    late_fee_waived_at = Column(DateTime, nullable=True)
    late_fee_waived_by = Column(UUID(as_uuid=True), nullable=True)

    created_at = Column(DateTime, default=lambda: datetime.utcnow())
    updated_at = Column(DateTime, default=lambda: datetime.utcnow(), onupdate=lambda: datetime.utcnow())

    # Relationships
    plan = relationship("Plan", lazy="joined")


# ═══════════════════════════════════════════════════════════
# PAYMENT HISTORY
# ═══════════════════════════════════════════════════════════

class PaymentHistory(Base):
    __tablename__ = "payment_history"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    subscription_id = Column(UUID(as_uuid=True), ForeignKey("school_subscriptions.id"), nullable=False)
    branch_id = Column(UUID(as_uuid=True), ForeignKey("branches.id"), nullable=False)

    amount = Column(Numeric(10, 2), nullable=False)
    currency = Column(String(10), default="INR")
    payment_method = Column(String(50), nullable=True)      # razorpay, bank_transfer, cash, cheque
    payment_ref = Column(String(200), nullable=True)
    invoice_number = Column(String(100), nullable=True)

    plan_name = Column(String(100), nullable=True)
    billing_cycle = Column(String(20), nullable=True)
    period_start = Column(DateTime, nullable=True)
    period_end = Column(DateTime, nullable=True)

    status = Column(String(50), default="completed")        # completed, pending, failed, refunded, late_fee_pending
    notes = Column(Text, nullable=True)

    # Coupon & late fee tracking
    coupon_code = Column(String(50), nullable=True)
    includes_late_fee = Column(Boolean, default=False)
    late_fee_amount = Column(Numeric(10, 2), default=0)

    created_at = Column(DateTime, default=lambda: datetime.utcnow())


# ═══════════════════════════════════════════════════════════
# DEFAULT PLAN DATA — Used by seed script
# ═══════════════════════════════════════════════════════════

DEFAULT_PLANS = [
    {
        "name": "Starter",
        "tier": "starter",
        "tagline": "Perfect for small schools getting started with digital management",
        "price_monthly": 999,
        "price_yearly": 9590,       # ~₹799/mo (20% off)
        "max_students": 300,
        "max_teachers": 15,
        "max_branches": 1,
        "max_storage_gb": 5,
        "sms_credits_monthly": 100,
        "whatsapp_enabled": False,
        "custom_branding": False,
        "priority_support": False,
        "api_access": False,
        "advanced_analytics": False,
        "online_fee_payment": False,
        "id_card_generator": False,
        "transport_module": False,
        "hostel_module": False,
        "library_module": False,
        "hr_payroll": False,
        "complaints_system": False,
        "backup_frequency": "weekly",
        "display_order": 1,
        "enabled_modules": [
            "student_admission", "student_attendance", "student_promotion",
            "class_management", "timetable", "exam_management", "results",
            "fee_structure", "fee_collection", "announcements", "parent_comm",
        ],
    },
    {
        "name": "Growth",
        "tier": "growth",
        "tagline": "For growing schools that need more power and features",
        "price_monthly": 2499,
        "price_yearly": 23990,      # ~₹1999/mo
        "max_students": 1000,
        "max_teachers": 50,
        "max_branches": 2,
        "max_storage_gb": 20,
        "sms_credits_monthly": 500,
        "whatsapp_enabled": True,
        "custom_branding": True,
        "priority_support": False,
        "api_access": False,
        "advanced_analytics": True,
        "online_fee_payment": True,
        "id_card_generator": True,
        "transport_module": True,
        "hostel_module": False,
        "library_module": True,
        "hr_payroll": False,
        "complaints_system": True,
        "backup_frequency": "daily",
        "display_order": 2,
        "enabled_modules": [
            "student_admission", "student_attendance", "student_promotion", "student_documents",
            "class_management", "timetable", "exam_management", "results", "activities",
            "fee_structure", "fee_collection", "fee_reports",
            "employee_management", "teacher_attendance",
            "transport", "library", "id_cards",
            "announcements", "complaints", "parent_comm",
            "analytics", "reports",
        ],
    },
    {
        "name": "Pro",
        "tier": "pro",
        "tagline": "Complete school management for large institutions",
        "price_monthly": 4999,
        "price_yearly": 47990,      # ~₹3999/mo
        "max_students": 3000,
        "max_teachers": 150,
        "max_branches": 5,
        "max_storage_gb": 100,
        "sms_credits_monthly": 2000,
        "whatsapp_enabled": True,
        "custom_branding": True,
        "priority_support": True,
        "api_access": True,
        "advanced_analytics": True,
        "online_fee_payment": True,
        "id_card_generator": True,
        "transport_module": True,
        "hostel_module": True,
        "library_module": True,
        "hr_payroll": True,
        "complaints_system": True,
        "backup_frequency": "daily",
        "display_order": 3,
        "enabled_modules": [
            "student_admission", "student_attendance", "student_promotion", "student_documents",
            "class_management", "timetable", "exam_management", "results", "activities",
            "fee_structure", "fee_collection", "fee_reports", "salary_payroll", "accounts_expenses",
            "employee_management", "teacher_attendance", "teacher_performance",
            "transport", "hostel", "library", "id_cards",
            "announcements", "complaints", "parent_comm",
            "analytics", "reports", "school_settings", "manage_staff",
        ],
    },
    {
        "name": "Enterprise",
        "tier": "enterprise",
        "tagline": "For school chains and institutions with 3000+ students — custom pricing",
        "price_monthly": 0,         # Custom quote
        "price_yearly": 0,
        "max_students": 99999,
        "max_teachers": 9999,
        "max_branches": 50,
        "max_storage_gb": 500,
        "sms_credits_monthly": 10000,
        "whatsapp_enabled": True,
        "custom_branding": True,
        "priority_support": True,
        "api_access": True,
        "advanced_analytics": True,
        "online_fee_payment": True,
        "id_card_generator": True,
        "transport_module": True,
        "hostel_module": True,
        "library_module": True,
        "hr_payroll": True,
        "complaints_system": True,
        "backup_frequency": "daily",
        "display_order": 4,
        "enabled_modules": list({
            "student_admission", "student_attendance", "student_promotion", "student_documents",
            "class_management", "timetable", "exam_management", "results", "activities",
            "fee_structure", "fee_collection", "fee_reports", "salary_payroll", "accounts_expenses",
            "employee_management", "teacher_attendance", "teacher_performance",
            "transport", "hostel", "library", "id_cards",
            "announcements", "complaints", "parent_comm",
            "analytics", "reports", "school_settings", "manage_staff",
        }),
    },
]