"""Analytics API — Drill-down data for charts, graphs, and real-time dashboards"""
from fastapi import APIRouter, Request, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, case, extract, and_
from database import get_db
from models.user import UserRole
from utils.permissions import require_role
from datetime import date, datetime, timedelta
import uuid, calendar

router = APIRouter(prefix="/api/school/analytics")


async def get_branch(request):
    return uuid.UUID(request.state.user["branch_id"])


# ═══════════════════════════════════════════════════════════
# ATTENDANCE ANALYTICS
# ═══════════════════════════════════════════════════════════
@router.get("/attendance/daily-trend")
@require_role(UserRole.SCHOOL_ADMIN)
async def attendance_daily_trend(request: Request, days: int = 30, db: AsyncSession = Depends(get_db)):
    """Last N days attendance trend — line chart data"""
    branch_id = await get_branch(request)
    from models.attendance import Attendance
    from models.student import Student

    total_students = await db.scalar(
        select(func.count()).select_from(Student).where(Student.branch_id == branch_id, Student.is_active == True)) or 1

    start = date.today() - timedelta(days=days)
    rows = (await db.execute(
        select(
            Attendance.date,
            func.count(func.distinct(case((Attendance.status == 'present', Attendance.student_id)))).label('present'),
            func.count(func.distinct(Attendance.student_id)).label('total'),
        ).where(Attendance.date >= start)
        .group_by(Attendance.date)
        .order_by(Attendance.date)
    )).all()

    labels = []
    present_data = []
    absent_data = []
    pct_data = []
    for r in rows:
        labels.append(r.date.strftime('%d %b'))
        present_data.append(r.present)
        absent_data.append(r.total - r.present)
        pct_data.append(round(r.present / r.total * 100) if r.total > 0 else 0)

    return {"labels": labels, "present": present_data, "absent": absent_data,
            "percentage": pct_data, "total_students": total_students}


@router.get("/attendance/class-wise")
@require_role(UserRole.SCHOOL_ADMIN)
async def attendance_class_wise(request: Request, db: AsyncSession = Depends(get_db)):
    """Today's attendance by class — bar chart"""
    branch_id = await get_branch(request)
    from models.attendance import Attendance
    from models.student import Student
    from models.academic import Class

    today = date.today()
    classes = (await db.execute(
        select(Class).where(Class.branch_id == branch_id, Class.is_active == True).order_by(Class.name)
    )).scalars().all()

    labels = []
    present = []
    absent = []
    total = []
    for cls in classes:
        students = await db.scalar(
            select(func.count()).select_from(Student).where(Student.class_id == cls.id, Student.is_active == True)) or 0
        p = await db.scalar(
            select(func.count(func.distinct(Attendance.student_id))).where(
                Attendance.date == today, Attendance.status == 'present',
                Attendance.student_id.in_(select(Student.id).where(Student.class_id == cls.id))
            )) or 0
        labels.append(cls.name)
        present.append(p)
        absent.append(students - p)
        total.append(students)

    return {"labels": labels, "present": present, "absent": absent, "total": total}


@router.get("/attendance/monthly-heatmap")
@require_role(UserRole.SCHOOL_ADMIN)
async def attendance_monthly_heatmap(request: Request, month: int = 0, year: int = 0, db: AsyncSession = Depends(get_db)):
    """Monthly attendance heatmap — percentage per day"""
    if not month: month = date.today().month
    if not year: year = date.today().year
    from models.attendance import Attendance
    from models.student import Student
    branch_id = await get_branch(request)

    total_students = await db.scalar(
        select(func.count()).select_from(Student).where(Student.branch_id == branch_id, Student.is_active == True)) or 1

    days_in_month = calendar.monthrange(year, month)[1]
    heatmap = []
    for d in range(1, days_in_month + 1):
        dt = date(year, month, d)
        if dt.weekday() == 6:  # Sunday
            heatmap.append({"day": d, "pct": -1, "label": "Sunday"})
            continue
        count = await db.scalar(
            select(func.count(func.distinct(Attendance.student_id))).where(
                Attendance.date == dt, Attendance.status == 'present')) or 0
        marked = await db.scalar(
            select(func.count(func.distinct(Attendance.student_id))).where(Attendance.date == dt)) or 0
        pct = round(count / marked * 100) if marked > 0 else 0
        heatmap.append({"day": d, "pct": pct, "present": count, "total": marked})

    return {"month": month, "year": year, "days": heatmap}


