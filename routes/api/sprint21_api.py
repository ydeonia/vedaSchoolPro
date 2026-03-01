"""Sprint 21 APIs — Event Calendar, Leave System, Assignment Upload, Daily Diary, Achievements"""
from fastapi import APIRouter, Request, Depends, UploadFile, File, Form
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_
from database import get_db
from models.user import UserRole, User
from models.student import Student
from models.academic import Class, Section
from models.teacher import Teacher
from models.exam import Exam, ExamSubject
from models.mega_modules import (
    SchoolEvent, EventType, StudentLeave, LeaveReasonType, ApprovalStatus,
    Homework, HomeworkSubmission, DailyDiary, DiaryEntryType,
    StudentAchievement, AchievementCategory, StudentHealth,
    StudentTransport, TransportRoute, RouteStop,
)
from utils.permissions import require_role
from datetime import date, datetime, timedelta
import uuid, json, os, shutil

router = APIRouter(prefix="/api/sprint21")

UPLOAD_DIR = "static/uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)


# ═══════════════════════════════════════════════════════════
# 1. EVENT CALENDAR APIs
# ═══════════════════════════════════════════════════════════

@router.get("/events")
@require_role(UserRole.STUDENT, UserRole.PARENT, UserRole.TEACHER, UserRole.SCHOOL_ADMIN, UserRole.SUPER_ADMIN)
async def get_events(request: Request, db: AsyncSession = Depends(get_db)):
    """Get all events for the branch."""
    user = request.state.user
    branch_id = user.get("branch_id")
    if not branch_id:
        # Get branch from student/teacher profile
        student = (await db.execute(
            select(Student).where(Student.user_id == uuid.UUID(user["user_id"]))
        )).scalar_one_or_none()
        if student:
            branch_id = str(student.branch_id)
        else:
            teacher = (await db.execute(
                select(Teacher).where(Teacher.user_id == uuid.UUID(user["user_id"]))
            )).scalar_one_or_none()
            if teacher:
                branch_id = str(teacher.branch_id)

    if not branch_id:
        return {"events": []}

    events = (await db.execute(
        select(SchoolEvent).where(
            SchoolEvent.branch_id == uuid.UUID(branch_id),
            SchoolEvent.is_active == True,
        ).order_by(SchoolEvent.start_date)
    )).scalars().all()

    return {"events": [{
        "id": str(e.id),
        "title": e.title,
        "description": e.description or "",
        "type": e.event_type.value,
        "start_date": e.start_date.isoformat(),
        "end_date": e.end_date.isoformat() if e.end_date else e.start_date.isoformat(),
        "is_holiday": e.is_holiday,
        "color": e.color or _event_color(e.event_type),
        "location": e.location or "",
    } for e in events]}


def _event_color(et):
    return {"holiday": "#EF4444", "exam": "#F59E0B", "event": "#10B981",
            "ptm": "#3B82F6", "sports": "#8B5CF6", "cultural": "#EC4899",
            "deadline": "#F97316", "other": "#6B7280"}.get(et.value, "#6B7280")


@router.post("/events")
@require_role(UserRole.SCHOOL_ADMIN)
async def create_event(request: Request, db: AsyncSession = Depends(get_db)):
    body = await request.json()
    user = request.state.user

    # Get branch
    branch_id = body.get("branch_id")
    if not branch_id:
        from models.branch import Branch
        branch = (await db.execute(select(Branch).limit(1))).scalar_one_or_none()
        branch_id = str(branch.id) if branch else None

    event = SchoolEvent(
        branch_id=uuid.UUID(branch_id),
        title=body["title"],
        description=body.get("description", ""),
        event_type=EventType(body.get("event_type", "event")),
        start_date=date.fromisoformat(body["start_date"]),
        end_date=date.fromisoformat(body["end_date"]) if body.get("end_date") else None,
        is_holiday=body.get("is_holiday", False),
        color=body.get("color", ""),
        location=body.get("location", ""),
        created_by=uuid.UUID(user["user_id"]),
    )
    db.add(event)
    await db.commit()
    return {"success": True, "id": str(event.id)}


# ═══════════════════════════════════════════════════════════
# 2. LEAVE APPLICATION APIs
# ═══════════════════════════════════════════════════════════

