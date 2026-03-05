"""
VedaFlow Fee Engine — Shared fee generation, overdue marking, late fee application.
Used by both the manual API endpoints and the automated scheduler.
"""
import logging
from datetime import date, timedelta
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger("fee_engine")


async def generate_fees_for_class(
    db: AsyncSession,
    branch_id,
    class_id,
    month: int,
    year: int,
    section_id=None,
) -> int:
    """Generate fee records for all students in a class for a given month.
    Returns count of records generated."""
    from models.fee import FeeStructure, FeeRecord, PaymentStatus
    from models.student import Student
    import uuid

    # Get fee structures for this class
    q = select(FeeStructure).where(
        FeeStructure.branch_id == branch_id,
        FeeStructure.is_active == True,
        (FeeStructure.class_id == class_id) | (FeeStructure.class_id == None),
    )
    fees = (await db.execute(q)).scalars().all()
    if not fees:
        return 0

    # Get active students
    sq = select(Student).where(
        Student.branch_id == branch_id,
        Student.class_id == class_id,
        Student.is_active == True,
    )
    if section_id:
        sq = sq.where(Student.section_id == section_id)
    students = (await db.execute(sq)).scalars().all()

    generated = 0
    for student in students:
        # Check for active waivers
        try:
            from models.mega_modules import FeeWaiver
            active_waivers = (await db.execute(
                select(FeeWaiver).where(
                    FeeWaiver.student_id == student.id,
                    FeeWaiver.status == "active",
                    (FeeWaiver.valid_to == None) | (FeeWaiver.valid_to >= date(year, month, 1)),
                )
            )).scalars().all()
        except Exception:
            active_waivers = []

        for fee in fees:
            due_date = date(year, month, min(fee.due_day or 10, 28))

            # Check if already exists
            existing = await db.execute(
                select(FeeRecord).where(
                    FeeRecord.student_id == student.id,
                    FeeRecord.fee_structure_id == fee.id,
                    FeeRecord.due_date == due_date,
                )
            )
            if existing.scalar_one_or_none():
                continue

            # Calculate amount after waiver
            amount = float(fee.amount)
            for w in active_waivers:
                if w.discount_type == "percentage":
                    amount = amount - (amount * (w.discount_value / 100))
                elif w.discount_type == "fixed":
                    amount = max(0, amount - w.discount_value)

            rec = FeeRecord(
                student_id=student.id,
                fee_structure_id=fee.id,
                branch_id=branch_id,
                amount_due=amount,
                due_date=due_date,
                status=PaymentStatus.PENDING,
            )
            db.add(rec)
            generated += 1

    await db.flush()
    return generated


async def mark_overdue_fees(db: AsyncSession, branch_id) -> int:
    """Mark PENDING fees past due date as OVERDUE. Returns count."""
    from models.fee import FeeRecord, PaymentStatus

    today = date.today()
    result = await db.execute(
        select(FeeRecord).where(
            FeeRecord.branch_id == branch_id,
            FeeRecord.status.in_([PaymentStatus.PENDING, PaymentStatus.PARTIAL]),
            FeeRecord.due_date < today,
        )
    )
    records = result.scalars().all()
    count = 0
    for rec in records:
        if rec.status == PaymentStatus.PENDING:
            rec.status = PaymentStatus.OVERDUE
            count += 1
    await db.flush()
    return count


async def apply_late_fees(db: AsyncSession, branch_id, late_fee_pct: float, late_fee_after_days: int) -> int:
    """Apply late fee to overdue records that haven't been charged yet. Returns count."""
    from models.fee import FeeRecord, PaymentStatus

    if late_fee_pct <= 0:
        return 0

    today = date.today()
    cutoff = today - timedelta(days=late_fee_after_days)

    result = await db.execute(
        select(FeeRecord).where(
            FeeRecord.branch_id == branch_id,
            FeeRecord.status == PaymentStatus.OVERDUE,
            FeeRecord.due_date <= cutoff,
            FeeRecord.late_fee == 0,  # Not yet charged
        )
    )
    records = result.scalars().all()
    count = 0
    for rec in records:
        rec.late_fee = round(float(rec.amount_due) * (late_fee_pct / 100), 2)
        count += 1
    await db.flush()
    return count


async def get_fees_due_in_days(db: AsyncSession, branch_id, days: int):
    """Get pending fee records due in exactly N days from today.
    Returns list of (FeeRecord, Student) tuples."""
    from models.fee import FeeRecord, PaymentStatus
    from models.student import Student

    target_date = date.today() + timedelta(days=days)
    result = await db.execute(
        select(FeeRecord, Student).join(
            Student, FeeRecord.student_id == Student.id
        ).where(
            FeeRecord.branch_id == branch_id,
            FeeRecord.status == PaymentStatus.PENDING,
            FeeRecord.due_date == target_date,
        )
    )
    return result.all()
