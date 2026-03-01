from fastapi import APIRouter, Request, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from database import get_db
from models.user import UserRole
from models.teacher import Teacher
from models.timetable import TimetableSlot, PeriodDefinition
from models.period_log import PeriodLog
from models.syllabus import Syllabus
from models.academic import Class, Subject, Section
from pydantic import BaseModel
from typing import Optional
from datetime import date, datetime
import uuid

router = APIRouter(prefix="/api/teacher")


async def verify_teacher(request: Request):
    from utils.permissions import get_current_user
    user = await get_current_user(request)
    if not user or user.get("role") != UserRole.TEACHER.value:
        raise HTTPException(403, "Teacher access required")
    request.state.user = user
    return user


async def get_teacher(request: Request, db: AsyncSession):
    user = await verify_teacher(request)
    user_id = uuid.UUID(user.get("user_id"))
    result = await db.execute(
        select(Teacher).where(Teacher.user_id == user_id, Teacher.is_active == True)
    )
    teacher = result.scalar_one_or_none()
    if not teacher:
        raise HTTPException(404, "Teacher profile not found")
    return teacher, user


# ─── PERIOD COMPLETION ─────────────────────────────────────
class CompletePeriodData(BaseModel):
    period_id: str
    class_id: str
    subject_id: str
    section_id: Optional[str] = None
    slot_id: Optional[str] = None
    topic_covered: Optional[str] = None
    syllabus_id: Optional[str] = None
    homework: Optional[str] = None
    remarks: Optional[str] = None
    date: Optional[str] = None  # YYYY-MM-DD, defaults to today


@router.post("/period/complete")
async def complete_period(data: CompletePeriodData, request: Request, db: AsyncSession = Depends(get_db)):
    teacher, _ = await get_teacher(request, db)

    log_date = date.fromisoformat(data.date) if data.date else date.today()

    # Check if already logged
    existing = await db.execute(
        select(PeriodLog).where(
            PeriodLog.teacher_id == teacher.id,
            PeriodLog.period_definition_id == uuid.UUID(data.period_id),
            PeriodLog.date == log_date,
        )
    )
    log = existing.scalar_one_or_none()

    if log:
        # Update existing
        log.topic_covered = data.topic_covered
        log.syllabus_id = uuid.UUID(data.syllabus_id) if data.syllabus_id else None
        log.homework = data.homework
        log.remarks = data.remarks
        log.completed_at = datetime.utcnow()
    else:
        # Create new
        log = PeriodLog(
            branch_id=teacher.branch_id,
            teacher_id=teacher.id,
            timetable_slot_id=uuid.UUID(data.slot_id) if data.slot_id else None,
            class_id=uuid.UUID(data.class_id),
            section_id=uuid.UUID(data.section_id) if data.section_id else None,
            subject_id=uuid.UUID(data.subject_id),
            period_definition_id=uuid.UUID(data.period_id),
            date=log_date,
            topic_covered=data.topic_covered,
            syllabus_id=uuid.UUID(data.syllabus_id) if data.syllabus_id else None,
            homework=data.homework,
            remarks=data.remarks,
            status="completed",
        )
        db.add(log)

    # If syllabus chapter linked, mark it completed
    if data.syllabus_id:
        syl = await db.execute(select(Syllabus).where(Syllabus.id == uuid.UUID(data.syllabus_id)))
        chapter = syl.scalar_one_or_none()
        if chapter:
            chapter.is_completed = True

    # Auto-detect: mark teacher present when they complete a period
    from utils.teacher_auto_attendance import auto_mark_teacher_present
    from models.teacher_attendance import CheckInSource
    await auto_mark_teacher_present(db, teacher.id, teacher.branch_id, CheckInSource.AUTO_PERIOD_LOG, teacher.user_id)

    await db.commit()
    return {"success": True, "message": "Period completed! ✅", "log_id": str(log.id)}


