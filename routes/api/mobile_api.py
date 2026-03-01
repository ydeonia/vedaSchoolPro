"""
Mobile API Endpoints — VedaSchoolPro Android/iOS App
Sprint A1: Auth, Dashboard, Profile
"""
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_, and_
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timedelta
from database import get_db
from models.base import User, UserRole
from models.student import Student, StudentClass
from models.academic import AcademicYear, Class, Section
from utils.auth import verify_password, create_access_token, decode_access_token
import uuid

router = APIRouter(prefix="/api/mobile", tags=["Mobile"])


# ─── REQUEST / RESPONSE MODELS ─────────────────────────────────────

class LoginRequest(BaseModel):
    username: str  # email or phone
    password: str
    device_id: Optional[str] = None
    device_name: Optional[str] = None
    fcm_token: Optional[str] = None


class LoginResponse(BaseModel):
    success: bool
    access_token: Optional[str] = None
    refresh_token: Optional[str] = None
    user: Optional[dict] = None
    error: Optional[str] = None


class RefreshRequest(BaseModel):
    refresh_token: str


class DeviceTokenRequest(BaseModel):
    fcm_token: str
    device_id: Optional[str] = None


# ─── AUTH ENDPOINTS ─────────────────────────────────────────────────

@router.post("/auth/login", response_model=LoginResponse)
async def mobile_login(body: LoginRequest, request: Request, db: AsyncSession = Depends(get_db)):
    """Mobile login — returns JWT tokens as JSON (not cookie)"""

    ip = request.headers.get("x-forwarded-for", request.client.host if request.client else "unknown").split(",")[0].strip()

    # Check banned IP
    try:
        from models.login_security import BannedIP, LoginAttempt
        banned = await db.scalar(
            select(BannedIP).where(BannedIP.ip_address == ip, BannedIP.is_active == True)
        )
        if banned:
            return LoginResponse(success=False, error="Access denied. Contact administrator.")
    except Exception:
        pass

    # Find user
    result = await db.execute(
        select(User).where(
            or_(User.email == body.username.strip(), User.phone == body.username.strip()),
            User.is_active == True
        )
    )
    user = result.scalar_one_or_none()

    if not user or not verify_password(body.password, user.password_hash):
        # Log failed attempt
        try:
            from models.login_security import LoginAttempt
            attempt = LoginAttempt(
                email=body.username.strip(), ip_address=ip,
                user_agent=f"VedaSchoolPro-App/{body.device_name or 'Unknown'}",
                os="Android/iOS", browser="Mobile App", device=body.device_name or "Unknown",
                success=False, failure_reason="WRONG_PASSWORD" if user else "USER_NOT_FOUND",
                user_id=user.id if user else None
            )
            db.add(attempt)
            await db.commit()
        except Exception:
            pass
        return LoginResponse(success=False, error="Invalid email/phone or password")

    # Block super_admin from mobile
    if user.role == UserRole.super_admin:
        return LoginResponse(success=False, error="Super Admin access is not available on mobile. Please use the web dashboard.")

    # Create tokens
    token_data = {
        "user_id": str(user.id),
        "email": user.email,
        "phone": user.phone,
        "first_name": user.first_name,
        "last_name": user.last_name or "",
        "role": user.role.value,
        "org_id": str(user.org_id) if user.org_id else None,
        "branch_id": str(user.branch_id) if user.branch_id else None,
        "privileges": user.privileges if user.privileges else {},
        "designation": getattr(user, 'designation', None),
        "platform": "mobile",
    }
    access_token = create_access_token(token_data)

    # Refresh token (longer-lived)
    refresh_data = {"user_id": str(user.id), "type": "refresh", "device_id": body.device_id}
    from utils.auth import create_access_token as create_token
    refresh_token = create_token(refresh_data, expires_minutes=43200)  # 30 days

    # Update last login + save FCM token
    user.last_login = datetime.utcnow()
    if body.fcm_token:
        if not hasattr(user, 'fcm_tokens') or not user.fcm_tokens:
            user.fcm_tokens = {}
        user.fcm_tokens[body.device_id or "default"] = body.fcm_token
    await db.commit()

    # Log success
    try:
        from models.login_security import LoginAttempt
        attempt = LoginAttempt(
            email=body.username.strip(), ip_address=ip,
            user_agent=f"VedaSchoolPro-App/{body.device_name or 'Unknown'}",
            os="Android/iOS", browser="Mobile App", device=body.device_name or "Unknown",
            success=True, user_id=user.id
        )
        db.add(attempt)
        await db.commit()
    except Exception:
        pass

    # Build user profile response
    user_data = {
        "id": str(user.id),
        "email": user.email,
        "phone": user.phone,
        "first_name": user.first_name,
        "last_name": user.last_name or "",
        "role": user.role.value,
        "org_id": str(user.org_id) if user.org_id else None,
        "branch_id": str(user.branch_id) if user.branch_id else None,
        "avatar_url": getattr(user, 'avatar_url', None),
        "designation": getattr(user, 'designation', None),
        "privileges": user.privileges or {},
    }

    return LoginResponse(success=True, access_token=access_token, refresh_token=refresh_token, user=user_data)


@router.post("/auth/refresh")
async def mobile_refresh(body: RefreshRequest, db: AsyncSession = Depends(get_db)):
    """Refresh access token using refresh token"""
    payload = decode_access_token(body.refresh_token)
    if not payload or payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")

    user = await db.get(User, uuid.UUID(payload["user_id"]))
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found or inactive")

    token_data = {
        "user_id": str(user.id),
        "email": user.email,
        "phone": user.phone,
        "first_name": user.first_name,
        "last_name": user.last_name or "",
        "role": user.role.value,
        "org_id": str(user.org_id) if user.org_id else None,
        "branch_id": str(user.branch_id) if user.branch_id else None,
        "privileges": user.privileges if user.privileges else {},
        "platform": "mobile",
    }
    new_access = create_access_token(token_data)
    return {"success": True, "access_token": new_access}


@router.post("/auth/logout")
async def mobile_logout(request: Request, db: AsyncSession = Depends(get_db)):
    """Remove FCM token on logout"""
    token = request.headers.get("Authorization", "").replace("Bearer ", "")
    if token:
        payload = decode_access_token(token)
        if payload:
            user = await db.get(User, uuid.UUID(payload["user_id"]))
            if user and hasattr(user, 'fcm_tokens') and user.fcm_tokens:
                user.fcm_tokens = {}
                await db.commit()
    return {"success": True}


@router.post("/auth/fcm-token")
async def update_fcm_token(body: DeviceTokenRequest, request: Request, db: AsyncSession = Depends(get_db)):
    """Update FCM push notification token"""
    token = request.headers.get("Authorization", "").replace("Bearer ", "")
    payload = decode_access_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Unauthorized")
    user = await db.get(User, uuid.UUID(payload["user_id"]))
    if user:
        if not hasattr(user, 'fcm_tokens') or not user.fcm_tokens:
            user.fcm_tokens = {}
        user.fcm_tokens[body.device_id or "default"] = body.fcm_token
        await db.commit()
    return {"success": True}


# ─── HELPER: Get current user from Bearer token ───────────────────

async def get_mobile_user(request: Request, db: AsyncSession = Depends(get_db)):
    token = request.headers.get("Authorization", "").replace("Bearer ", "")
    if not token:
        raise HTTPException(status_code=401, detail="Missing authorization token")
    payload = decode_access_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    user = await db.get(User, uuid.UUID(payload["user_id"]))
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found or inactive")
    return user, payload


# ─── DASHBOARD ENDPOINTS ───────────────────────────────────────────

@router.get("/dashboard")
async def mobile_dashboard(request: Request, db: AsyncSession = Depends(get_db)):
    """Role-aware dashboard — returns data based on user role"""
    user, payload = await get_mobile_user(request, db)
    role = user.role.value
    branch_id = user.branch_id

    if role == "student":
        return await _student_dashboard(user, db)
    elif role == "parent":
        return await _parent_dashboard(user, db)
    elif role == "teacher":
        return await _teacher_dashboard(user, db)
    elif role == "chairman":
        return await _chairman_dashboard(user, db)
    else:
        return await _admin_dashboard(user, payload, db)


