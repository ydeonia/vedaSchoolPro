from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from database import get_db
from models.user import UserRole
from models.academic import AcademicYear, Class, Section, Subject, ClassSubject
from models.student import Student
from models.teacher import Teacher
from models.timetable import PeriodDefinition, TimetableSlot, PeriodType, DayOfWeek
from utils.permissions import get_current_user, require_role, require_auth, require_privilege
import uuid

router = APIRouter(prefix="/school")
templates = Jinja2Templates(directory="templates")


def get_branch_id(request):
    return uuid.UUID(request.state.user.get("branch_id"))


@router.get("/morning-brief", response_class=HTMLResponse)
@require_role(UserRole.SCHOOL_ADMIN)
async def morning_brief_page(request: Request, db: AsyncSession = Depends(get_db)):
    user = request.state.user
    from datetime import date, datetime
    return templates.TemplateResponse("school_admin/morning_brief.html", {
        "request": request, "user": user, "active_page": "morning_brief",
        "today": date.today().strftime("%A, %d %B %Y"),
        "hour": datetime.now().hour,
    })


@router.get("/board-results", response_class=HTMLResponse)
@require_privilege("results")
async def board_results_page(request: Request, db: AsyncSession = Depends(get_db)):
    user = request.state.user
    return templates.TemplateResponse("school_admin/board_results.html", {
        "request": request, "user": user, "active_page": "board_results",
    })


@router.get("/activities", response_class=HTMLResponse)
@require_privilege("activities")
async def activities_page(request: Request, db: AsyncSession = Depends(get_db)):
    user = request.state.user
    return templates.TemplateResponse("school_admin/activities.html", {
        "request": request, "user": user, "active_page": "activities",
    })


@router.get("/teacher-awards", response_class=HTMLResponse)
@require_privilege("teacher_performance")
async def teacher_awards_page(request: Request, db: AsyncSession = Depends(get_db)):
    user = request.state.user
    from datetime import date
    MONTHS = ['','January','February','March','April','May','June','July','August','September','October','November','December']
    return templates.TemplateResponse("school_admin/teacher_awards.html", {
        "request": request, "user": user, "active_page": "teacher_awards",
        "month_name": MONTHS[date.today().month] + " " + str(date.today().year),
    })


