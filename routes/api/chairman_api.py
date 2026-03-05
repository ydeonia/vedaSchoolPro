"""
Chairman / Trustee API — Organization-level oversight across all branches.
Read-only aggregated data for the Command Tower dashboard.
Uses parameterized queries throughout for SQL injection protection.
"""
import uuid
from datetime import datetime, date, timedelta
from fastapi import APIRouter, Request, Depends, HTTPException
from sqlalchemy import select, func, text, and_, or_, case, literal_column
from sqlalchemy.ext.asyncio import AsyncSession
from database import get_db
from models.user import User, UserRole
from models.branch import Branch
from models.student import Student
from models.teacher import Teacher
from models.attendance import Attendance, AttendanceStatus
from models.fee import FeeRecord, PaymentStatus

router = APIRouter(prefix="/api/chairman", tags=["Chairman"])


def require_chairman(func):
    """Decorator: only chairman or super_admin can access."""
    from functools import wraps
    from utils.auth import decode_access_token
    @wraps(func)
    async def wrapper(request: Request, *args, **kwargs):
        token = request.cookies.get("access_token")
        if not token:
            raise HTTPException(401, "Not authenticated")
        user = decode_access_token(token)
        if not user:
            raise HTTPException(401, "Invalid or expired token")
        role = (user.get("role") or "").lower()
        if role not in ("chairman", "super_admin"):
            raise HTTPException(403, "Chairman access required")
        request.state.user = user
        return await func(request, *args, **kwargs)
    return wrapper


@router.get("/pulse")
@require_chairman
async def morning_pulse(request: Request, db: AsyncSession = Depends(get_db)):
    """Morning Pulse — single-glance overview of entire org."""
    user = request.state.user
    org_id = user.get("org_id")
    if not org_id:
        return {"error": "No organization assigned"}
    today = date.today()
    month_start = today.replace(day=1)

    # Get all branches using ORM
    branches_result = await db.execute(
        select(Branch.id, Branch.name, Branch.city)
        .where(Branch.org_id == org_id, Branch.is_active == True)
    )
    branches = branches_result.all()
    branch_ids = [b.id for b in branches]

    if not branch_ids:
        return {
            "branches": 0, "total_students": 0, "total_teachers": 0, "total_staff": 0,
            "present_today": 0, "attendance_pct": 0, "fee_this_month": 0, "alerts": [],
            "total_employees": 0, "date": today.isoformat(), "org_id": org_id,
        }

    # Total students — parameterized
    total_students = (await db.execute(
        select(func.count()).select_from(Student)
        .where(Student.branch_id.in_(branch_ids), Student.is_active == True)
    )).scalar() or 0

    # Total teachers — parameterized
    total_teachers = (await db.execute(
        select(func.count()).select_from(Teacher)
        .where(Teacher.branch_id.in_(branch_ids), Teacher.is_active == True)
    )).scalar() or 0

    # Total employees (non-teaching) — parameterized
    total_employees = 0
    try:
        from models.mega_modules import Employee
        total_employees = (await db.execute(
            select(func.count()).select_from(Employee)
            .where(Employee.branch_id.in_(branch_ids), Employee.is_active == True)
        )).scalar() or 0
    except Exception:
        pass

    # Today's attendance — parameterized
    present_today = (await db.execute(
        select(func.count()).select_from(Attendance)
        .where(
            Attendance.branch_id.in_(branch_ids),
            Attendance.date == today,
            Attendance.status.in_([AttendanceStatus.PRESENT, AttendanceStatus.LATE])
        )
    )).scalar() or 0

    att_pct = round((present_today / total_students * 100), 1) if total_students > 0 else 0

    # Fee collected this month — parameterized
    fee_this_month = (await db.execute(
        select(func.coalesce(func.sum(FeeRecord.amount_paid), 0))
        .where(
            FeeRecord.branch_id.in_(branch_ids),
            FeeRecord.payment_date >= month_start
        )
    )).scalar() or 0

    # Alerts
    alerts = []

    # Separation request alerts
    try:
        from models.mega_modules import SeparationRequest
        sep_count = (await db.execute(
            select(func.count()).select_from(SeparationRequest)
            .where(SeparationRequest.branch_id.in_(branch_ids), SeparationRequest.status == "PENDING")
        )).scalar() or 0
        if sep_count > 0:
            alerts.append({"type": "warning", "text": f"{sep_count} separation request(s) pending approval"})
    except Exception:
        pass

    # Fee due alert — parameterized
    try:
        total_due = float((await db.execute(
            select(func.coalesce(func.sum(FeeRecord.amount_due - FeeRecord.amount_paid), 0))
            .where(
                FeeRecord.branch_id.in_(branch_ids),
                FeeRecord.status.in_([PaymentStatus.PENDING, PaymentStatus.PARTIAL, PaymentStatus.OVERDUE])
            )
        )).scalar() or 0)
        if total_due > 0:
            alerts.append({"type": "info", "text": f"₹{total_due:,.0f} total fee pending across branches"})
    except Exception:
        pass

    return {
        "branches": len(branches),
        "total_students": total_students,
        "total_teachers": total_teachers,
        "total_employees": total_employees,
        "total_staff": total_teachers + total_employees,
        "present_today": present_today,
        "attendance_pct": att_pct,
        "fee_this_month": float(fee_this_month),
        "alerts": alerts,
        "date": today.isoformat(),
        "org_id": org_id,
    }


