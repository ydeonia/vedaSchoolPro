"""Student Analytics API — Serves performance data for Chart.js dashboards"""
from fastapi import APIRouter, Request, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from database import get_db
from models.user import UserRole
from models.student import Student
from models.academic import Class, Section, Subject, ClassSubject
from models.attendance import Attendance, AttendanceStatus
from models.exam import Exam, ExamSubject, Marks
from models.fee import FeeRecord, PaymentStatus
from models.teacher import Teacher
from utils.permissions import require_role
from datetime import date, timedelta
import uuid

router = APIRouter(prefix="/api/student")


async def _get_student(request, db):
    user = request.state.user
    uid = uuid.UUID(user["user_id"])
    result = await db.execute(
        select(Student).where(Student.user_id == uid, Student.is_active == True))
    return result.scalar_one_or_none(), user


@router.get("/analytics")
@require_role(UserRole.STUDENT)
async def student_analytics(request: Request, db: AsyncSession = Depends(get_db)):
    student, user = await _get_student(request, db)
    if not student:
        return {"error": "No profile"}

    today = date.today()
    branch_id = student.branch_id
    class_id = student.class_id
    section_id = student.section_id

    # ═══════════════════════════════════════
    # 1. ATTENDANCE ANALYTICS (30-day trend)
    # ═══════════════════════════════════════
    att_records = (await db.execute(
        select(Attendance.date, Attendance.status)
        .where(Attendance.student_id == student.id)
        .order_by(Attendance.date.desc())
    )).all()

    total_days = len(att_records)
    present_days = sum(1 for _, s in att_records if s.value == 'present')
    absent_days = sum(1 for _, s in att_records if s.value == 'absent')
    late_days = sum(1 for _, s in att_records if s.value == 'late')
    att_pct = round((present_days / total_days * 100) if total_days > 0 else 0)

    # 30-day daily trend
    att_trend = []
    for days_ago in range(29, -1, -1):
        d = today - timedelta(days=days_ago)
        if d.weekday() == 6:  # Skip Sunday
            continue
        status = "none"
        for rec_date, rec_status in att_records:
            if rec_date == d:
                status = rec_status.value
                break
        att_trend.append({"date": d.strftime("%d %b"), "status": status,
                          "value": 1 if status == "present" else 0})

    # ═══════════════════════════════════════
    # 2. EXAM PERFORMANCE (subject-wise + class comparison)
    # ═══════════════════════════════════════
    exams = (await db.execute(
        select(Exam).where(Exam.branch_id == branch_id, Exam.is_published == True)
        .order_by(Exam.start_date)
    )).scalars().all()

    # Get all subjects
    all_subjects = (await db.execute(select(Subject).where(Subject.branch_id == branch_id))).scalars().all()
    subj_map = {s.id: s.name for s in all_subjects}

    # Get classmates for comparison
    classmates = (await db.execute(
        select(Student.id).where(
            Student.class_id == class_id, Student.section_id == section_id,
            Student.is_active == True)
    )).scalars().all()
    classmate_ids = list(classmates)
    class_strength = len(classmate_ids)

    exam_analytics = []
    subject_totals = {}  # subject_name -> {my_total, my_max, class_total, class_max, count}
    my_overall_pcts = []  # for trend across exams

    for exam in exams:
        exam_subjects = (await db.execute(
            select(ExamSubject).where(
                ExamSubject.exam_id == exam.id, ExamSubject.class_id == class_id)
        )).scalars().all()

        if not exam_subjects:
            continue

        subjects_data = []
        exam_total_my = 0
        exam_total_max = 0

        for es in exam_subjects:
            sname = subj_map.get(es.subject_id, "?")

            # My marks
            my_mark = (await db.execute(
                select(Marks).where(Marks.exam_subject_id == es.id, Marks.student_id == student.id)
            )).scalar_one_or_none()
            my_obtained = my_mark.marks_obtained if my_mark and not my_mark.is_absent else 0

            # Class average for this subject
            class_avg_result = await db.execute(
                select(func.avg(Marks.marks_obtained))
                .where(Marks.exam_subject_id == es.id, Marks.is_absent == False)
            )
            class_avg = round(float(class_avg_result.scalar() or 0), 1)

            # Class highest
            class_max_result = await db.execute(
                select(func.max(Marks.marks_obtained))
                .where(Marks.exam_subject_id == es.id, Marks.is_absent == False)
            )
            class_highest = float(class_max_result.scalar() or 0)

            # My percentage in this subject
            my_pct = round((my_obtained / es.max_marks * 100) if es.max_marks > 0 else 0)
            avg_pct = round((class_avg / es.max_marks * 100) if es.max_marks > 0 else 0)

            subjects_data.append({
                "subject": sname,
                "my_marks": my_obtained,
                "max_marks": es.max_marks,
                "my_pct": my_pct,
                "class_avg": class_avg,
                "class_avg_pct": avg_pct,
                "class_highest": class_highest,
                "grade": my_mark.grade if my_mark else "",
            })

            exam_total_my += my_obtained
            exam_total_max += es.max_marks

            # Accumulate for radar chart
            if sname not in subject_totals:
                subject_totals[sname] = {"my": 0, "max": 0, "avg": 0, "count": 0}
            subject_totals[sname]["my"] += my_obtained
            subject_totals[sname]["max"] += es.max_marks
            subject_totals[sname]["avg"] += class_avg
            subject_totals[sname]["count"] += 1

        exam_pct = round((exam_total_my / exam_total_max * 100) if exam_total_max > 0 else 0)
        my_overall_pcts.append({"exam": exam.name, "pct": exam_pct})

        # My position (percentile based)
        # Count how many students scored less than me in this exam
        # Use total marks across all subjects
        students_below = 0
        for cid in classmate_ids:
            if cid == student.id:
                continue
            c_total = 0
            for es in exam_subjects:
                cm = (await db.execute(
                    select(Marks.marks_obtained).where(
                        Marks.exam_subject_id == es.id, Marks.student_id == cid, Marks.is_absent == False)
                )).scalar()
                c_total += (cm or 0)
            if c_total < exam_total_my:
                students_below += 1

        percentile = round((students_below / max(class_strength - 1, 1)) * 100)

        exam_analytics.append({
            "exam_name": exam.name,
            "subjects": subjects_data,
            "total": exam_total_my,
            "max": exam_total_max,
            "pct": exam_pct,
            "percentile": percentile,
        })

    # ═══════════════════════════════════════
    # 3. RADAR CHART DATA (average % per subject)
    # ═══════════════════════════════════════
    radar_data = []
    for sname, vals in subject_totals.items():
        my_avg_pct = round((vals["my"] / vals["max"] * 100) if vals["max"] > 0 else 0)
        class_avg_pct = round((vals["avg"] / vals["max"] * 100 * vals["count"]) if vals["max"] > 0 else 0)
        # Fix: class_avg is already averaged per exam, so divide by count
        class_avg_pct = round((vals["avg"] / vals["count"] / (vals["max"] / vals["count"]) * 100) if vals["count"] > 0 and vals["max"] > 0 else 0)
        radar_data.append({
            "subject": sname, "my_pct": my_avg_pct, "class_avg_pct": class_avg_pct
        })

    # ═══════════════════════════════════════
    # 4. CLASS INFO
    # ═══════════════════════════════════════
    class_obj = (await db.execute(select(Class).where(Class.id == class_id))).scalar_one_or_none()
    section_obj = (await db.execute(select(Section).where(Section.id == section_id))).scalar_one_or_none()

    # Subject-teacher mapping
    class_subjects = (await db.execute(
        select(ClassSubject).where(ClassSubject.class_id == class_id)
    )).scalars().all()
    teacher_ids = [cs.teacher_id for cs in class_subjects if cs.teacher_id]
    teachers_map = {}
    if teacher_ids:
        ts = (await db.execute(select(Teacher).where(Teacher.id.in_(teacher_ids)))).scalars().all()
        teachers_map = {t.id: {"name": t.full_name, "designation": t.designation or ""} for t in ts}

    my_teachers = []
    for cs in class_subjects:
        sname = subj_map.get(cs.subject_id, "?")
        t = teachers_map.get(cs.teacher_id, {}) if cs.teacher_id else {}
        my_teachers.append({
            "subject": sname,
            "teacher": t.get("name", "—"),
            "designation": t.get("designation", ""),
        })

    # ═══════════════════════════════════════
    # 5. FEE SUMMARY
    # ═══════════════════════════════════════
    fees = (await db.execute(
        select(FeeRecord).where(FeeRecord.student_id == student.id)
    )).scalars().all()
    total_due = sum(f.amount_due for f in fees)
    total_paid = sum(f.amount_paid for f in fees)
    total_discount = sum(f.discount for f in fees)
    fee_balance = total_due - total_paid - total_discount

    return {
        "student": {
            "name": student.full_name,
            "class": class_obj.name if class_obj else "",
            "section": section_obj.name if section_obj else "",
            "roll": student.roll_number or "",
            "admission": student.admission_number or "",
        },
        "attendance": {
            "total": total_days, "present": present_days, "absent": absent_days,
            "late": late_days, "pct": att_pct, "trend": att_trend,
        },
        "exams": exam_analytics,
        "progress_trend": my_overall_pcts,
        "radar": radar_data,
        "class_info": {
            "strength": class_strength,
            "class_name": class_obj.name if class_obj else "",
            "section_name": section_obj.name if section_obj else "",
            "teachers": my_teachers,
        },
        "fees": {
            "total_due": round(total_due),
            "total_paid": round(total_paid),
            "balance": round(fee_balance),
        },
    }


