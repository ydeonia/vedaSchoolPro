import uuid
import enum
from datetime import datetime, date
from sqlalchemy import Column, String, Boolean, DateTime, Date, ForeignKey, Text, Integer, Numeric, Enum, Float, Time
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from database import Base


class AssetCategory(Base):
    __tablename__ = "asset_categories"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    branch_id = Column(UUID(as_uuid=True), ForeignKey("branches.id"), nullable=False, index=True)
    name = Column(String(200), nullable=False)  # Furniture, Electronics, Lab Equipment, Sports, Books, Vehicles, IT Equipment
    description = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True)

    assets = relationship("Asset", back_populates="category")


class Asset(Base):
    __tablename__ = "assets"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    branch_id = Column(UUID(as_uuid=True), ForeignKey("branches.id"), nullable=False, index=True)
    category_id = Column(UUID(as_uuid=True), ForeignKey("asset_categories.id"), nullable=True, index=True)
    asset_code = Column(String(50), nullable=False, unique=True)
    name = Column(String(300), nullable=False)
    description = Column(Text, nullable=True)
    location = Column(String(200), nullable=True)  # where it's stored/placed
    quantity = Column(Integer, default=1)
    unit_price = Column(Numeric(12, 2), nullable=True)
    total_value = Column(Numeric(12, 2), nullable=True)
    purchase_date = Column(Date, nullable=True)
    warranty_expiry = Column(Date, nullable=True)
    vendor_name = Column(String(200), nullable=True)
    vendor_contact = Column(String(100), nullable=True)
    condition = Column(String(20), default="good")  # good, fair, poor, damaged, disposed
    assigned_to = Column(String(200), nullable=True)  # room/department/person
    serial_number = Column(String(100), nullable=True)
    notes = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.utcnow())
    updated_at = Column(DateTime, default=lambda: datetime.utcnow(), onupdate=lambda: datetime.utcnow())

    category = relationship("AssetCategory", back_populates="assets")
    logs = relationship("AssetLog", back_populates="asset")


class AssetLog(Base):
    __tablename__ = "asset_logs"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    asset_id = Column(UUID(as_uuid=True), ForeignKey("assets.id"), nullable=False, index=True)
    log_type = Column(String(30), nullable=False)  # purchase, transfer, maintenance, repair, dispose, audit, damage
    description = Column(Text, nullable=False)
    performed_by = Column(String(200), nullable=True)
    log_date = Column(Date, default=date.today)
    cost = Column(Numeric(10, 2), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.utcnow())

    asset = relationship("Asset", back_populates="logs")
