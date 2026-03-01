"""
VedaFlow Messaging API
=======================
Privacy-aware messaging between school staff, parents, and students.

Endpoints:
  GET  /api/messages/threads          — List my threads
  POST /api/messages/threads          — Create new thread
  GET  /api/messages/threads/{id}     — Get thread messages
  POST /api/messages/threads/{id}     — Reply to thread
  PUT  /api/messages/threads/{id}     — Update thread (resolve/close)
  GET  /api/messages/contacts         — Get available contacts
  GET  /api/messages/complaints       — List complaints (Tier 2)
  POST /api/messages/complaints       — Submit complaint
"""

from fastapi import APIRouter, Request, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_, and_, desc
from sqlalchemy.orm import selectinload
from database import get_db
from utils.permissions import get_current_user
from models.user import User, UserRole
from models.messaging import (
    MessageThread, ThreadParticipant, Message, Complaint,
    ThreadType, ThreadStatus, ComplaintStatus, ComplaintPriority
)
from models.student import Student
import uuid
from datetime import datetime

router = APIRouter(prefix="/api/messages", tags=["messaging"])


# ═══════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════

async def get_user_or_401(request: Request):
    user = await get_current_user(request)
    if not user:
        return None
    return user


def get_branch_id(user):
    return uuid.UUID(user["branch_id"]) if user.get("branch_id") else None


def can_see_complaints(user):
    """Check if user can see complaint threads (Tier 2)."""
    if user.get("is_first_admin"):
        return True
    privs = user.get("privileges", {}) or {}
    return privs.get("complaints", False)


def can_see_messages(user):
    """Check if user has parent_comm or announcements privilege."""
    role = user.get("role", "")
    if role in ("teacher", "parent", "student"):
        return True  # These roles always see their own messages
    if user.get("is_first_admin"):
        return True
    privs = user.get("privileges", {}) or {}
    return privs.get("parent_comm", False) or privs.get("complaints", False)


# ═══════════════════════════════════════════════════════════
# LIST THREADS — Only threads where user is a participant
# ═══════════════════════════════════════════════════════════

@router.get("/threads")
async def list_threads(request: Request, thread_type: str = "", db: AsyncSession = Depends(get_db)):
    user = await get_user_or_401(request)
    if not user:
        return {"error": "unauthorized"}

    user_id = uuid.UUID(user["user_id"])
    branch_id = get_branch_id(user)

    # PRIVACY CORE: Only threads where user is a participant
    q = (
        select(MessageThread)
        .join(ThreadParticipant, ThreadParticipant.thread_id == MessageThread.id)
        .where(
            ThreadParticipant.user_id == user_id,
            MessageThread.branch_id == branch_id,
        )
    )

    # Filter by type
    if thread_type == "complaint":
        if not can_see_complaints(user):
            return {"error": "No access to complaints"}
        q = q.where(MessageThread.thread_type == ThreadType.COMPLAINT)
    elif thread_type == "confidential":
        q = q.where(MessageThread.thread_type == ThreadType.CONFIDENTIAL)
    elif thread_type == "general":
        q = q.where(MessageThread.thread_type == ThreadType.GENERAL)

    q = q.options(selectinload(MessageThread.participants)).order_by(desc(MessageThread.last_message_at))

    result = await db.execute(q.limit(50))
    threads = result.scalars().unique().all()

    thread_list = []
    for t in threads:
        # Get unread count for this user
        my_participation = next((p for p in t.participants if p.user_id == user_id), None)
        unread = not my_participation.is_read if my_participation else False

        # Get other participants' names
        other_names = []
        for p in t.participants:
            if p.user_id != user_id:
                u = await db.scalar(select(User).where(User.id == p.user_id))
                if u:
                    other_names.append({"name": u.full_name, "role": p.role_in_thread or u.role.value})

        thread_list.append({
            "id": str(t.id),
            "subject": t.subject,
            "type": t.thread_type.value,
            "status": t.status.value,
            "student_id": str(t.student_id) if t.student_id else None,
            "last_message": t.last_message_preview or "",
            "last_message_at": t.last_message_at.strftime("%d %b, %I:%M %p") if t.last_message_at else "",
            "unread": unread,
            "participants": other_names,
            "created_at": t.created_at.strftime("%d %b %Y") if t.created_at else "",
        })

    return {"threads": thread_list}