# ═══════════════════════════════════════════════════════════
# FEE PAYMENT (Razorpay integration)
# ═══════════════════════════════════════════════════════════

@router.post("/fees/create-order")
async def create_fee_order(request: Request, db: AsyncSession = Depends(get_db)):
    """Create Razorpay order for fee payment."""
    from utils.permissions import get_current_user
    user = await get_current_user(request)
    if not user:
        raise HTTPException(401, "Unauthorized")

    data = await request.json()
    amount = data.get("amount", 0)
    if amount <= 0:
        raise HTTPException(400, "Invalid amount")

    # Get student
    student = (await db.execute(
        select(Student).where(Student.user_id == uuid.UUID(user["user_id"]))
    )).scalar_one_or_none()
    if not student:
        raise HTTPException(404, "Student not found")

    # Get payment config
    from models.branch import PaymentGatewayConfig, Branch
    config = (await db.execute(
        select(PaymentGatewayConfig).where(PaymentGatewayConfig.branch_id == student.branch_id)
    )).scalar_one_or_none()

    if not config or not config.razorpay_enabled or not config.razorpay_key_id:
        raise HTTPException(400, "Online payment is not configured for your school. Please pay at the fee counter.")

    branch = await db.scalar(select(Branch).where(Branch.id == student.branch_id))

    # Create Razorpay order
    try:
        import razorpay
        client = razorpay.Client(auth=(config.razorpay_key_id, config.razorpay_key_secret))
        order = client.order.create({
            "amount": int(amount * 100),  # paise
            "currency": "INR",
            "receipt": f"fee_{student.id}_{uuid.uuid4().hex[:8]}",
            "notes": {"student_id": str(student.id), "student_name": student.full_name},
        })
        return {
            "gateway": "razorpay",
            "key_id": config.razorpay_key_id,
            "order_id": order["id"],
            "amount": order["amount"],
            "school_name": branch.name if branch else "School",
            "student_name": student.full_name,
            "email": "",
            "phone": student.father_phone or student.mother_phone or "",
        }
    except ImportError:
        raise HTTPException(400, "Razorpay SDK not installed. Contact school admin.")
    except Exception as e:
        raise HTTPException(400, f"Payment error: {str(e)}")


