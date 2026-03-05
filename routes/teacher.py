from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from database import get_db
from models.user import UserRole
from models.teacher import Teacher
from models.academic import AcademicYear, Class, Section, Subject
from models.timetable import PeriodDefinition, TimetableSlot, DayOfWeek
from models.period_log import PeriodLog
from models.syllabus import Syllabus
from utils.permissions import require_role
from datetime import date, datetime
import uuid
import json

router = APIRouter(prefix="/teacher")
templates = Jinja2Templates(directory="templates")

DAY_MAP = {
    0: DayOfWeek.MONDAY, 1: DayOfWeek.TUESDAY, 2: DayOfWeek.WEDNESDAY,
    3: DayOfWeek.THURSDAY, 4: DayOfWeek.FRIDAY, 5: DayOfWeek.SATURDAY,
}


async def get_teacher_profile(request: Request, db: AsyncSession):
    """Get the Teacher record linked to current logged-in user"""
    user = request.state.user
    user_id = uuid.UUID(user.get("user_id"))
    result = await db.execute(
        select(Teacher).where(Teacher.user_id == user_id, Teacher.is_active == True)
    )
    teacher = result.scalar_one_or_none()
    return teacher, user


@router.get("/dashboard", response_class=HTMLResponse)
@require_role(UserRole.TEACHER)
async def teacher_dashboard(request: Request, db: AsyncSession = Depends(get_db)):
    teacher, user = await get_teacher_profile(request, db)
    if not teacher:
        return templates.TemplateResponse("teacher/no_profile.html", {
            "request": request, "user": user, "active_page": "dashboard"
        })

    branch_id = teacher.branch_id
    today = date.today()
    weekday = today.weekday()  # 0=Monday

    # Get today's day enum
    today_day = DAY_MAP.get(weekday)
    day_name = today_day.value if today_day else None

    # Get period definitions
    periods_result = await db.execute(
        select(PeriodDefinition)
        .where(PeriodDefinition.branch_id == branch_id, PeriodDefinition.is_active == True)
        .order_by(PeriodDefinition.period_number)
    )
    periods = periods_result.scalars().all()

    # Get today's timetable slots for this teacher
    schedule = []
    if today_day and today_day != DayOfWeek.SATURDAY or today_day == DayOfWeek.SATURDAY:
        slots_result = await db.execute(
            select(TimetableSlot)
            .where(
                TimetableSlot.branch_id == branch_id,
                TimetableSlot.teacher_id == teacher.id,
                TimetableSlot.day_of_week == today_day,
                TimetableSlot.is_active == True,
            )
        )
        slots = slots_result.scalars().all()

        # Get today's period logs
        logs_result = await db.execute(
            select(PeriodLog)
            .where(PeriodLog.teacher_id == teacher.id, PeriodLog.date == today)
        )
        logs = {str(log.period_definition_id): log for log in logs_result.scalars().all()}

        # Map class/subject names
        class_ids = {s.class_id for s in slots}
        subject_ids = {s.subject_id for s in slots if s.subject_id}
        section_ids = {s.section_id for s in slots if s.section_id}

        classes_map = {}
        if class_ids:
            r = await db.execute(select(Class).where(Class.id.in_(class_ids)))
            classes_map = {c.id: c.name for c in r.scalars().all()}

        subjects_map = {}
        if subject_ids:
            r = await db.execute(select(Subject).where(Subject.id.in_(subject_ids)))
            subjects_map = {s.id: s.name for s in r.scalars().all()}

        sections_map = {}
        if section_ids:
            r = await db.execute(select(Section).where(Section.id.in_(section_ids)))
            sections_map = {s.id: s.name for s in r.scalars().all()}

        # Build period-keyed map for slots
        slot_by_period = {s.period_id: s for s in slots}

        for p in periods:
            slot = slot_by_period.get(p.id)
            log = logs.get(str(p.id))
            is_break = p.period_type.value in ('break', 'lunch', 'assembly')

            entry = {
                "period_id": str(p.id),
                "period_number": p.period_number,
                "label": p.label,
                "start": p.start_time.strftime("%H:%M") if p.start_time else "",
                "end": p.end_time.strftime("%H:%M") if p.end_time else "",
                "type": p.period_type.value,
                "is_break": is_break,
                "has_class": slot is not None and not is_break,
                "class_name": classes_map.get(slot.class_id, "") if slot else "",
                "section_name": sections_map.get(slot.section_id, "") if slot and slot.section_id else "",
                "subject_name": subjects_map.get(slot.subject_id, "") if slot and slot.subject_id else "",
                "room": slot.room if slot else "",
                "class_id": str(slot.class_id) if slot else "",
                "section_id": str(slot.section_id) if slot and slot.section_id else "",
                "subject_id": str(slot.subject_id) if slot and slot.subject_id else "",
                "slot_id": str(slot.id) if slot else "",
                "completed": log is not None,
                "topic_covered": log.topic_covered if log else "",
                "log_id": str(log.id) if log else "",
            }
            schedule.append(entry)

    # Check for substitution assignments today
    substitutions = []
    try:
        from models.timetable import Substitution
        sub_result = await db.execute(
            select(Substitution).where(
                Substitution.substitute_teacher_id == teacher.id,
                Substitution.date == today,
                Substitution.status.in_(["pending", "accepted"]),
            )
        )
        subs = sub_result.scalars().all()
        for sub in subs:
            # Get the slot details
            slot_r = await db.execute(select(TimetableSlot).where(TimetableSlot.id == sub.timetable_slot_id))
            slot_obj = slot_r.scalar_one_or_none()
            if slot_obj:
                cls_name = classes_map.get(slot_obj.class_id, "") if slot_obj.class_id in classes_map else ""
                if not cls_name and slot_obj.class_id:
                    cr = await db.execute(select(Class).where(Class.id == slot_obj.class_id))
                    c = cr.scalar_one_or_none()
                    cls_name = c.name if c else ""
                sub_name = subjects_map.get(slot_obj.subject_id, "") if slot_obj.subject_id and slot_obj.subject_id in subjects_map else ""
                if not sub_name and slot_obj.subject_id:
                    sr = await db.execute(select(Subject).where(Subject.id == slot_obj.subject_id))
                    s = sr.scalar_one_or_none()
                    sub_name = s.name if s else ""
                # Find the period for timing
                per_r = await db.execute(select(PeriodDefinition).where(PeriodDefinition.id == slot_obj.period_id))
                per_obj = per_r.scalar_one_or_none()
                substitutions.append({
                    "id": str(sub.id),
                    "class_name": cls_name,
                    "subject_name": sub_name,
                    "period_label": per_obj.label if per_obj else "",
                    "period_time": f"{per_obj.start_time.strftime('%H:%M')}-{per_obj.end_time.strftime('%H:%M')}" if per_obj else "",
                    "reason": sub.reason or "",
                    "status": sub.status.value if hasattr(sub.status, 'value') else str(sub.status),
                })
    except Exception:
        pass

    # Stats
    total_assigned = sum(1 for s in schedule if s['has_class'])
    total_completed = sum(1 for s in schedule if s['completed'])
    is_sunday = weekday == 6

    # Week stats
    week_start = today.replace(day=max(1, today.day - weekday))
    week_logs_result = await db.execute(
        select(func.count(PeriodLog.id))
        .where(PeriodLog.teacher_id == teacher.id, PeriodLog.date >= week_start, PeriodLog.date <= today)
    )
    week_completed = week_logs_result.scalar() or 0

    return templates.TemplateResponse("teacher/dashboard.html", {
        "request": request,
        "user": user,
        "teacher": teacher,
        "active_page": "dashboard",
        "today": today,
        "day_name": today_day.value.title() if today_day else "Sunday",
        "is_sunday": is_sunday,
        "schedule": schedule,
        "schedule_json": json.dumps(schedule),
        "total_assigned": total_assigned,
        "total_completed": total_completed,
        "week_completed": week_completed,
        "substitutions": substitutions,
    })