@router.get("/dashboard", response_class=HTMLResponse)
@require_role(UserRole.SCHOOL_ADMIN)
async def dashboard(request: Request, db: AsyncSession = Depends(get_db)):
    user = request.state.user
    branch_id = get_branch_id(request)
    from datetime import date, datetime
    from models.attendance import Attendance as StudentAttendance
    from models.teacher_attendance import TeacherAttendance, LeaveRequest
    from models.period_log import PeriodLog
    from models.fee import FeeRecord, PaymentStatus
    from models.exam import Exam
    from models.timetable import TimetableSlot, PeriodDefinition
    import json

    today = date.today()

    # ─── COUNTS ───
    student_count = await db.scalar(
        select(func.count(Student.id)).where(Student.branch_id == branch_id, Student.is_active == True)
    ) or 0
    teacher_count = await db.scalar(
        select(func.count(Teacher.id)).where(Teacher.branch_id == branch_id, Teacher.is_active == True)
    ) or 0
    class_count = await db.scalar(
        select(func.count(Class.id)).where(Class.branch_id == branch_id, Class.is_active == True)
    ) or 0

    # Current academic year
    ay_result = await db.execute(
        select(AcademicYear).where(AcademicYear.branch_id == branch_id, AcademicYear.is_current == True)
    )
    academic_year = ay_result.scalar_one_or_none()

    # ─── LIVE: Student Attendance Today ───
    students_present = await db.scalar(
        select(func.count(func.distinct(StudentAttendance.student_id)))
        .where(StudentAttendance.branch_id == branch_id, StudentAttendance.date == today, StudentAttendance.status == 'present')
    ) or 0
    students_absent = await db.scalar(
        select(func.count(func.distinct(StudentAttendance.student_id)))
        .where(StudentAttendance.branch_id == branch_id, StudentAttendance.date == today, StudentAttendance.status == 'absent')
    ) or 0
    students_marked = students_present + students_absent
    att_pct = round((students_present / students_marked * 100) if students_marked > 0 else 0)

    # ─── LIVE: Teacher Attendance Today ───
    teachers_present = await db.scalar(
        select(func.count(TeacherAttendance.id))
        .where(TeacherAttendance.branch_id == branch_id, TeacherAttendance.date == today,
               TeacherAttendance.status.in_(['present', 'late']))
    ) or 0
    teachers_absent = await db.scalar(
        select(func.count(TeacherAttendance.id))
        .where(TeacherAttendance.branch_id == branch_id, TeacherAttendance.date == today,
               TeacherAttendance.status == 'absent')
    ) or 0
    teachers_on_leave = await db.scalar(
        select(func.count(TeacherAttendance.id))
        .where(TeacherAttendance.branch_id == branch_id, TeacherAttendance.date == today,
               TeacherAttendance.status == 'on_leave')
    ) or 0

    # ─── LIVE: Periods Completed Today ───
    total_slots = await db.scalar(
        select(func.count(TimetableSlot.id)).where(TimetableSlot.branch_id == branch_id)
    ) or 0
    # Approximate today's slots (total / 6 days)
    today_expected = round(total_slots / 6) if total_slots > 0 else 0
    periods_done_today = await db.scalar(
        select(func.count(PeriodLog.id)).where(PeriodLog.date == today, PeriodLog.status == 'completed')
    ) or 0

    # ─── LIVE: Fee Collection ───
    fee_collected_today = await db.scalar(
        select(func.sum(FeeRecord.amount_paid))
        .where(FeeRecord.branch_id == branch_id, FeeRecord.payment_date == today)
    ) or 0
    fee_collected_month = await db.scalar(
        select(func.sum(FeeRecord.amount_paid))
        .where(FeeRecord.branch_id == branch_id,
               func.extract('month', FeeRecord.payment_date) == today.month,
               func.extract('year', FeeRecord.payment_date) == today.year)
    ) or 0
    total_pending = await db.scalar(
        select(func.sum(FeeRecord.amount_due - FeeRecord.amount_paid - FeeRecord.discount))
        .where(FeeRecord.branch_id == branch_id,
               FeeRecord.status.in_([PaymentStatus.PENDING, PaymentStatus.PARTIAL, PaymentStatus.OVERDUE]))
    ) or 0
    total_overdue = await db.scalar(
        select(func.count(func.distinct(FeeRecord.student_id)))
        .where(FeeRecord.branch_id == branch_id, FeeRecord.status == PaymentStatus.OVERDUE)
    ) or 0

    # ─── LIVE: Pending Leaves ───
    pending_leaves = await db.scalar(
        select(func.count(LeaveRequest.id))
        .where(LeaveRequest.status == 'pending')
    ) or 0

    # ─── ALERTS LIST ───
    alerts = []
    if students_marked == 0:
        alerts.append({"type": "warning", "icon": "fa-exclamation-triangle", "text": "Student attendance not marked today", "link": "/school/attendance"})
    if students_absent > 10:
        alerts.append({"type": "danger", "icon": "fa-user-times", "text": f"{students_absent} students absent today", "link": "/school/attendance/reports"})
    if teachers_absent > 0:
        alerts.append({"type": "danger", "icon": "fa-chalkboard-teacher", "text": f"{teachers_absent} teacher(s) absent today", "link": "/school/teacher-attendance"})
    if total_overdue > 0:
        alerts.append({"type": "warning", "icon": "fa-rupee-sign", "text": f"{total_overdue} students have overdue fees", "link": "/school/fee-collection"})
    if pending_leaves > 0:
        alerts.append({"type": "info", "icon": "fa-calendar-minus", "text": f"{pending_leaves} leave request(s) pending approval", "link": "/school/leave-management"})
    if not academic_year:
        alerts.append({"type": "danger", "icon": "fa-calendar", "text": "No academic year set! Configure it now.", "link": "/school/academic-years"})

    # Recent students (keep existing)
    students_result = await db.execute(
        select(Student)
        .where(Student.branch_id == branch_id, Student.is_active == True)
        .options(selectinload(Student.class_), selectinload(Student.section))
        .order_by(Student.created_at.desc()).limit(5)
    )
    recent_students = students_result.scalars().all()

    return templates.TemplateResponse("school_admin/dashboard.html", {
        "request": request, "user": user, "active_page": "dashboard",
        "academic_year": academic_year,
        "stats": {"total_students": student_count, "total_teachers": teacher_count, "total_classes": class_count},
        "live": {
            "students_present": students_present, "students_absent": students_absent,
            "students_marked": students_marked, "att_pct": att_pct,
            "teachers_present": teachers_present, "teachers_absent": teachers_absent,
            "teachers_on_leave": teachers_on_leave,
            "periods_done": periods_done_today, "periods_expected": today_expected,
            "fee_today": round(fee_collected_today), "fee_month": round(fee_collected_month),
            "fee_pending": round(total_pending), "fee_overdue_students": total_overdue,
            "pending_leaves": pending_leaves,
        },
        "alerts": alerts,
        "recent_students": recent_students,
    })


@router.get("/academic-years", response_class=HTMLResponse)
@require_privilege("school_settings")
async def academic_years_page(request: Request, db: AsyncSession = Depends(get_db)):
    user = request.state.user
    branch_id = get_branch_id(request)

    result = await db.execute(
        select(AcademicYear)
        .where(AcademicYear.branch_id == branch_id)
        .order_by(AcademicYear.start_date.desc())
    )
    academic_years = result.scalars().all()

    return templates.TemplateResponse("school_admin/academic_years.html", {
        "request": request,
        "user": user,
        "active_page": "academic_years",
        "academic_years": academic_years,
    })