@router.delete("/period/undo/{log_id}")
async def undo_period(log_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    teacher, _ = await get_teacher(request, db)

    result = await db.execute(
        select(PeriodLog).where(PeriodLog.id == uuid.UUID(log_id), PeriodLog.teacher_id == teacher.id)
    )
    log = result.scalar_one_or_none()
    if not log:
        raise HTTPException(404, "Log not found")

    await db.delete(log)
    await db.commit()
    return {"success": True, "message": "Period unmarked"}


# ─── SYLLABUS ──────────────────────────────────────────────
@router.get("/syllabus/chapters")
async def get_syllabus_chapters(
    request: Request, class_id: str, subject_id: str, db: AsyncSession = Depends(get_db)
):
    teacher, _ = await get_teacher(request, db)

    result = await db.execute(
        select(Syllabus)
        .where(
            Syllabus.branch_id == teacher.branch_id,
            Syllabus.class_id == uuid.UUID(class_id),
            Syllabus.subject_id == uuid.UUID(subject_id),
        )
        .order_by(Syllabus.chapter_number)
    )
    chapters = result.scalars().all()

    return {
        "chapters": [
            {"id": str(c.id), "number": c.chapter_number or 0,
             "name": c.chapter_name or c.title,
             "topics": c.topics or "", "completed": c.is_completed}
            for c in chapters
        ]
    }


@router.post("/syllabus/toggle/{chapter_id}")
async def toggle_syllabus(chapter_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    teacher, _ = await get_teacher(request, db)

    result = await db.execute(
        select(Syllabus).where(
            Syllabus.id == uuid.UUID(chapter_id),
            Syllabus.branch_id == teacher.branch_id,
        )
    )
    chapter = result.scalar_one_or_none()
    if not chapter:
        raise HTTPException(404, "Chapter not found")

    chapter.is_completed = not chapter.is_completed
    await db.commit()
    return {"success": True, "completed": chapter.is_completed}


# ─── STATS / REPORTS ───────────────────────────────────────
@router.get("/stats")
async def teacher_stats(request: Request, db: AsyncSession = Depends(get_db)):
    teacher, _ = await get_teacher(request, db)
    today = date.today()

    # Total periods assigned per week
    from models.timetable import DayOfWeek
    slots_result = await db.execute(
        select(func.count(TimetableSlot.id))
        .where(TimetableSlot.teacher_id == teacher.id, TimetableSlot.is_active == True)
    )
    weekly_assigned = slots_result.scalar() or 0

    # Periods completed this month
    month_start = today.replace(day=1)
    month_logs = await db.execute(
        select(func.count(PeriodLog.id))
        .where(PeriodLog.teacher_id == teacher.id, PeriodLog.date >= month_start, PeriodLog.date <= today)
    )
    month_completed = month_logs.scalar() or 0

    # Total periods completed all time
    total_logs = await db.execute(
        select(func.count(PeriodLog.id)).where(PeriodLog.teacher_id == teacher.id)
    )
    total_completed = total_logs.scalar() or 0

    # Syllabus progress (across all subjects)
    combos_result = await db.execute(
        select(TimetableSlot.class_id, TimetableSlot.subject_id)
        .where(TimetableSlot.teacher_id == teacher.id, TimetableSlot.is_active == True)
        .distinct()
    )
    combos = combos_result.all()

    total_chapters = 0
    completed_chapters = 0
    for class_id, subject_id in combos:
        if not subject_id:
            continue
        syl = await db.execute(
            select(Syllabus).where(
                Syllabus.branch_id == teacher.branch_id,
                Syllabus.class_id == class_id,
                Syllabus.subject_id == subject_id,
            )
        )
        chapters = syl.scalars().all()
        total_chapters += len(chapters)
        completed_chapters += sum(1 for c in chapters if c.is_completed)

    syllabus_pct = round(completed_chapters / total_chapters * 100) if total_chapters > 0 else 0

    return {
        "weekly_assigned": weekly_assigned,
        "month_completed": month_completed,
        "total_completed": total_completed,
        "syllabus_total": total_chapters,
        "syllabus_done": completed_chapters,
        "syllabus_pct": syllabus_pct,
    }


# ─── SELF CHECK-IN ────────────────────────────────────────
@router.post("/check-in")
async def self_check_in(request: Request, db: AsyncSession = Depends(get_db)):
    teacher, _ = await get_teacher(request, db)
    from utils.teacher_auto_attendance import auto_mark_teacher_present
    from models.teacher_attendance import CheckInSource, TeacherAttendance, TeacherAttendanceStatus
    from utils.timezone import get_school_time

    today = date.today()
    now, tz_name = await get_school_time(db, teacher.branch_id)

    # Check existing
    result = await db.execute(
        select(TeacherAttendance).where(
            TeacherAttendance.teacher_id == teacher.id,
            TeacherAttendance.date == today,
        )
    )
    existing = result.scalar_one_or_none()

    if existing:
        return {"success": True, "message": "Already checked in today", "already": True,
                "time": existing.check_in_time.strftime("%I:%M:%S %p") if existing.check_in_time else ""}

    att = TeacherAttendance(
        branch_id=teacher.branch_id,
        teacher_id=teacher.id,
        date=today,
        status=TeacherAttendanceStatus.PRESENT,
        check_in_time=now,
        source=CheckInSource.SELF_CHECKIN,
        marked_by=teacher.user_id,
    )
    db.add(att)
    await db.commit()
    return {"success": True, "message": "Checked in! ✅", "time": now.strftime("%I:%M:%S %p")}


@router.post("/check-out")
async def self_check_out(request: Request, db: AsyncSession = Depends(get_db)):
    teacher, _ = await get_teacher(request, db)
    from models.teacher_attendance import TeacherAttendance
    from utils.timezone import get_school_time

    today = date.today()
    now, _ = await get_school_time(db, teacher.branch_id)

    result = await db.execute(
        select(TeacherAttendance).where(
            TeacherAttendance.teacher_id == teacher.id,
            TeacherAttendance.date == today,
        )
    )
    att = result.scalar_one_or_none()
    if not att:
        raise HTTPException(400, "Not checked in today")

    att.check_out_time = now
    await db.commit()
    return {"success": True, "message": "Checked out!", "time": now.strftime("%I:%M:%S %p")}


@router.get("/checkin-status")
async def checkin_status(request: Request, db: AsyncSession = Depends(get_db)):
    """Get today's check-in/out status for the teacher."""
    teacher, _ = await get_teacher(request, db)
    from models.teacher_attendance import TeacherAttendance

    today = date.today()
    result = await db.execute(
        select(TeacherAttendance).where(
            TeacherAttendance.teacher_id == teacher.id,
            TeacherAttendance.date == today,
        )
    )
    att = result.scalar_one_or_none()
    if not att:
        return {"checked_in": False, "checked_out": False, "check_in_time": "", "check_out_time": ""}
    return {
        "checked_in": True,
        "checked_out": att.check_out_time is not None,
        "check_in_time": att.check_in_time.strftime("%I:%M:%S %p") if att.check_in_time else "",
        "check_out_time": att.check_out_time.strftime("%I:%M:%S %p") if att.check_out_time else "",
    }


@router.get("/my-attendance")
async def my_attendance(request: Request, month: int = 0, year: int = 0, db: AsyncSession = Depends(get_db)):
    teacher, _ = await get_teacher(request, db)
    from models.teacher_attendance import TeacherAttendance

    today = date.today()
    m = month or today.month
    y = year or today.year

    from calendar import monthrange
    _, days_in_month = monthrange(y, m)
    month_start = date(y, m, 1)
    month_end = date(y, m, days_in_month)

    result = await db.execute(
        select(TeacherAttendance)
        .where(
            TeacherAttendance.teacher_id == teacher.id,
            TeacherAttendance.date >= month_start,
            TeacherAttendance.date <= month_end,
        )
        .order_by(TeacherAttendance.date)
    )
    records = result.scalars().all()

    present = sum(1 for r in records if r.status.value == "present")
    absent = sum(1 for r in records if r.status.value == "absent")
    late = sum(1 for r in records if r.status.value == "late")
    on_leave = sum(1 for r in records if r.status.value == "on_leave")
    half_day = sum(1 for r in records if r.status.value == "half_day")

    return {
        "records": [
            {"date": r.date.isoformat(), "status": r.status.value,
             "check_in": r.check_in_time.strftime("%I:%M:%S %p") if r.check_in_time else "",
             "check_out": r.check_out_time.strftime("%I:%M:%S %p") if r.check_out_time else "",
             "source": r.source.value if r.source else ""}
            for r in records
        ],
        "summary": {"present": present, "absent": absent, "late": late, "on_leave": on_leave, "half_day": half_day},
        "month": m, "year": y,
    }


# ─── LEAVE MANAGEMENT ────────────────────────────────────
from models.teacher_attendance import LeaveRequest, LeaveType, LeaveStatus

class LeaveRequestData(BaseModel):
    leave_type: str
    start_date: str  # YYYY-MM-DD
    end_date: str
    reason: str


@router.post("/leave/apply")
async def apply_leave(data: LeaveRequestData, request: Request, db: AsyncSession = Depends(get_db)):
    teacher, _ = await get_teacher(request, db)

    start = date.fromisoformat(data.start_date)
    end = date.fromisoformat(data.end_date)
    if end < start:
        raise HTTPException(400, "End date must be after start date")

    leave = LeaveRequest(
        branch_id=teacher.branch_id,
        teacher_id=teacher.id,
        leave_type=LeaveType(data.leave_type),
        start_date=start,
        end_date=end,
        reason=data.reason,
        status=LeaveStatus.PENDING,
    )
    db.add(leave)
    await db.commit()

    days = (end - start).days + 1
    return {"success": True, "message": f"Leave applied for {days} day(s)", "id": str(leave.id)}


@router.get("/leave/my-requests")
async def my_leave_requests(request: Request, db: AsyncSession = Depends(get_db)):
    teacher, _ = await get_teacher(request, db)

    result = await db.execute(
        select(LeaveRequest)
        .where(LeaveRequest.teacher_id == teacher.id)
        .order_by(LeaveRequest.created_at.desc())
        .limit(50)
    )
    leaves = result.scalars().all()

    return {
        "leaves": [
            {"id": str(l.id), "type": l.leave_type.value, "start": l.start_date.isoformat(),
             "end": l.end_date.isoformat(), "days": (l.end_date - l.start_date).days + 1,
             "reason": l.reason, "status": l.status.value,
             "admin_remarks": l.admin_remarks or "",
             "created": l.created_at.strftime("%d %b %Y") if l.created_at else ""}
            for l in leaves
        ]
    }


@router.delete("/leave/cancel/{leave_id}")
async def cancel_leave(leave_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    teacher, _ = await get_teacher(request, db)

    result = await db.execute(
        select(LeaveRequest).where(
            LeaveRequest.id == uuid.UUID(leave_id),
            LeaveRequest.teacher_id == teacher.id,
        )
    )
    leave = result.scalar_one_or_none()
    if not leave:
        raise HTTPException(404, "Leave not found")
    if leave.status != LeaveStatus.PENDING:
        raise HTTPException(400, f"Cannot cancel — already {leave.status.value}")

    leave.status = LeaveStatus.CANCELLED
    await db.commit()
    return {"success": True, "message": "Leave cancelled"}



# ═══════════════════════════════════════════════════════════
# SPRINT 23: Class Management, Attendance, Marks, Homework, Diary
# ═══════════════════════════════════════════════════════════
from models.academic import ClassSubject
from models.student import Student
from models.attendance import Attendance, AttendanceStatus
from models.exam import Exam, ExamSubject, Marks as ExamMarks
from models.fee import FeeRecord
from models.mega_modules import DailyDiary, Homework, HomeworkSubmission
from utils.permissions import require_role
from datetime import date as date_cls, timedelta
import json


@router.get("/my-classes")
@require_role(UserRole.TEACHER)
async def my_classes(request: Request, db: AsyncSession = Depends(get_db)):
    """Get all classes/sections/subjects assigned to this teacher via timetable."""
    teacher, _ = await get_teacher(request, db)
    if not teacher: return {"classes": []}
    # Get from timetable slots — these have class_id, section_id, subject_id
    from models.timetable import TimetableSlot
    slots = (await db.execute(
        select(TimetableSlot.class_id, TimetableSlot.section_id, TimetableSlot.subject_id)
        .where(TimetableSlot.teacher_id == teacher.id)
        .distinct()
    )).all()
    if not slots:
        # Fallback to ClassSubject (no sections)
        assignments = (await db.execute(select(ClassSubject).where(ClassSubject.teacher_id == teacher.id))).scalars().all()
        cids = list(set(a.class_id for a in assignments))
        subids = list(set(a.subject_id for a in assignments))
        classes = {c.id: c for c in (await db.execute(select(Class).where(Class.id.in_(cids)))).scalars().all()} if cids else {}
        subjects = {s.id: s for s in (await db.execute(select(Subject).where(Subject.id.in_(subids)))).scalars().all()} if subids else {}
        # Get all sections for these classes
        all_secs = (await db.execute(select(Section).where(Section.branch_id == teacher.branch_id))).scalars().all()
        sec_map = {s.id: s for s in all_secs}
        result = []
        for a in assignments:
            if a.class_id not in classes or a.subject_id not in subjects: continue
            # Find sections that have students in this class
            sec_ids = (await db.execute(select(Student.section_id).where(Student.class_id == a.class_id, Student.is_active == True).distinct())).scalars().all()
            for sid in sec_ids:
                sc = sec_map.get(sid)
                result.append({"class_id": str(a.class_id), "class_name": classes[a.class_id].name, "section_id": str(sid) if sid else "", "section_name": sc.name if sc else "", "subject_id": str(a.subject_id), "subject_name": subjects[a.subject_id].name})
        return {"classes": result}

    # Build from timetable slots
    cids = list(set(s[0] for s in slots))
    sids = list(set(s[1] for s in slots if s[1]))
    subids = list(set(s[2] for s in slots if s[2]))
    classes = {c.id: c for c in (await db.execute(select(Class).where(Class.id.in_(cids)))).scalars().all()} if cids else {}
    sections = {s.id: s for s in (await db.execute(select(Section).where(Section.id.in_(sids)))).scalars().all()} if sids else {}
    subjects = {s.id: s for s in (await db.execute(select(Subject).where(Subject.id.in_(subids)))).scalars().all()} if subids else {}
    seen = set()
    result = []
    for cid, sid, subid in slots:
        key = f"{cid}-{sid}-{subid}"
        if key in seen: continue
        seen.add(key)
        if cid not in classes: continue
        result.append({"class_id": str(cid), "class_name": classes[cid].name, "section_id": str(sid) if sid else "", "section_name": sections.get(sid, type('',(),{'name':''})()).name if sid else "", "subject_id": str(subid) if subid else "", "subject_name": subjects.get(subid, type('',(),{'name':'?'})()).name if subid else "?"})
    return {"classes": result}


@router.get("/class-students")
@require_role(UserRole.TEACHER)
async def class_students(request: Request, class_id: str, section_id: str, db: AsyncSession = Depends(get_db)):
    students = (await db.execute(select(Student).where(Student.class_id == uuid.UUID(class_id), Student.section_id == uuid.UUID(section_id), Student.is_active == True).order_by(Student.roll_number, Student.first_name))).scalars().all()
    result = []
    for s in students:
        total = await db.scalar(select(func.count(Attendance.id)).where(Attendance.student_id == s.id)) or 0
        present = await db.scalar(select(func.count(Attendance.id)).where(Attendance.student_id == s.id, Attendance.status == AttendanceStatus.present)) or 0
        fees = (await db.execute(select(FeeRecord).where(FeeRecord.student_id == s.id))).scalars().all()
        balance = sum(f.amount_due - f.amount_paid - f.discount for f in fees)
        result.append({"id": str(s.id), "name": s.full_name, "roll": s.roll_number, "admission": s.admission_number or "", "att_pct": round((present/total*100) if total>0 else 0), "fee_balance": round(balance), "last_exam_pct": None, "father_name": s.father_name or "", "father_phone": s.father_phone or "", "mother_name": s.mother_name or "", "mother_phone": s.mother_phone or ""})
    return {"students": result, "count": len(result)}


@router.get("/attendance-status")
@require_role(UserRole.TEACHER)
async def attendance_status(request: Request, class_id: str, section_id: str, date: str, db: AsyncSession = Depends(get_db)):
    att_date = date_cls.fromisoformat(date)
    sids = (await db.execute(select(Student.id).where(Student.class_id == uuid.UUID(class_id), Student.section_id == uuid.UUID(section_id), Student.is_active == True))).scalars().all()
    records = {}
    for sid in sids:
        att = (await db.execute(select(Attendance).where(Attendance.student_id == sid, Attendance.date == att_date))).scalar_one_or_none()
        if att: records[str(sid)] = att.status.value
    return {"records": records, "date": date}


@router.post("/save-attendance")
@require_role(UserRole.TEACHER)
async def save_attendance(request: Request, db: AsyncSession = Depends(get_db)):
    teacher, _ = await get_teacher(request, db)
    if not teacher: return {"error": "Not found"}
    data = await request.json()
    att_date = date_cls.fromisoformat(data["date"])
    for sid_str, status in data["records"].items():
        sid = uuid.UUID(sid_str)
        existing = (await db.execute(select(Attendance).where(Attendance.student_id == sid, Attendance.date == att_date))).scalar_one_or_none()
        if existing:
            existing.status = AttendanceStatus(status)
            existing.marked_by = teacher.user_id
        else:
            db.add(Attendance(student_id=sid, date=att_date, status=AttendanceStatus(status), class_id=uuid.UUID(data["class_id"]), section_id=uuid.UUID(data["section_id"]), branch_id=teacher.branch_id, marked_by=teacher.user_id))
    await db.commit()
    return {"status": "saved", "count": len(data["records"])}


@router.get("/available-exams")
@require_role(UserRole.TEACHER)
async def available_exams(request: Request, db: AsyncSession = Depends(get_db)):
    teacher, _ = await get_teacher(request, db)
    if not teacher: return {"exams": []}
    exams = (await db.execute(select(Exam).where(Exam.branch_id == teacher.branch_id).order_by(Exam.start_date.desc()))).scalars().all()
    return {"exams": [{"id": str(e.id), "name": e.name, "published": e.is_published} for e in exams]}


@router.get("/exam-subjects")
@require_role(UserRole.TEACHER)
async def exam_subjects(request: Request, exam_id: str, class_id: str, db: AsyncSession = Depends(get_db)):
    teacher, _ = await get_teacher(request, db)
    if not teacher: return {"subjects": []}
    es_list = (await db.execute(select(ExamSubject).where(ExamSubject.exam_id == uuid.UUID(exam_id), ExamSubject.class_id == uuid.UUID(class_id)))).scalars().all()
    subjects = {s.id: s.name for s in (await db.execute(select(Subject).where(Subject.branch_id == teacher.branch_id))).scalars().all()}
    my_subs = set(str(a.subject_id) for a in (await db.execute(select(ClassSubject).where(ClassSubject.teacher_id == teacher.id))).scalars().all())
    return {"subjects": [{"exam_subject_id": str(es.id), "subject_name": subjects.get(es.subject_id, "?"), "max_marks": es.max_marks, "subject_id": str(es.subject_id)} for es in es_list if str(es.subject_id) in my_subs]}


@router.get("/marks-entry")
@require_role(UserRole.TEACHER)
async def marks_entry(request: Request, exam_subject_id: str, class_id: str, section_id: str, db: AsyncSession = Depends(get_db)):
    students = (await db.execute(select(Student).where(Student.class_id == uuid.UUID(class_id), Student.section_id == uuid.UUID(section_id), Student.is_active == True).order_by(Student.roll_number, Student.first_name))).scalars().all()
    result = []
    for s in students:
        m = (await db.execute(select(ExamMarks).where(ExamMarks.exam_subject_id == uuid.UUID(exam_subject_id), ExamMarks.student_id == s.id))).scalar_one_or_none()
        result.append({"id": str(s.id), "name": s.full_name, "roll": s.roll_number, "marks": m.marks_obtained if m and not m.is_absent else None, "is_absent": m.is_absent if m else False, "grade": m.grade if m else ""})
    return {"students": result}


@router.post("/save-marks")
@require_role(UserRole.TEACHER)
async def save_marks(request: Request, db: AsyncSession = Depends(get_db)):
    teacher, _ = await get_teacher(request, db)
    if not teacher: return {"error": "Not found"}
    data = await request.json()
    esid = uuid.UUID(data["exam_subject_id"])
    es = (await db.execute(select(ExamSubject).where(ExamSubject.id == esid))).scalar_one_or_none()
    if not es: return {"error": "Not found"}
    def grade(m, mx):
        if m is None: return ""
        p = m/mx*100 if mx>0 else 0
        return "A+" if p>=90 else "A" if p>=80 else "B+" if p>=70 else "B" if p>=60 else "C" if p>=50 else "D" if p>=35 else "F"
    for r in data["records"]:
        sid = uuid.UUID(r["student_id"])
        existing = (await db.execute(select(ExamMarks).where(ExamMarks.exam_subject_id == esid, ExamMarks.student_id == sid))).scalar_one_or_none()
        if existing:
            existing.marks_obtained = r["marks"] if not r.get("is_absent") else 0
            existing.is_absent = r.get("is_absent", False)
            existing.grade = grade(r["marks"], es.max_marks) if not r.get("is_absent") else "AB"
        else:
            db.add(ExamMarks(exam_subject_id=esid, student_id=sid, marks_obtained=r["marks"] if not r.get("is_absent") else 0, is_absent=r.get("is_absent", False), grade=grade(r["marks"], es.max_marks) if not r.get("is_absent") else "AB"))
    await db.commit()
    return {"status": "saved"}


@router.get("/my-homework")
@require_role(UserRole.TEACHER)
async def my_homework_list(request: Request, class_id: str = None, status: str = None, db: AsyncSession = Depends(get_db)):
    teacher, _ = await get_teacher(request, db)
    if not teacher: return {"homework": []}
    q = select(Homework).where(Homework.teacher_id == teacher.id)
    if class_id: q = q.where(Homework.class_id == uuid.UUID(class_id))
    hws = (await db.execute(q.order_by(Homework.due_date.desc()))).scalars().all()
    subjects = {s.id: s.name for s in (await db.execute(select(Subject).where(Subject.branch_id == teacher.branch_id))).scalars().all()}
    classes = {c.id: c.name for c in (await db.execute(select(Class).where(Class.branch_id == teacher.branch_id))).scalars().all()}
    sections = {s.id: s.name for s in (await db.execute(select(Section).where(Section.branch_id == teacher.branch_id))).scalars().all()}
    today = date_cls.today()
    result = []
    for h in hws:
        if status == 'active' and h.due_date < today: continue
        if status == 'past' and h.due_date >= today: continue
        total = await db.scalar(select(func.count(Student.id)).where(Student.class_id == h.class_id, Student.is_active == True)) or 0
        submitted = await db.scalar(select(func.count(HomeworkSubmission.id)).where(HomeworkSubmission.homework_id == h.id)) or 0
        result.append({"id": str(h.id), "title": h.title, "description": h.description or "", "subject": subjects.get(h.subject_id, "?"), "class_name": classes.get(h.class_id, "?"), "section_name": sections.get(h.section_id, "") if h.section_id else "", "due_date": h.due_date.isoformat(), "total_students": total, "submitted": submitted})
    return {"homework": result}


@router.post("/create-homework")
@require_role(UserRole.TEACHER)
async def create_hw(request: Request, db: AsyncSession = Depends(get_db)):
    teacher, _ = await get_teacher(request, db)
    if not teacher: return {"error": "Not found"}
    data = await request.json()
    hw = Homework(title=data["title"], description=data.get("description", ""), class_id=uuid.UUID(data["class_id"]), section_id=uuid.UUID(data["section_id"]) if data.get("section_id") else None, subject_id=uuid.UUID(data["subject_id"]), teacher_id=teacher.id, branch_id=teacher.branch_id, due_date=date_cls.fromisoformat(data["due_date"]), max_marks=data.get("max_marks"))
    db.add(hw)
    await db.commit()
    return {"status": "created", "id": str(hw.id)}


@router.get("/diary-history")
@require_role(UserRole.TEACHER)
async def diary_history(request: Request, class_id: str, section_id: str = None, db: AsyncSession = Depends(get_db)):
    teacher, _ = await get_teacher(request, db)
    if not teacher: return {"entries": []}
    q = select(DailyDiary).where(DailyDiary.teacher_id == teacher.id, DailyDiary.class_id == uuid.UUID(class_id)).order_by(DailyDiary.entry_date.desc(), DailyDiary.created_at.desc()).limit(30)
    entries = (await db.execute(q)).scalars().all()
    sids = list(set(e.student_id for e in entries if e.student_id))
    smap = {s.id: s.full_name for s in (await db.execute(select(Student).where(Student.id.in_(sids)))).scalars().all()} if sids else {}
    return {"entries": [{"id": str(e.id), "entry_date": e.entry_date.isoformat(), "entry_type": e.entry_type, "content": e.content, "student_name": smap.get(e.student_id, "Entire Class") if e.student_id else "Entire Class", "is_visible_to_parent": e.is_visible_to_parent, "parent_acknowledged": e.parent_acknowledged} for e in entries]}


@router.get("/messages")
@require_role(UserRole.TEACHER)
async def teacher_messages(request: Request, db: AsyncSession = Depends(get_db)):
    """Get teacher's message threads."""
    teacher, _ = await get_teacher(request, db)
    if not teacher:
        return {"threads": []}
    # For now return empty — will be populated when messages are sent
    return {"threads": []}