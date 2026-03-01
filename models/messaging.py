"""
VedaFlow Messaging & Complaints System
========================================
Privacy-Aware School Communication

RULES:
  Principal → Parent: Private (student NOT auto-copied)
  Principal → Student: Auto-copy to parent
  Teacher → Parent: Private (about child, student NOT auto-copied)
  Teacher → Student: Auto-copy to parent
  Parent → Teacher/Principal: Can initiate

CONFIDENTIALITY:
  Normal: Anyone with parent_comm privilege can see thread list (not content)
  Confidential: ONLY sender + receiver. Nobody else. Period. (Tier 3)
  Complaint: Only principal/assigned_to can see (Tier 2)

SQL Migration at bottom of file.
"""

import uuid
import enum
from datetime import datetime
from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey, Text, Enum as SAEnum, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from database import Base


# ═══════════════════════════════════════════════════════════
# ENUMS
# ═══════════════════════════════════════════════════════════

class ThreadType(str, enum.Enum):
    GENERAL = "general"           # Normal school communication
    COMPLAINT = "complaint"       # Complaint — Tier 2 (principal + assigned only)
    CONFIDENTIAL = "confidential" # Locked — Tier 3 (sender + receiver ONLY)


class ThreadStatus(str, enum.Enum):
    ACTIVE = "active"
    RESOLVED = "resolved"
    CLOSED = "closed"


class ComplaintStatus(str, enum.Enum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    ESCALATED = "escalated"
    CLOSED = "closed"


class ComplaintPriority(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


# ═══════════════════════════════════════════════════════════
# MESSAGE THREAD — The Conversation Container
# ═══════════════════════════════════════════════════════════

class MessageThread(Base):
    __tablename__ = "message_threads"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    branch_id = Column(UUID(as_uuid=True), ForeignKey("branches.id"), nullable=False, index=True)

    # Who started it
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    created_by_role = Column(String(50), nullable=True)  # school_admin, teacher, parent

    # Subject
    subject = Column(String(300), nullable=False)
    thread_type = Column(SAEnum(ThreadType), default=ThreadType.GENERAL, index=True)
    status = Column(SAEnum(ThreadStatus), default=ThreadStatus.ACTIVE)

    # Related student (if applicable — for parent-teacher communication about a child)
    student_id = Column(UUID(as_uuid=True), ForeignKey("students.id"), nullable=True)

    # Last message preview for list display
    last_message_at = Column(DateTime, default=lambda: datetime.utcnow())
    last_message_preview = Column(String(200), nullable=True)

    created_at = Column(DateTime, default=lambda: datetime.utcnow())
    updated_at = Column(DateTime, default=lambda: datetime.utcnow(), onupdate=lambda: datetime.utcnow())

    # Relationships
    messages = relationship("Message", back_populates="thread", cascade="all, delete-orphan",
                            order_by="Message.created_at")
    participants = relationship("ThreadParticipant", back_populates="thread", cascade="all, delete-orphan")


# ═══════════════════════════════════════════════════════════
# THREAD PARTICIPANTS — Who Can See This Thread
# This is the KEY to privacy enforcement
# ═══════════════════════════════════════════════════════════

class ThreadParticipant(Base):
    __tablename__ = "thread_participants"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    thread_id = Column(UUID(as_uuid=True), ForeignKey("message_threads.id"), nullable=False, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    role_in_thread = Column(String(50), nullable=True)  # sender, receiver, cc, auto_copy
    can_reply = Column(Boolean, default=True)
    is_read = Column(Boolean, default=False)
    last_read_at = Column(DateTime, nullable=True)
    added_at = Column(DateTime, default=lambda: datetime.utcnow())

    thread = relationship("MessageThread", back_populates="participants")

    __table_args__ = (
        Index("ix_participant_thread_user", "thread_id", "user_id", unique=True),
    )


# ═══════════════════════════════════════════════════════════
# MESSAGE — Individual Messages in a Thread
# ═══════════════════════════════════════════════════════════

class Message(Base):
    __tablename__ = "messages"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    thread_id = Column(UUID(as_uuid=True), ForeignKey("message_threads.id"), nullable=False, index=True)
    sender_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    sender_name = Column(String(200), nullable=True)
    sender_role = Column(String(50), nullable=True)
    content = Column(Text, nullable=False)
    is_system_message = Column(Boolean, default=False)  # "Thread created", "Resolved" etc.

    created_at = Column(DateTime, default=lambda: datetime.utcnow())

    thread = relationship("MessageThread", back_populates="messages")


# ═══════════════════════════════════════════════════════════
# COMPLAINT — Linked to Thread but with Extra Fields
# ═══════════════════════════════════════════════════════════

class Complaint(Base):
    __tablename__ = "complaints"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    branch_id = Column(UUID(as_uuid=True), ForeignKey("branches.id"), nullable=False, index=True)
    thread_id = Column(UUID(as_uuid=True), ForeignKey("message_threads.id"), nullable=True)  # linked thread

    submitted_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    submitter_name = Column(String(200), nullable=True)
    student_id = Column(UUID(as_uuid=True), ForeignKey("students.id"), nullable=True)

    subject = Column(String(300), nullable=False)
    description = Column(Text, nullable=False)
    category = Column(String(100), nullable=True)
    priority = Column(SAEnum(ComplaintPriority), default=ComplaintPriority.MEDIUM)
    status = Column(SAEnum(ComplaintStatus), default=ComplaintStatus.OPEN, index=True)

    assigned_to = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    is_escalated = Column(Boolean, default=False)
    escalated_to = Column(String(50), nullable=True)
    resolution_notes = Column(Text, nullable=True)

    created_at = Column(DateTime, default=lambda: datetime.utcnow())
    updated_at = Column(DateTime, default=lambda: datetime.utcnow(), onupdate=lambda: datetime.utcnow())
    resolved_at = Column(DateTime, nullable=True)


# ═══════════════════════════════════════════════════════════
# PRIVACY RULES — Auto-Copy Logic
# ═══════════════════════════════════════════════════════════

"""
AUTO-COPY RULES (implemented in API, not model):

1. Principal/Teacher → Student message:
   - Student is participant (receiver)
   - Parent is auto-added as participant (role="auto_copy", can_reply=True)
   - Because parent should know what school tells their child

2. Principal/Teacher → Parent message:
   - Parent is participant (receiver)
   - Student is NOT auto-added
   - Because it might be about fees, complaints, sensitive matters

3. Parent → Teacher/Principal message:
   - Parent is participant (sender)
   - Student is NOT auto-added
   - It's the parent's choice to communicate privately

4. Confidential thread:
   - ONLY sender and receiver in participants
   - No auto-copy, no privilege-based access
   - Even first_admin cannot see (unless they ARE the sender/receiver)

5. Complaint thread:
   - Submitter + principal are participants
   - If assigned to a teacher, teacher is added
   - Clerk with parent_comm privilege CANNOT see complaints
"""