@router.get("/classes", response_class=HTMLResponse)
@require_privilege("class_management")
async def classes_page(request: Request, db: AsyncSession = Depends(get_db)):
    user = request.state.user
    branch_id = get_branch_id(request)

    result = await db.execute(
        select(Class)
        .where(Class.branch_id == branch_id, Class.is_active == True)
        .options(selectinload(Class.sections), selectinload(Class.students))
        .order_by(Class.numeric_order)
    )
    classes = result.scalars().unique().all()

    return templates.TemplateResponse("school_admin/classes.html", {
        "request": request,
        "user": user,
        "active_page": "classes",
        "classes": classes,
    })


@router.get("/subjects", response_class=HTMLResponse)
@require_privilege("class_management")
async def subjects_page(request: Request, db: AsyncSession = Depends(get_db)):
    user = request.state.user
    branch_id = get_branch_id(request)

    result = await db.execute(
        select(Subject)
        .where(Subject.branch_id == branch_id, Subject.is_active == True)
        .options(selectinload(Subject.class_subjects).selectinload(ClassSubject.class_))
        .order_by(Subject.name)
    )
    subjects = result.scalars().unique().all()

    classes_result = await db.execute(
        select(Class)
        .where(Class.branch_id == branch_id, Class.is_active == True)
        .order_by(Class.numeric_order)
    )
    classes = classes_result.scalars().all()

    return templates.TemplateResponse("school_admin/subjects.html", {
        "request": request,
        "user": user,
        "active_page": "subjects",
        "subjects": subjects,
        "classes": classes,
    })


@router.get("/teachers", response_class=HTMLResponse)
@require_privilege("employee_management")
async def teachers_page(request: Request, db: AsyncSession = Depends(get_db)):
    user = request.state.user
    branch_id = get_branch_id(request)
    action = request.query_params.get("action")

    result = await db.execute(
        select(Teacher)
        .where(Teacher.branch_id == branch_id)
        .order_by(Teacher.created_at.desc())
    )
    teachers = result.scalars().all()

    return templates.TemplateResponse("school_admin/teachers.html", {
        "request": request,
        "user": user,
        "active_page": "teachers",
        "teachers": teachers,
        "action": action,
    })


@router.get("/students", response_class=HTMLResponse)
@require_privilege("student_admission", "student_attendance", "student_documents")
async def students_page(request: Request, db: AsyncSession = Depends(get_db)):
    user = request.state.user
    branch_id = get_branch_id(request)
    action = request.query_params.get("action")
    selected_class = request.query_params.get("class_id", "")

    # Get classes with sections
    classes_result = await db.execute(
        select(Class)
        .where(Class.branch_id == branch_id, Class.is_active == True)
        .options(selectinload(Class.sections))
        .order_by(Class.numeric_order)
    )
    classes = classes_result.scalars().unique().all()

    # Build class-section JSON map for frontend
    import json
    sections_map = {}
    for cls in classes:
        sections_map[str(cls.id)] = [
            {"id": str(sec.id), "name": sec.name}
            for sec in cls.sections if sec.is_active
        ]

    # Get students
    query = select(Student).where(
        Student.branch_id == branch_id, Student.is_active == True
    ).options(
        selectinload(Student.class_), selectinload(Student.section)
    ).order_by(Student.first_name)

    students_result = await db.execute(query)
    students = students_result.scalars().unique().all()

    return templates.TemplateResponse("school_admin/students.html", {
        "request": request,
        "user": user,
        "active_page": "students",
        "students": students,
        "classes": classes,
        "sections_json": json.dumps(sections_map),
        "selected_class": selected_class,
        "action": action,
    })


@router.get("/students/{student_id}", response_class=HTMLResponse)
@require_privilege("student_admission", "student_attendance", "student_documents")
async def student_profile(request: Request, student_id: str, db: AsyncSession = Depends(get_db)):
    user = request.state.user
    # The template loads data via /api/school/students/{id}/profile JS call
    return templates.TemplateResponse("school_admin/student_profile.html", {
        "request": request,
        "user": user,
        "active_page": "students",
        "student_id": student_id,
    })


# ─── ATTENDANCE ──────────────────────────────────────────

@router.get("/attendance", response_class=HTMLResponse)
@require_privilege("student_attendance")
async def attendance_page(request: Request, db: AsyncSession = Depends(get_db)):
    user = request.state.user
    branch_id = get_branch_id(request)

    classes_result = await db.execute(
        select(Class)
        .where(Class.branch_id == branch_id, Class.is_active == True)
        .options(selectinload(Class.sections))
        .order_by(Class.numeric_order)
    )
    classes = classes_result.scalars().unique().all()

    import json
    from datetime import date as date_type, datetime
    sections_map = {}
    for cls in classes:
        sections_map[str(cls.id)] = [
            {"id": str(sec.id), "name": sec.name}
            for sec in cls.sections if sec.is_active
        ]

    today = date_type.today()
    today_display = today.strftime("%A, %d %B %Y")
    selected_class = request.query_params.get("class_id", "")

    return templates.TemplateResponse("school_admin/attendance.html", {
        "request": request,
        "user": user,
        "active_page": "attendance",
        "classes": classes,
        "sections_json": json.dumps(sections_map),
        "today": today.isoformat(),
        "today_display": today_display,
        "selected_class": selected_class,
    })