@router.post("/leave/apply")
@require_role(UserRole.STUDENT)
async def apply_leave(request: Request, db: AsyncSession = Depends(get_db)):
    """Student applies for leave. Auto-checks exam/event conflicts."""
    user = request.state.user
    body = await request.json()

    student = (await db.execute(
        select(Student).where(Student.user_id == uuid.UUID(user["user_id"]))
    )).scalar_one_or_none()
    if not student:
        return {"error": "Student profile not found"}

    start = date.fromisoformat(body["start_date"])
    end = date.fromisoformat(body["end_date"])
    total = (end - start).days + 1

    # Check exam conflicts
    exam_conflict = False
    conflict_text = ""
    exams = (await db.execute(
        select(Exam).where(
            Exam.branch_id == student.branch_id,
            Exam.start_date <= end, Exam.end_date >= start,
        )
    )).scalars().all()
    if exams:
        exam_conflict = True
        conflict_text = ", ".join(f"{e.name} ({e.start_date})" for e in exams)

    # Check event conflicts
    event_conflict = False
    event_text = ""
    events = (await db.execute(
        select(SchoolEvent).where(
            SchoolEvent.branch_id == student.branch_id,
            SchoolEvent.start_date <= end,
            or_(SchoolEvent.end_date >= start, SchoolEvent.end_date == None),
            SchoolEvent.is_active == True,
            SchoolEvent.is_holiday == False,
        )
    )).scalars().all()
    if events:
        event_conflict = True
        event_text = ", ".join(f"{e.title} ({e.start_date})" for e in events)

    leave = StudentLeave(
        branch_id=student.branch_id,
        student_id=student.id,
        start_date=start, end_date=end,
        reason_type=LeaveReasonType(body.get("reason_type", "personal")),
        reason_text=body.get("reason_text", ""),
        total_days=total,
        has_exam_conflict=exam_conflict,
        conflict_details=conflict_text if exam_conflict else None,
        has_event_conflict=event_conflict,
        event_conflict_details=event_text if event_conflict else None,
        applied_by="student",
    )
    db.add(leave)
    await db.commit()

    warnings = []
    if exam_conflict:
        warnings.append(f"⚠️ EXAM CONFLICT: {conflict_text}")
    if event_conflict:
        warnings.append(f"⚠️ EVENT CONFLICT: {event_text}")

    return {
        "success": True, "id": str(leave.id),
        "total_days": total, "warnings": warnings,
        "message": "Leave applied! Waiting for parent approval." + (f" WARNING: {'; '.join(warnings)}" if warnings else ""),
    }


@router.get("/leave/my")
@require_role(UserRole.STUDENT)
async def get_my_leaves(request: Request, db: AsyncSession = Depends(get_db)):
    user = request.state.user
    student = (await db.execute(
        select(Student).where(Student.user_id == uuid.UUID(user["user_id"]))
    )).scalar_one_or_none()
    if not student:
        return {"leaves": []}

    leaves = (await db.execute(
        select(StudentLeave).where(
            StudentLeave.student_id == student.id,
            StudentLeave.is_cancelled == False,
        ).order_by(StudentLeave.created_at.desc()).limit(30)
    )).scalars().all()

    return {"leaves": [{
        "id": str(l.id),
        "start_date": l.start_date.isoformat(),
        "end_date": l.end_date.isoformat(),
        "total_days": l.total_days,
        "reason_type": l.reason_type.value,
        "reason_text": l.reason_text or "",
        "parent_status": l.parent_status.value,
        "teacher_status": l.teacher_status.value,
        "has_exam_conflict": l.has_exam_conflict,
        "conflict_details": l.conflict_details or "",
        "has_event_conflict": l.has_event_conflict,
        "event_conflict_details": l.event_conflict_details or "",
        "applied_on": l.created_at.strftime("%d %b %Y"),
        "overall_status": "approved" if l.parent_status.value == "approved" and l.teacher_status.value == "approved"
            else "rejected" if l.parent_status.value == "rejected" or l.teacher_status.value == "rejected"
            else "pending",
    } for l in leaves]}


@router.post("/leave/approve")
@require_role(UserRole.PARENT, UserRole.TEACHER, UserRole.SCHOOL_ADMIN)
async def approve_leave(request: Request, db: AsyncSession = Depends(get_db)):
    """Parent or Teacher approves/rejects leave. Body: {leave_id, action: approve/reject, comment, role: parent/teacher}"""
    user = request.state.user
    body = await request.json()
    leave_id = uuid.UUID(body["leave_id"])
    action = body.get("action", "approve")
    comment = body.get("comment", "")
    role = body.get("role", "parent")

    leave = (await db.execute(select(StudentLeave).where(StudentLeave.id == leave_id))).scalar_one_or_none()
    if not leave:
        return {"error": "Leave not found"}

    status = ApprovalStatus.APPROVED if action == "approve" else ApprovalStatus.REJECTED
    now = datetime.utcnow()

    if role == "parent":
        leave.parent_status = status
        leave.parent_comment = comment
        leave.parent_approved_at = now
        leave.parent_approved_by = uuid.UUID(user["user_id"])
    elif role == "teacher":
        leave.teacher_status = status
        leave.teacher_comment = comment
        leave.teacher_approved_at = now
        leave.teacher_approved_by = uuid.UUID(user["user_id"])

    await db.commit()
    return {"success": True, "message": f"Leave {action}d successfully."}


