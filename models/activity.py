import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime, Date, ForeignKey, Text, Boolean, Integer, Float
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from database import Base


class Activity(Base):
    __tablename__ = "activities"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    branch_id = Column(UUID(as_uuid=True), ForeignKey("branches.id"), nullable=False, index=True)
    name = Column(String(255), nullable=False)  # also used as title
    title = Column(String(300), nullable=True)  # alias for name
    activity_type = Column(String(50), nullable=True)  # sports, cultural, academic, arts, tech
    category = Column(String(100), nullable=True)  # sports, arts, academics, cultural
    description = Column(Text, nullable=True)
    event_date = Column(Date, nullable=True)
    registration_deadline = Column(Date, nullable=True)
    venue = Column(String(200), nullable=True)
    max_participants = Column(Integer, nullable=True)
    eligible_classes = Column(JSONB, nullable=True)
    status = Column(String(20), default="upcoming")
    is_active = Column(Boolean, default=True)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.utcnow())

    student_activities = relationship("StudentActivity", back_populates="activity")


class StudentActivity(Base):
    __tablename__ = "student_activities"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    student_id = Column(UUID(as_uuid=True), ForeignKey("students.id"), nullable=False)
    activity_id = Column(UUID(as_uuid=True), ForeignKey("activities.id"), nullable=False)
    participation = Column(String(50), nullable=True)  # participated, winner, runner_up
    achievement = Column(String(255), nullable=True)
    remarks = Column(Text, nullable=True)
    date = Column(Date, nullable=True)
    nominated_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    nomination_type = Column(String(20), default="self")
    team_name = Column(String(100), nullable=True)
    position = Column(String(50), nullable=True)  # 1st, 2nd, 3rd, participant
    score = Column(Float, nullable=True)
    status = Column(String(20), default="registered")
    created_at = Column(DateTime, default=lambda: datetime.utcnow())

    student = relationship("Student", back_populates="activities")
    activity = relationship("Activity", back_populates="student_activities")