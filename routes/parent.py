"""Parent Portal — View child's data, message teachers, file complaints"""
from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from database import get_db
from models.user import UserRole
from models.student import Student
from utils.permissions import require_role
import uuid

router = APIRouter(prefix="/parent")
templates = Jinja2Templates(directory="templates")


async def get_parent_children(request, db):
    """Get children linked to parent user. Link via father_phone/mother_phone matching user phone."""
    user = request.state.user
    user_id = uuid.UUID(user["user_id"])
    # Direct link: Student.parent_user_id or phone match
    # For now, use parent_user_id field (we'll add it)
    from models.user import User
    u = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if not u:
        return [], user

    # Find children by matching phone
    phone = u.phone or ""
    q = select(Student).where(
        Student.is_active == True,
        (Student.father_phone == phone) | (Student.mother_phone == phone) | (Student.guardian_phone == phone)
    ).options(selectinload(Student.class_), selectinload(Student.section))
    result = await db.execute(q)
    children = result.scalars().all()
    return children, user


@router.get("/dashboard", response_class=HTMLResponse)
@require_role(UserRole.PARENT)
async def parent_dashboard(request: Request, db: AsyncSession = Depends(get_db)):
    children, user = await get_parent_children(request, db)

    if not children:
        return templates.TemplateResponse("parent/no_children.html", {
            "request": request, "user": user, "active_page": "dashboard"})

    from datetime import date
    from models.attendance import Attendance
    from models.fee import FeeRecord, PaymentStatus
    from models.notification import Announcement
    from models.messaging import Complaint, ComplaintStatus

    child_data = []
    for child in children:
        # Attendance
        total = await db.scalar(select(func.count(func.distinct(Attendance.date))).where(Attendance.student_id == child.id)) or 0
        present = await db.scalar(select(func.count(func.distinct(Attendance.date))).where(
            Attendance.student_id == child.id, Attendance.status == 'present')) or 0
        att_pct = round((present / total * 100) if total > 0 else 0)

        # Today
        today_att = (await db.execute(select(Attendance).where(
            Attendance.student_id == child.id, Attendance.date == date.today()))).scalar_one_or_none()

        # Fees
        pending = await db.scalar(select(func.sum(FeeRecord.amount_due - FeeRecord.amount_paid - FeeRecord.discount)).where(
            FeeRecord.student_id == child.id,
            FeeRecord.status.in_([PaymentStatus.PENDING, PaymentStatus.PARTIAL, PaymentStatus.OVERDUE]))) or 0

        child_data.append({
            "student": child, "att_pct": att_pct,
            "today": today_att.status if today_att else None,
            "pending_fees": round(pending),
        })

    # Announcements
    branch_id = children[0].branch_id if children else None
    announcements = []
    if branch_id:
        ann = await db.execute(select(Announcement).where(
            Announcement.branch_id == branch_id, Announcement.is_active == True,
            Announcement.target_role.in_(['all', 'parent'])
        ).order_by(Announcement.is_pinned.desc(), Announcement.created_at.desc()).limit(5))
        announcements = ann.scalars().all()

    # Open complaints
    open_complaints = await db.scalar(select(func.count()).select_from(Complaint).where(
        Complaint.submitted_by == uuid.UUID(user["user_id"]),
        Complaint.status.in_([ComplaintStatus.OPEN, ComplaintStatus.IN_PROGRESS]))) or 0

    return templates.TemplateResponse("parent/dashboard.html", {
        "request": request, "user": user, "active_page": "dashboard",
        "children": child_data, "announcements": announcements,
        "open_complaints": open_complaints,
    })


@router.get("/messages", response_class=HTMLResponse)
@require_role(UserRole.PARENT)
async def parent_messages(request: Request, db: AsyncSession = Depends(get_db)):
    children, user = await get_parent_children(request, db)
    from models.messaging import MessageThread

    threads = (await db.execute(
        select(MessageThread).where(MessageThread.parent_id == uuid.UUID(user["user_id"]))
        .options(selectinload(MessageThread.messages))
        .order_by(MessageThread.updated_at.desc())
    )).scalars().all()

    return templates.TemplateResponse("parent/messages.html", {
        "request": request, "user": user, "active_page": "messages",
        "threads": threads, "children": [c["student"] for c in []] if not children else children,
    })