# ═══════════════════════════════════════════════════════════
# FEE ANALYTICS
# ═══════════════════════════════════════════════════════════
@router.get("/fees/collection-trend")
@require_role(UserRole.SCHOOL_ADMIN)
async def fee_collection_trend(request: Request, months: int = 6, db: AsyncSession = Depends(get_db)):
    """Monthly fee collection trend — bar chart"""
    branch_id = await get_branch(request)
    from models.fee import FeeRecord

    labels = []
    collected = []
    pending = []
    today = date.today()
    for i in range(months - 1, -1, -1):
        m = today.month - i
        y = today.year
        while m <= 0: m += 12; y -= 1

        month_name = calendar.month_abbr[m]
        labels.append(f"{month_name} {y}")

        c = await db.scalar(
            select(func.sum(FeeRecord.amount_paid)).where(
                FeeRecord.branch_id == branch_id,
                extract('month', FeeRecord.payment_date) == m,
                extract('year', FeeRecord.payment_date) == y
            )) or 0
        collected.append(float(c))

    total_pending = await db.scalar(
        select(func.sum(FeeRecord.amount_due - FeeRecord.amount_paid - FeeRecord.discount)).where(
            FeeRecord.branch_id == branch_id,
            FeeRecord.status.in_(['pending', 'partial', 'overdue'])
        )) or 0

    total_collected = await db.scalar(
        select(func.sum(FeeRecord.amount_paid)).where(FeeRecord.branch_id == branch_id)) or 0

    return {"labels": labels, "collected": collected,
            "total_pending": float(total_pending), "total_collected": float(total_collected)}


@router.get("/fees/class-wise-dues")
@require_role(UserRole.SCHOOL_ADMIN)
async def fee_class_wise(request: Request, db: AsyncSession = Depends(get_db)):
    """Fee dues by class — horizontal bar chart"""
    branch_id = await get_branch(request)
    from models.fee import FeeRecord
    from models.student import Student
    from models.academic import Class

    classes = (await db.execute(
        select(Class).where(Class.branch_id == branch_id, Class.is_active == True).order_by(Class.name)
    )).scalars().all()

    labels = []
    dues = []
    paid = []
    for cls in classes:
        student_ids = (await db.execute(
            select(Student.id).where(Student.class_id == cls.id, Student.is_active == True)
        )).scalars().all()
        if not student_ids:
            continue
        d = await db.scalar(
            select(func.sum(FeeRecord.amount_due - FeeRecord.amount_paid - FeeRecord.discount)).where(
                FeeRecord.student_id.in_(student_ids),
                FeeRecord.status.in_(['pending', 'partial', 'overdue'])
            )) or 0
        p = await db.scalar(
            select(func.sum(FeeRecord.amount_paid)).where(FeeRecord.student_id.in_(student_ids))) or 0
        labels.append(cls.name)
        dues.append(float(d))
        paid.append(float(p))

    return {"labels": labels, "dues": dues, "paid": paid}


@router.get("/fees/payment-mode-split")
@require_role(UserRole.SCHOOL_ADMIN)
async def fee_payment_modes(request: Request, db: AsyncSession = Depends(get_db)):
    """Payment mode distribution — doughnut chart"""
    branch_id = await get_branch(request)
    from models.fee import FeeRecord

    modes = ['cash', 'upi', 'bank_transfer', 'cheque', 'razorpay', 'phonepe']
    labels = []
    values = []
    for mode in modes:
        amt = await db.scalar(
            select(func.sum(FeeRecord.amount_paid)).where(
                FeeRecord.branch_id == branch_id, FeeRecord.payment_mode == mode
            )) or 0
        if float(amt) > 0:
            labels.append(mode.replace('_', ' ').title())
            values.append(float(amt))

    # Group remaining as "Other"
    total = await db.scalar(
        select(func.sum(FeeRecord.amount_paid)).where(FeeRecord.branch_id == branch_id)) or 0
    accounted = sum(values)
    if float(total) - accounted > 0:
        labels.append("Other")
        values.append(float(total) - accounted)

    return {"labels": labels, "values": values}


# ═══════════════════════════════════════════════════════════
# EXAM / ACADEMIC ANALYTICS
# ═══════════════════════════════════════════════════════════
@router.get("/exams/performance-trend")
@require_role(UserRole.SCHOOL_ADMIN)
async def exam_performance_trend(request: Request, db: AsyncSession = Depends(get_db)):
    """Average percentage across exams — line chart"""
    branch_id = await get_branch(request)
    from models.exam import Exam, ExamSubject, Marks

    exams = (await db.execute(
        select(Exam).where(Exam.branch_id == branch_id, Exam.is_published == True)
        .order_by(Exam.start_date)
    )).scalars().all()

    labels = []
    averages = []
    pass_rates = []
    for exam in exams:
        subjects = (await db.execute(select(ExamSubject).where(ExamSubject.exam_id == exam.id))).scalars().all()
        if not subjects: continue

        total_pct = 0
        total_count = 0
        passed = 0
        for es in subjects:
            marks = (await db.execute(select(Marks).where(Marks.exam_subject_id == es.id))).scalars().all()
            for m in marks:
                if not m.is_absent and es.max_marks > 0:
                    pct = m.marks_obtained / es.max_marks * 100
                    total_pct += pct
                    total_count += 1
                    if pct >= 33: passed += 1

        avg = round(total_pct / total_count) if total_count > 0 else 0
        pr = round(passed / total_count * 100) if total_count > 0 else 0
        labels.append(exam.name[:15])
        averages.append(avg)
        pass_rates.append(pr)

    return {"labels": labels, "averages": averages, "pass_rates": pass_rates}