@router.get("/branch-scorecard")
@require_chairman
async def branch_scorecard(request: Request, db: AsyncSession = Depends(get_db)):
    """Comparative scorecard across all branches."""
    user = request.state.user
    org_id = user.get("org_id")
    today = date.today()
    month_start = today.replace(day=1)

    branches = (await db.execute(
        select(Branch.id, Branch.name, Branch.city, Branch.phone)
        .where(Branch.org_id == org_id, Branch.is_active == True)
        .order_by(Branch.name)
    )).all()

    scorecard = []
    for b in branches:
        bid = b.id

        # Students — ORM parameterized
        students = (await db.execute(
            select(func.count()).select_from(Student)
            .where(Student.branch_id == bid, Student.is_active == True)
        )).scalar() or 0

        # Teachers — ORM parameterized
        teachers = (await db.execute(
            select(func.count()).select_from(Teacher)
            .where(Teacher.branch_id == bid, Teacher.is_active == True)
        )).scalar() or 0

        # Attendance today — ORM parameterized
        present = (await db.execute(
            select(func.count()).select_from(Attendance)
            .where(
                Attendance.branch_id == bid,
                Attendance.date == today,
                Attendance.status.in_([AttendanceStatus.PRESENT, AttendanceStatus.LATE])
            )
        )).scalar() or 0
        att_pct = round(present / students * 100, 1) if students > 0 else 0

        # Fee collected this month — ORM parameterized
        fee_month = float((await db.execute(
            select(func.coalesce(func.sum(FeeRecord.amount_paid), 0))
            .where(FeeRecord.branch_id == bid, FeeRecord.payment_date >= month_start)
        )).scalar() or 0)

        # New admissions this month — ORM parameterized
        new_admissions = (await db.execute(
            select(func.count()).select_from(Student)
            .where(Student.branch_id == bid, Student.admission_date >= month_start)
        )).scalar() or 0

        # TCs this month — ORM parameterized
        tcs = 0
        try:
            from models.student import AdmissionStatus
            tcs = (await db.execute(
                select(func.count()).select_from(Student)
                .where(
                    Student.branch_id == bid,
                    Student.admission_status.in_([
                        AdmissionStatus.TC_ISSUED, AdmissionStatus.LEFT, AdmissionStatus.WITHDRAWN
                    ]),
                    Student.updated_at >= month_start
                )
            )).scalar() or 0
        except Exception:
            pass

        ratio = round(students / teachers, 1) if teachers > 0 else 0

        scorecard.append({
            "id": str(bid),
            "name": b.name,
            "city": b.city or "",
            "students": students,
            "teachers": teachers,
            "ratio": ratio,
            "attendance_pct": att_pct,
            "fee_collected": fee_month,
            "new_admissions": new_admissions,
            "withdrawals": tcs,
        })

    return {"scorecard": scorecard, "date": today.isoformat()}


@router.get("/revenue")
@require_chairman
async def revenue_overview(request: Request, db: AsyncSession = Depends(get_db)):
    """Revenue overview — monthly collection across branches."""
    user = request.state.user
    org_id = user.get("org_id")
    today = date.today()
    month_start = today.replace(day=1)

    branches = (await db.execute(
        select(Branch.id, Branch.name)
        .where(Branch.org_id == org_id, Branch.is_active == True)
        .order_by(Branch.name)
    )).all()

    revenue_data = []
    total_collected = 0
    total_pending = 0

    for b in branches:
        bid = b.id

        # Monthly collection — ORM parameterized
        collected = float((await db.execute(
            select(func.coalesce(func.sum(FeeRecord.amount_paid), 0))
            .where(FeeRecord.branch_id == bid, FeeRecord.payment_date >= month_start)
        )).scalar() or 0)

        # Pending fees — ORM parameterized
        pending = float((await db.execute(
            select(func.coalesce(func.sum(FeeRecord.amount_due - FeeRecord.amount_paid), 0))
            .where(
                FeeRecord.branch_id == bid,
                FeeRecord.status.in_([PaymentStatus.PENDING, PaymentStatus.PARTIAL, PaymentStatus.OVERDUE])
            )
        )).scalar() or 0)

        total_collected += collected
        total_pending += pending

        revenue_data.append({
            "branch": b.name,
            "collected": collected,
            "pending": pending,
        })

    return {
        "branches": revenue_data,
        "total_collected": total_collected,
        "total_pending": total_pending,
        "month": today.strftime("%B %Y"),
    }
