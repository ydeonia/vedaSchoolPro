from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from database import get_db
from models.user import UserRole
from models.student import Student
from models.academic import AcademicYear, Class, Section, Subject
from utils.permissions import require_role
import uuid

router = APIRouter(prefix="/student")
templates = Jinja2Templates(directory="templates")


async def get_student_profile(request, db):
    """Get the Student record linked to the logged-in user"""
    user = request.state.user
    user_id = uuid.UUID(user["user_id"])
    result = await db.execute(
        select(Student).where(Student.user_id == user_id, Student.is_active == True)
        .options(selectinload(Student.class_), selectinload(Student.section))
    )
    student = result.scalar_one_or_none()
    if not student:
        return None, user
    return student, user


@router.get("/dashboard", response_class=HTMLResponse)
@require_role(UserRole.STUDENT)
async def student_dashboard(request: Request, db: AsyncSession = Depends(get_db)):
    student, user = await get_student_profile(request, db)
    if not student:
        return templates.TemplateResponse("student/no_profile.html", {
            "request": request, "user": user, "active_page": "dashboard"
        })

    from datetime import date, datetime
    from models.attendance import Attendance
    from models.fee import FeeRecord, PaymentStatus
    from models.notification import Announcement
    today = date.today()

    # Attendance stats
    total_days = await db.scalar(
        select(func.count(func.distinct(Attendance.date)))
        .where(Attendance.student_id == student.id)) or 0
    present_days = await db.scalar(
        select(func.count(func.distinct(Attendance.date)))
        .where(Attendance.student_id == student.id, Attendance.status == 'present')) or 0
    att_pct = round((present_days / total_days * 100) if total_days > 0 else 0)

    # Today's attendance
    today_att = await db.execute(
        select(Attendance).where(Attendance.student_id == student.id, Attendance.date == today))
    today_status = today_att.scalar_one_or_none()

    # Fee status
    pending_fees = await db.scalar(
        select(func.sum(FeeRecord.amount_due - FeeRecord.amount_paid - FeeRecord.discount))
        .where(FeeRecord.student_id == student.id,
               FeeRecord.status.in_([PaymentStatus.PENDING, PaymentStatus.PARTIAL, PaymentStatus.OVERDUE]))) or 0

    # Announcements
    ann_result = await db.execute(
        select(Announcement).where(
            Announcement.branch_id == student.branch_id, Announcement.is_active == True,
            (Announcement.target_role.in_(['all', 'student'])) | (Announcement.target_class_id == student.class_id)
        ).order_by(Announcement.is_pinned.desc(), Announcement.created_at.desc()).limit(5))
    announcements = ann_result.scalars().all()

    # Today's timetable
    today_timetable = []
    try:
        from models.timetable import TimetableSlot, PeriodDefinition, ClassScheduleAssignment
        day_names = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
        today_day = day_names[today.weekday()]

        assignment_result = await db.execute(
            select(ClassScheduleAssignment).where(
                ClassScheduleAssignment.class_id == student.class_id,
                ClassScheduleAssignment.is_active == True,
                ClassScheduleAssignment.day_of_week == None,
            ))
        assignment = assignment_result.scalar_one_or_none()

        if assignment:
            periods_result = await db.execute(
                select(PeriodDefinition).where(
                    PeriodDefinition.template_id == assignment.template_id,
                    PeriodDefinition.is_active == True
                ).order_by(PeriodDefinition.period_number))
        else:
            periods_result = await db.execute(
                select(PeriodDefinition).where(
                    PeriodDefinition.branch_id == student.branch_id,
                    PeriodDefinition.is_active == True
                ).order_by(PeriodDefinition.period_number))
        periods = periods_result.scalars().all()

        slots_result = await db.execute(
            select(TimetableSlot).where(
                TimetableSlot.class_id == student.class_id,
                TimetableSlot.section_id == student.section_id,
                TimetableSlot.day_of_week == today_day,
            ).options(selectinload(TimetableSlot.subject), selectinload(TimetableSlot.teacher)))
        slots = slots_result.scalars().all()
        slots_map = {str(s.period_id): s for s in slots}

        for p in periods:
            slot = slots_map.get(str(p.id))
            if slot and slot.subject:
                today_timetable.append({
                    "period": p.period_number,
                    "label": p.label or f"Period {p.period_number}",
                    "start": p.start_time.strftime("%I:%M %p") if p.start_time else "",
                    "end": p.end_time.strftime("%I:%M %p") if p.end_time else "",
                    "subject": slot.subject.name if slot.subject else "Free",
                    "teacher": slot.teacher.full_name if slot.teacher else "",
                    "room": slot.room or "",
                    "type": p.period_type.value if p.period_type else "class",
                })
    except Exception:
        today_timetable = []

    # Pending homework (top 5) — with subject names
    pending_homework = []
    try:
        from models.homework import Homework
        hw_result = await db.execute(
            select(Homework).where(
                Homework.class_id == student.class_id,
                Homework.is_active == True,
                Homework.due_date >= today,
            ).order_by(Homework.due_date.asc()).limit(5))
        hw_list = hw_result.scalars().all()

        # Fetch subject names for homework
        hw_subject_ids = list({h.subject_id for h in hw_list if h.subject_id})
        hw_subject_map = {}
        if hw_subject_ids:
            sn_result = await db.execute(select(Subject).where(Subject.id.in_(hw_subject_ids)))
            hw_subject_map = {s.id: s.name for s in sn_result.scalars().all()}

        # Attach subject_name to each homework (as simple dict)
        for h in hw_list:
            h._subject_name = hw_subject_map.get(h.subject_id, "—")
        pending_homework = hw_list
    except Exception:
        pending_homework = []

    # Student's subjects via ClassSubject
    subjects_list = []
    try:
        from models.academic import ClassSubject
        cs_result = await db.execute(
            select(ClassSubject).where(ClassSubject.class_id == student.class_id)
            .options(selectinload(ClassSubject.subject)))
        class_subjects = cs_result.scalars().all()
        subjects_list = [cs.subject for cs in class_subjects if cs.subject and cs.subject.is_active]
    except Exception:
        subjects_list = []

    # Upcoming online classes (next 3)
    upcoming_online = []
    try:
        from models.online_class import OnlineClass, OnlineClassStatus
        from sqlalchemy import or_
        oc_query = select(OnlineClass).where(
            OnlineClass.branch_id == student.branch_id,
            OnlineClass.class_id == student.class_id,
            OnlineClass.scheduled_date >= today,
            OnlineClass.status == OnlineClassStatus.SCHEDULED,
            OnlineClass.is_active == True,
        )
        if student.section_id:
            oc_query = oc_query.where(
                or_(OnlineClass.section_id == student.section_id, OnlineClass.section_id == None)
            )
        oc_query = oc_query.order_by(OnlineClass.scheduled_date, OnlineClass.start_time).limit(3)
        upcoming_online = (await db.execute(oc_query)).scalars().all()
    except Exception:
        upcoming_online = []

    return templates.TemplateResponse("student/dashboard.html", {
        "request": request, "user": user, "active_page": "dashboard",
        "student": student,
        "att_pct": att_pct, "present_days": present_days, "total_days": total_days,
        "today_status": today_status.status if today_status else None,
        "pending_fees": round(pending_fees),
        "announcements": announcements,
        "today_timetable": today_timetable,
        "pending_homework": pending_homework,
        "subjects": subjects_list,
        "today": today,
        "upcoming_online": upcoming_online,
    })


