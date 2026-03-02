"""
Student Login ID Generator v3.0
PO-Approved Format: <SchoolCode><YY><RunningNumber>
Examples: GNK24123, CNV251, DPS2610249

This module is imported by school_admin_api.py during student creation.
Also provides admin endpoints for stats and backfill.
"""
from fastapi import APIRouter, Request, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text, func
from database import get_db
from utils.permissions import require_role
from models.user import UserRole
import uuid

router = APIRouter(prefix="/api/school/student-login-id", tags=["Student Login ID"])


async def _get_school_code(db, branch_id: str) -> str:
    """Get branch code, cleaned for use in login ID."""
    row = (await db.execute(
        text("SELECT code, name FROM branches WHERE id = :bid"),
        {"bid": branch_id}
    )).mappings().first()

    if row and row['code']:
        # Clean: remove dashes, spaces, keep only alphanumeric, uppercase
        code = ''.join(c for c in row['code'] if c.isalnum()).upper()
        if code:
            return code

    # Fallback: first 3 chars of branch name
    if row and row['name']:
        return ''.join(c for c in row['name'] if c.isalpha())[:3].upper() or "VSP"

    return "VSP"


async def _get_next_seq(db, branch_id: str, year_2digit: str) -> int:
    """Get the next sequence number for this branch+year combination."""
    # Count existing students with same prefix pattern
    school_code = await _get_school_code(db, branch_id)
    prefix = f"{school_code}{year_2digit}"

    # Find the highest existing sequence for this prefix
    result = await db.execute(
        text("""
            SELECT student_login_id FROM students
            WHERE branch_id = :bid
              AND student_login_id LIKE :prefix || '%'
              AND student_login_id IS NOT NULL
            ORDER BY LENGTH(student_login_id) DESC, student_login_id DESC
            LIMIT 1
        """),
        {"bid": branch_id, "prefix": prefix}
    )
    last_id = result.scalar()

    if last_id:
        # Extract the numeric suffix
        suffix = last_id[len(prefix):]
        try:
            return int(suffix) + 1
        except ValueError:
            pass

    # No existing IDs — start at 1
    return 1


async def generate_student_login_id(db, branch_id: str, admission_year: int = None) -> str:
    """
    Generate a unique Student Login ID.
    Format: <SchoolCode><YY><RunningNumber>
    Called during student admission.
    """
    from datetime import date

    if admission_year is None:
        admission_year = date.today().year

    year_2digit = str(admission_year)[-2:]
    school_code = await _get_school_code(db, branch_id)
    seq = await _get_next_seq(db, str(branch_id), year_2digit)

    login_id = f"{school_code}{year_2digit}{seq}"

    # Verify uniqueness (handle race conditions)
    for attempt in range(5):
        exists = (await db.execute(
            text("SELECT COUNT(*) FROM students WHERE branch_id = :bid AND student_login_id = :lid"),
            {"bid": str(branch_id), "lid": login_id}
        )).scalar() or 0

        if exists == 0:
            return login_id

        seq += 1
        login_id = f"{school_code}{year_2digit}{seq}"

    # Extremely unlikely — return with timestamp suffix
    import time
    return f"{school_code}{year_2digit}{int(time.time()) % 100000}"


# ─── ADMIN ENDPOINTS ───

@router.get("/stats")
@require_role(UserRole.SCHOOL_ADMIN)
async def login_id_stats(request: Request, db: AsyncSession = Depends(get_db)):
    """Statistics about student login IDs in this branch."""
    branch_id = request.state.user.get("branch_id")

    total = (await db.execute(
        text("SELECT COUNT(*) FROM students WHERE branch_id = :bid AND is_active = true"),
        {"bid": branch_id}
    )).scalar() or 0

    with_id = (await db.execute(
        text("SELECT COUNT(*) FROM students WHERE branch_id = :bid AND is_active = true AND student_login_id IS NOT NULL AND student_login_id != ''"),
        {"bid": branch_id}
    )).scalar() or 0

    without_id = total - with_id

    samples = (await db.execute(
        text("SELECT student_login_id FROM students WHERE branch_id = :bid AND student_login_id IS NOT NULL ORDER BY student_login_id LIMIT 10"),
        {"bid": branch_id}
    )).scalars().all()

    school_code = await _get_school_code(db, branch_id)

    return {
        "total_students": total,
        "with_login_id": with_id,
        "without_login_id": without_id,
        "coverage_pct": round(with_id / total * 100, 1) if total > 0 else 0,
        "sample_ids": list(samples),
        "school_code": school_code,
        "needs_backfill": without_id > 0,
    }


@router.post("/backfill")
@require_role(UserRole.SCHOOL_ADMIN)
async def backfill_login_ids(request: Request, db: AsyncSession = Depends(get_db)):
    """Generate login IDs for all students who don't have one."""
    branch_id = request.state.user.get("branch_id")

    rows = (await db.execute(
        text("""
            SELECT id, COALESCE(admission_date, created_at) as adm_date
            FROM students
            WHERE branch_id = :bid
              AND (student_login_id IS NULL OR student_login_id = '')
              AND is_active = true
            ORDER BY COALESCE(admission_date, created_at)
        """),
        {"bid": branch_id}
    )).mappings().all()

    if not rows:
        return {"success": True, "filled": 0, "message": "All students already have login IDs"}

    filled = 0
    for row in rows:
        adm_year = row['adm_date'].year if row['adm_date'] else None
        login_id = await generate_student_login_id(db, branch_id, adm_year)

        await db.execute(
            text("UPDATE students SET student_login_id = :lid WHERE id = :sid"),
            {"lid": login_id, "sid": str(row['id'])}
        )
        filled += 1

    await db.commit()

    return {
        "success": True,
        "filled": filled,
        "message": f"Generated login IDs for {filled} students",
    }


@router.get("/preview")
@require_role(UserRole.SCHOOL_ADMIN)
async def preview_next_ids(request: Request, db: AsyncSession = Depends(get_db)):
    """Preview what the next 5 login IDs would look like."""
    branch_id = request.state.user.get("branch_id")
    from datetime import date

    school_code = await _get_school_code(db, branch_id)
    year_2digit = str(date.today().year)[-2:]
    seq = await _get_next_seq(db, branch_id, year_2digit)

    previews = [f"{school_code}{year_2digit}{seq + i}" for i in range(5)]

    return {
        "school_code": school_code,
        "year": year_2digit,
        "next_sequence": seq,
        "previews": previews,
    }