@router.post("/fees/verify-payment")
async def verify_fee_payment(request: Request, db: AsyncSession = Depends(get_db)):
    """Verify Razorpay payment and mark fees as paid."""
    from utils.permissions import get_current_user
    user = await get_current_user(request)
    if not user:
        raise HTTPException(401, "Unauthorized")

    data = await request.json()
    student = (await db.execute(
        select(Student).where(Student.user_id == uuid.UUID(user["user_id"]))
    )).scalar_one_or_none()
    if not student:
        raise HTTPException(404, "Student not found")

    from models.branch import PaymentGatewayConfig
    config = (await db.execute(
        select(PaymentGatewayConfig).where(PaymentGatewayConfig.branch_id == student.branch_id)
    )).scalar_one_or_none()

    if not config:
        raise HTTPException(400, "Payment config not found")

    # Verify signature
    try:
        import razorpay, hmac, hashlib
        generated_signature = hmac.new(
            config.razorpay_key_secret.encode(),
            f"{data['razorpay_order_id']}|{data['razorpay_payment_id']}".encode(),
            hashlib.sha256
        ).hexdigest()

        if generated_signature != data.get("razorpay_signature"):
            raise HTTPException(400, "Invalid signature")

        # Mark pending fees as paid
        from models.fee import FeeRecord
        pending_fees = (await db.execute(
            select(FeeRecord).where(
                FeeRecord.student_id == student.id,
                FeeRecord.amount_paid < FeeRecord.amount_due
            ).order_by(FeeRecord.due_date)
        )).scalars().all()

        # Get payment amount from Razorpay
        client = razorpay.Client(auth=(config.razorpay_key_id, config.razorpay_key_secret))
        payment = client.payment.fetch(data["razorpay_payment_id"])
        paid_amount = payment["amount"] / 100  # convert from paise

        remaining = paid_amount
        for fee in pending_fees:
            if remaining <= 0:
                break
            due = fee.amount_due - fee.amount_paid - fee.discount
            apply_amount = min(remaining, due)
            fee.amount_paid += apply_amount
            fee.payment_date = date.today()
            fee.payment_mode = "online"
            fee.transaction_id = data["razorpay_payment_id"]
            remaining -= apply_amount

        await db.commit()
        return {"status": "verified", "message": "Payment recorded successfully"}

    except ImportError:
        raise HTTPException(400, "Razorpay SDK not installed")
    except Exception as e:
        raise HTTPException(400, f"Verification failed: {str(e)}")