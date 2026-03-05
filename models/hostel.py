import uuid
import enum
from datetime import datetime, date
from sqlalchemy import Column, String, Boolean, DateTime, Date, ForeignKey, Text, Integer, Numeric, Enum, Float, Time
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from database import Base


class Hostel(Base):
    __tablename__ = "hostels"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    branch_id = Column(UUID(as_uuid=True), ForeignKey("branches.id"), nullable=False, index=True)
    name = Column(String(200), nullable=False)  # "Boys Hostel A"
    hostel_type = Column(String(20), default="boys")  # boys, girls, co-ed
    warden_name = Column(String(200), nullable=True)
    warden_phone = Column(String(15), nullable=True)
    total_rooms = Column(Integer, default=0)
    total_beds = Column(Integer, default=0)
    address = Column(Text, nullable=True)
    monthly_fee = Column(Float, default=0)
    mess_fee = Column(Float, default=0)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.utcnow())


class HostelRoom(Base):
    __tablename__ = "hostel_rooms"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    hostel_id = Column(UUID(as_uuid=True), ForeignKey("hostels.id"), nullable=False)
    room_number = Column(String(20), nullable=False)
    floor = Column(String(10), nullable=True)
    room_type = Column(String(20), default="shared")  # single, double, shared, dormitory
    bed_count = Column(Integer, default=4)
    occupied_beds = Column(Integer, default=0)
    status = Column(String(20), default="available")  # available, full, maintenance
    created_at = Column(DateTime, default=lambda: datetime.utcnow())


class HostelAllocation(Base):
    __tablename__ = "hostel_allocations"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    student_id = Column(UUID(as_uuid=True), ForeignKey("students.id"), nullable=False)
    hostel_id = Column(UUID(as_uuid=True), ForeignKey("hostels.id"), nullable=False)
    room_id = Column(UUID(as_uuid=True), ForeignKey("hostel_rooms.id"), nullable=False)
    bed_number = Column(String(10), nullable=True)
    check_in_date = Column(Date, nullable=True)
    check_out_date = Column(Date, nullable=True)
    emergency_contact = Column(String(200), nullable=True)
    emergency_phone = Column(String(15), nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.utcnow())