@router.get("/my-timetable", response_class=HTMLResponse)
@require_role(UserRole.TEACHER)
async def teacher_timetable(request: Request, db: AsyncSession = Depends(get_db)):
    teacher, user = await get_teacher_profile(request, db)
    if not teacher:
        return templates.TemplateResponse("teacher/no_profile.html", {
            "request": request, "user": user, "active_page": "my_timetable"
        })

    branch_id = teacher.branch_id

    # Get all periods
    periods_result = await db.execute(
        select(PeriodDefinition)
        .where(PeriodDefinition.branch_id == branch_id, PeriodDefinition.is_active == True)
        .order_by(PeriodDefinition.period_number)
    )
    periods = periods_result.scalars().all()

    # Get all slots for this teacher
    slots_result = await db.execute(
        select(TimetableSlot)
        .where(TimetableSlot.branch_id == branch_id, TimetableSlot.teacher_id == teacher.id, TimetableSlot.is_active == True)
    )
    slots = slots_result.scalars().all()

    # Build name maps
    class_ids = {s.class_id for s in slots}
    subject_ids = {s.subject_id for s in slots if s.subject_id}
    section_ids = {s.section_id for s in slots if s.section_id}

    classes_map, subjects_map, sections_map = {}, {}, {}
    if class_ids:
        r = await db.execute(select(Class).where(Class.id.in_(class_ids)))
        classes_map = {c.id: c.name for c in r.scalars().all()}
    if subject_ids:
        r = await db.execute(select(Subject).where(Subject.id.in_(subject_ids)))
        subjects_map = {s.id: s.name for s in r.scalars().all()}
    if section_ids:
        r = await db.execute(select(Section).where(Section.id.in_(section_ids)))
        sections_map = {s.id: s.name for s in r.scalars().all()}

    # Build timetable grid: {day: {period_id: {...}}}
    timetable = {}
    for slot in slots:
        day = slot.day_of_week.value
        if day not in timetable:
            timetable[day] = {}
        timetable[day][str(slot.period_id)] = {
            "class": classes_map.get(slot.class_id, ""),
            "section": sections_map.get(slot.section_id, "") if slot.section_id else "",
            "subject": subjects_map.get(slot.subject_id, "") if slot.subject_id else "",
            "room": slot.room or "",
        }

    days = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday"]
    total_periods_week = len(slots)

    return templates.TemplateResponse("teacher/my_timetable.html", {
        "request": request,
        "user": user,
        "teacher": teacher,
        "active_page": "my_timetable",
        "periods": periods,
        "timetable": timetable,
        "timetable_json": json.dumps(timetable),
        "days": days,
        "total_periods_week": total_periods_week,
        "today_weekday": date.today().weekday(),
    })