@router.get("/attendance/reports", response_class=HTMLResponse)
@require_privilege("student_attendance", "reports")
async def attendance_reports_page(request: Request, db: AsyncSession = Depends(get_db)):
    user = request.state.user
    branch_id = get_branch_id(request)

    classes_result = await db.execute(
        select(Class)
        .where(Class.branch_id == branch_id, Class.is_active == True)
        .options(selectinload(Class.sections))
        .order_by(Class.numeric_order)
    )
    classes = classes_result.scalars().unique().all()

    import json
    from datetime import date as date_type
    sections_map = {}
    for cls in classes:
        sections_map[str(cls.id)] = [
            {"id": str(sec.id), "name": sec.name}
            for sec in cls.sections if sec.is_active
        ]

    return templates.TemplateResponse("school_admin/attendance_reports.html", {
        "request": request,
        "user": user,
        "active_page": "attendance_reports",
        "classes": classes,
        "sections_json": json.dumps(sections_map),
        "current_year": date_type.today().year,
    })


# ─── TIMETABLE ─────────────────────────────────────────────
@router.get("/timetable", response_class=HTMLResponse)
@require_privilege("timetable")
async def timetable_page(request: Request, db: AsyncSession = Depends(get_db)):
    user = request.state.user
    branch_id = get_branch_id(request)
    import json

    # Get period definitions
    periods_result = await db.execute(
        select(PeriodDefinition)
        .where(PeriodDefinition.branch_id == branch_id, PeriodDefinition.is_active == True)
        .order_by(PeriodDefinition.period_number)
    )
    periods = periods_result.scalars().all()

    # Get classes with sections
    classes_result = await db.execute(
        select(Class)
        .where(Class.branch_id == branch_id, Class.is_active == True)
        .options(selectinload(Class.sections))
        .order_by(Class.numeric_order)
    )
    classes = classes_result.scalars().unique().all()

    sections_map = {}
    for cls in classes:
        sections_map[str(cls.id)] = [
            {"id": str(sec.id), "name": sec.name}
            for sec in cls.sections if sec.is_active
        ]

    # Get subjects
    subjects_result = await db.execute(
        select(Subject).where(Subject.branch_id == branch_id, Subject.is_active == True).order_by(Subject.name)
    )
    subjects = subjects_result.scalars().all()

    # Get teachers
    teachers_result = await db.execute(
        select(Teacher).where(Teacher.branch_id == branch_id, Teacher.is_active == True).order_by(Teacher.first_name)
    )
    teachers = teachers_result.scalars().all()

    # Build JSON for frontend
    periods_json = [
        {"id": str(p.id), "number": p.period_number, "label": p.label,
         "start": p.start_time.strftime("%H:%M") if p.start_time else "",
         "end": p.end_time.strftime("%H:%M") if p.end_time else "",
         "type": p.period_type.value}
        for p in periods
    ]

    subjects_json = [{"id": str(s.id), "name": s.name, "code": s.code or ""} for s in subjects]
    teachers_json = [{"id": str(t.id), "name": f"{t.first_name} {t.last_name or ''}".strip()} for t in teachers]

    days = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday"]

    return templates.TemplateResponse("school_admin/timetable.html", {
        "request": request,
        "user": user,
        "active_page": "timetable",
        "classes": classes,
        "sections_json": json.dumps(sections_map),
        "periods": periods,
        "periods_json": json.dumps(periods_json),
        "subjects_json": json.dumps(subjects_json),
        "teachers_json": json.dumps(teachers_json),
        "days": days,
    })