async def _student_dashboard(user, db):
    """Student home: attendance, timetable, results, homework, fees"""
    # Find student record
    student = await db.scalar(select(Student).where(Student.user_id == user.id))
    if not student:
        return {"role": "student", "error": "Student profile not found"}

    # Get current class
    sc = await db.scalar(
        select(StudentClass).where(StudentClass.student_id == student.id, StudentClass.is_current == True)
    )

    # Attendance percentage (current month)
    attendance_pct = 0.0
    try:
        from models.attendance import Attendance
        now = datetime.utcnow()
        first_day = now.replace(day=1)
        total = await db.scalar(
            select(func.count()).where(Attendance.student_id == student.id, Attendance.date >= first_day)
        )
        present = await db.scalar(
            select(func.count()).where(Attendance.student_id == student.id, Attendance.date >= first_day, Attendance.status == "present")
        )
        attendance_pct = round((present / total * 100), 1) if total else 0
    except Exception:
        pass

    # Pending fees
    fee_due = 0
    try:
        from models.fee import FeeRecord
        pending = await db.execute(
            select(func.sum(FeeRecord.amount - FeeRecord.paid_amount)).where(
                FeeRecord.student_id == student.id, FeeRecord.status.in_(["unpaid", "partial"])
            )
        )
        fee_due = pending.scalar() or 0
    except Exception:
        pass

    return {
        "role": "student",
        "greeting": f"Good Morning, {user.first_name}!",
        "student_id": str(student.id),
        "class_name": sc.class_name if sc else "",
        "section": sc.section if sc else "",
        "roll_no": sc.roll_no if sc else "",
        "stats": {
            "attendance_pct": attendance_pct,
            "fee_due": float(fee_due),
        },
    }


async def _parent_dashboard(user, db):
    """Parent home: children list, attendance, fees, announcements"""
    # Find children
    children = []
    try:
        from models.student import Student, StudentClass, ParentStudent
        result = await db.execute(
            select(Student, StudentClass).join(
                ParentStudent, ParentStudent.student_id == Student.id
            ).outerjoin(
                StudentClass, and_(StudentClass.student_id == Student.id, StudentClass.is_current == True)
            ).where(ParentStudent.parent_user_id == user.id)
        )
        for student, sc in result.all():
            # Fee pending
            fee_due = 0
            try:
                from models.fee import FeeRecord
                r = await db.scalar(
                    select(func.sum(FeeRecord.amount - FeeRecord.paid_amount)).where(
                        FeeRecord.student_id == student.id, FeeRecord.status.in_(["unpaid", "partial"])
                    )
                )
                fee_due = r or 0
            except Exception:
                pass
            children.append({
                "student_id": str(student.id),
                "name": student.full_name,
                "class_name": sc.class_name if sc else "",
                "section": sc.section if sc else "",
                "fee_due": float(fee_due),
            })
    except Exception:
        pass

    return {
        "role": "parent",
        "greeting": f"Welcome, {user.first_name}!",
        "children": children,
        "total_fee_due": sum(c["fee_due"] for c in children),
    }


async def _teacher_dashboard(user, db):
    """Teacher home: my classes, today's schedule, pending tasks"""
    classes = []
    try:
        from models.teacher import Teacher, TeacherSubjectAssignment
        teacher = await db.scalar(select(Teacher).where(Teacher.user_id == user.id))
        if teacher:
            # Get assigned classes
            result = await db.execute(
                select(TeacherSubjectAssignment).where(TeacherSubjectAssignment.teacher_id == teacher.id)
            )
            for assignment in result.scalars():
                classes.append({
                    "class_name": assignment.class_name,
                    "section": assignment.section,
                    "subject": assignment.subject_name,
                })
    except Exception:
        pass

    return {
        "role": "teacher",
        "greeting": f"Good Morning, {user.first_name}!",
        "designation": getattr(user, 'designation', 'Teacher'),
        "classes": classes,
        "pending_tasks": [],
    }


async def _admin_dashboard(user, payload, db):
    """Admin/Staff home: stats, quick actions, alerts"""
    branch_id = user.branch_id
    stats = {}

    # Total students
    try:
        count = await db.scalar(
            select(func.count()).select_from(Student).where(Student.branch_id == branch_id)
        )
        stats["total_students"] = count or 0
    except Exception:
        stats["total_students"] = 0

    # Today's attendance
    try:
        from models.attendance import Attendance
        today = datetime.utcnow().date()
        total = await db.scalar(
            select(func.count()).where(Attendance.branch_id == branch_id, Attendance.date == today)
        )
        present = await db.scalar(
            select(func.count()).where(Attendance.branch_id == branch_id, Attendance.date == today, Attendance.status == "present")
        )
        stats["attendance_pct"] = round((present / total * 100), 1) if total else 0
    except Exception:
        stats["attendance_pct"] = 0

    # Fee collected MTD
    try:
        from models.fee import FeeRecord
        now = datetime.utcnow()
        first_day = now.replace(day=1)
        collected = await db.scalar(
            select(func.sum(FeeRecord.paid_amount)).where(
                FeeRecord.branch_id == branch_id,
                FeeRecord.last_payment_date >= first_day
            )
        )
        stats["fee_collected_mtd"] = float(collected or 0)
    except Exception:
        stats["fee_collected_mtd"] = 0

    return {
        "role": "school_admin",
        "greeting": f"Good Morning, {user.first_name}!",
        "privileges": payload.get("privileges", {}),
        "stats": stats,
    }


async def _chairman_dashboard(user, db):
    """Chairman home: multi-branch overview"""
    from models.base import Branch
    branches = []
    try:
        result = await db.execute(
            select(Branch).where(Branch.org_id == user.org_id, Branch.is_active == True)
        )
        for branch in result.scalars():
            # Student count
            count = await db.scalar(
                select(func.count()).select_from(Student).where(Student.branch_id == branch.id)
            ) or 0
            branches.append({
                "branch_id": str(branch.id),
                "name": branch.name,
                "student_count": count,
            })
    except Exception:
        pass

    return {
        "role": "chairman",
        "greeting": f"Good Morning, Chairman!",
        "branches": branches,
        "total_students": sum(b["student_count"] for b in branches),
    }


# ─── PROFILE ───────────────────────────────────────────────────────

@router.get("/profile")
async def mobile_profile(request: Request, db: AsyncSession = Depends(get_db)):
    """Get current user profile"""
    user, payload = await get_mobile_user(request, db)
    return {
        "id": str(user.id),
        "email": user.email,
        "phone": user.phone,
        "first_name": user.first_name,
        "last_name": user.last_name or "",
        "role": user.role.value,
        "avatar_url": getattr(user, 'avatar_url', None),
        "designation": getattr(user, 'designation', None),
        "branch_id": str(user.branch_id) if user.branch_id else None,
        "org_id": str(user.org_id) if user.org_id else None,
    }


class PasswordChangeRequest(BaseModel):
    current_password: str
    new_password: str