@router.get("/syllabus-progress", response_class=HTMLResponse)
@require_role(UserRole.TEACHER)
async def syllabus_progress(request: Request, db: AsyncSession = Depends(get_db)):
    teacher, user = await get_teacher_profile(request, db)
    if not teacher:
        return templates.TemplateResponse("teacher/no_profile.html", {
            "request": request, "user": user, "active_page": "syllabus"
        })

    branch_id = teacher.branch_id

    # Get subjects this teacher teaches (from timetable)
    slots_result = await db.execute(
        select(TimetableSlot.class_id, TimetableSlot.subject_id)
        .where(TimetableSlot.branch_id == branch_id, TimetableSlot.teacher_id == teacher.id, TimetableSlot.is_active == True)
        .distinct()
    )
    teaching_combos = slots_result.all()

    # Get class/subject names
    class_ids = {c[0] for c in teaching_combos}
    subject_ids = {c[1] for c in teaching_combos if c[1]}

    classes_map, subjects_map = {}, {}
    if class_ids:
        r = await db.execute(select(Class).where(Class.id.in_(class_ids)))
        classes_map = {c.id: c.name for c in r.scalars().all()}
    if subject_ids:
        r = await db.execute(select(Subject).where(Subject.id.in_(subject_ids)))
        subjects_map = {s.id: s.name for s in r.scalars().all()}

    # For each class+subject combo, get syllabus chapters & completion
    progress = []
    for class_id, subject_id in teaching_combos:
        if not subject_id:
            continue
        syl_result = await db.execute(
            select(Syllabus)
            .where(Syllabus.branch_id == branch_id, Syllabus.class_id == class_id, Syllabus.subject_id == subject_id)
            .order_by(Syllabus.chapter_number)
        )
        chapters = syl_result.scalars().all()
        total = len(chapters)
        completed = sum(1 for c in chapters if c.is_completed)
        pct = round(completed / total * 100) if total > 0 else 0

        progress.append({
            "class_id": str(class_id),
            "subject_id": str(subject_id),
            "class_name": classes_map.get(class_id, ""),
            "subject_name": subjects_map.get(subject_id, ""),
            "total_chapters": total,
            "completed_chapters": completed,
            "percentage": pct,
            "chapters": [
                {"id": str(c.id), "number": c.chapter_number or 0, "name": c.chapter_name or c.title,
                 "completed": c.is_completed}
                for c in chapters
            ]
        })

    return templates.TemplateResponse("teacher/syllabus_progress.html", {
        "request": request,
        "user": user,
        "teacher": teacher,
        "active_page": "syllabus",
        "progress": progress,
        "progress_json": json.dumps(progress),
    })


