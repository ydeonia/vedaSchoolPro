import uuid
import enum
from datetime import datetime
from sqlalchemy import (
    Column, String, DateTime, Date, Time, Integer, Boolean, Text,
    ForeignKey, Enum as SAEnum, UniqueConstraint
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from database import Base


class OnlinePlatform(str, enum.Enum):
    GOOGLE_MEET = "google_meet"
    ZOOM = "zoom"
    TEAMS = "teams"


class OnlineClassStatus(str, enum.Enum):
    SCHEDULED = "scheduled"
    LIVE = "live"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class LectureAttendanceType(str, enum.Enum):
    JOINED = "joined"
    WATCHED = "watched"


class OnlinePlatformConfig(Base):
    """Per-branch OAuth settings for video platforms."""
    __tablename__ = "online_platform_configs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    branch_id = Column(UUID(as_uuid=True), ForeignKey("branches.id"), unique=True, nullable=False)

    default_platform = Column(SAEnum(OnlinePlatform), default=OnlinePlatform.GOOGLE_MEET)

    # Google Meet (via Calendar API — OAuth2)
    google_enabled = Column(Boolean, default=False)
    google_access_token = Column(Text, nullable=True)
    google_refresh_token = Column(Text, nullable=True)
    google_token_expiry = Column(DateTime, nullable=True)
    google_email = Column(String(255), nullable=True)

    # Zoom (Server-to-Server OAuth)
    zoom_enabled = Column(Boolean, default=False)
    zoom_account_id = Column(String(255), nullable=True)
    zoom_client_id = Column(String(255), nullable=True)
    zoom_client_secret = Column(String(255), nullable=True)

    # Microsoft Teams (Graph API — OAuth2)
    teams_enabled = Column(Boolean, default=False)
    teams_access_token = Column(Text, nullable=True)
    teams_refresh_token = Column(Text, nullable=True)
    teams_token_expiry = Column(DateTime, nullable=True)
    teams_tenant_id = Column(String(255), nullable=True)

    # ── Health tracking — detect broken auth before teachers hit it ──
    google_last_verified = Column(DateTime, nullable=True)
    google_error = Column(String(500), nullable=True)  # NULL = healthy, set = broken
    zoom_last_verified = Column(DateTime, nullable=True)
    zoom_error = Column(String(500), nullable=True)
    teams_last_verified = Column(DateTime, nullable=True)
    teams_error = Column(String(500), nullable=True)

    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.utcnow())
    updated_at = Column(DateTime, default=lambda: datetime.utcnow(), onupdate=lambda: datetime.utcnow())


class TeacherPlatformToken(Base):
    """
    Per-TEACHER OAuth tokens — each teacher connects their own Google/Teams account.
    Solves the single-admin-session problem: if one teacher's token expires,
    only that teacher is affected. Others continue working.
    Zoom uses branch-level S2S (no user session), so not stored here.
    """
    __tablename__ = "teacher_platform_tokens"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    teacher_id = Column(UUID(as_uuid=True), ForeignKey("teachers.id"), nullable=False, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    branch_id = Column(UUID(as_uuid=True), ForeignKey("branches.id"), nullable=False)
    platform = Column(SAEnum(OnlinePlatform), nullable=False)

    access_token = Column(Text, nullable=True)
    refresh_token = Column(Text, nullable=True)
    token_expiry = Column(DateTime, nullable=True)
    account_email = Column(String(255), nullable=True)  # e.g. teacher@gmail.com
    tenant_id = Column(String(255), nullable=True)  # Teams only

    # Health
    last_verified = Column(DateTime, nullable=True)
    error = Column(String(500), nullable=True)  # NULL = healthy

    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.utcnow())
    updated_at = Column(DateTime, default=lambda: datetime.utcnow(), onupdate=lambda: datetime.utcnow())

    teacher = relationship("Teacher")

    __table_args__ = (
        UniqueConstraint('teacher_id', 'platform', name='uq_teacher_platform'),
    )


class OnlineClass(Base):
    """A scheduled online class / virtual lecture."""
    __tablename__ = "online_classes"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    branch_id = Column(UUID(as_uuid=True), ForeignKey("branches.id"), nullable=False, index=True)

    teacher_id = Column(UUID(as_uuid=True), ForeignKey("teachers.id"), nullable=False, index=True)
    class_id = Column(UUID(as_uuid=True), ForeignKey("classes.id"), nullable=False)
    section_id = Column(UUID(as_uuid=True), ForeignKey("sections.id"), nullable=True)
    subject_id = Column(UUID(as_uuid=True), ForeignKey("subjects.id"), nullable=True)

    title = Column(String(300), nullable=False)
    description = Column(Text, nullable=True)
    scheduled_date = Column(Date, nullable=False, index=True)
    start_time = Column(Time, nullable=False)
    end_time = Column(Time, nullable=True)
    duration_minutes = Column(Integer, default=45)

    platform = Column(SAEnum(OnlinePlatform), nullable=False)
    meeting_link = Column(String(500), nullable=True)
    meeting_id = Column(String(100), nullable=True)
    meeting_password = Column(String(50), nullable=True)
    calendar_event_id = Column(String(255), nullable=True)

    status = Column(SAEnum(OnlineClassStatus), default=OnlineClassStatus.SCHEDULED, index=True)

    recording_url = Column(String(500), nullable=True)
    recording_added_at = Column(DateTime, nullable=True)

    reminder_sent = Column(Boolean, default=False)

    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.utcnow())
    updated_at = Column(DateTime, default=lambda: datetime.utcnow(), onupdate=lambda: datetime.utcnow())

    teacher = relationship("Teacher")
    class_ = relationship("Class")
    section = relationship("Section")
    subject = relationship("Subject")
    attendance_records = relationship("LectureAttendance", back_populates="online_class", cascade="all, delete-orphan")


class LectureAttendance(Base):
    """Tracks who attended (joined live) or watched (recording) an online class."""
    __tablename__ = "lecture_attendance"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    online_class_id = Column(UUID(as_uuid=True), ForeignKey("online_classes.id"), nullable=False, index=True)
    student_id = Column(UUID(as_uuid=True), ForeignKey("students.id"), nullable=False, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)

    attendance_type = Column(SAEnum(LectureAttendanceType), nullable=False)
    joined_at = Column(DateTime, default=lambda: datetime.utcnow())
    ip_address = Column(String(45), nullable=True)

    online_class = relationship("OnlineClass", back_populates="attendance_records")

    __table_args__ = (
        UniqueConstraint('online_class_id', 'student_id', 'attendance_type',
                         name='uq_lecture_student_type'),
    )
