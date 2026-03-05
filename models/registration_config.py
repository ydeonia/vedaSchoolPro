"""models/registration_config.py"""
import uuid
from datetime import datetime
from sqlalchemy import Column, String, Boolean, DateTime, Integer, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from database import Base


class RegistrationNumberConfig(Base):
    __tablename__ = "registration_number_configs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    branch_id = Column(UUID(as_uuid=True), ForeignKey("branches.id"), nullable=False, unique=True)
    format_template = Column(String(200), nullable=False, default="{SCHOOL4}{YY}{SEQ4}")
    school_code = Column(String(10), nullable=True)
    current_year = Column(Integer, nullable=True)
    current_sequence = Column(Integer, default=0)
    use_base36 = Column(Boolean, default=False)
    created_at = Column(DateTime, default=lambda: datetime.utcnow())
    updated_at = Column(DateTime, default=lambda: datetime.utcnow(), onupdate=lambda: datetime.utcnow())