@router.get("/my-attendance", response_class=HTMLResponse)
@require_role(UserRole.TEACHER)
async def my_attendance_page(request: Request, db: AsyncSession = Depends(get_db)):
    teacher, user = await get_teacher_profile(request, db)
    if not teacher:
        return templates.TemplateResponse("teacher/no_profile.html", {
            "request": request, "user": user, "active_page": "my_attendance"
        })

    return templates.TemplateResponse("teacher/my_attendance.html", {
        "request": request, "user": user, "teacher": teacher, "active_page": "my_attendance",
    })


@router.get("/leave", response_class=HTMLResponse)
@require_role(UserRole.TEACHER)
async def leave_page(request: Request, db: AsyncSession = Depends(get_db)):
    teacher, user = await get_teacher_profile(request, db)
    if not teacher:
        return templates.TemplateResponse("teacher/no_profile.html", {
            "request": request, "user": user, "active_page": "leave"
        })

    return templates.TemplateResponse("teacher/leave.html", {
        "request": request, "user": user, "teacher": teacher, "active_page": "leave",
    })


@router.get("/student-feedback", response_class=HTMLResponse)
@require_role(UserRole.TEACHER)
async def student_feedback_page(request: Request, db: AsyncSession = Depends(get_db)):
    """Teacher page to give quick tag-based feedback per student."""
    teacher, user = await get_teacher_profile(request, db)
    if not teacher:
        return templates.TemplateResponse("teacher/no_profile.html", {
            "request": request, "user": user, "active_page": "student_feedback"
        })

    from models.academic import ClassSubject
    from models.student import Student

    # Get classes this teacher teaches
    class_subjects = (await db.execute(
        select(ClassSubject).where(ClassSubject.teacher_id == teacher.id)
    )).scalars().all()
    class_ids = list(set(cs.class_id for cs in class_subjects))

    # Get students from those classes
    students = []
    if class_ids:
        students = (await db.execute(
            select(Student).where(
                Student.class_id.in_(class_ids),
                Student.is_active == True
            ).order_by(Student.first_name)
        )).scalars().all()

    return templates.TemplateResponse("teacher/student_feedback.html", {
        "request": request, "user": user, "teacher": teacher,
        "active_page": "student_feedback", "students": students,
    })


# ═══════════════════════════════════════════════════════════
# SPRINT 23: Teacher Class Management Pages
# ═══════════════════════════════════════════════════════════

@router.get("/attendance", response_class=HTMLResponse)
@require_role(UserRole.TEACHER)
async def mark_attendance_page(request: Request, db: AsyncSession = Depends(get_db)):
    teacher, user = await get_teacher_profile(request, db)
    if not teacher:
        return templates.TemplateResponse("teacher/no_profile.html", {"request": request, "user": user, "active_page": "attendance"})
    from datetime import date
    return templates.TemplateResponse("teacher/mark_attendance.html", {"request": request, "user": user, "teacher": teacher, "active_page": "attendance", "today": date.today().isoformat()})


@router.get("/marks", response_class=HTMLResponse)
@require_role(UserRole.TEACHER)
async def enter_marks_page(request: Request, db: AsyncSession = Depends(get_db)):
    teacher, user = await get_teacher_profile(request, db)
    if not teacher:
        return templates.TemplateResponse("teacher/no_profile.html", {"request": request, "user": user, "active_page": "marks"})
    return templates.TemplateResponse("teacher/enter_marks.html", {"request": request, "user": user, "teacher": teacher, "active_page": "marks"})


@router.get("/homework", response_class=HTMLResponse)
@require_role(UserRole.TEACHER)
async def homework_page(request: Request, db: AsyncSession = Depends(get_db)):
    teacher, user = await get_teacher_profile(request, db)
    if not teacher:
        return templates.TemplateResponse("teacher/no_profile.html", {"request": request, "user": user, "active_page": "homework"})
    return templates.TemplateResponse("teacher/homework.html", {"request": request, "user": user, "teacher": teacher, "active_page": "homework"})