@router.get("/exams/subject-wise")
@require_role(UserRole.SCHOOL_ADMIN)
async def exam_subject_analysis(request: Request, exam_id: str = "", db: AsyncSession = Depends(get_db)):
    """Subject-wise performance for an exam — radar chart"""
    branch_id = await get_branch(request)
    from models.exam import Exam, ExamSubject, Marks
    from models.academic import Subject

    if not exam_id:
        exam = (await db.execute(
            select(Exam).where(Exam.branch_id == branch_id, Exam.is_published == True)
            .order_by(Exam.start_date.desc()).limit(1)
        )).scalar_one_or_none()
        if not exam: return {"labels": [], "averages": [], "pass_rates": []}
        exam_id = str(exam.id)

    subjects_data = (await db.execute(
        select(ExamSubject).where(ExamSubject.exam_id == uuid.UUID(exam_id))
    )).scalars().all()

    labels = []
    averages = []
    pass_rates = []
    for es in subjects_data:
        subj = (await db.execute(select(Subject).where(Subject.id == es.subject_id))).scalar_one_or_none()
        marks = (await db.execute(select(Marks).where(Marks.exam_subject_id == es.id))).scalars().all()

        total_pct = 0
        count = 0
        passed = 0
        for m in marks:
            if not m.is_absent and es.max_marks > 0:
                pct = m.marks_obtained / es.max_marks * 100
                total_pct += pct
                count += 1
                if pct >= 33: passed += 1

        labels.append(subj.name[:12] if subj else "?")
        averages.append(round(total_pct / count) if count > 0 else 0)
        pass_rates.append(round(passed / count * 100) if count > 0 else 0)

    return {"labels": labels, "averages": averages, "pass_rates": pass_rates}


# ═══════════════════════════════════════════════════════════
# OVERVIEW STATS (Real-time)
# ═══════════════════════════════════════════════════════════
@router.get("/overview")
@require_role(UserRole.SCHOOL_ADMIN)
async def overview_stats(request: Request, db: AsyncSession = Depends(get_db)):
    """Complete overview — all key metrics in one call"""
    branch_id = await get_branch(request)
    from models.student import Student
    from models.teacher import Teacher
    from models.attendance import Attendance
    from models.fee import FeeRecord
    from models.academic import Class
    from models.mega_modules import Employee, Admission, Book, Vehicle

    today = date.today()

    students = await db.scalar(select(func.count()).select_from(Student).where(Student.branch_id == branch_id, Student.is_active == True)) or 0
    teachers = await db.scalar(select(func.count()).select_from(Teacher).where(Teacher.branch_id == branch_id, Teacher.is_active == True)) or 0
    classes = await db.scalar(select(func.count()).select_from(Class).where(Class.branch_id == branch_id, Class.is_active == True)) or 0
    employees = await db.scalar(select(func.count()).select_from(Employee).where(Employee.branch_id == branch_id, Employee.is_active == True)) or 0

    # Attendance today
    present_today = await db.scalar(
        select(func.count(func.distinct(Attendance.student_id))).where(
            Attendance.date == today, Attendance.status == 'present')) or 0
    marked_today = await db.scalar(
        select(func.count(func.distinct(Attendance.student_id))).where(Attendance.date == today)) or 0

    # Fees
    total_collected = await db.scalar(
        select(func.sum(FeeRecord.amount_paid)).where(FeeRecord.branch_id == branch_id)) or 0
    total_pending = await db.scalar(
        select(func.sum(FeeRecord.amount_due - FeeRecord.amount_paid - FeeRecord.discount)).where(
            FeeRecord.branch_id == branch_id,
            FeeRecord.status.in_(['pending', 'partial', 'overdue']))) or 0
    collected_today = await db.scalar(
        select(func.sum(FeeRecord.amount_paid)).where(
            FeeRecord.branch_id == branch_id, FeeRecord.payment_date == today)) or 0

    # New admissions
    new_admissions = await db.scalar(
        select(func.count()).select_from(Admission).where(
            Admission.branch_id == branch_id, Admission.status.in_(['enquiry', 'application']))) or 0

    # Library
    books = await db.scalar(select(func.count()).select_from(Book).where(Book.branch_id == branch_id, Book.is_active == True)) or 0

    # Transport
    vehicles = await db.scalar(select(func.count()).select_from(Vehicle).where(Vehicle.branch_id == branch_id, Vehicle.is_active == True)) or 0

    return {
        "students": students, "teachers": teachers, "classes": classes, "employees": employees,
        "present_today": present_today, "marked_today": marked_today,
        "attendance_pct": round(present_today / marked_today * 100) if marked_today > 0 else 0,
        "total_collected": float(total_collected), "total_pending": float(total_pending),
        "collected_today": float(collected_today),
        "new_admissions": new_admissions, "books": books, "vehicles": vehicles,
    }