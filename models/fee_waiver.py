import uuid
import enum
from datetime import datetime, date
from sqlalchemy import Column, String, Boolean, DateTime, Date, ForeignKey, Text, Integer, Numeric, Enum, Float, Time
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from database import Base


class FeeWaiver(Base):
    __tablename__ = "fee_waivers"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    branch_id = Column(UUID(as_uuid=True), ForeignKey("branches.id"), nullable=False, index=True)
    student_id = Column(UUID(as_uuid=True), ForeignKey("students.id"), nullable=False)
    waiver_type = Column(String(50), nullable=False)  # scholarship, sibling_discount, staff_ward, merit, financial_aid, rte
    title = Column(String(200), nullable=False)  # "Merit Scholarship 50%"
    discount_type = Column(String(20), default="percentage")  # percentage, fixed
    discount_value = Column(Float, nullable=False)  # 50 (means 50%) or 5000 (fixed)
    applicable_fees = Column(JSONB, nullable=True)  # ["tuition","transport"] or null=all
    valid_from = Column(Date, nullable=True)
    valid_to = Column(Date, nullable=True)
    approved_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    status = Column(String(20), default="active")  # active, expired, revoked
    remarks = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.utcnow())