@router.get("/diary", response_class=HTMLResponse)
@require_role(UserRole.TEACHER)
async def diary_page(request: Request, db: AsyncSession = Depends(get_db)):
    teacher, user = await get_teacher_profile(request, db)
    if not teacher:
        return templates.TemplateResponse("teacher/no_profile.html", {"request": request, "user": user, "active_page": "diary"})
    from datetime import date
    return templates.TemplateResponse("teacher/diary.html", {"request": request, "user": user, "teacher": teacher, "active_page": "diary", "today": date.today().isoformat()})


@router.get("/students", response_class=HTMLResponse)
@require_role(UserRole.TEACHER)
async def my_students_page(request: Request, db: AsyncSession = Depends(get_db)):
    teacher, user = await get_teacher_profile(request, db)
    if not teacher:
        return templates.TemplateResponse("teacher/no_profile.html", {"request": request, "user": user, "active_page": "students"})
    return templates.TemplateResponse("teacher/my_students.html", {"request": request, "user": user, "teacher": teacher, "active_page": "students"})


@router.get("/online-classes", response_class=HTMLResponse)
@require_role(UserRole.TEACHER)
async def teacher_online_classes(request: Request, db: AsyncSession = Depends(get_db)):
    teacher, user = await get_teacher_profile(request, db)
    if not teacher:
        return templates.TemplateResponse("teacher/no_profile.html", {"request": request, "user": user, "active_page": "online_classes"})
    return templates.TemplateResponse("teacher/online_classes.html", {"request": request, "user": user, "teacher": teacher, "active_page": "online_classes"})


@router.get("/question-papers", response_class=HTMLResponse)
@require_role(UserRole.TEACHER)
async def question_papers_page(request: Request, db: AsyncSession = Depends(get_db)):
    teacher, user = await get_teacher_profile(request, db)
    if not teacher:
        return templates.TemplateResponse("teacher/no_profile.html", {"request": request, "user": user, "active_page": "question_papers"})
    return templates.TemplateResponse("teacher/question_papers.html", {"request": request, "user": user, "teacher": teacher, "active_page": "question_papers"})


@router.get("/messages", response_class=HTMLResponse)
@require_role(UserRole.TEACHER)
async def messages_page(request: Request, db: AsyncSession = Depends(get_db)):
    teacher, user = await get_teacher_profile(request, db)
    if not teacher:
        return templates.TemplateResponse("teacher/no_profile.html", {"request": request, "user": user, "active_page": "messages"})
    return templates.TemplateResponse("teacher/messages.html", {"request": request, "user": user, "teacher": teacher, "active_page": "messages"})


@router.get("/house-assignment", response_class=HTMLResponse)
@require_role(UserRole.TEACHER)
async def house_assignment_page(request: Request, db: AsyncSession = Depends(get_db)):
    teacher, user = await get_teacher_profile(request, db)
    if not teacher:
        return templates.TemplateResponse("teacher/no_profile.html", {"request": request, "user": user, "active_page": "house_assign"})
    return templates.TemplateResponse("teacher/house_assign_teacher.html", {"request": request, "user": user, "teacher": teacher, "active_page": "house_assign"})


# ═══════════════════════════════════════════════════════════
# REPORT CARD: Teacher Upload Marks & Class Teacher Review
# ═══════════════════════════════════════════════════════════

@router.get("/upload-marks", response_class=HTMLResponse)
@require_role(UserRole.TEACHER)
async def upload_marks_page(request: Request, db: AsyncSession = Depends(get_db)):
    teacher, user = await get_teacher_profile(request, db)
    if not teacher:
        return templates.TemplateResponse("teacher/no_profile.html", {"request": request, "user": user, "active_page": "upload_marks"})
    return templates.TemplateResponse("teacher/upload_marks.html", {"request": request, "user": user, "teacher": teacher, "active_page": "upload_marks"})


@router.get("/class-review", response_class=HTMLResponse)
@require_role(UserRole.TEACHER)
async def class_review_page(request: Request, db: AsyncSession = Depends(get_db)):
    teacher, user = await get_teacher_profile(request, db)
    if not teacher:
        return templates.TemplateResponse("teacher/no_profile.html", {"request": request, "user": user, "active_page": "class_review"})
    return templates.TemplateResponse("teacher/class_teacher_review.html", {"request": request, "user": user, "teacher": teacher, "active_page": "class_review"})