# ═══════════════════════════════════════════════════════════
# 3. HOMEWORK SUBMISSION (File Upload)
# ═══════════════════════════════════════════════════════════

@router.post("/homework/submit")
@require_role(UserRole.STUDENT)
async def submit_homework(
    request: Request,
    homework_id: str = Form(...),
    file: UploadFile = File(None),
    content: str = Form(""),
    db: AsyncSession = Depends(get_db),
):
    user = request.state.user
    student = (await db.execute(
        select(Student).where(Student.user_id == uuid.UUID(user["user_id"]))
    )).scalar_one_or_none()
    if not student:
        return {"error": "Student not found"}

    hw = (await db.execute(select(Homework).where(Homework.id == uuid.UUID(homework_id)))).scalar_one_or_none()
    if not hw:
        return {"error": "Homework not found"}

    # Handle file upload
    file_path = None
    if file and file.filename:
        ext = os.path.splitext(file.filename)[1].lower()
        if ext not in [".pdf", ".doc", ".docx", ".jpg", ".jpeg", ".png", ".txt"]:
            return {"error": f"File type {ext} not allowed. Use PDF, DOC, JPG, PNG."}
        fname = f"hw_{student.id}_{hw.id}_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}{ext}"
        fpath = os.path.join(UPLOAD_DIR, "homework", fname)
        os.makedirs(os.path.dirname(fpath), exist_ok=True)
        with open(fpath, "wb") as f:
            shutil.copyfileobj(file.file, f)
        file_path = f"/static/uploads/homework/{fname}"

    # Check late
    is_late = date.today() > hw.due_date if hw.due_date else False

    submission = HomeworkSubmission(
        homework_id=hw.id,
        student_id=student.id,
        content=content or "",
        attachment_url=file_path,
        submitted_at=datetime.utcnow(),
        status="late" if is_late else "submitted",
    )
    db.add(submission)
    await db.commit()

    return {
        "success": True, "id": str(submission.id),
        "is_late": is_late,
        "message": f"Assignment submitted{'  (⚠️ Late submission!)' if is_late else ' ✅'}",
    }


@router.get("/homework/submissions/{homework_id}")
@require_role(UserRole.TEACHER)
async def get_homework_submissions(request: Request, homework_id: str, db: AsyncSession = Depends(get_db)):
    """Teacher view: who submitted, who didn't."""
    hw = (await db.execute(select(Homework).where(Homework.id == uuid.UUID(homework_id)))).scalar_one_or_none()
    if not hw:
        return {"error": "Not found"}

    subs = (await db.execute(
        select(HomeworkSubmission).where(HomeworkSubmission.homework_id == hw.id)
    )).scalars().all()

    # Get all students in that class
    students = (await db.execute(
        select(Student).where(Student.class_id == hw.class_id, Student.is_active == True)
    )).scalars().all()

    submitted_ids = {s.student_id for s in subs}
    sub_map = {s.student_id: s for s in subs}

    result = []
    for st in students:
        sub = sub_map.get(st.id)
        result.append({
            "student_id": str(st.id),
            "name": st.full_name,
            "roll": st.roll_number or "",
            "submitted": st.id in submitted_ids,
            "status": sub.status if sub else "missing",
            "submitted_at": sub.submitted_at.strftime("%d %b %Y %H:%M") if sub else None,
            "file_url": sub.attachment_url if sub else None,
            "grade": sub.marks_obtained if sub else None,
            "teacher_remarks": sub.teacher_remarks if sub else None,
        })

    return {
        "homework": {"title": hw.title, "due_date": hw.due_date.isoformat() if hw.due_date else ""},
        "total": len(students),
        "submitted_count": len(submitted_ids),
        "submissions": sorted(result, key=lambda x: (x["submitted"], x["name"])),
    }