# ═══════════════════════════════════════════════════════════
# CREATE THREAD — With auto-copy rules
# ═══════════════════════════════════════════════════════════

@router.post("/threads")
async def create_thread(request: Request, db: AsyncSession = Depends(get_db)):
    """
    Create a new message thread.

    Body JSON:
        receiver_id: str         — UUID of receiver
        subject: str             — Thread subject
        message: str             — First message content
        thread_type: str         — "general" | "confidential" | "complaint"
        student_id: str          — Optional: related student
        complaint_category: str  — Optional: if type is complaint
        complaint_priority: str  — Optional: low/medium/high/urgent
    """
    user = await get_user_or_401(request)
    if not user:
        return {"error": "unauthorized"}

    data = await request.json()
    receiver_id_str = data.get("receiver_id", "").strip()
    subject = data.get("subject", "").strip()
    message_text = data.get("message", "").strip()
    thread_type_str = data.get("thread_type", "general")
    student_id_str = data.get("student_id", "").strip()

    if not receiver_id_str or not subject or not message_text:
        return {"error": "Receiver, subject, and message are required"}

    sender_id = uuid.UUID(user["user_id"])
    receiver_id = uuid.UUID(receiver_id_str)
    branch_id = get_branch_id(user)
    student_id = uuid.UUID(student_id_str) if student_id_str else None

    # Validate receiver exists
    receiver = await db.scalar(select(User).where(User.id == receiver_id))
    if not receiver:
        return {"error": "Receiver not found"}

    # Determine thread type
    try:
        thread_type = ThreadType(thread_type_str)
    except ValueError:
        thread_type = ThreadType.GENERAL

    # Create thread
    thread = MessageThread(
        branch_id=branch_id,
        created_by=sender_id,
        created_by_role=user.get("role", ""),
        subject=subject,
        thread_type=thread_type,
        student_id=student_id,
        last_message_at=datetime.utcnow(),
        last_message_preview=message_text[:200],
    )
    db.add(thread)
    await db.flush()

    # Add sender as participant
    db.add(ThreadParticipant(
        thread_id=thread.id, user_id=sender_id,
        role_in_thread="sender", can_reply=True, is_read=True,
    ))

    # Add receiver as participant
    db.add(ThreadParticipant(
        thread_id=thread.id, user_id=receiver_id,
        role_in_thread="receiver", can_reply=True, is_read=False,
    ))

    # ═══════════════════════════════════════════════════════
    # AUTO-COPY RULES
    # ═══════════════════════════════════════════════════════
    sender_role = user.get("role", "")
    receiver_role = receiver.role.value if receiver.role else ""

    if thread_type != ThreadType.CONFIDENTIAL:
        # Rule 1: Staff → Student → auto-copy Parent
        if sender_role in ("school_admin", "teacher") and receiver_role == "student":
            # Find parent of this student
            student = await db.scalar(select(Student).where(Student.user_id == receiver_id))
            if student and student.parent_id:
                parent_user = await db.scalar(select(User).where(User.id == student.parent_id))
                if parent_user and parent_user.id != sender_id:
                    db.add(ThreadParticipant(
                        thread_id=thread.id, user_id=parent_user.id,
                        role_in_thread="auto_copy", can_reply=True, is_read=False,
                    ))

        # Rule 2: Staff → Parent → student NOT auto-copied (private about child)
        # Nothing to do — just sender + receiver

        # Rule 3: If complaint, auto-add first admin (principal)
        if thread_type == ThreadType.COMPLAINT:
            first_admin = await db.scalar(
                select(User).where(
                    User.branch_id == branch_id,
                    User.is_first_admin == True,
                    User.is_active == True,
                )
            )
            if first_admin and first_admin.id != sender_id and first_admin.id != receiver_id:
                db.add(ThreadParticipant(
                    thread_id=thread.id, user_id=first_admin.id,
                    role_in_thread="escalated_to", can_reply=True, is_read=False,
                ))

    # Create first message
    msg = Message(
        thread_id=thread.id,
        sender_id=sender_id,
        sender_name=f"{user.get('first_name', '')} {user.get('last_name', '')}".strip(),
        sender_role=sender_role,
        content=message_text,
    )
    db.add(msg)

    # If complaint, create complaint record
    if thread_type == ThreadType.COMPLAINT:
        complaint = Complaint(
            branch_id=branch_id,
            thread_id=thread.id,
            submitted_by=sender_id,
            submitter_name=f"{user.get('first_name', '')} {user.get('last_name', '')}".strip(),
            student_id=student_id,
            subject=subject,
            description=message_text,
            category=data.get("complaint_category", "general"),
            priority=ComplaintPriority(data.get("complaint_priority", "medium")),
            assigned_to=receiver_id,
        )
        db.add(complaint)

    await db.commit()

    return {
        "success": True,
        "thread_id": str(thread.id),
        "message": f"Message sent to {receiver.full_name}",
        "auto_copied": thread_type != ThreadType.CONFIDENTIAL and sender_role in ("school_admin", "teacher") and receiver_role == "student",
    }