@router.post("/profile/change-password")
async def mobile_change_password(body: PasswordChangeRequest, request: Request, db: AsyncSession = Depends(get_db)):
    """Change password from mobile"""
    user, _ = await get_mobile_user(request, db)
    if not verify_password(body.current_password, user.password_hash):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    if len(body.new_password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters")
    from utils.auth import hash_password
    user.password_hash = hash_password(body.new_password)
    await db.commit()
    return {"success": True, "message": "Password changed successfully"}


# ─── ANNOUNCEMENTS (shared across roles) ───────────────────────────

@router.get("/announcements")
async def mobile_announcements(request: Request, db: AsyncSession = Depends(get_db)):
    """Get announcements for current user's branch"""
    user, _ = await get_mobile_user(request, db)
    try:
        from models.announcement import Announcement
        result = await db.execute(
            select(Announcement).where(
                Announcement.branch_id == user.branch_id,
                Announcement.is_active == True
            ).order_by(Announcement.created_at.desc()).limit(20)
        )
        announcements = []
        for ann in result.scalars():
            announcements.append({
                "id": str(ann.id),
                "title": ann.title,
                "message": ann.message,
                "priority": getattr(ann, 'priority', 'normal'),
                "created_at": ann.created_at.isoformat() if ann.created_at else None,
            })
        return {"announcements": announcements}
    except Exception:
        return {"announcements": []}


# ─── APP CONFIG ────────────────────────────────────────────────────

@router.get("/config")
async def mobile_config():
    """App configuration — version check, feature flags, colors"""
    return {
        "min_app_version": "1.0.0",
        "latest_version": "1.0.0",
        "force_update": False,
        "maintenance_mode": False,
        "features": {
            "biometric_login": True,
            "dark_mode": True,
            "push_notifications": True,
            "payment_gateway": True,
            "languages": ["en", "hi", "ta", "te", "ml", "as", "gu", "pa"],
        },
        "support": {
            "email": "support@vedaSchoolpro.com",
            "phone": "+91 98765 43210",
            "whatsapp": "+91 98765 43210",
        }
    }

# ═══════════════════════════════════════════════════════════════
# V2 — Extended endpoints for all app screens
# ═══════════════════════════════════════════════════════════════

# ═══ STUDENT DETAIL ═══
@router.get("/student/{student_id}/detail")
async def student_detail(student_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    user, _ = await get_mobile_user(request, db)
    from models.student import Student, StudentClass, StudentDocument
    from models.fee import FeeRecord
    sid = uuid.UUID(student_id)
    student = await db.get(Student, sid)
    if not student: raise HTTPException(404, "Student not found")
    sc = await db.scalar(select(StudentClass).where(StudentClass.student_id == sid, StudentClass.is_current == True))
    docs = []
    try:
        r = await db.execute(select(StudentDocument).where(StudentDocument.student_id == sid))
        docs = [{"id": str(d.id), "name": d.document_name, "type": getattr(d,'document_type',''), "url": getattr(d,'file_url','')} for d in r.scalars()]
    except: pass
    fee_total = await db.scalar(select(func.sum(FeeRecord.amount)).where(FeeRecord.student_id == sid)) or 0
    fee_paid = await db.scalar(select(func.sum(FeeRecord.paid_amount)).where(FeeRecord.student_id == sid)) or 0
    return {
        "id": str(student.id), "full_name": student.full_name,
        "admission_no": getattr(student,'admission_no',''), "dob": str(getattr(student,'dob','')),
        "gender": getattr(student,'gender',''), "blood_group": getattr(student,'blood_group',''),
        "father_name": getattr(student,'father_name',''), "mother_name": getattr(student,'mother_name',''),
        "phone": getattr(student,'phone',''), "email": getattr(student,'email',''),
        "address": getattr(student,'address',''),
        "class_name": sc.class_name if sc else '', "section": sc.section if sc else '', "roll_no": sc.roll_no if sc else '',
        "documents": docs, "fee_total": float(fee_total), "fee_paid": float(fee_paid), "fee_due": float(fee_total - fee_paid),
    }

# ═══ TIMETABLE ═══
@router.get("/timetable")
async def get_timetable(request: Request, class_id: str = Query(None), section: str = Query(None), db: AsyncSession = Depends(get_db)):
    user, _ = await get_mobile_user(request, db)
    from models.academic import TimetableSlot
    from models.teacher import Teacher
    slots = []
    if user.role.value == "teacher":
        teacher = await db.scalar(select(Teacher).where(Teacher.user_id == user.id))
        if teacher:
            r = await db.execute(select(TimetableSlot).where(TimetableSlot.teacher_id == teacher.id).order_by(TimetableSlot.day_of_week, TimetableSlot.period_number))
            slots = [{"day": s.day_of_week, "period": s.period_number, "subject": getattr(s,'subject_name',''),
                       "class_name": getattr(s,'class_name',''), "section": getattr(s,'section',''),
                       "room": getattr(s,'room',''), "start_time": str(getattr(s,'start_time','')), "end_time": str(getattr(s,'end_time',''))} for s in r.scalars()]
    elif class_id and section:
        r = await db.execute(select(TimetableSlot).where(TimetableSlot.class_id == uuid.UUID(class_id), TimetableSlot.section == section).order_by(TimetableSlot.day_of_week, TimetableSlot.period_number))
        slots = [{"day": s.day_of_week, "period": s.period_number, "subject": getattr(s,'subject_name',''),
                   "teacher": getattr(s,'teacher_name',''), "room": getattr(s,'room',''),
                   "start_time": str(getattr(s,'start_time','')), "end_time": str(getattr(s,'end_time',''))} for s in r.scalars()]
    return {"slots": slots}

# ═══ ATTENDANCE — STUDENT VIEW ═══
@router.get("/attendance/student/{student_id}")
async def student_attendance(student_id: str, month: int = Query(None), year: int = Query(None), request: Request = None, db: AsyncSession = Depends(get_db)):
    user, _ = await get_mobile_user(request, db)
    from models.attendance import Attendance
    now = datetime.utcnow()
    m, y2 = month or now.month, year or now.year
    first = date(y2, m, 1)
    last = date(y2, m + 1, 1) - timedelta(days=1) if m < 12 else date(y2, 12, 31)
    r = await db.execute(select(Attendance).where(Attendance.student_id == uuid.UUID(student_id), Attendance.date >= first, Attendance.date <= last).order_by(Attendance.date))
    days = {a.date.day: a.status for a in r.scalars()}
    present = sum(1 for s in days.values() if s == "present")
    absent = sum(1 for s in days.values() if s == "absent")
    late = sum(1 for s in days.values() if s == "late")
    total = present + absent + late
    return {"month": m, "year": y2, "days_in_month": last.day, "attendance": days,
            "present": present, "absent": absent, "late": late, "working_days": total,
            "percentage": round(present / total * 100, 1) if total else 0}

# ═══ RESULTS ═══
@router.get("/results/student/{student_id}")
async def student_results(student_id: str, request: Request = None, db: AsyncSession = Depends(get_db)):
    user, _ = await get_mobile_user(request, db)
    from models.exam import Exam, Marks
    sid = uuid.UUID(student_id)
    r = await db.execute(select(Exam).where(Exam.branch_id == user.branch_id, Exam.is_published == True).order_by(desc(Exam.created_at)))
    exams_data = []
    for exam in r.scalars():
        mr = await db.execute(select(Marks).where(Marks.exam_id == exam.id, Marks.student_id == sid))
        subjects = [{"subject": getattr(m,'subject_name',''), "marks": m.marks_obtained or 0, "max_marks": m.max_marks or 100, "grade": getattr(m,'grade','')} for m in mr.scalars()]
        if subjects:
            tm = sum(s["marks"] for s in subjects); mx = sum(s["max_marks"] for s in subjects)
            pct = round(tm/mx*100,1) if mx else 0
            grade = "A+" if pct>=90 else "A" if pct>=75 else "B" if pct>=60 else "C" if pct>=45 else "D" if pct>=33 else "F"
            exams_data.append({"exam_id": str(exam.id), "name": exam.name, "percentage": pct, "grade": grade, "subjects": subjects})
    return {"exams": exams_data}

# ═══ FEES ═══
@router.get("/fees/student/{student_id}")
async def student_fees(student_id: str, request: Request = None, db: AsyncSession = Depends(get_db)):
    user, _ = await get_mobile_user(request, db)
    from models.fee import FeeRecord
    r = await db.execute(select(FeeRecord).where(FeeRecord.student_id == uuid.UUID(student_id)).order_by(desc(FeeRecord.due_date)))
    fees = [{"id": str(f.id), "fee_type": f.fee_type, "amount": float(f.amount), "paid": float(f.paid_amount),
             "due": float(f.amount - f.paid_amount), "due_date": str(f.due_date) if f.due_date else '',
             "status": f.status} for f in r.scalars()]
    total = sum(f["amount"] for f in fees); paid = sum(f["paid"] for f in fees)
    return {"fees": fees, "total": total, "paid": paid, "due": total - paid}

# ═══ HOMEWORK ═══
@router.get("/homework")
async def get_homework(request: Request, class_id: str = Query(None), student_id: str = Query(None), db: AsyncSession = Depends(get_db)):
    user, _ = await get_mobile_user(request, db)
    from models.homework import Homework, HomeworkSubmission
    q = select(Homework).where(Homework.branch_id == user.branch_id).order_by(desc(Homework.created_at)).limit(30)
    if class_id: q = q.where(Homework.class_id == uuid.UUID(class_id))
    r = await db.execute(q)
    items = []
    for h in r.scalars():
        submitted = False
        if student_id:
            sub = await db.scalar(select(HomeworkSubmission).where(HomeworkSubmission.homework_id == h.id, HomeworkSubmission.student_id == uuid.UUID(student_id)))
            submitted = sub is not None
        items.append({"id": str(h.id), "title": h.title, "description": getattr(h,'description',''),
                       "subject": getattr(h,'subject_name',''), "teacher": getattr(h,'teacher_name',''),
                       "due_date": str(h.due_date) if h.due_date else '',
                       "is_submitted": submitted, "is_overdue": h.due_date < date.today() if h.due_date else False})
    return {"homework": items}

@router.post("/homework/create")
async def create_homework_mobile(request: Request, db: AsyncSession = Depends(get_db)):
    user, _ = await get_mobile_user(request, db)
    body = await request.json()
    from models.homework import Homework
    from models.teacher import Teacher
    teacher = await db.scalar(select(Teacher).where(Teacher.user_id == user.id))
    hw = Homework(title=body["title"], description=body.get("description",""), class_id=uuid.UUID(body["class_id"]),
                  subject_name=body.get("subject",""), teacher_id=teacher.id if teacher else None,
                  due_date=date.fromisoformat(body["due_date"]) if body.get("due_date") else None, branch_id=user.branch_id)
    db.add(hw); await db.commit()
    return {"success": True, "id": str(hw.id)}

# ═══ DIARY ═══
@router.get("/diary/{student_id}")
async def student_diary(student_id: str, request: Request = None, db: AsyncSession = Depends(get_db)):
    user, _ = await get_mobile_user(request, db)
    from models.diary import DailyDiary
    r = await db.execute(select(DailyDiary).where(DailyDiary.student_id == uuid.UUID(student_id)).order_by(desc(DailyDiary.date)).limit(30))
    return {"entries": [{"id": str(d.id), "date": str(d.date), "title": getattr(d,'title',''), "message": d.message,
                          "teacher": getattr(d,'teacher_name',''), "acknowledged": getattr(d,'acknowledged',False)} for d in r.scalars()]}

# ═══ LIBRARY ═══
@router.get("/library")
async def library_books(request: Request, student_id: str = Query(None), db: AsyncSession = Depends(get_db)):
    user, _ = await get_mobile_user(request, db)
    from models.library import Book, BookIssue
    issued = []
    if student_id:
        r = await db.execute(select(BookIssue, Book).join(Book, BookIssue.book_id == Book.id).where(BookIssue.student_id == uuid.UUID(student_id), BookIssue.returned_at == None))
        issued = [{"book_title": book.title, "author": getattr(book,'author',''), "issue_date": str(issue.issued_at.date()) if issue.issued_at else '',
                    "due_date": str(issue.due_date) if issue.due_date else '', "is_overdue": issue.due_date < date.today() if issue.due_date else False} for issue, book in r.all()]
    return {"issued_books": issued}

# ═══ COMPLAINTS ═══
@router.get("/complaints")
async def get_complaints(request: Request, db: AsyncSession = Depends(get_db)):
    user, _ = await get_mobile_user(request, db)
    from models.complaint import Complaint
    r = await db.execute(select(Complaint).where(Complaint.user_id == user.id).order_by(desc(Complaint.created_at)).limit(20))
    return {"complaints": [{"id": str(c.id), "subject": c.subject, "description": c.description, "status": c.status,
                             "priority": getattr(c,'priority','normal'), "created_at": c.created_at.isoformat() if c.created_at else ''} for c in r.scalars()]}

@router.post("/complaints")
async def create_complaint(request: Request, db: AsyncSession = Depends(get_db)):
    user, _ = await get_mobile_user(request, db)
    body = await request.json()
    from models.complaint import Complaint
    c = Complaint(user_id=user.id, branch_id=user.branch_id, subject=body.get("subject",""), description=body.get("description",""), status="open", priority=body.get("priority","normal"))
    db.add(c); await db.commit()
    return {"success": True, "id": str(c.id)}

# ═══ TRANSPORT ═══
@router.get("/transport")
async def transport_info(request: Request, student_id: str = Query(None), db: AsyncSession = Depends(get_db)):
    user, _ = await get_mobile_user(request, db)
    try:
        from models.transport import TransportRoute, Vehicle, StudentTransport, RouteStop
        if student_id:
            st = await db.scalar(select(StudentTransport).where(StudentTransport.student_id == uuid.UUID(student_id)))
            if st:
                route = await db.get(TransportRoute, st.route_id)
                vehicle = await db.get(Vehicle, route.vehicle_id) if route and route.vehicle_id else None
                sr = await db.execute(select(RouteStop).where(RouteStop.route_id == route.id).order_by(RouteStop.stop_order))
                return {"route_name": route.name if route else '', "vehicle_no": vehicle.vehicle_number if vehicle else '',
                        "driver": getattr(vehicle,'driver_name','') if vehicle else '', "driver_phone": getattr(vehicle,'driver_phone','') if vehicle else '',
                        "stops": [{"name": s.stop_name, "time": str(getattr(s,'pickup_time',''))} for s in sr.scalars()]}
    except: pass
    return {"route_name": "", "stops": []}

# ═══ TEACHER ENDPOINTS ═══
@router.get("/teacher/classes")
async def teacher_classes(request: Request, db: AsyncSession = Depends(get_db)):
    user, _ = await get_mobile_user(request, db)
    from models.teacher import Teacher, TeacherSubjectAssignment
    from models.student import StudentClass
    teacher = await db.scalar(select(Teacher).where(Teacher.user_id == user.id))
    if not teacher: return {"classes": []}
    r = await db.execute(select(TeacherSubjectAssignment).where(TeacherSubjectAssignment.teacher_id == teacher.id))
    classes, seen = [], set()
    for a in r.scalars():
        key = f"{a.class_id}-{a.section}"
        if key not in seen:
            seen.add(key)
            count = await db.scalar(select(func.count()).where(StudentClass.class_id == a.class_id, StudentClass.section == a.section, StudentClass.is_current == True)) or 0
            classes.append({"class_id": str(a.class_id), "class_name": a.class_name, "section": a.section, "subject": a.subject_name, "student_count": count})
    return {"classes": classes, "teacher_id": str(teacher.id)}

@router.get("/teacher/students/{class_id}/{section}")
async def teacher_students(class_id: str, section: str, request: Request, db: AsyncSession = Depends(get_db)):
    user, _ = await get_mobile_user(request, db)
    from models.student import Student, StudentClass
    r = await db.execute(select(Student, StudentClass).join(StudentClass, StudentClass.student_id == Student.id).where(StudentClass.class_id == uuid.UUID(class_id), StudentClass.section == section, StudentClass.is_current == True).order_by(StudentClass.roll_no))
    return {"students": [{"student_id": str(s.id), "name": s.full_name, "roll_no": sc.roll_no} for s, sc in r.all()]}

@router.get("/attendance/load/{class_id}/{section}")
async def load_attendance(class_id: str, section: str, date_str: str = Query(None), request: Request = None, db: AsyncSession = Depends(get_db)):
    user, _ = await get_mobile_user(request, db)
    from models.attendance import Attendance
    from models.student import Student, StudentClass
    today = date.fromisoformat(date_str) if date_str else date.today()
    sr = await db.execute(select(Student, StudentClass).join(StudentClass, StudentClass.student_id == Student.id).where(StudentClass.class_id == uuid.UUID(class_id), StudentClass.section == section, StudentClass.is_current == True).order_by(StudentClass.roll_no))
    students = []
    for s, sc in sr.all():
        att = await db.scalar(select(Attendance).where(Attendance.student_id == s.id, Attendance.date == today))
        students.append({"student_id": str(s.id), "name": s.full_name, "roll_no": sc.roll_no, "status": att.status if att else "not_marked"})
    return {"date": str(today), "students": students}

@router.post("/attendance/save")
async def save_attendance_mobile(request: Request, db: AsyncSession = Depends(get_db)):
    user, _ = await get_mobile_user(request, db)
    body = await request.json()
    from models.attendance import Attendance
    att_date = date.fromisoformat(body.get("date", str(date.today())))
    saved = 0
    for rec in body.get("records", []):
        sid = uuid.UUID(rec["student_id"])
        existing = await db.scalar(select(Attendance).where(Attendance.student_id == sid, Attendance.date == att_date))
        if existing: existing.status = rec["status"]
        else:
            db.add(Attendance(student_id=sid, date=att_date, status=rec["status"], branch_id=user.branch_id, marked_by=user.id))
        saved += 1
    await db.commit()
    return {"success": True, "saved": saved}

@router.get("/exams/list")
async def exams_list(request: Request, db: AsyncSession = Depends(get_db)):
    user, _ = await get_mobile_user(request, db)
    from models.exam import Exam, ExamSubject
    r = await db.execute(select(Exam).where(Exam.branch_id == user.branch_id).order_by(desc(Exam.created_at)).limit(20))
    exams = []
    for e in r.scalars():
        sr = await db.execute(select(ExamSubject).where(ExamSubject.exam_id == e.id))
        exams.append({"id": str(e.id), "name": e.name, "is_published": e.is_published,
                       "subjects": [{"id": str(s.id), "name": s.subject_name, "max_marks": s.max_marks} for s in sr.scalars()]})
    return {"exams": exams}

@router.post("/marks/save")
async def save_marks_mobile(request: Request, db: AsyncSession = Depends(get_db)):
    user, _ = await get_mobile_user(request, db)
    body = await request.json()
    from models.exam import Marks
    exam_id, subject_id = uuid.UUID(body["exam_id"]), uuid.UUID(body["subject_id"])
    saved = 0
    for rec in body.get("records", []):
        if rec.get("marks") is None: continue
        sid = uuid.UUID(rec["student_id"])
        existing = await db.scalar(select(Marks).where(Marks.exam_id == exam_id, Marks.subject_id == subject_id, Marks.student_id == sid))
        if existing: existing.marks_obtained = int(rec["marks"])
        else: db.add(Marks(exam_id=exam_id, subject_id=subject_id, student_id=sid, marks_obtained=int(rec["marks"]), max_marks=rec.get("max_marks",100), branch_id=user.branch_id))
        saved += 1
    await db.commit()
    return {"success": True, "saved": saved}

@router.get("/teacher/leave")
async def teacher_leaves(request: Request, db: AsyncSession = Depends(get_db)):
    user, _ = await get_mobile_user(request, db)
    from models.leave import LeaveRequest
    r = await db.execute(select(LeaveRequest).where(LeaveRequest.user_id == user.id).order_by(desc(LeaveRequest.created_at)).limit(20))
    return {"leaves": [{"id": str(l.id), "type": l.leave_type, "from_date": str(l.from_date), "to_date": str(l.to_date),
                         "reason": l.reason, "status": l.status, "days": (l.to_date - l.from_date).days + 1 if l.from_date and l.to_date else 1} for l in r.scalars()]}

@router.post("/teacher/leave/apply")
async def apply_leave(request: Request, db: AsyncSession = Depends(get_db)):
    user, _ = await get_mobile_user(request, db)
    body = await request.json()
    from models.leave import LeaveRequest
    l = LeaveRequest(user_id=user.id, branch_id=user.branch_id, leave_type=body.get("type","casual"),
                     from_date=date.fromisoformat(body["from_date"]), to_date=date.fromisoformat(body["to_date"]),
                     reason=body.get("reason",""), status="pending")
    db.add(l); await db.commit()
    return {"success": True, "id": str(l.id)}

# ═══ ADMIN ENDPOINTS ═══
@router.get("/students")
async def list_students(request: Request, class_id: str = Query(None), search: str = Query(None), db: AsyncSession = Depends(get_db)):
    user, _ = await get_mobile_user(request, db)
    from models.student import Student, StudentClass
    from models.fee import FeeRecord
    q = select(Student, StudentClass).join(StudentClass, StudentClass.student_id == Student.id).where(Student.branch_id == user.branch_id, StudentClass.is_current == True)
    if class_id: q = q.where(StudentClass.class_id == uuid.UUID(class_id))
    if search: q = q.where(or_(Student.full_name.ilike(f"%{search}%")))
    r = await db.execute(q.order_by(StudentClass.class_name, StudentClass.roll_no).limit(100))
    students = []
    for s, sc in r.all():
        fee_due = await db.scalar(select(func.sum(FeeRecord.amount - FeeRecord.paid_amount)).where(FeeRecord.student_id == s.id, FeeRecord.status.in_(["unpaid","partial"]))) or 0
        students.append({"id": str(s.id), "name": s.full_name, "admission_no": getattr(s,'admission_no',''),
                          "class_name": sc.class_name, "section": sc.section, "roll_no": sc.roll_no,
                          "phone": getattr(s,'phone',''), "fee_due": float(fee_due), "fee_status": "paid" if fee_due == 0 else "unpaid"})
    return {"students": students, "total": len(students)}

@router.get("/teachers")
async def list_teachers(request: Request, db: AsyncSession = Depends(get_db)):
    user, _ = await get_mobile_user(request, db)
    from models.teacher import Teacher
    r = await db.execute(select(Teacher).where(Teacher.branch_id == user.branch_id, Teacher.is_active == True).order_by(Teacher.full_name))
    return {"teachers": [{"id": str(t.id), "name": t.full_name, "phone": getattr(t,'phone',''),
                           "email": getattr(t,'email',''), "designation": getattr(t,'designation','Teacher')} for t in r.scalars()]}

@router.get("/admissions")
async def list_admissions(request: Request, db: AsyncSession = Depends(get_db)):
    user, _ = await get_mobile_user(request, db)
    from models.admission import Admission
    r = await db.execute(select(Admission).where(Admission.branch_id == user.branch_id).order_by(desc(Admission.created_at)).limit(50))
    return {"admissions": [{"id": str(a.id), "student_name": a.student_name, "class_applied": getattr(a,'class_applied',''),
                             "parent_name": getattr(a,'parent_name',''), "phone": getattr(a,'phone',''), "status": a.status,
                             "created_at": a.created_at.isoformat() if a.created_at else ''} for a in r.scalars()]}

@router.get("/donations")
async def list_donations(request: Request, db: AsyncSession = Depends(get_db)):
    user, _ = await get_mobile_user(request, db)
    from models.donation import Donation
    r = await db.execute(select(Donation).where(Donation.branch_id == user.branch_id).order_by(desc(Donation.created_at)).limit(50))
    items = [{"id": str(d.id), "donor_name": d.donor_name if not d.is_anonymous else "Anonymous",
              "amount": float(d.amount), "purpose": getattr(d,'purpose',''), "is_anonymous": d.is_anonymous,
              "date": d.created_at.isoformat() if d.created_at else ''} for d in r.scalars()]
    return {"donations": items, "total": sum(d["amount"] for d in items)}

@router.get("/transactions")
async def list_transactions(request: Request, db: AsyncSession = Depends(get_db)):
    user, _ = await get_mobile_user(request, db)
    from models.fee import PaymentTransaction
    r = await db.execute(select(PaymentTransaction).where(PaymentTransaction.branch_id == user.branch_id).order_by(desc(PaymentTransaction.created_at)).limit(50))
    return {"transactions": [{"id": str(t.id), "amount": float(t.amount), "status": t.status,
                               "gateway": getattr(t,'gateway',''), "student_name": getattr(t,'student_name',''),
                               "fee_type": getattr(t,'fee_type',''), "date": t.created_at.isoformat() if t.created_at else '',
                               "transaction_id": getattr(t,'transaction_id','')} for t in r.scalars()]}

@router.get("/fee/defaulters")
async def fee_defaulters(request: Request, db: AsyncSession = Depends(get_db)):
    user, _ = await get_mobile_user(request, db)
    from models.student import Student, StudentClass
    from models.fee import FeeRecord
    r = await db.execute(
        select(Student, StudentClass, func.sum(FeeRecord.amount - FeeRecord.paid_amount).label("due"))
        .join(StudentClass, StudentClass.student_id == Student.id)
        .join(FeeRecord, FeeRecord.student_id == Student.id)
        .where(Student.branch_id == user.branch_id, StudentClass.is_current == True, FeeRecord.status.in_(["unpaid","partial"]))
        .group_by(Student.id, StudentClass.id).having(func.sum(FeeRecord.amount - FeeRecord.paid_amount) > 0)
        .order_by(desc("due")).limit(100))
    return {"defaulters": [{"id": str(s.id), "name": s.full_name, "class_name": sc.class_name, "section": sc.section, "due": float(due)} for s, sc, due in r.all()]}

# ═══ CHAIRMAN ENDPOINTS ═══
@router.get("/chairman/branch/{branch_id}")
async def branch_detail(branch_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    user, _ = await get_mobile_user(request, db)
    from models.base import Branch
    from models.student import Student
    from models.fee import FeeRecord
    from models.attendance import Attendance
    bid = uuid.UUID(branch_id)
    branch = await db.get(Branch, bid)
    if not branch: raise HTTPException(404, "Branch not found")
    student_count = await db.scalar(select(func.count()).select_from(Student).where(Student.branch_id == bid)) or 0
    today = date.today()
    att_total = await db.scalar(select(func.count()).where(Attendance.branch_id == bid, Attendance.date == today)) or 0
    att_present = await db.scalar(select(func.count()).where(Attendance.branch_id == bid, Attendance.date == today, Attendance.status == "present")) or 0
    first_day = today.replace(day=1)
    fee_mtd = await db.scalar(select(func.sum(FeeRecord.paid_amount)).where(FeeRecord.branch_id == bid, FeeRecord.last_payment_date >= first_day)) or 0
    fee_due = await db.scalar(select(func.sum(FeeRecord.amount - FeeRecord.paid_amount)).where(FeeRecord.branch_id == bid, FeeRecord.status.in_(["unpaid","partial"]))) or 0
    return {
        "branch_id": str(branch.id), "name": branch.name, "student_count": student_count,
        "attendance_today": att_present, "attendance_total": att_total,
        "attendance_pct": round(att_present/att_total*100,1) if att_total else 0,
        "fee_collected_mtd": float(fee_mtd), "fee_due_total": float(fee_due),
    }

@router.get("/chairman/finance")
async def chairman_finance(request: Request, db: AsyncSession = Depends(get_db)):
    user, _ = await get_mobile_user(request, db)
    from models.base import Branch
    from models.fee import FeeRecord
    r = await db.execute(select(Branch).where(Branch.org_id == user.org_id, Branch.is_active == True))
    branches = []
    grand_collected, grand_due = 0, 0
    first_day = date.today().replace(day=1)
    for b in r.scalars():
        collected = await db.scalar(select(func.sum(FeeRecord.paid_amount)).where(FeeRecord.branch_id == b.id, FeeRecord.last_payment_date >= first_day)) or 0
        due = await db.scalar(select(func.sum(FeeRecord.amount - FeeRecord.paid_amount)).where(FeeRecord.branch_id == b.id, FeeRecord.status.in_(["unpaid","partial"]))) or 0
        branches.append({"branch_id": str(b.id), "name": b.name, "collected_mtd": float(collected), "due_total": float(due)})
        grand_collected += float(collected); grand_due += float(due)
    return {"branches": branches, "total_collected_mtd": grand_collected, "total_due": grand_due}

# ═══ CLASS LIST (for selectors) ═══
@router.get("/classes")
async def list_classes(request: Request, db: AsyncSession = Depends(get_db)):
    user, _ = await get_mobile_user(request, db)
    from models.academic import Class, Section
    r = await db.execute(select(Class).where(Class.branch_id == user.branch_id).order_by(Class.name))
    classes = []
    for c in r.scalars():
        sr = await db.execute(select(Section).where(Section.class_id == c.id))
        sections = [s.name for s in sr.scalars()]
        classes.append({"id": str(c.id), "name": c.name, "sections": sections})
    return {"classes": classes}


# ═══ FEE COLLECTION (Admin) ═══
@router.post("/fee/collect")
async def collect_fee(request: Request, db: AsyncSession = Depends(get_db)):
    """Admin collects fee for a student"""
    user, _ = await get_mobile_user(request, db)
    body = await request.json()
    from models.fee import FeeRecord, PaymentTransaction

    fee_ids = body.get("fee_ids", [])
    payment_mode = body.get("payment_mode", "cash")
    amount = body.get("amount", 0)
    reference = body.get("reference", "")
    student_id = uuid.UUID(body["student_id"])

    updated = 0
    for fid in fee_ids:
        fee = await db.get(FeeRecord, uuid.UUID(fid))
        if fee and fee.student_id == student_id:
            remaining = float(fee.amount) - float(fee.paid_amount)
            if remaining > 0:
                fee.paid_amount = fee.amount  # Mark full paid
                fee.status = "paid"
                fee.last_payment_date = date.today()
                updated += 1

    # Create transaction record
    txn = PaymentTransaction(
        student_id=student_id, branch_id=user.branch_id,
        amount=amount, status="success", gateway=payment_mode,
        collected_by=user.id, transaction_id=reference or str(uuid.uuid4())[:12],
    )
    db.add(txn)
    await db.commit()
    return {"success": True, "updated": updated, "receipt_id": str(txn.id)}


# ═══ NOTIFICATION LIST ═══
@router.get("/notifications")
async def notifications_list(request: Request, db: AsyncSession = Depends(get_db)):
    """Push notification history for current user"""
    user, _ = await get_mobile_user(request, db)
    from models.notification import Notification

    result = await db.execute(
        select(Notification).where(Notification.user_id == user.id).order_by(desc(Notification.created_at)).limit(30))

    items = []
    for n in result.scalars():
        items.append({
            "id": str(n.id), "title": n.title, "body": getattr(n, 'body', ''),
            "type": getattr(n, 'notification_type', 'general'),
            "is_read": getattr(n, 'is_read', False),
            "created_at": n.created_at.isoformat() if n.created_at else '',
        })
    return {"notifications": items}


@router.post("/notifications/{notif_id}/read")
async def mark_notification_read(notif_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    user, _ = await get_mobile_user(request, db)
    from models.notification import Notification
    n = await db.get(Notification, uuid.UUID(notif_id))
    if n and n.user_id == user.id:
        n.is_read = True
        await db.commit()
    return {"success": True}


# ═══ SEND NOTICE (Admin) ═══
@router.post("/announcements/create")
async def create_announcement_mobile(request: Request, db: AsyncSession = Depends(get_db)):
    """Admin creates announcement from mobile"""
    user, _ = await get_mobile_user(request, db)
    body = await request.json()
    from models.announcement import Announcement

    ann = Announcement(
        title=body["title"], message=body.get("message", ""),
        branch_id=user.branch_id, created_by=user.id,
        priority=body.get("priority", "normal"),
        target_audience=body.get("target", "all"),
    )
    db.add(ann)
    await db.commit()
    return {"success": True, "id": str(ann.id)}


# ═══ ID CARD ═══
@router.get("/student/{student_id}/id-card")
async def student_id_card(student_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    """Digital ID card data"""
    user, _ = await get_mobile_user(request, db)
    from models.student import Student, StudentClass

    student = await db.get(Student, uuid.UUID(student_id))
    if not student:
        raise HTTPException(404, "Student not found")

    sc = await db.scalar(select(StudentClass).where(
        StudentClass.student_id == student.id, StudentClass.is_current == True))

    branch = await db.get(Branch, student.branch_id) if student.branch_id else None

    return {
        "name": student.full_name,
        "admission_no": getattr(student, 'admission_no', ''),
        "class_name": sc.class_name if sc else '', "section": sc.section if sc else '',
        "roll_no": sc.roll_no if sc else '',
        "dob": str(getattr(student, 'dob', '')),
        "blood_group": getattr(student, 'blood_group', ''),
        "father_name": getattr(student, 'father_name', ''),
        "phone": getattr(student, 'phone', ''),
        "address": getattr(student, 'address', ''),
        "school_name": branch.name if branch else '',
        "school_address": getattr(branch, 'address', '') if branch else '',
        "school_phone": getattr(branch, 'phone', '') if branch else '',
        "photo_url": getattr(student, 'photo_url', ''),
    }


# ═══════════════════════════════════════════════════════════════
# NEW FEATURES — Sprint A3
# ═══════════════════════════════════════════════════════════════

# ─── 1. QR CODE ATTENDANCE ───
@router.get("/qr/generate/{student_id}")
async def generate_qr_data(student_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    """Generate QR data string for student ID card / attendance"""
    user, _ = await get_mobile_user(request, db)
    from models.student import Student
    s = await db.get(Student, uuid.UUID(student_id))
    if not s: raise HTTPException(404, "Student not found")
    import hashlib, json
    payload = json.dumps({"sid": student_id, "bid": str(s.branch_id), "ts": datetime.utcnow().isoformat()})
    checksum = hashlib.sha256(payload.encode()).hexdigest()[:8]
    return {"qr_data": f"VEDA:{student_id}:{checksum}", "student_name": s.full_name}

@router.post("/qr/scan")
async def scan_qr_attendance(request: Request, db: AsyncSession = Depends(get_db)):
    """Scan QR code to mark check-in/check-out"""
    user, _ = await get_mobile_user(request, db)
    body = await request.json()
    qr_data = body.get("qr_data", "")
    action = body.get("action", "check_in")  # check_in or check_out
    parts = qr_data.split(":")
    if len(parts) < 3 or parts[0] != "VEDA": raise HTTPException(400, "Invalid QR code")
    student_id = parts[1]
    from models.attendance import Attendance
    today = date.today()
    existing = await db.scalar(select(Attendance).where(Attendance.student_id == uuid.UUID(student_id), Attendance.date == today))
    if existing:
        if action == "check_out": existing.check_out_time = datetime.utcnow()
        return {"success": True, "message": f"Already marked. {action} updated.", "student_id": student_id}
    att = Attendance(student_id=uuid.UUID(student_id), date=today, status="present", branch_id=user.branch_id, marked_by=user.id)
    db.add(att)
    await db.commit()
    from models.student import Student
    s = await db.get(Student, uuid.UUID(student_id))
    return {"success": True, "student_name": s.full_name if s else "", "action": action, "time": datetime.utcnow().isoformat()}


# ─── 2. IN-APP MESSAGING ───
@router.get("/messages/threads")
async def get_message_threads(request: Request, db: AsyncSession = Depends(get_db)):
    """Get all message threads for current user"""
    user, _ = await get_mobile_user(request, db)
    from models.messaging import MessageThread, Message, ThreadParticipant
    result = await db.execute(
        select(MessageThread).join(ThreadParticipant, ThreadParticipant.thread_id == MessageThread.id)
        .where(ThreadParticipant.user_id == user.id).order_by(desc(MessageThread.updated_at)).limit(30))
    threads = []
    for t in result.scalars():
        last_msg = await db.scalar(select(Message).where(Message.thread_id == t.id).order_by(desc(Message.created_at)))
        unread = await db.scalar(select(func.count()).select_from(Message).where(
            Message.thread_id == t.id, Message.sender_id != user.id, Message.is_read == False)) or 0
        threads.append({
            "id": str(t.id), "subject": t.subject, "type": getattr(t, 'thread_type', 'direct'),
            "last_message": last_msg.content[:80] if last_msg else "",
            "last_message_time": last_msg.created_at.isoformat() if last_msg else "",
            "unread_count": unread, "participant_name": getattr(t, 'participant_names', ''),
        })
    return {"threads": threads}

@router.get("/messages/thread/{thread_id}")
async def get_thread_messages(thread_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    """Get messages in a thread"""
    user, _ = await get_mobile_user(request, db)
    from models.messaging import Message
    result = await db.execute(
        select(Message).where(Message.thread_id == uuid.UUID(thread_id)).order_by(Message.created_at).limit(100))
    messages = []
    for m in result.scalars():
        messages.append({
            "id": str(m.id), "content": m.content, "sender_id": str(m.sender_id),
            "sender_name": getattr(m, 'sender_name', ''), "is_mine": str(m.sender_id) == str(user.id),
            "created_at": m.created_at.isoformat() if m.created_at else "",
            "is_read": getattr(m, 'is_read', True),
        })
    # Mark all as read
    await db.execute(select(Message).where(Message.thread_id == uuid.UUID(thread_id), Message.sender_id != user.id).update({Message.is_read: True}))
    await db.commit()
    return {"messages": messages, "thread_id": thread_id}

@router.post("/messages/send")
async def send_message(request: Request, db: AsyncSession = Depends(get_db)):
    """Send a message in a thread"""
    user, _ = await get_mobile_user(request, db)
    body = await request.json()
    from models.messaging import Message, MessageThread
    thread_id = body.get("thread_id")
    if not thread_id:
        # Create new thread
        thread = MessageThread(subject=body.get("subject", ""), created_by=user.id, branch_id=user.branch_id)
        db.add(thread)
        await db.flush()
        thread_id = str(thread.id)
    msg = Message(thread_id=uuid.UUID(thread_id), sender_id=user.id, content=body["content"])
    db.add(msg)
    # Update thread timestamp
    t = await db.get(MessageThread, uuid.UUID(thread_id))
    if t: t.updated_at = datetime.utcnow()
    await db.commit()
    return {"success": True, "message_id": str(msg.id), "thread_id": thread_id}


# ─── 3. PHOTO GALLERY ───
@router.get("/gallery")
async def get_gallery(request: Request, db: AsyncSession = Depends(get_db)):
    """School photo gallery — events, activities"""
    user, _ = await get_mobile_user(request, db)
    try:
        from models.content import DigitalContent
        result = await db.execute(
            select(DigitalContent).where(DigitalContent.branch_id == user.branch_id, DigitalContent.content_type == "photo")
            .order_by(desc(DigitalContent.created_at)).limit(50))
        photos = [{"id": str(p.id), "title": getattr(p, 'title', ''), "url": p.file_url,
                    "event": getattr(p, 'event_name', ''), "date": p.created_at.isoformat() if p.created_at else ""} for p in result.scalars()]
    except:
        photos = []
    # Also get from school events
    try:
        from models.event import SchoolEvent
        events = await db.execute(
            select(SchoolEvent).where(SchoolEvent.branch_id == user.branch_id).order_by(desc(SchoolEvent.event_date)).limit(20))
        albums = [{"id": str(e.id), "title": e.title, "date": str(e.event_date) if e.event_date else "",
                    "photo_count": getattr(e, 'photo_count', 0), "cover_url": getattr(e, 'cover_photo', '')} for e in events.scalars()]
    except:
        albums = []
    return {"photos": photos, "albums": albums}


# ─── 4. STUDENT LEAVE APPLY ───
@router.get("/student-leave/{student_id}")
async def get_student_leaves(student_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    """Get leave history for a student"""
    user, _ = await get_mobile_user(request, db)
    from models.student import StudentLeave
    result = await db.execute(
        select(StudentLeave).where(StudentLeave.student_id == uuid.UUID(student_id)).order_by(desc(StudentLeave.created_at)).limit(20))
    leaves = [{"id": str(l.id), "type": getattr(l, 'leave_type', 'casual'), "from_date": str(l.from_date), "to_date": str(l.to_date),
               "reason": l.reason, "status": l.status, "days": (l.to_date - l.from_date).days + 1 if l.from_date and l.to_date else 1} for l in result.scalars()]
    return {"leaves": leaves}

@router.post("/student-leave/apply")
async def apply_student_leave(request: Request, db: AsyncSession = Depends(get_db)):
    """Parent applies leave for child"""
    user, _ = await get_mobile_user(request, db)
    body = await request.json()
    from models.student import StudentLeave
    leave = StudentLeave(
        student_id=uuid.UUID(body["student_id"]), applied_by=user.id, branch_id=user.branch_id,
        leave_type=body.get("type", "casual"), from_date=date.fromisoformat(body["from_date"]),
        to_date=date.fromisoformat(body["to_date"]), reason=body.get("reason", ""), status="pending")
    db.add(leave)
    await db.commit()
    return {"success": True, "id": str(leave.id)}


# ─── 5. SALARY SLIP ───
@router.get("/salary-slips")
async def get_salary_slips(request: Request, db: AsyncSession = Depends(get_db)):
    """Teacher views own salary slips"""
    user, _ = await get_mobile_user(request, db)
    from models.hr import SalarySlip
    result = await db.execute(
        select(SalarySlip).where(SalarySlip.employee_id == user.id).order_by(desc(SalarySlip.month)).limit(12))
    slips = [{"id": str(s.id), "month": str(s.month), "year": getattr(s, 'year', ''),
              "basic": float(getattr(s, 'basic_pay', 0)), "hra": float(getattr(s, 'hra', 0)),
              "da": float(getattr(s, 'da', 0)), "other_allowance": float(getattr(s, 'other_allowance', 0)),
              "pf": float(getattr(s, 'pf_deduction', 0)), "tax": float(getattr(s, 'tax_deduction', 0)),
              "other_deduction": float(getattr(s, 'other_deduction', 0)),
              "gross": float(getattr(s, 'gross_salary', 0)), "net": float(getattr(s, 'net_salary', 0)),
              "status": getattr(s, 'status', 'paid'), "pdf_url": getattr(s, 'pdf_url', '')} for s in result.scalars()]
    return {"slips": slips}


# ─── 6. CERTIFICATES ───
@router.get("/certificates/{student_id}")
async def get_certificates(student_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    """Certificates issued to a student"""
    user, _ = await get_mobile_user(request, db)
    from models.certificate import Certificate
    result = await db.execute(
        select(Certificate).where(Certificate.student_id == uuid.UUID(student_id)).order_by(desc(Certificate.created_at)))
    certs = [{"id": str(c.id), "type": c.certificate_type, "title": getattr(c, 'title', c.certificate_type),
              "issued_date": str(c.created_at.date()) if c.created_at else "", "pdf_url": getattr(c, 'pdf_url', '')} for c in result.scalars()]
    return {"certificates": certs}


# ─── 7. ACHIEVEMENTS & BADGES ───
@router.get("/achievements/{student_id}")
async def get_achievements(student_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    """Badges, awards, achievements for a student"""
    user, _ = await get_mobile_user(request, db)
    from models.student import StudentAchievement
    result = await db.execute(
        select(StudentAchievement).where(StudentAchievement.student_id == uuid.UUID(student_id)).order_by(desc(StudentAchievement.created_at)))
    items = [{"id": str(a.id), "title": a.title, "description": getattr(a, 'description', ''),
              "category": getattr(a, 'category', 'academic'), "date": str(a.created_at.date()) if a.created_at else "",
              "badge_icon": getattr(a, 'badge_icon', '🏆')} for a in result.scalars()]
    return {"achievements": items}


# ─── 8. STUDENT REMARKS ───
@router.get("/remarks/{student_id}")
async def get_remarks(student_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    """Teacher remarks about student — behavior, appreciation"""
    user, _ = await get_mobile_user(request, db)
    from models.student import StudentRemark
    result = await db.execute(
        select(StudentRemark).where(StudentRemark.student_id == uuid.UUID(student_id)).order_by(desc(StudentRemark.created_at)).limit(30))
    remarks = [{"id": str(r.id), "type": getattr(r, 'remark_type', 'general'), "content": r.content,
                "teacher": getattr(r, 'teacher_name', ''), "date": str(r.created_at.date()) if r.created_at else "",
                "category": getattr(r, 'category', ''), "is_positive": getattr(r, 'is_positive', True)} for r in result.scalars()]
    return {"remarks": remarks}


# ─── 9. HOMEWORK SUBMISSION ───
@router.post("/homework/{homework_id}/submit")
async def submit_homework(homework_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    """Student submits homework (text or file reference)"""
    user, _ = await get_mobile_user(request, db)
    body = await request.json()
    from models.homework import HomeworkSubmission
    sub = HomeworkSubmission(
        homework_id=uuid.UUID(homework_id), student_id=uuid.UUID(body["student_id"]),
        content=body.get("content", ""), file_url=body.get("file_url", ""))
    db.add(sub)
    await db.commit()
    return {"success": True, "id": str(sub.id)}


# ─── 10. EXAM SCHEDULE ───
@router.get("/exam-schedule")
async def get_exam_schedule(request: Request, db: AsyncSession = Depends(get_db)):
    """Upcoming exam dates and schedule"""
    user, _ = await get_mobile_user(request, db)
    from models.exam import Exam, ExamSubject
    result = await db.execute(
        select(Exam).where(Exam.branch_id == user.branch_id).order_by(desc(Exam.created_at)).limit(10))
    exams = []
    for e in result.scalars():
        subs = await db.execute(select(ExamSubject).where(ExamSubject.exam_id == e.id).order_by(ExamSubject.exam_date))
        subjects = [{"name": s.subject_name, "date": str(s.exam_date) if s.exam_date else "",
                      "start_time": str(getattr(s, 'start_time', '')), "max_marks": s.max_marks} for s in subs.scalars()]
        exams.append({"id": str(e.id), "name": e.name, "type": getattr(e, 'exam_type', ''),
                       "start_date": str(getattr(e, 'start_date', '')), "end_date": str(getattr(e, 'end_date', '')),
                       "subjects": subjects})
    return {"exams": exams}


# ─── 11. SCHOOL EVENTS ───
@router.get("/events")
async def get_events(request: Request, db: AsyncSession = Depends(get_db)):
    """School events calendar"""
    user, _ = await get_mobile_user(request, db)
    from models.event import SchoolEvent
    result = await db.execute(
        select(SchoolEvent).where(SchoolEvent.branch_id == user.branch_id).order_by(SchoolEvent.event_date).limit(30))
    events = [{"id": str(e.id), "title": e.title, "description": getattr(e, 'description', ''),
               "date": str(e.event_date) if e.event_date else "", "time": str(getattr(e, 'event_time', '')),
               "venue": getattr(e, 'venue', ''), "type": getattr(e, 'event_type', 'general'),
               "is_holiday": getattr(e, 'is_holiday', False)} for e in result.scalars()]
    return {"events": events}


# ─── 12. REPORT CARD PDF ───
@router.get("/report-card/{student_id}/{exam_id}")
async def get_report_card_url(student_id: str, exam_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    """Get report card PDF URL for a student/exam"""
    user, _ = await get_mobile_user(request, db)
    # Build PDF URL (assumes web endpoint exists)
    pdf_url = f"/api/results/report-card-pdf?student_id={student_id}&exam_id={exam_id}"
    return {"pdf_url": pdf_url, "student_id": student_id, "exam_id": exam_id}


# ─── 13. PAYMENT RECEIPT ───
@router.get("/receipt/{transaction_id}")
async def get_receipt(transaction_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    """Get payment receipt data"""
    user, _ = await get_mobile_user(request, db)
    from models.fee import PaymentTransaction
    t = await db.get(PaymentTransaction, uuid.UUID(transaction_id))
    if not t: raise HTTPException(404, "Transaction not found")
    return {"receipt_id": str(t.id), "amount": float(t.amount), "date": t.created_at.isoformat() if t.created_at else "",
            "status": t.status, "gateway": getattr(t, 'gateway', ''), "student_name": getattr(t, 'student_name', ''),
            "fee_type": getattr(t, 'fee_type', ''), "transaction_id": getattr(t, 'transaction_id', ''),
            "pdf_url": f"/api/certificates/pdf/{transaction_id}"}


# ─── 14. SYLLABUS PROGRESS ───
@router.get("/syllabus")
async def get_syllabus(request: Request, class_id: str = Query(None), subject_id: str = Query(None), db: AsyncSession = Depends(get_db)):
    """Chapter-wise syllabus completion tracking"""
    user, _ = await get_mobile_user(request, db)
    from models.academic import Syllabus
    query = select(Syllabus).where(Syllabus.branch_id == user.branch_id)
    if class_id: query = query.where(Syllabus.class_id == uuid.UUID(class_id))
    if subject_id: query = query.where(Syllabus.subject_id == uuid.UUID(subject_id))
    result = await db.execute(query.order_by(Syllabus.chapter_number))
    chapters = [{"id": str(c.id), "chapter_number": c.chapter_number, "title": c.title,
                  "is_completed": getattr(c, 'is_completed', False), "completed_date": str(getattr(c, 'completed_date', '')),
                  "subject": getattr(c, 'subject_name', '')} for c in result.scalars()]
    total = len(chapters)
    done = sum(1 for c in chapters if c["is_completed"])
    return {"chapters": chapters, "total": total, "completed": done, "percentage": round(done/total*100, 1) if total else 0}