# ─── TEACHER PERIOD TRACKING (Principal View) ─────────────
@router.get("/teacher-tracking", response_class=HTMLResponse)
@require_privilege("teacher_attendance")
async def teacher_tracking_page(request: Request, db: AsyncSession = Depends(get_db)):
    user = request.state.user
    branch_id = get_branch_id(request)
    import json
    from models.period_log import PeriodLog
    from models.timetable import TimetableSlot
    from datetime import date as date_type
    from sqlalchemy import func

    today = date_type.today()
    month_start = today.replace(day=1)

    # Get all teachers
    teachers_result = await db.execute(
        select(Teacher).where(Teacher.branch_id == branch_id, Teacher.is_active == True).order_by(Teacher.first_name)
    )
    teachers = teachers_result.scalars().all()

    teacher_stats = []
    for t in teachers:
        # Weekly assigned periods
        assigned_result = await db.execute(
            select(func.count(TimetableSlot.id))
            .where(TimetableSlot.teacher_id == t.id, TimetableSlot.is_active == True)
        )
        weekly_assigned = assigned_result.scalar() or 0

        # Today's completed
        today_result = await db.execute(
            select(func.count(PeriodLog.id))
            .where(PeriodLog.teacher_id == t.id, PeriodLog.date == today)
        )
        today_done = today_result.scalar() or 0

        # Month completed
        month_result = await db.execute(
            select(func.count(PeriodLog.id))
            .where(PeriodLog.teacher_id == t.id, PeriodLog.date >= month_start, PeriodLog.date <= today)
        )
        month_done = month_result.scalar() or 0

        teacher_stats.append({
            "id": str(t.id),
            "name": t.full_name,
            "designation": t.designation or "",
            "weekly_assigned": weekly_assigned,
            "today_done": today_done,
            "month_done": month_done,
        })

    return templates.TemplateResponse("school_admin/teacher_tracking.html", {
        "request": request,
        "user": user,
        "active_page": "teacher_tracking",
        "teacher_stats": teacher_stats,
        "today": today,
    })


# ─── TEACHER ATTENDANCE (Admin Page) ──────────────────────
@router.get("/teacher-attendance", response_class=HTMLResponse)
@require_privilege("teacher_attendance")
async def teacher_attendance_page(request: Request, db: AsyncSession = Depends(get_db)):
    user = request.state.user
    branch_id = get_branch_id(request)

    return templates.TemplateResponse("school_admin/teacher_attendance.html", {
        "request": request,
        "user": user,
        "active_page": "teacher_attendance",
    })


# ─── LEAVE MANAGEMENT (Admin Page) ────────────────────────
@router.get("/leave-management", response_class=HTMLResponse)
@require_privilege("teacher_attendance")
async def leave_management_page(request: Request, db: AsyncSession = Depends(get_db)):
    user = request.state.user
    return templates.TemplateResponse("school_admin/leave_management.html", {
        "request": request,
        "user": user,
        "active_page": "leave_management",
    })


# ─── EXAMS & RESULTS ──────────────────────────────────────
from models.exam import Exam, ExamSubject, Marks

@router.get("/exams", response_class=HTMLResponse)
@require_privilege("exam_management")
async def exams_page(request: Request, db: AsyncSession = Depends(get_db)):
    user = request.state.user
    branch_id = get_branch_id(request)
    import json

    # Get current academic year
    ay_result = await db.execute(
        select(AcademicYear).where(AcademicYear.branch_id == branch_id, AcademicYear.is_current == True)
    )
    academic_year = ay_result.scalar_one_or_none()

    # Get exams
    exams = []
    if academic_year:
        exams_result = await db.execute(
            select(Exam)
            .where(Exam.branch_id == branch_id, Exam.academic_year_id == academic_year.id)
            .options(selectinload(Exam.exam_subjects))
            .order_by(Exam.created_at.desc())
        )
        exams = exams_result.scalars().unique().all()

    # Get classes & subjects
    classes_result = await db.execute(
        select(Class).where(Class.branch_id == branch_id, Class.is_active == True)
        .options(selectinload(Class.sections))
        .order_by(Class.numeric_order)
    )
    classes = classes_result.scalars().unique().all()

    subjects_result = await db.execute(
        select(Subject).where(Subject.branch_id == branch_id, Subject.is_active == True).order_by(Subject.name)
    )
    subjects = subjects_result.scalars().all()

    sections_map = {}
    for cls in classes:
        sections_map[str(cls.id)] = [{"id": str(s.id), "name": s.name} for s in cls.sections if s.is_active]

    return templates.TemplateResponse("school_admin/exams.html", {
        "request": request, "user": user, "active_page": "exams",
        "exams": exams, "academic_year": academic_year,
        "classes": classes, "subjects": subjects,
        "sections_json": json.dumps(sections_map),
        "subjects_json": json.dumps([{"id": str(s.id), "name": s.name} for s in subjects]),
    })


@router.get("/marks-entry", response_class=HTMLResponse)
@require_privilege("exam_management")
async def marks_entry_page(request: Request, db: AsyncSession = Depends(get_db)):
    user = request.state.user
    branch_id = get_branch_id(request)
    import json

    ay_result = await db.execute(
        select(AcademicYear).where(AcademicYear.branch_id == branch_id, AcademicYear.is_current == True)
    )
    academic_year = ay_result.scalar_one_or_none()

    exams = []
    if academic_year:
        exams_result = await db.execute(
            select(Exam).where(Exam.branch_id == branch_id, Exam.academic_year_id == academic_year.id)
            .order_by(Exam.created_at.desc())
        )
        exams = exams_result.scalars().all()

    classes_result = await db.execute(
        select(Class).where(Class.branch_id == branch_id, Class.is_active == True)
        .options(selectinload(Class.sections)).order_by(Class.numeric_order)
    )
    classes = classes_result.scalars().unique().all()

    sections_map = {}
    for cls in classes:
        sections_map[str(cls.id)] = [{"id": str(s.id), "name": s.name} for s in cls.sections if s.is_active]

    return templates.TemplateResponse("school_admin/marks_entry.html", {
        "request": request, "user": user, "active_page": "marks_entry",
        "exams": exams, "classes": classes,
        "sections_json": json.dumps(sections_map),
    })