@router.get("/attendance", response_class=HTMLResponse)
@require_role(UserRole.STUDENT)
async def student_attendance(request: Request, db: AsyncSession = Depends(get_db)):
    student, user = await get_student_profile(request, db)
    if not student:
        return templates.TemplateResponse("student/no_profile.html", {
            "request": request, "user": user, "active_page": "attendance"})

    from models.attendance import Attendance
    from datetime import date
    import json

    # Get all attendance records
    records = await db.execute(
        select(Attendance).where(Attendance.student_id == student.id)
        .order_by(Attendance.date.desc()))
    all_records = records.scalars().all()

    total = len(all_records)
    present = sum(1 for r in all_records if r.status == 'present')
    absent = sum(1 for r in all_records if r.status == 'absent')
    late = sum(1 for r in all_records if r.status == 'late')
    att_pct = round((present / total * 100) if total > 0 else 0)

    # Calendar data
    cal_data = {}
    for r in all_records:
        cal_data[r.date.isoformat()] = r.status

    return templates.TemplateResponse("student/attendance.html", {
        "request": request, "user": user, "active_page": "attendance",
        "student": student,
        "total": total, "present": present, "absent": absent, "late": late, "att_pct": att_pct,
        "cal_data": json.dumps(cal_data),
    })


@router.get("/results", response_class=HTMLResponse)
@require_role(UserRole.STUDENT)
async def student_results(request: Request, db: AsyncSession = Depends(get_db)):
    student, user = await get_student_profile(request, db)
    if not student:
        return templates.TemplateResponse("student/no_profile.html", {
            "request": request, "user": user, "active_page": "results"})

    from models.exam import Exam, ExamSubject, Marks
    import json

    # Get published exams
    exams_result = await db.execute(
        select(Exam).where(Exam.branch_id == student.branch_id, Exam.is_published == True)
        .order_by(Exam.start_date.desc()))
    exams = exams_result.scalars().all()

    exam_results = []
    for exam in exams:
        # Get subjects for this exam and student's class
        subj_result = await db.execute(
            select(ExamSubject).where(
                ExamSubject.exam_id == exam.id, ExamSubject.class_id == student.class_id)
        )
        subjects = subj_result.scalars().all()

        if not subjects:
            continue

        # Fetch subject names
        from models.academic import Subject as SubjectModel
        es_subj_ids = [es.subject_id for es in subjects]
        subj_names = {}
        if es_subj_ids:
            sn_result = await db.execute(select(SubjectModel).where(SubjectModel.id.in_(es_subj_ids)))
            subj_names = {s.id: s.name for s in sn_result.scalars().all()}
            continue

        # Get marks
        subj_ids = [s.id for s in subjects]
        marks_result = await db.execute(
            select(Marks).where(Marks.student_id == student.id, Marks.exam_subject_id.in_(subj_ids)))
        marks_map = {m.exam_subject_id: m for m in marks_result.scalars().all()}

        subject_marks = []
        total_obtained = 0
        total_max = 0
        all_pass = True

        for es in subjects:
            m = marks_map.get(es.id)
            obtained = m.marks_obtained if m and not m.is_absent else 0
            subject_marks.append({
                "name": subj_names.get(es.subject_id, "?"),
                "max": es.max_marks, "passing": es.passing_marks,
                "obtained": obtained,
                "grade": m.grade if m else "",
                "absent": m.is_absent if m else False,
                "passed": obtained >= es.passing_marks if m and not m.is_absent else False,
            })
            total_obtained += obtained
            total_max += es.max_marks
            if m and not m.is_absent and obtained < es.passing_marks:
                all_pass = False

        pct = round((total_obtained / total_max * 100) if total_max > 0 else 0)
        exam_results.append({
            "name": exam.name, "id": str(exam.id),
            "subjects": subject_marks,
            "total": total_obtained, "max": total_max,
            "pct": pct, "passed": all_pass,
        })

    return templates.TemplateResponse("student/results.html", {
        "request": request, "user": user, "active_page": "results",
        "student": student, "exam_results": exam_results,
    })


