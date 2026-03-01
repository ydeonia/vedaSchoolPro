import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime, ForeignKey, Text, Boolean
from sqlalchemy.dialects.postgresql import UUID, JSONB
from database import Base


class IDCardTemplate(Base):
    __tablename__ = "id_card_templates"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    branch_id = Column(UUID(as_uuid=True), ForeignKey("branches.id"), nullable=False, index=True)
    name = Column(String(100), nullable=False)  # "Student ID", "Teacher ID"
    target_type = Column(String(20), nullable=False)  # student, teacher
    template_config = Column(JSONB, nullable=True)  # layout, colors, fields config
    background_url = Column(String(500), nullable=True)
    is_default = Column(Boolean, default=False)
    created_at = Column(DateTime, default=lambda: datetime.utcnow())