# ═══════════════════════════════════════════════════════════
# GET THREAD MESSAGES
# ═══════════════════════════════════════════════════════════

@router.get("/threads/{thread_id}")
async def get_thread(request: Request, thread_id: str, db: AsyncSession = Depends(get_db)):
    user = await get_user_or_401(request)
    if not user:
        return {"error": "unauthorized"}

    user_id = uuid.UUID(user["user_id"])
    tid = uuid.UUID(thread_id)

    # PRIVACY: Check user is a participant
    participant = await db.scalar(
        select(ThreadParticipant).where(
            ThreadParticipant.thread_id == tid,
            ThreadParticipant.user_id == user_id,
        )
    )
    if not participant:
        return {"error": "Access denied — you are not a participant in this thread"}

    # Get thread with messages
    thread = await db.scalar(
        select(MessageThread).where(MessageThread.id == tid)
        .options(selectinload(MessageThread.messages), selectinload(MessageThread.participants))
    )
    if not thread:
        return {"error": "Thread not found"}

    # Mark as read
    participant.is_read = True
    participant.last_read_at = datetime.utcnow()
    await db.commit()

    # Get participant details
    participants = []
    for p in thread.participants:
        u = await db.scalar(select(User).where(User.id == p.user_id))
        if u:
            participants.append({
                "user_id": str(u.id),
                "name": u.full_name,
                "role": u.role.value,
                "role_in_thread": p.role_in_thread,
                "designation": getattr(u, 'designation', None),
            })

    messages = [{
        "id": str(m.id),
        "sender_id": str(m.sender_id),
        "sender_name": m.sender_name or "Unknown",
        "sender_role": m.sender_role or "",
        "content": m.content,
        "is_system": m.is_system_message,
        "is_mine": m.sender_id == user_id,
        "time": m.created_at.strftime("%d %b, %I:%M %p") if m.created_at else "",
    } for m in thread.messages]

    # Get complaint info if complaint thread
    complaint_info = None
    if thread.thread_type == ThreadType.COMPLAINT:
        comp = await db.scalar(select(Complaint).where(Complaint.thread_id == tid))
        if comp:
            complaint_info = {
                "id": str(comp.id),
                "status": comp.status.value,
                "priority": comp.priority.value,
                "category": comp.category,
                "resolution_notes": comp.resolution_notes,
            }

    return {
        "thread": {
            "id": str(thread.id),
            "subject": thread.subject,
            "type": thread.thread_type.value,
            "status": thread.status.value,
            "student_id": str(thread.student_id) if thread.student_id else None,
            "created_at": thread.created_at.strftime("%d %b %Y") if thread.created_at else "",
        },
        "messages": messages,
        "participants": participants,
        "complaint": complaint_info,
    }