@router.get("/fees", response_class=HTMLResponse)
@require_role(UserRole.STUDENT)
async def student_fees(request: Request, db: AsyncSession = Depends(get_db)):
    student, user = await get_student_profile(request, db)
    if not student:
        return templates.TemplateResponse("student/no_profile.html", {
            "request": request, "user": user, "active_page": "fees"})

    from models.fee import FeeRecord
    records = await db.execute(
        select(FeeRecord).where(FeeRecord.student_id == student.id)
        .options(selectinload(FeeRecord.fee_structure))
        .order_by(FeeRecord.due_date.desc()))
    fees = records.scalars().all()

    total_due = sum(f.amount_due for f in fees)
    total_paid = sum(f.amount_paid for f in fees)
    total_discount = sum(f.discount for f in fees)
    balance = total_due - total_paid - total_discount

    return templates.TemplateResponse("student/fees.html", {
        "request": request, "user": user, "active_page": "fees",
        "student": student, "fees": fees,
        "total_due": round(total_due), "total_paid": round(total_paid),
        "total_discount": round(total_discount), "balance": round(balance),
    })


@router.get("/timetable", response_class=HTMLResponse)
@require_role(UserRole.STUDENT)
async def student_timetable(request: Request, db: AsyncSession = Depends(get_db)):
    student, user = await get_student_profile(request, db)
    if not student:
        return templates.TemplateResponse("student/no_profile.html", {
            "request": request, "user": user, "active_page": "timetable"})

    from models.timetable import TimetableSlot, PeriodDefinition, DayOfWeek, ClassScheduleAssignment
    import json

    # Resolve periods from class's assigned bell schedule template (or fall back to all)
    assignment_result = await db.execute(
        select(ClassScheduleAssignment).where(
            ClassScheduleAssignment.class_id == student.class_id,
            ClassScheduleAssignment.is_active == True,
            ClassScheduleAssignment.day_of_week == None,
        )
    )
    assignment = assignment_result.scalar_one_or_none()

    if assignment:
        periods_result = await db.execute(
            select(PeriodDefinition).where(
                PeriodDefinition.template_id == assignment.template_id,
                PeriodDefinition.is_active == True
            ).order_by(PeriodDefinition.period_number))
    else:
        periods_result = await db.execute(
            select(PeriodDefinition).where(
                PeriodDefinition.branch_id == student.branch_id,
                PeriodDefinition.is_active == True
            ).order_by(PeriodDefinition.period_number))
    periods = periods_result.scalars().all()

    # Load timetable slots
    slots_result = await db.execute(
        select(TimetableSlot).where(
            TimetableSlot.class_id == student.class_id,
            TimetableSlot.section_id == student.section_id
        ).options(selectinload(TimetableSlot.subject), selectinload(TimetableSlot.teacher)))
    slots = slots_result.scalars().all()

    timetable = {}
    for s in slots:
        day = s.day_of_week.value
        if day not in timetable:
            timetable[day] = {}
        timetable[day][str(s.period_id)] = {
            "subject": s.subject.name if s.subject else "?",
            "teacher": s.teacher.full_name if s.teacher else "",
            "room": s.room or "",
        }

    # Serialize periods for JSON
    periods_serialized = [
        {"id": str(p.id), "number": p.period_number, "label": p.label,
         "start": p.start_time.strftime("%H:%M") if p.start_time else "",
         "end": p.end_time.strftime("%H:%M") if p.end_time else "",
         "type": p.period_type.value}
        for p in periods
    ]

    return templates.TemplateResponse("student/timetable.html", {
        "request": request, "user": user, "active_page": "timetable",
        "student": student, "periods": periods_serialized,
        "timetable_json": json.dumps(timetable),
    })


