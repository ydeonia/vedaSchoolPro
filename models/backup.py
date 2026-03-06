"""
VedaFlow Backup System — Models for tracking database backups per branch.
Supports manual triggers, scheduled nightly backups, and uploaded restore files.
"""

import uuid
import enum
from datetime import datetime
from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey, Text, Integer, BigInteger, JSON, Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from database import Base


class BackupStatus(str, enum.Enum):
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


class BackupType(str, enum.Enum):
    FULL = "full"            # Full branch data dump
    MANUAL = "manual"        # Triggered by super admin
    SCHEDULED = "scheduled"  # Nightly cron
    UPLOADED = "uploaded"    # Uploaded .sql.gz file


class BackupRecord(Base):
    __tablename__ = "backup_records"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    branch_id = Column(UUID(as_uuid=True), ForeignKey("branches.id"), nullable=False, index=True)
    org_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False)

    file_path = Column(String(500), nullable=True)        # Relative path: backups/{branch_id}/2026-03-05_020000.sql.gz
    file_name = Column(String(200), nullable=True)         # Just the filename
    file_size_bytes = Column(BigInteger, default=0)

    backup_type = Column(
        SAEnum(BackupType, values_callable=lambda x: [e.value for e in x]),
        default=BackupType.MANUAL
    )
    status = Column(
        SAEnum(BackupStatus, values_callable=lambda x: [e.value for e in x]),
        default=BackupStatus.IN_PROGRESS,
        index=True,
    )

    tables_included = Column(JSON, nullable=True)          # ["students", "teachers", "attendance", ...]
    record_counts = Column(JSON, nullable=True)            # {"students": 150, "teachers": 20, ...}
    error_message = Column(Text, nullable=True)

    started_at = Column(DateTime, default=lambda: datetime.utcnow())
    completed_at = Column(DateTime, nullable=True)

    triggered_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)  # null for scheduled

    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.utcnow())