@router.get("/complaints", response_class=HTMLResponse)
@require_role(UserRole.PARENT)
async def parent_complaints(request: Request, db: AsyncSession = Depends(get_db)):
    children, user = await get_parent_children(request, db)
    from models.messaging import Complaint

    complaints = (await db.execute(
        select(Complaint).where(Complaint.submitted_by == uuid.UUID(user["user_id"]))
        .order_by(Complaint.created_at.desc())
    )).scalars().all()

    return templates.TemplateResponse("parent/complaints.html", {
        "request": request, "user": user, "active_page": "complaints",
        "complaints": complaints, "children": children,
    })


@router.get("/child/{student_id}", response_class=HTMLResponse)
@require_role(UserRole.PARENT)
async def view_child(request: Request, student_id: str, db: AsyncSession = Depends(get_db)):
    children, user = await get_parent_children(request, db)
    child = next((c for c in children if str(c.id) == student_id), None)
    if not child:
        raise HTTPException(403, "Not authorized to view this student")

    from datetime import date
    from models.attendance import Attendance
    from models.fee import FeeRecord
    from models.exam import Exam, ExamSubject, Marks
    import json

    # Attendance
    records = (await db.execute(select(Attendance).where(Attendance.student_id == child.id)
        .order_by(Attendance.date.desc()))).scalars().all()
    total = len(records)
    present = sum(1 for r in records if r.status == 'present')
    att_pct = round((present / total * 100) if total > 0 else 0)
    cal_data = {r.date.isoformat(): r.status for r in records}

    # Fees
    fees = (await db.execute(select(FeeRecord).where(FeeRecord.student_id == child.id)
        .options(selectinload(FeeRecord.fee_structure))
        .order_by(FeeRecord.due_date.desc()))).scalars().all()
    balance = sum(f.amount_due - f.amount_paid - f.discount for f in fees)

    # Results
    exams = (await db.execute(select(Exam).where(
        Exam.branch_id == child.branch_id, Exam.is_published == True)
        .order_by(Exam.start_date.desc()))).scalars().all()

    exam_results = []
    for exam in exams:
        subjects = (await db.execute(select(ExamSubject).where(
            ExamSubject.exam_id == exam.id, ExamSubject.class_id == child.class_id))).scalars().all()
        if not subjects:
            continue
        total_obt = 0
        total_max = 0
        for es in subjects:
            m = (await db.execute(select(Marks).where(
                Marks.exam_subject_id == es.id, Marks.student_id == child.id))).scalar_one_or_none()
            total_obt += (m.marks_obtained if m and not m.is_absent else 0)
            total_max += es.max_marks
        pct = round((total_obt / total_max * 100) if total_max > 0 else 0)
        exam_results.append({"name": exam.name, "pct": pct, "total": total_obt, "max": total_max})

    return templates.TemplateResponse("parent/child_detail.html", {
        "request": request, "user": user, "active_page": "dashboard",
        "child": child, "att_pct": att_pct, "total_days": total,
        "present_days": present, "cal_data": json.dumps(cal_data),
        "fees": fees, "balance": round(balance),
        "exam_results": exam_results,
    })


# ═══════════════════════════════════════════════════════════
# SPRINT 22: Parent Analytics, Calendar, Leave Approval
# ═══════════════════════════════════════════════════════════

@router.get("/child/{student_id}/analytics", response_class=HTMLResponse)
@require_role(UserRole.PARENT)
async def parent_child_analytics(request: Request, student_id: str, db: AsyncSession = Depends(get_db)):
    children, user = await get_parent_children(request, db)
    child = next((c for c in children if str(c.id) == student_id), None)
    if not child:
        return templates.TemplateResponse("parent/no_children.html", {"request": request, "user": user, "active_page": "dashboard"})
    return templates.TemplateResponse("parent/child_analytics.html", {
        "request": request, "user": user, "active_page": "analytics", "child": child,
    })


@router.get("/calendar", response_class=HTMLResponse)
@require_role(UserRole.PARENT)
async def parent_calendar(request: Request, db: AsyncSession = Depends(get_db)):
    children, user = await get_parent_children(request, db)
    return templates.TemplateResponse("student/calendar.html", {
        "request": request, "user": user, "active_page": "calendar",
    })