# ═══════════════════════════════════════════════════════════
# REPLY TO THREAD
# ═══════════════════════════════════════════════════════════

@router.post("/threads/{thread_id}")
async def reply_to_thread(request: Request, thread_id: str, db: AsyncSession = Depends(get_db)):
    user = await get_user_or_401(request)
    if not user:
        return {"error": "unauthorized"}

    user_id = uuid.UUID(user["user_id"])
    tid = uuid.UUID(thread_id)

    # Check participant and can_reply
    participant = await db.scalar(
        select(ThreadParticipant).where(
            ThreadParticipant.thread_id == tid,
            ThreadParticipant.user_id == user_id,
        )
    )
    if not participant:
        return {"error": "Access denied"}
    if not participant.can_reply:
        return {"error": "You cannot reply to this thread"}

    data = await request.json()
    content = data.get("message", "").strip()
    if not content:
        return {"error": "Message cannot be empty"}

    # Get thread
    thread = await db.scalar(
        select(MessageThread).where(MessageThread.id == tid)
        .options(selectinload(MessageThread.participants))
    )
    if not thread or thread.status == ThreadStatus.CLOSED:
        return {"error": "Thread is closed"}

    # Create message
    msg = Message(
        thread_id=tid,
        sender_id=user_id,
        sender_name=f"{user.get('first_name', '')} {user.get('last_name', '')}".strip(),
        sender_role=user.get("role", ""),
        content=content,
    )
    db.add(msg)

    # Update thread preview
    thread.last_message_at = datetime.utcnow()
    thread.last_message_preview = content[:200]

    # Mark all other participants as unread
    for p in thread.participants:
        if p.user_id != user_id:
            p.is_read = False

    # Mark sender as read
    participant.is_read = True

    await db.commit()

    return {
        "success": True,
        "message_id": str(msg.id),
    }


# ═══════════════════════════════════════════════════════════
# UPDATE THREAD STATUS (resolve/close)
# ═══════════════════════════════════════════════════════════

@router.put("/threads/{thread_id}")
async def update_thread(request: Request, thread_id: str, db: AsyncSession = Depends(get_db)):
    user = await get_user_or_401(request)
    if not user:
        return {"error": "unauthorized"}

    user_id = uuid.UUID(user["user_id"])
    tid = uuid.UUID(thread_id)

    # Check participant
    participant = await db.scalar(
        select(ThreadParticipant).where(
            ThreadParticipant.thread_id == tid,
            ThreadParticipant.user_id == user_id,
        )
    )
    if not participant:
        return {"error": "Access denied"}

    data = await request.json()
    thread = await db.scalar(select(MessageThread).where(MessageThread.id == tid))
    if not thread:
        return {"error": "Thread not found"}

    new_status = data.get("status")
    if new_status:
        try:
            thread.status = ThreadStatus(new_status)
        except ValueError:
            return {"error": "Invalid status"}

    # If complaint, update complaint too
    if thread.thread_type == ThreadType.COMPLAINT:
        comp = await db.scalar(select(Complaint).where(Complaint.thread_id == tid))
        if comp:
            if new_status == "resolved":
                comp.status = ComplaintStatus.RESOLVED
                comp.resolved_at = datetime.utcnow()
                comp.resolution_notes = data.get("resolution_notes", "")
            elif new_status == "closed":
                comp.status = ComplaintStatus.CLOSED

    # Add system message
    msg = Message(
        thread_id=tid,
        sender_id=user_id,
        sender_name="System",
        sender_role="system",
        content=f"Thread marked as {new_status} by {user.get('first_name', '')}",
        is_system_message=True,
    )
    db.add(msg)

    await db.commit()
    return {"success": True}


