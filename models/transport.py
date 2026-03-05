import uuid
import enum
from datetime import datetime, date
from sqlalchemy import Column, String, Boolean, DateTime, Date, ForeignKey, Text, Integer, Numeric, Enum, Float, Time
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from database import Base


class Vehicle(Base):
    __tablename__ = "vehicles"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    branch_id = Column(UUID(as_uuid=True), ForeignKey("branches.id"), nullable=False, index=True)
    vehicle_number = Column(String(20), nullable=False)  # KA-01-AB-1234
    vehicle_type = Column(String(50), default="bus")  # bus, van, auto
    capacity = Column(Integer, default=40)
    make_model = Column(String(100), nullable=True)  # Tata Starbus, Force Traveller
    year = Column(Integer, nullable=True)
    # Driver details
    driver_name = Column(String(200), nullable=True)
    driver_phone = Column(String(15), nullable=True)
    driver_license = Column(String(50), nullable=True)
    # Conductor details
    conductor_name = Column(String(200), nullable=True)
    conductor_phone = Column(String(15), nullable=True)
    # Documents
    insurance_number = Column(String(100), nullable=True)
    insurance_expiry = Column(Date, nullable=True)
    fitness_expiry = Column(Date, nullable=True)
    permit_expiry = Column(Date, nullable=True)
    gps_device_id = Column(String(100), nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.utcnow())

    routes = relationship("TransportRoute", back_populates="vehicle")


class TransportRoute(Base):
    __tablename__ = "transport_routes"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    branch_id = Column(UUID(as_uuid=True), ForeignKey("branches.id"), nullable=False, index=True)
    vehicle_id = Column(UUID(as_uuid=True), ForeignKey("vehicles.id"), nullable=True)
    route_name = Column(String(200), nullable=False)  # "Route 1 - Koramangala"
    route_number = Column(String(20), nullable=True)
    driver_id = Column(UUID(as_uuid=True), ForeignKey("employees.id"), nullable=True)
    conductor_id = Column(UUID(as_uuid=True), ForeignKey("employees.id"), nullable=True)
    start_time = Column(Time, nullable=True)
    end_time = Column(Time, nullable=True)
    distance_km = Column(Float, nullable=True)
    monthly_fee = Column(Numeric(10, 2), default=0)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.utcnow())

    vehicle = relationship("Vehicle", back_populates="routes")
    stops = relationship("RouteStop", back_populates="route", cascade="all, delete-orphan")


class RouteStop(Base):
    __tablename__ = "route_stops"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    route_id = Column(UUID(as_uuid=True), ForeignKey("transport_routes.id"), nullable=False, index=True)
    stop_name = Column(String(200), nullable=False)
    stop_order = Column(Integer, default=1)
    pickup_time = Column(Time, nullable=True)
    drop_time = Column(Time, nullable=True)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)

    route = relationship("TransportRoute", back_populates="stops")


class StudentTransport(Base):
    __tablename__ = "student_transport"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    student_id = Column(UUID(as_uuid=True), ForeignKey("students.id"), nullable=False, index=True)
    route_id = Column(UUID(as_uuid=True), ForeignKey("transport_routes.id"), nullable=False)
    stop_id = Column(UUID(as_uuid=True), ForeignKey("route_stops.id"), nullable=True)
    pickup_stop_id = Column(UUID(as_uuid=True), ForeignKey("route_stops.id"), nullable=True)
    drop_stop_id = Column(UUID(as_uuid=True), ForeignKey("route_stops.id"), nullable=True)
    start_date = Column(Date, default=date.today)
    end_date = Column(Date, nullable=True)
    is_active = Column(Boolean, default=True)