@router.get("/results", response_class=HTMLResponse)
@require_privilege("results")
async def results_page(request: Request, db: AsyncSession = Depends(get_db)):
    user = request.state.user
    branch_id = get_branch_id(request)
    import json

    ay_result = await db.execute(
        select(AcademicYear).where(AcademicYear.branch_id == branch_id, AcademicYear.is_current == True)
    )
    academic_year = ay_result.scalar_one_or_none()

    exams = []
    if academic_year:
        exams_result = await db.execute(
            select(Exam).where(Exam.branch_id == branch_id, Exam.academic_year_id == academic_year.id)
            .order_by(Exam.created_at.desc())
        )
        exams = exams_result.scalars().all()

    classes_result = await db.execute(
        select(Class).where(Class.branch_id == branch_id, Class.is_active == True)
        .options(selectinload(Class.sections)).order_by(Class.numeric_order)
    )
    classes = classes_result.scalars().unique().all()

    sections_map = {}
    for cls in classes:
        sections_map[str(cls.id)] = [{"id": str(s.id), "name": s.name} for s in cls.sections if s.is_active]

    return templates.TemplateResponse("school_admin/results.html", {
        "request": request, "user": user, "active_page": "results",
        "exams": exams, "classes": classes,
        "sections_json": json.dumps(sections_map),
    })


# ─── FEE MANAGEMENT ───────────────────────────────────────
from models.fee import FeeStructure, FeeRecord
from models.branch import PaymentGatewayConfig

@router.get("/payment-settings", response_class=HTMLResponse)
@require_privilege("fee_structure", "school_settings")
async def payment_settings_page(request: Request, db: AsyncSession = Depends(get_db)):
    user = request.state.user
    branch_id = get_branch_id(request)
    result = await db.execute(select(PaymentGatewayConfig).where(PaymentGatewayConfig.branch_id == branch_id))
    config = result.scalar_one_or_none()
    return templates.TemplateResponse("school_admin/payment_settings.html", {
        "request": request, "user": user, "active_page": "payment_settings", "config": config,
    })

@router.get("/fee-structure", response_class=HTMLResponse)
@require_privilege("fee_structure")
async def fee_structure_page(request: Request, db: AsyncSession = Depends(get_db)):
    user = request.state.user
    branch_id = get_branch_id(request)
    classes_result = await db.execute(
        select(Class).where(Class.branch_id == branch_id, Class.is_active == True).order_by(Class.numeric_order))
    classes = classes_result.scalars().all()
    fees_result = await db.execute(
        select(FeeStructure).where(FeeStructure.branch_id == branch_id, FeeStructure.is_active == True).order_by(FeeStructure.fee_name))
    fees = fees_result.scalars().all()
    return templates.TemplateResponse("school_admin/fee_structure.html", {
        "request": request, "user": user, "active_page": "fee_structure", "classes": classes, "fees": fees,
    })

@router.get("/fee-collection", response_class=HTMLResponse)
@require_privilege("fee_collection")
async def fee_collection_page(request: Request, db: AsyncSession = Depends(get_db)):
    user = request.state.user
    branch_id = get_branch_id(request)
    import json
    classes_result = await db.execute(
        select(Class).where(Class.branch_id == branch_id, Class.is_active == True)
        .options(selectinload(Class.sections)).order_by(Class.numeric_order))
    classes = classes_result.scalars().unique().all()
    sections_map = {}
    for cls in classes:
        sections_map[str(cls.id)] = [{"id": str(s.id), "name": s.name} for s in cls.sections if s.is_active]
    return templates.TemplateResponse("school_admin/fee_collection.html", {
        "request": request, "user": user, "active_page": "fee_collection",
        "classes": classes, "sections_json": json.dumps(sections_map),
    })

# ─── COMMUNICATION SYSTEM ─────────────────────────────────
from models.notification import Announcement, Notification
from models.branch import CommunicationConfig

@router.get("/announcements", response_class=HTMLResponse)
@require_privilege("announcements")
async def announcements_page(request: Request, db: AsyncSession = Depends(get_db)):
    user = request.state.user
    branch_id = get_branch_id(request)
    import json
    classes_result = await db.execute(
        select(Class).where(Class.branch_id == branch_id, Class.is_active == True).order_by(Class.numeric_order))
    classes = classes_result.scalars().all()
    ann_result = await db.execute(
        select(Announcement).where(Announcement.branch_id == branch_id, Announcement.is_active == True)
        .order_by(Announcement.is_pinned.desc(), Announcement.created_at.desc()).limit(50))
    announcements = ann_result.scalars().all()
    return templates.TemplateResponse("school_admin/announcements.html", {
        "request": request, "user": user, "active_page": "announcements",
        "classes": classes, "announcements": announcements,
    })

