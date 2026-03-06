"""
VedaFlow Invoice System — GST-compliant tax invoices for plan subscriptions.
India SaaS: 18% GST (SAC 998315)
  - Intra-state: CGST 9% + SGST 9%
  - Inter-state: IGST 18%
"""

import uuid
import enum
from datetime import datetime, date
from sqlalchemy import Column, String, Boolean, DateTime, Date, ForeignKey, Text, Numeric, JSON, Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
from database import Base


class InvoiceStatus(str, enum.Enum):
    DRAFT = "draft"
    ISSUED = "issued"
    PAID = "paid"
    CANCELLED = "cancelled"


class Invoice(Base):
    __tablename__ = "invoices"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    invoice_number = Column(String(50), unique=True, nullable=False, index=True)  # "EF-2526-0001"

    org_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False)
    branch_id = Column(UUID(as_uuid=True), ForeignKey("branches.id"), nullable=False, index=True)
    subscription_id = Column(UUID(as_uuid=True), ForeignKey("school_subscriptions.id"), nullable=True)
    payment_id = Column(UUID(as_uuid=True), ForeignKey("payment_history.id"), nullable=True)

    # ── Supplier (Platform) ─────────────────────────
    supplier_name = Column(String(300), nullable=True)
    supplier_gstin = Column(String(15), nullable=True)
    supplier_address = Column(Text, nullable=True)
    supplier_state_code = Column(String(2), nullable=True)

    # ── Buyer (School/Org) ───────────────────────────
    buyer_name = Column(String(300), nullable=True)
    buyer_gstin = Column(String(15), nullable=True)
    buyer_address = Column(Text, nullable=True)
    buyer_state_code = Column(String(2), nullable=True)

    # ── Line Items ───────────────────────────────────
    # [{"description": "Growth Plan - Monthly", "sac": "998315", "qty": 1, "rate": 2499.00, "amount": 2499.00}]
    line_items = Column(JSON, nullable=True)

    # ── Amounts ──────────────────────────────────────
    subtotal = Column(Numeric(10, 2), default=0)
    discount_amount = Column(Numeric(10, 2), default=0)
    coupon_code = Column(String(50), nullable=True)
    taxable_amount = Column(Numeric(10, 2), default=0)      # subtotal - discount

    # Tax breakup
    cgst_rate = Column(Numeric(5, 2), default=0)             # 9 or 0
    cgst_amount = Column(Numeric(10, 2), default=0)
    sgst_rate = Column(Numeric(5, 2), default=0)             # 9 or 0
    sgst_amount = Column(Numeric(10, 2), default=0)
    igst_rate = Column(Numeric(5, 2), default=0)             # 18 or 0
    igst_amount = Column(Numeric(10, 2), default=0)
    total_tax = Column(Numeric(10, 2), default=0)
    total_amount = Column(Numeric(10, 2), default=0)         # taxable + tax

    # ── Dates ────────────────────────────────────────
    invoice_date = Column(Date, default=lambda: date.today())
    due_date = Column(Date, nullable=True)
    paid_date = Column(Date, nullable=True)

    # ── Status & Storage ─────────────────────────────
    status = Column(
        SAEnum(InvoiceStatus, values_callable=lambda x: [e.value for e in x]),
        default=InvoiceStatus.DRAFT,
    )
    pdf_path = Column(String(500), nullable=True)            # static/invoices/EF-2526-0001.pdf
    notes = Column(Text, nullable=True)

    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.utcnow())
    updated_at = Column(DateTime, default=lambda: datetime.utcnow(), onupdate=lambda: datetime.utcnow())