@router.get("/announcements", response_class=HTMLResponse)
@require_role(UserRole.STUDENT)
async def student_announcements(request: Request, db: AsyncSession = Depends(get_db)):
    student, user = await get_student_profile(request, db)
    if not student:
        return templates.TemplateResponse("student/no_profile.html", {
            "request": request, "user": user, "active_page": "announcements"})

    from models.notification import Announcement
    ann_result = await db.execute(
        select(Announcement).where(
            Announcement.branch_id == student.branch_id, Announcement.is_active == True,
            (Announcement.target_role.in_(['all', 'student'])) | (Announcement.target_class_id == student.class_id)
        ).order_by(Announcement.is_pinned.desc(), Announcement.created_at.desc()).limit(30))
    announcements = ann_result.scalars().all()

    return templates.TemplateResponse("student/announcements.html", {
        "request": request, "user": user, "active_page": "announcements",
        "student": student, "announcements": announcements,
    })


# ─── Student PDF Downloads ──────────────────────────
from fastapi.responses import StreamingResponse
from io import BytesIO

@router.get("/fees/receipt-pdf/{record_id}")
@require_role(UserRole.STUDENT)
async def student_fee_receipt_pdf(record_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    student, user = await get_student_profile(request, db)
    if not student:
        raise HTTPException(404, "Profile not found")

    from models.fee import FeeRecord
    from models.branch import Branch, PaymentGatewayConfig as PGC
    from utils.pdf_generator import generate_fee_receipt_pdf

    rec = (await db.execute(
        select(FeeRecord).where(FeeRecord.id == uuid.UUID(record_id), FeeRecord.student_id == student.id)
        .options(selectinload(FeeRecord.fee_structure))
    )).scalar_one_or_none()
    if not rec:
        raise HTTPException(404, "Fee record not found")

    branch = (await db.execute(select(Branch).where(Branch.id == student.branch_id))).scalar_one_or_none()
    school_name = branch.name if branch else "School"
    pgc = (await db.execute(select(PGC).where(PGC.branch_id == student.branch_id))).scalar_one_or_none()

    receipt_data = {
        "receipt_number": rec.receipt_number or "N/A",
        "date": rec.payment_date.strftime('%d %b %Y') if rec.payment_date else "",
        "student_name": student.full_name,
        "class_name": student.class_.name if student.class_ else "",
        "roll_number": student.roll_number or "",
        "admission_number": student.admission_number or "",
        "father_name": student.father_name or "",
        "fee_name": rec.fee_structure.fee_name if rec.fee_structure else "Fee",
        "amount_due": rec.amount_due, "amount_paid": rec.amount_paid,
        "discount": rec.discount, "balance": rec.amount_due - rec.amount_paid - rec.discount,
        "payment_mode": rec.payment_mode.value if rec.payment_mode else "cash",
        "transaction_id": rec.transaction_id or "",
        "upi_id": pgc.upi_id if pgc and pgc.show_upi_on_invoice else None,
        "bank_details": f"{pgc.bank_name} | A/C: {pgc.account_number} | IFSC: {pgc.ifsc_code}" if pgc and pgc.show_bank_on_invoice and pgc.account_number else None,
    }

    pdf_bytes = generate_fee_receipt_pdf(school_name, receipt_data)
    return StreamingResponse(
        BytesIO(pdf_bytes), media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=receipt_{rec.receipt_number or 'fee'}.pdf"}
    )


@router.get("/results/report-card-pdf")
@require_role(UserRole.STUDENT)
async def student_report_card_pdf(request: Request, db: AsyncSession = Depends(get_db)):
    student, user = await get_student_profile(request, db)
    if not student:
        raise HTTPException(404, "Profile not found")

    from models.exam import Exam, ExamSubject, Marks
    from models.branch import Branch
    from utils.pdf_generator import generate_report_card_pdf

    branch = (await db.execute(select(Branch).where(Branch.id == student.branch_id))).scalar_one_or_none()
    school_name = branch.name if branch else "School"

    from models.academic import AcademicYear, Subject
    ay = (await db.execute(select(AcademicYear).where(
        AcademicYear.branch_id == student.branch_id, AcademicYear.is_current == True))).scalar_one_or_none()

    exams = (await db.execute(
        select(Exam).where(Exam.branch_id == student.branch_id, Exam.is_published == True)
        .order_by(Exam.start_date))).scalars().all()

    exam_results = []
    for exam in exams:
        subjects = (await db.execute(
            select(ExamSubject).where(ExamSubject.exam_id == exam.id, ExamSubject.class_id == student.class_id)
        )).scalars().all()
        if not subjects:
            continue

        # Fetch subject names for this batch
        _sids = [es.subject_id for es in subjects]
        _snames = {}
        if _sids:
            _sr = await db.execute(select(Subject).where(Subject.id.in_(_sids)))
            _snames = {s.id: s.name for s in _sr.scalars().all()}

        subj_list = []
        total_obt = 0
        total_max = 0
        all_pass = True
        for es in subjects:
            m = (await db.execute(select(Marks).where(
                Marks.exam_subject_id == es.id, Marks.student_id == student.id))).scalar_one_or_none()
            obt = m.marks_obtained if m and not m.is_absent else 0
            passed = obt >= es.passing_marks if m and not m.is_absent else False
            subj_list.append({
                "name": _snames.get(es.subject_id, "?"),
                "max": es.max_marks, "obtained": obt,
                "grade": m.grade if m else "", "passed": passed,
                "absent": m.is_absent if m else False,
            })
            total_obt += obt
            total_max += es.max_marks
            if m and not m.is_absent and not passed:
                all_pass = False

        exam_results.append({
            "exam_name": exam.name, "subjects": subj_list,
            "total": total_obt, "max": total_max,
            "pct": round((total_obt / total_max * 100) if total_max > 0 else 0),
            "passed": all_pass,
        })

    student_data = {
        "name": student.full_name,
        "class_name": student.class_.name if student.class_ else "",
        "section": student.section.name if student.section else "",
        "roll": student.roll_number or "",
        "admission": student.admission_number or "",
        "father_name": student.father_name or "",
        "academic_year": ay.label if ay else "",
    }

    pdf_bytes = generate_report_card_pdf(school_name, student_data, exam_results)
    return StreamingResponse(
        BytesIO(pdf_bytes), media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=report_card_{student.first_name}.pdf"}
    )

# ─── NEW STUDENT PAGES ──────────────────────────────

@router.get("/homework", response_class=HTMLResponse)
@require_role(UserRole.STUDENT)
async def student_homework(request: Request, db: AsyncSession = Depends(get_db)):
    student, user = await get_student_profile(request, db)
    if not student:
        return templates.TemplateResponse("student/no_profile.html", {
            "request": request, "user": user, "active_page": "homework"})

    from models.mega_modules import Homework
    homework = (await db.execute(
        select(Homework).where(
            Homework.class_id == student.class_id,
            Homework.is_active == True
        ).order_by(Homework.due_date.desc()).limit(30)
    )).scalars().all()

    from datetime import date as date_cls
    return templates.TemplateResponse("student/homework.html", {
        "request": request, "user": user, "active_page": "homework",
        "student": student, "homework": homework, "today": date_cls.today(),
    })


@router.get("/syllabus", response_class=HTMLResponse)
@require_role(UserRole.STUDENT)
async def student_syllabus(request: Request, db: AsyncSession = Depends(get_db)):
    student, user = await get_student_profile(request, db)
    if not student:
        return templates.TemplateResponse("student/no_profile.html", {
            "request": request, "user": user, "active_page": "syllabus"})

    from models.syllabus import Syllabus
    chapters = (await db.execute(
        select(Syllabus).where(
            Syllabus.branch_id == student.branch_id,
            Syllabus.class_id == student.class_id
        ).order_by(Syllabus.subject_id, Syllabus.chapter_number)
    )).scalars().all()

    # Group by subject
    from models.academic import Subject
    subject_ids = list({c.subject_id for c in chapters})
    subjects_map = {}
    if subject_ids:
        subs = (await db.execute(select(Subject).where(Subject.id.in_(subject_ids)))).scalars().all()
        subjects_map = {s.id: s.name for s in subs}

    syllabus = {}
    for ch in chapters:
        sname = subjects_map.get(ch.subject_id, "Unknown")
        if sname not in syllabus:
            syllabus[sname] = []
        syllabus[sname].append(ch)

    return templates.TemplateResponse("student/syllabus.html", {
        "request": request, "user": user, "active_page": "syllabus",
        "student": student, "syllabus": syllabus,
    })


@router.get("/subjects", response_class=HTMLResponse)
@require_role(UserRole.STUDENT)
async def student_subjects(request: Request, db: AsyncSession = Depends(get_db)):
    student, user = await get_student_profile(request, db)
    if not student:
        return templates.TemplateResponse("student/no_profile.html", {
            "request": request, "user": user, "active_page": "subjects"})

    from models.academic import ClassSubject, Subject
    from models.teacher import Teacher
    cs_result = await db.execute(
        select(ClassSubject).where(ClassSubject.class_id == student.class_id)
    )
    class_subjects = cs_result.scalars().all()

    subject_ids = [cs.subject_id for cs in class_subjects]
    teacher_ids = [cs.teacher_id for cs in class_subjects if cs.teacher_id]

    subjects_map = {}
    if subject_ids:
        subs = (await db.execute(select(Subject).where(Subject.id.in_(subject_ids)))).scalars().all()
        subjects_map = {s.id: s for s in subs}
    teachers_map = {}
    if teacher_ids:
        ts = (await db.execute(select(Teacher).where(Teacher.id.in_(teacher_ids)))).scalars().all()
        teachers_map = {t.id: t for t in ts}

    my_subjects = []
    for cs in class_subjects:
        subj = subjects_map.get(cs.subject_id)
        teacher = teachers_map.get(cs.teacher_id) if cs.teacher_id else None
        if subj:
            my_subjects.append({
                "name": subj.name, "code": subj.code or "",
                "teacher": teacher.full_name if teacher else "—",
                "teacher_phone": teacher.phone if teacher else "",
            })

    return templates.TemplateResponse("student/subjects.html", {
        "request": request, "user": user, "active_page": "subjects",
        "student": student, "subjects": my_subjects,
    })


@router.get("/datesheet", response_class=HTMLResponse)
@require_role(UserRole.STUDENT)
async def student_datesheet(request: Request, db: AsyncSession = Depends(get_db)):
    student, user = await get_student_profile(request, db)
    if not student:
        return templates.TemplateResponse("student/no_profile.html", {
            "request": request, "user": user, "active_page": "datesheet"})

    from models.exam import Exam, ExamSubject
    from models.academic import Subject
    exams = (await db.execute(
        select(Exam).where(Exam.branch_id == student.branch_id)
        .order_by(Exam.start_date.desc())
    )).scalars().all()

    datesheets = []
    for exam in exams:
        es_list = (await db.execute(
            select(ExamSubject).where(
                ExamSubject.exam_id == exam.id, ExamSubject.class_id == student.class_id
            ).order_by(ExamSubject.exam_date)
        )).scalars().all()
        if not es_list:
            continue
        subj_ids = [e.subject_id for e in es_list]
        subs = (await db.execute(select(Subject).where(Subject.id.in_(subj_ids)))).scalars().all()
        smap = {s.id: s.name for s in subs}
        papers = [{"subject": smap.get(e.subject_id, "?"), "date": e.exam_date,
                   "time": e.exam_time or "", "max_marks": e.max_marks} for e in es_list]
        datesheets.append({"exam": exam, "papers": papers})

    return templates.TemplateResponse("student/datesheet.html", {
        "request": request, "user": user, "active_page": "datesheet",
        "student": student, "datesheets": datesheets,
    })


@router.get("/report-card", response_class=HTMLResponse)
@require_role(UserRole.STUDENT)
async def student_report_card_page(request: Request, db: AsyncSession = Depends(get_db)):
    student, user = await get_student_profile(request, db)
    if not student:
        return templates.TemplateResponse("student/no_profile.html", {
            "request": request, "user": user, "active_page": "report_card"})

    # Use the new Report Card View page (API-driven)
    return templates.TemplateResponse("student/report_card_view.html", {
        "request": request, "user": user, "active_page": "report_card",
        "student": student,
    })


@router.get("/library", response_class=HTMLResponse)
@require_role(UserRole.STUDENT)
async def student_library(request: Request, db: AsyncSession = Depends(get_db)):
    student, user = await get_student_profile(request, db)
    if not student:
        return templates.TemplateResponse("student/no_profile.html", {
            "request": request, "user": user, "active_page": "library"})
    from models.mega_modules import Book
    books = (await db.execute(
        select(Book).where(Book.branch_id == student.branch_id, Book.is_active == True)
        .order_by(Book.title).limit(50)
    )).scalars().all()
    return templates.TemplateResponse("student/library.html", {
        "request": request, "user": user, "active_page": "library",
        "student": student, "books": books,
    })


@router.get("/transport", response_class=HTMLResponse)
@require_role(UserRole.STUDENT)
async def student_transport(request: Request, db: AsyncSession = Depends(get_db)):
    student, user = await get_student_profile(request, db)
    if not student:
        return templates.TemplateResponse("student/no_profile.html", {
            "request": request, "user": user, "active_page": "transport"})
    from models.mega_modules import StudentTransport, TransportRoute, RouteStop
    assignment = (await db.execute(
        select(StudentTransport).where(StudentTransport.student_id == student.id, StudentTransport.is_active == True)
    )).scalar_one_or_none()
    route = None
    stops = []
    if assignment:
        route = (await db.execute(select(TransportRoute).where(TransportRoute.id == assignment.route_id))).scalar_one_or_none()
        if route:
            stops = (await db.execute(
                select(RouteStop).where(RouteStop.route_id == route.id).order_by(RouteStop.stop_order)
            )).scalars().all()
    return templates.TemplateResponse("student/transport.html", {
        "request": request, "user": user, "active_page": "transport",
        "student": student, "assignment": assignment, "route": route, "stops": stops,
    })


@router.get("/id-card", response_class=HTMLResponse)
@require_role(UserRole.STUDENT)
async def student_id_card(request: Request, db: AsyncSession = Depends(get_db)):
    student, user = await get_student_profile(request, db)
    if not student:
        return templates.TemplateResponse("student/no_profile.html", {
            "request": request, "user": user, "active_page": "id_card"})
    from models.branch import Branch
    branch = (await db.execute(select(Branch).where(Branch.id == student.branch_id))).scalar_one_or_none()
    return templates.TemplateResponse("student/id_card.html", {
        "request": request, "user": user, "active_page": "id_card",
        "student": student, "branch": branch,
    })


@router.get("/analytics", response_class=HTMLResponse)
@require_role(UserRole.STUDENT)
async def student_analytics_page(request: Request, db: AsyncSession = Depends(get_db)):
    student, user = await get_student_profile(request, db)
    if not student:
        return templates.TemplateResponse("student/no_profile.html", {
            "request": request, "user": user, "active_page": "analytics"})
    return templates.TemplateResponse("student/analytics.html", {
        "request": request, "user": user, "active_page": "analytics",
        "student": student,
    })


# ═══════════════════════════════════════════════════════════
# SPRINT 21: Event Calendar, Leave, My Profile
# ═══════════════════════════════════════════════════════════

@router.get("/calendar", response_class=HTMLResponse)
@require_role(UserRole.STUDENT)
async def student_calendar(request: Request, db: AsyncSession = Depends(get_db)):
    student, user = await get_student_profile(request, db)
    if not student:
        return templates.TemplateResponse("student/no_profile.html", {
            "request": request, "user": user, "active_page": "calendar"})
    return templates.TemplateResponse("student/calendar.html", {
        "request": request, "user": user, "active_page": "calendar",
        "student": student,
    })


@router.get("/online-classes", response_class=HTMLResponse)
@require_role(UserRole.STUDENT)
async def student_online_classes(request: Request, db: AsyncSession = Depends(get_db)):
    student, user = await get_student_profile(request, db)
    if not student:
        return templates.TemplateResponse("student/no_profile.html", {
            "request": request, "user": user, "active_page": "online_classes"})
    return templates.TemplateResponse("student/online_classes.html", {
        "request": request, "user": user, "active_page": "online_classes",
        "student": student,
    })


@router.get("/leave", response_class=HTMLResponse)
@require_role(UserRole.STUDENT)
async def student_leave(request: Request, db: AsyncSession = Depends(get_db)):
    student, user = await get_student_profile(request, db)
    if not student:
        return templates.TemplateResponse("student/no_profile.html", {
            "request": request, "user": user, "active_page": "leave"})
    return templates.TemplateResponse("student/leave.html", {
        "request": request, "user": user, "active_page": "leave",
        "student": student,
    })


@router.get("/my-profile", response_class=HTMLResponse)
@require_role(UserRole.STUDENT)
async def student_my_profile(request: Request, db: AsyncSession = Depends(get_db)):
    student, user = await get_student_profile(request, db)
    if not student:
        return templates.TemplateResponse("student/no_profile.html", {
            "request": request, "user": user, "active_page": "my_profile"})
    from sqlalchemy.orm import selectinload
    # Re-fetch with relationships for template
    student = (await db.execute(
        select(Student).where(Student.id == student.id)
        .options(selectinload(Student.class_), selectinload(Student.section))
    )).scalar_one_or_none()
    return templates.TemplateResponse("student/my_profile.html", {
        "request": request, "user": user, "active_page": "my_profile",
        "student": student,
    })


# ═══ Complaints & Messages (transferred from parent module — PO v3.0) ═══

@router.get("/complaints", response_class=HTMLResponse)
@require_role(UserRole.STUDENT)
async def student_complaints(request: Request, db: AsyncSession = Depends(get_db)):
    student, user = await get_student_profile(request, db)
    if not student:
        return templates.TemplateResponse("student/no_profile.html", {
            "request": request, "user": user, "active_page": "complaints"})
    try:
        from models.messaging import Complaint
        complaints = (await db.execute(
            select(Complaint).where(Complaint.submitted_by == uuid.UUID(user["user_id"]))
            .order_by(Complaint.created_at.desc())
        )).scalars().all()
    except Exception:
        complaints = []

    return templates.TemplateResponse("student/student_complaints.html", {
        "request": request, "user": user, "active_page": "complaints",
        "student": student, "complaints": complaints,
    })


@router.get("/messages", response_class=HTMLResponse)
@require_role(UserRole.STUDENT)
async def student_messages(request: Request, db: AsyncSession = Depends(get_db)):
    student, user = await get_student_profile(request, db)
    if not student:
        return templates.TemplateResponse("student/no_profile.html", {
            "request": request, "user": user, "active_page": "messages"})
    try:
        from models.messaging import MessageThread
        threads = (await db.execute(
            select(MessageThread).where(
                MessageThread.parent_id == uuid.UUID(user["user_id"])
            ).options(selectinload(MessageThread.messages))
            .order_by(MessageThread.updated_at.desc())
        )).scalars().all()
    except Exception:
        threads = []

    return templates.TemplateResponse("student/student_messages.html", {
        "request": request, "user": user, "active_page": "messages",
        "student": student, "threads": threads,
    })