@router.get("/notifications", response_class=HTMLResponse)
@require_privilege("announcements")
async def notification_center_page(request: Request, db: AsyncSession = Depends(get_db)):
    user = request.state.user
    branch_id = get_branch_id(request)
    notifs_result = await db.execute(
        select(Notification).where(Notification.branch_id == branch_id)
        .order_by(Notification.created_at.desc()).limit(100))
    notifs = notifs_result.scalars().all()
    return templates.TemplateResponse("school_admin/notification_center.html", {
        "request": request, "user": user, "active_page": "notifications", "notifications": notifs,
    })

@router.get("/communication-settings", response_class=HTMLResponse)
@require_privilege("school_settings")
async def comm_settings_page(request: Request, db: AsyncSession = Depends(get_db)):
    user = request.state.user
    branch_id = get_branch_id(request)
    result = await db.execute(select(CommunicationConfig).where(CommunicationConfig.branch_id == branch_id))
    config = result.scalar_one_or_none()
    return templates.TemplateResponse("school_admin/communication_settings.html", {
        "request": request, "user": user, "active_page": "comm_settings", "config": config,
    })


@router.get("/data-export", response_class=HTMLResponse)
@require_privilege("reports")
async def data_export_page(request: Request, db: AsyncSession = Depends(get_db)):
    user = request.state.user
    branch_id = get_branch_id(request)
    from models.exam import Exam
    from datetime import datetime

    classes = (await db.execute(
        select(Class).where(Class.branch_id == branch_id).order_by(Class.name)
    )).scalars().all()
    exams = (await db.execute(
        select(Exam).where(Exam.branch_id == branch_id).order_by(Exam.start_date.desc())
    )).scalars().all()
    students = (await db.execute(
        select(Student).where(Student.branch_id == branch_id, Student.is_active == True)
        .order_by(Student.first_name)
    )).scalars().all()

    return templates.TemplateResponse("school_admin/data_export.html", {
        "request": request, "user": user, "active_page": "data_export",
        "classes": classes, "exams": exams, "students": students,
        "current_month": datetime.now().month, "current_year": datetime.now().year,
    })


@router.get("/signatures", response_class=HTMLResponse)
@require_privilege("school_settings")
async def signatures_page(request: Request, db: AsyncSession = Depends(get_db)):
    user = request.state.user
    return templates.TemplateResponse("school_admin/signatures.html", {
        "request": request, "user": user, "active_page": "signatures",
    })


@router.get("/data-safety", response_class=HTMLResponse)
@require_privilege("school_settings")
async def data_safety_page(request: Request, db: AsyncSession = Depends(get_db)):
    user = request.state.user
    return templates.TemplateResponse("school_admin/data_safety.html", {
        "request": request, "user": user, "active_page": "data_safety",
    })


@router.get("/analytics", response_class=HTMLResponse)
@require_privilege("analytics")
async def analytics_dashboard(request: Request, db: AsyncSession = Depends(get_db)):
    user = request.state.user
    return templates.TemplateResponse("school_admin/analytics.html", {
        "request": request, "user": user, "active_page": "analytics",
    })


@router.get("/student-promotion", response_class=HTMLResponse)
@require_privilege("student_promotion")
async def student_promotion_page(request: Request, db: AsyncSession = Depends(get_db)):
    user = request.state.user
    return templates.TemplateResponse("school_admin/student_promotion.html", {
        "request": request, "user": user, "active_page": "student_promotion",
    })


@router.get("/quizzes", response_class=HTMLResponse)
@require_privilege("activities", "exam_management")
async def quizzes_page(request: Request, db: AsyncSession = Depends(get_db)):
    user = request.state.user
    return templates.TemplateResponse("school_admin/quizzes.html", {
        "request": request, "user": user, "active_page": "quizzes",
    })


@router.get("/accounts", response_class=HTMLResponse)
@require_privilege("accounts_expenses")
async def accounts_page(request: Request, db: AsyncSession = Depends(get_db)):
    user = request.state.user
    return templates.TemplateResponse("school_admin/accounts.html", {
        "request": request, "user": user, "active_page": "accounts",
    })


@router.get("/qr-attendance", response_class=HTMLResponse)
@require_privilege("student_attendance")
async def qr_attendance_page(request: Request, db: AsyncSession = Depends(get_db)):
    user = request.state.user
    return templates.TemplateResponse("school_admin/qr_attendance.html", {
        "request": request, "user": user, "active_page": "qr_attendance",
    })


@router.get("/fee-waivers", response_class=HTMLResponse)
@require_privilege("fee_structure", "fee_collection")
async def fee_waivers_page(request: Request, db: AsyncSession = Depends(get_db)):
    user = request.state.user
    return templates.TemplateResponse("school_admin/fee_waivers.html", {
        "request": request, "user": user, "active_page": "fee_waivers",
    })