@router.post("/homework/grade")
@require_role(UserRole.TEACHER)
async def grade_submission(request: Request, db: AsyncSession = Depends(get_db)):
    """Teacher grades: {submission_id, marks, remarks, status: accepted/redo/rejected}"""
    body = await request.json()
    sub = (await db.execute(
        select(HomeworkSubmission).where(HomeworkSubmission.id == uuid.UUID(body["submission_id"]))
    )).scalar_one_or_none()
    if not sub:
        return {"error": "Submission not found"}

    sub.marks_obtained = body.get("marks")
    sub.teacher_remarks = body.get("remarks", "")
    sub.status = body.get("status", "graded")
    sub.graded_at = datetime.utcnow()
    await db.commit()
    return {"success": True}


# ═══════════════════════════════════════════════════════════
# 4. DAILY DIARY APIs
# ═══════════════════════════════════════════════════════════

@router.post("/diary/write")
@require_role(UserRole.TEACHER)
async def write_diary(request: Request, db: AsyncSession = Depends(get_db)):
    body = await request.json()
    user = request.state.user
    teacher = (await db.execute(
        select(Teacher).where(Teacher.user_id == uuid.UUID(user["user_id"]))
    )).scalar_one_or_none()
    if not teacher:
        return {"error": "Teacher not found"}

    entry = DailyDiary(
        branch_id=teacher.branch_id,
        teacher_id=teacher.id,
        student_id=uuid.UUID(body["student_id"]) if body.get("student_id") else None,
        class_id=uuid.UUID(body["class_id"]) if body.get("class_id") else None,
        section_id=uuid.UUID(body["section_id"]) if body.get("section_id") else None,
        entry_date=date.fromisoformat(body.get("date", date.today().isoformat())),
        entry_type=DiaryEntryType(body.get("type", "informational")),
        content=body["content"],
        is_visible_to_parent=body.get("visible_to_parent", True),
    )
    db.add(entry)
    await db.commit()
    return {"success": True, "id": str(entry.id)}


@router.get("/diary/student/{student_id}")
@require_role(UserRole.STUDENT, UserRole.PARENT, UserRole.TEACHER, UserRole.SCHOOL_ADMIN)
async def get_student_diary(request: Request, student_id: str, db: AsyncSession = Depends(get_db)):
    """Get diary entries for a student (personal + class-wide)."""
    student = (await db.execute(select(Student).where(Student.id == uuid.UUID(student_id)))).scalar_one_or_none()
    if not student:
        return {"entries": []}

    entries = (await db.execute(
        select(DailyDiary).where(
            DailyDiary.is_active == True,
            DailyDiary.is_visible_to_parent == True,
            or_(
                DailyDiary.student_id == student.id,
                and_(DailyDiary.class_id == student.class_id, DailyDiary.student_id == None),
            )
        ).order_by(DailyDiary.entry_date.desc()).limit(30)
    )).scalars().all()

    # Get teacher names
    teacher_ids = list(set(e.teacher_id for e in entries))
    teachers = {}
    if teacher_ids:
        ts = (await db.execute(select(Teacher).where(Teacher.id.in_(teacher_ids)))).scalars().all()
        teachers = {t.id: t.full_name for t in ts}

    return {"entries": [{
        "id": str(e.id),
        "date": e.entry_date.isoformat(),
        "date_display": e.entry_date.strftime("%d %b %Y"),
        "type": e.entry_type.value,
        "content": e.content,
        "teacher": teachers.get(e.teacher_id, "—"),
        "is_personal": e.student_id is not None,
        "parent_acknowledged": e.parent_acknowledged,
    } for e in entries]}


@router.post("/diary/acknowledge")
@require_role(UserRole.PARENT, UserRole.STUDENT)
async def acknowledge_diary(request: Request, db: AsyncSession = Depends(get_db)):
    body = await request.json()
    entry = (await db.execute(
        select(DailyDiary).where(DailyDiary.id == uuid.UUID(body["entry_id"]))
    )).scalar_one_or_none()
    if entry:
        entry.parent_acknowledged = True
        entry.parent_acknowledged_at = datetime.utcnow()
        await db.commit()
    return {"success": True}


# ═══════════════════════════════════════════════════════════
# 5. ACHIEVEMENTS APIs
# ═══════════════════════════════════════════════════════════

@router.get("/achievements/{student_id}")
@require_role(UserRole.STUDENT, UserRole.PARENT, UserRole.TEACHER, UserRole.SCHOOL_ADMIN)
async def get_achievements(request: Request, student_id: str, db: AsyncSession = Depends(get_db)):
    achs = (await db.execute(
        select(StudentAchievement).where(
            StudentAchievement.student_id == uuid.UUID(student_id),
            StudentAchievement.is_active == True,
        ).order_by(StudentAchievement.awarded_date.desc())
    )).scalars().all()

    return {"achievements": [{
        "id": str(a.id),
        "title": a.title,
        "description": a.description or "",
        "category": a.category.value,
        "badge": a.badge_icon,
        "date": a.awarded_date.strftime("%d %b %Y"),
    } for a in achs]}


