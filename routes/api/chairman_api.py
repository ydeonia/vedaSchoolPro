"""
Chairman / Trustee API — Organization-level oversight across all branches.
Read-only aggregated data for the Command Tower dashboard.
"""
import uuid
from datetime import datetime, date, timedelta
from fastapi import APIRouter, Request, Depends, HTTPException
from sqlalchemy import select, func, text, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession
from database import get_db
from models.user import User, UserRole

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

    # Get all branches in this org
    branches = (await db.execute(
        text("SELECT id, name, city FROM branches WHERE org_id = :oid AND is_active = true"),
        {"oid": org_id}
    )).mappings().all()
    branch_ids = [str(b['id']) for b in branches]

    if not branch_ids:
        return {"branches": 0, "total_students": 0, "total_teachers": 0, "total_staff": 0,
                "present_today": 0, "attendance_pct": 0, "fee_this_month": 0, "alerts": [],
                "total_employees": 0, "date": today.isoformat(), "org_id": org_id}

    bid_list = ",".join(f"'{b}'" for b in branch_ids)

    # Total students — use is_active flag instead of enum
    total_students = 0
    try:
        total_students = (await db.execute(
            text(f"SELECT COUNT(*) FROM students WHERE branch_id IN ({bid_list}) AND is_active = true")
        )).scalar() or 0
    except Exception:
        try:
            total_students = (await db.execute(
                text(f"SELECT COUNT(*) FROM students WHERE branch_id IN ({bid_list})")
            )).scalar() or 0
        except Exception:
            pass

    # Total teachers
    total_teachers = 0
    try:
        total_teachers = (await db.execute(
            text(f"SELECT COUNT(*) FROM teachers WHERE branch_id IN ({bid_list}) AND is_active = true")
        )).scalar() or 0
    except Exception:
        pass

    # Total employees (non-teaching)
    total_employees = 0
    try:
        total_employees = (await db.execute(
            text(f"SELECT COUNT(*) FROM employees WHERE branch_id IN ({bid_list}) AND is_active = true")
        )).scalar() or 0
    except Exception:
        pass

    # Today's attendance — try both cases
    present_today = 0
    try:
        present_today = (await db.execute(
            text(f"SELECT COUNT(*) FROM student_attendance WHERE branch_id IN ({bid_list}) AND date = :d AND UPPER(status::text) = 'PRESENT'"),
            {"d": today}
        )).scalar() or 0
    except Exception:
        pass

    att_pct = round((present_today / total_students * 100), 1) if total_students > 0 else 0

    # Fee collected this month
    month_start = today.replace(day=1)
    fee_this_month = 0
    try:
        fee_this_month = (await db.execute(
            text(f"SELECT COALESCE(SUM(amount), 0) FROM fee_payments WHERE branch_id IN ({bid_list}) AND payment_date >= :ms"),
            {"ms": month_start}
        )).scalar() or 0
    except Exception:
        pass

    # Alerts
    alerts = []
    try:
        sep_count = (await db.execute(
            text(f"SELECT COUNT(*) FROM separation_requests WHERE branch_id IN ({bid_list}) AND UPPER(status::text) = 'PENDING'")
        )).scalar() or 0
        if sep_count > 0:
            alerts.append({"type": "warning", "text": f"{sep_count} separation request(s) pending approval"})
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
        "org_id": org_id
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
        text("SELECT id, name, city, phone FROM branches WHERE org_id = :oid AND is_active = true ORDER BY name"),
        {"oid": org_id}
    )).mappings().all()

    scorecard = []
    for b in branches:
        bid = str(b['id'])

        # Students — use is_active
        students = 0
        try:
            students = (await db.execute(
                text("SELECT COUNT(*) FROM students WHERE branch_id = :bid AND is_active = true"),
                {"bid": bid}
            )).scalar() or 0
        except Exception:
            try:
                students = (await db.execute(
                    text("SELECT COUNT(*) FROM students WHERE branch_id = :bid"),
                    {"bid": bid}
                )).scalar() or 0
            except Exception:
                pass

        # Teachers
        teachers = 0
        try:
            teachers = (await db.execute(
                text("SELECT COUNT(*) FROM teachers WHERE branch_id = :bid AND is_active = true"),
                {"bid": bid}
            )).scalar() or 0
        except Exception:
            pass

        # Attendance today — case insensitive
        present = 0
        try:
            present = (await db.execute(
                text("SELECT COUNT(*) FROM student_attendance WHERE branch_id = :bid AND date = :d AND UPPER(status::text) = 'PRESENT'"),
                {"bid": bid, "d": today}
            )).scalar() or 0
        except Exception:
            pass
        att_pct = round(present / students * 100, 1) if students > 0 else 0

        # Fee collected this month
        fee_month = 0
        try:
            fee_month = float((await db.execute(
                text("SELECT COALESCE(SUM(amount), 0) FROM fee_payments WHERE branch_id = :bid AND payment_date >= :ms"),
                {"bid": bid, "ms": month_start}
            )).scalar() or 0)
        except Exception:
            pass

        # New admissions this month
        new_admissions = 0
        try:
            new_admissions = (await db.execute(
                text("SELECT COUNT(*) FROM students WHERE branch_id = :bid AND date_of_admission >= :ms"),
                {"bid": bid, "ms": month_start}
            )).scalar() or 0
        except Exception:
            pass

        # TCs this month — case insensitive
        tcs = 0
        try:
            tcs = (await db.execute(
                text("SELECT COUNT(*) FROM students WHERE branch_id = :bid AND UPPER(admission_status::text) IN ('TC_ISSUED','LEFT','WITHDRAWN') AND updated_at >= :ms"),
                {"bid": bid, "ms": month_start}
            )).scalar() or 0
        except Exception:
            pass

        ratio = round(students / teachers, 1) if teachers > 0 else 0

        scorecard.append({
            "id": bid,
            "name": b['name'],
            "city": b['city'] or '',
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

    branches = (await db.execute(
        text("SELECT id, name FROM branches WHERE org_id = :oid AND is_active = true ORDER BY name"),
        {"oid": org_id}
    )).mappings().all()

    revenue_data = []
    total_collected = 0
    total_pending = 0

    for b in branches:
        bid = str(b['id'])
        month_start = today.replace(day=1)

        # Monthly collection
        collected = 0
        try:
            collected = float((await db.execute(
                text("SELECT COALESCE(SUM(amount), 0) FROM fee_payments WHERE branch_id = :bid AND payment_date >= :ms"),
                {"bid": bid, "ms": month_start}
            )).scalar() or 0)
        except Exception:
            pass

        # Pending fees — case insensitive
        pending = 0
        try:
            pending = float((await db.execute(
                text("SELECT COALESCE(SUM(balance), 0) FROM fee_invoices WHERE branch_id = :bid AND UPPER(status::text) IN ('UNPAID', 'PARTIAL', 'PENDING', 'OVERDUE')"),
                {"bid": bid}
            )).scalar() or 0)
        except Exception:
            pass

        total_collected += collected
        total_pending += pending

        revenue_data.append({
            "branch": b['name'],
            "collected": collected,
            "pending": pending,
        })

    return {
        "branches": revenue_data,
        "total_collected": total_collected,
        "total_pending": total_pending,
        "month": today.strftime("%B %Y")
    }