@router.get("/hostel", response_class=HTMLResponse)
@require_privilege("hostel")
async def hostel_page(request: Request, db: AsyncSession = Depends(get_db)):
    user = request.state.user
    return templates.TemplateResponse("school_admin/hostel.html", {
        "request": request, "user": user, "active_page": "hostel",
    })


@router.get("/id-card-designer", response_class=HTMLResponse)
@require_privilege("id_cards")
async def id_card_designer_page(request: Request, db: AsyncSession = Depends(get_db)):
    user = request.state.user
    return templates.TemplateResponse("school_admin/id_card_designer.html", {
        "request": request, "user": user, "active_page": "id_card_designer",
    })


@router.get("/houses", response_class=HTMLResponse)
@require_privilege("student_admission", "class_management")
async def houses_page(request: Request, db: AsyncSession = Depends(get_db)):
    user = request.state.user
    return templates.TemplateResponse("school_admin/houses.html", {
        "request": request, "user": user, "active_page": "houses",
    })


@router.get("/digital-library", response_class=HTMLResponse)
@require_privilege("library")
async def digital_library_page(request: Request, db: AsyncSession = Depends(get_db)):
    user = request.state.user
    return templates.TemplateResponse("school_admin/digital_library.html", {
        "request": request, "user": user, "active_page": "digital_library",
    })


@router.get("/admission", response_class=HTMLResponse)
@require_privilege("student_admission")
async def admission_wizard(request: Request, db: AsyncSession = Depends(get_db)):
    return templates.TemplateResponse("school_admin/admission_wizard.html", {
        "request": request, "user": request.state.user, "active_page": "admission",
    })


@router.get("/separation", response_class=HTMLResponse)
@require_privilege("student_promotion")
async def separation_wizard(request: Request, db: AsyncSession = Depends(get_db)):
    user = request.state.user
    branch_name = ""
    branch_address = ""
    logo_url = ""
    principal_sig = ""
    stamp_url = ""
    try:
        branch = await db.scalar(select(Branch).where(Branch.id == uuid.UUID(user.get("branch_id"))))
        if branch:
            branch_name = branch.name or ""
            branch_address = f"{branch.address or ''} {branch.city or ''} {branch.state or ''} {branch.pincode or ''}".strip()
            logo_url = branch.logo_url or ""
            principal_sig = branch.principal_signature_url or ""
            stamp_url = branch.school_stamp_url or ""
    except:
        pass
    return templates.TemplateResponse("school_admin/separation_wizard.html", {
        "request": request, "user": user, "active_page": "separation",
        "branch_name": branch_name, "branch_address": branch_address,
        "logo_url": logo_url, "principal_sig": principal_sig, "stamp_url": stamp_url,
    })


@router.get("/onboarding", response_class=HTMLResponse)
@require_privilege("employee_management")
async def employee_onboarding(request: Request, db: AsyncSession = Depends(get_db)):
    return templates.TemplateResponse("school_admin/employee_onboarding.html", {
        "request": request, "user": request.state.user, "active_page": "onboarding",
    })


@router.get("/staff-privileges", response_class=HTMLResponse)
@require_privilege("manage_staff")
async def staff_privileges(request: Request, db: AsyncSession = Depends(get_db)):
    return templates.TemplateResponse("school_admin/staff_privileges.html", {
        "request": request, "user": request.state.user, "active_page": "staff_privileges",
    })


@router.get("/messages", response_class=HTMLResponse)
@require_privilege("parent_comm", "complaints", "announcements")
async def messages_page(request: Request, db: AsyncSession = Depends(get_db)):
    return templates.TemplateResponse("school_admin/messages.html", {
        "request": request, "user": request.state.user, "active_page": "messages",
    })


# ─── Sprint 26: Donations, Notification Settings, Transactions ───

@router.get("/donations", response_class=HTMLResponse)
@require_privilege("fee_collection", "fee_structure")
async def donations_page(request: Request, db: AsyncSession = Depends(get_db)):
    user = request.state.user
    branch_id = get_branch_id(request)
    return templates.TemplateResponse("school_admin/donations.html", {
        "request": request, "user": user, "active_page": "donations", "branch_id": str(branch_id),
    })


@router.get("/notification-settings", response_class=HTMLResponse)
@require_privilege("school_settings")
async def notification_settings_page(request: Request, db: AsyncSession = Depends(get_db)):
    return templates.TemplateResponse("school_admin/notification_settings.html", {
        "request": request, "user": request.state.user, "active_page": "notification_settings",
    })


@router.get("/transactions", response_class=HTMLResponse)
@require_privilege("fee_collection")
async def transactions_page(request: Request, db: AsyncSession = Depends(get_db)):
    user = request.state.user
    branch_id = get_branch_id(request)
    return templates.TemplateResponse("school_admin/transactions.html", {
        "request": request, "user": user, "active_page": "transactions", "branch_id": str(branch_id),
    })