@router.post("/achievements")
@require_role(UserRole.TEACHER)
async def award_achievement(request: Request, db: AsyncSession = Depends(get_db)):
    body = await request.json()
    user = request.state.user
    teacher = (await db.execute(
        select(Teacher).where(Teacher.user_id == uuid.UUID(user["user_id"]))
    )).scalar_one_or_none()

    ach = StudentAchievement(
        branch_id=teacher.branch_id if teacher else uuid.UUID(body.get("branch_id", "00000000-0000-0000-0000-000000000000")),
        student_id=uuid.UUID(body["student_id"]),
        title=body["title"],
        description=body.get("description", ""),
        category=AchievementCategory(body.get("category", "academic")),
        badge_icon=body.get("badge", "🏆"),
        awarded_date=date.fromisoformat(body.get("date", date.today().isoformat())),
        awarded_by=uuid.UUID(user["user_id"]),
    )
    db.add(ach)
    await db.commit()
    return {"success": True, "id": str(ach.id)}


# ═══════════════════════════════════════════════════════════
# 6. STUDENT PROFILE ENRICHMENT (Transport + Health + Address)
# ═══════════════════════════════════════════════════════════

@router.get("/student/profile-extra")
@require_role(UserRole.STUDENT)
async def get_student_extra_profile(request: Request, db: AsyncSession = Depends(get_db)):
    """Returns transport, health, address, achievements, diary — the full enriched profile."""
    user = request.state.user
    student = (await db.execute(
        select(Student).where(Student.user_id == uuid.UUID(user["user_id"]))
    )).scalar_one_or_none()
    if not student:
        return {"error": "No profile"}

    # Transport
    transport_info = None
    st = (await db.execute(
        select(StudentTransport).where(StudentTransport.student_id == student.id, StudentTransport.is_active == True)
    )).scalar_one_or_none()
    if st:
        route = (await db.execute(select(TransportRoute).where(TransportRoute.id == st.route_id))).scalar_one_or_none()
        stop = (await db.execute(select(RouteStop).where(RouteStop.id == st.stop_id))).scalar_one_or_none() if st.stop_id else None
        transport_info = {
            "route_name": route.name if route else "—",
            "route_number": route.route_number if route else "",
            "stop_name": stop.name if stop else "—",
            "pickup_time": stop.pickup_time.strftime("%I:%M %p") if stop and stop.pickup_time else "—",
            "drop_time": stop.drop_time.strftime("%I:%M %p") if stop and stop.drop_time else "—",
            "fee_monthly": float(st.monthly_fee) if hasattr(st, 'monthly_fee') and st.monthly_fee else None,
        }

    # Health
    health_info = None
    health = (await db.execute(
        select(StudentHealth).where(StudentHealth.student_id == student.id)
    )).scalar_one_or_none()
    if health:
        health_info = {
            "blood_group": health.blood_group or "—",
            "height": health.height_cm, "weight": health.weight_kg, "bmi": health.bmi,
            "vision_left": health.vision_left, "vision_right": health.vision_right,
            "wears_glasses": health.wears_glasses,
            "allergies": json.loads(health.allergies) if health.allergies else [],
            "conditions": json.loads(health.chronic_conditions) if health.chronic_conditions else [],
            "emergency_1": health.emergency_contact_1 or "",
            "emergency_2": health.emergency_contact_2 or "",
            "doctor": health.family_doctor or "",
            "last_checkup": health.last_checkup_date.isoformat() if health.last_checkup_date else None,
        }

    # Address
    address_info = {
        "address": student.address or "",
        "city": student.city or "",
        "state": student.state or "",
        "pincode": student.pincode or "",
        "full": ", ".join(filter(None, [student.address, student.city, student.state, student.pincode])) or "Not set",
    }

    # Achievements
    achs = (await db.execute(
        select(StudentAchievement).where(
            StudentAchievement.student_id == student.id, StudentAchievement.is_active == True
        ).order_by(StudentAchievement.awarded_date.desc()).limit(10)
    )).scalars().all()

    return {
        "transport": transport_info,
        "health": health_info,
        "address": address_info,
        "achievements": [{"title": a.title, "badge": a.badge_icon, "date": a.awarded_date.strftime("%d %b %Y"), "category": a.category.value} for a in achs],
    }