# ═══════════════════════════════════════════════════════════
# GET CONTACTS — Who can this user message?
# ═══════════════════════════════════════════════════════════

@router.get("/contacts")
async def get_contacts(request: Request, search: str = "", role_filter: str = "",
                       db: AsyncSession = Depends(get_db)):
    user = await get_user_or_401(request)
    if not user:
        return {"error": "unauthorized"}

    branch_id = get_branch_id(user)
    user_role = user.get("role", "")
    user_id = uuid.UUID(user["user_id"])

    contacts = []

    # Build query based on who the user is
    q = select(User).where(User.branch_id == branch_id, User.is_active == True, User.id != user_id)

    if role_filter:
        try:
            q = q.where(User.role == UserRole(role_filter.upper()))
        except ValueError:
            pass

    if search:
        q = q.where(
            or_(
                User.first_name.ilike(f"%{search}%"),
                User.last_name.ilike(f"%{search}%"),
                User.email.ilike(f"%{search}%"),
            )
        )

    # Role-based contact visibility
    if user_role == "parent":
        # Parents can message: teachers and school admins only
        q = q.where(User.role.in_([UserRole.TEACHER, UserRole.SCHOOL_ADMIN]))
    elif user_role == "student":
        # Students can message: teachers only
        q = q.where(User.role == UserRole.TEACHER)
    elif user_role == "teacher":
        # Teachers can message: parents, other teachers, school admins
        q = q.where(User.role.in_([UserRole.PARENT, UserRole.TEACHER, UserRole.SCHOOL_ADMIN]))
    elif user_role == "school_admin":
        # School admins can message: everyone in branch
        pass  # No filter

    result = await db.execute(q.order_by(User.role, User.first_name).limit(50))
    users = result.scalars().all()

    for u in users:
        contacts.append({
            "id": str(u.id),
            "name": u.full_name,
            "email": u.email,
            "role": u.role.value,
            "designation": getattr(u, 'designation', None),
        })

    return {"contacts": contacts}


# ═══════════════════════════════════════════════════════════
# COMPLAINTS LIST — Tier 2 (only principal/assigned sees)
# ═══════════════════════════════════════════════════════════

@router.get("/complaints")
async def list_complaints(request: Request, status: str = "", db: AsyncSession = Depends(get_db)):
    user = await get_user_or_401(request)
    if not user:
        return {"error": "unauthorized"}

    user_id = uuid.UUID(user["user_id"])
    branch_id = get_branch_id(user)
    user_role = user.get("role", "")

    # TIER 2: Only see complaints you're involved in
    if user_role == "parent":
        # Parents see only their own complaints
        q = select(Complaint).where(Complaint.branch_id == branch_id, Complaint.submitted_by == user_id)
    elif can_see_complaints(user):
        # Principal / staff with complaints privilege — see all for branch
        q = select(Complaint).where(Complaint.branch_id == branch_id)
    elif user_role == "teacher":
        # Teachers see only complaints assigned to them
        q = select(Complaint).where(Complaint.branch_id == branch_id, Complaint.assigned_to == user_id)
    else:
        return {"complaints": []}  # No access

    if status:
        try:
            q = q.where(Complaint.status == ComplaintStatus(status))
        except ValueError:
            pass

    result = await db.execute(q.order_by(desc(Complaint.created_at)).limit(50))
    complaints = result.scalars().all()

    return {"complaints": [{
        "id": str(c.id),
        "subject": c.subject,
        "description": c.description[:200],
        "category": c.category,
        "priority": c.priority.value if c.priority else "medium",
        "status": c.status.value if c.status else "open",
        "submitter": c.submitter_name,
        "thread_id": str(c.thread_id) if c.thread_id else None,
        "created_at": c.created_at.strftime("%d %b %Y") if c.created_at else "",
    } for c in complaints]}