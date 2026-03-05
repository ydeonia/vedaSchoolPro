"""
Timetable V2 API — Bell schedule templates, timetable views, substitutions, subject hours.
"""
import uuid
from typing import List, Optional
from datetime import datetime, time, date

from fastapi import APIRouter, Request, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_, delete
from sqlalchemy.orm import selectinload

from database import get_db
from models.timetable import (
    BellScheduleTemplate,
    ClassScheduleAssignment,
    PeriodDefinition,
    TimetableSlot,
    SubjectHoursConfig,
    Substitution,
    SubstitutionStatus,
    DayOfWeek,
    PeriodType,
)
from models.teacher import Teacher
from models.academic import Class, Section, Subject
from models.teacher_attendance import LeaveRequest, LeaveStatus
from models.notification import Notification, NotificationType

from utils.permissions import get_current_user

router = APIRouter(prefix="/api/school/timetable/v2", tags=["Timetable V2"])


# ═══════════════════════════════════════════════════════════
# AUTH HELPERS
# ═══════════════════════════════════════════════════════════

async def verify_school_admin(request: Request):
    user = await get_current_user(request)
    if not user or user.get("role") not in ["school_admin", "staff"]:
        raise HTTPException(status_code=403, detail="Access denied")
    return user


def get_branch_id(user: dict) -> uuid.UUID:
    bid = user.get("branch_id")
    if not bid:
        raise HTTPException(status_code=400, detail="No branch")
    return uuid.UUID(bid) if isinstance(bid, str) else bid


def _parse_time(t: str) -> time:
    """Parse HH:MM string to time object."""
    try:
        return datetime.strptime(t, "%H:%M").time()
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail=f"Invalid time format: {t}. Expected HH:MM")


# ═══════════════════════════════════════════════════════════
# PYDANTIC SCHEMAS
# ═══════════════════════════════════════════════════════════

# --- Templates ---

class PeriodCreate(BaseModel):
    period_number: int
    label: str
    start_time: str  # "HH:MM"
    end_time: str
    period_type: str = "regular"


class TemplateCreate(BaseModel):
    name: str
    description: Optional[str] = None
    periods: Optional[List[PeriodCreate]] = None


class TemplateUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None


class PeriodUpdate(BaseModel):
    period_number: Optional[int] = None
    label: Optional[str] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    period_type: Optional[str] = None


class BulkPeriodItem(BaseModel):
    id: Optional[str] = None  # if present, update existing; otherwise create new
    label: str
    start_time: str
    end_time: str
    period_type: str = "regular"


class BulkPeriodRequest(BaseModel):
    periods: List[BulkPeriodItem]


# --- Assignments ---

class AssignmentCreate(BaseModel):
    class_id: str
    section_id: Optional[str] = None
    template_id: str
    day_of_week: Optional[str] = None


class BulkAssignmentCreate(BaseModel):
    template_id: str
    class_ids: List[str]
    day_of_week: Optional[str] = None


# --- Substitutions ---

class SubstitutionCreate(BaseModel):
    date: date
    timetable_slot_id: str
    original_teacher_id: str
    substitute_teacher_id: str
    reason: Optional[str] = None


class SubstitutionUpdate(BaseModel):
    status: Optional[str] = None
    notes: Optional[str] = None


# --- Subject Hours ---

class SubjectHourItem(BaseModel):
    subject_id: str
    periods_per_week: int


class SubjectHoursUpsert(BaseModel):
    class_id: str
    items: List[SubjectHourItem]


# ═══════════════════════════════════════════════════════════
# PHASE 1 — TEMPLATE MANAGEMENT
# ═══════════════════════════════════════════════════════════

# 1. GET /templates
@router.get("/templates")
async def list_templates(request: Request, db: AsyncSession = Depends(get_db)):
    """List all bell schedule templates for the branch with period count and assigned class count."""
    user = await verify_school_admin(request)
    branch_id = get_branch_id(user)

    try:
        result = await db.execute(
            select(BellScheduleTemplate)
            .where(
                BellScheduleTemplate.branch_id == branch_id,
                BellScheduleTemplate.is_active == True,
            )
            .options(
                selectinload(BellScheduleTemplate.periods),
                selectinload(BellScheduleTemplate.assignments),
            )
            .order_by(BellScheduleTemplate.created_at.desc())
        )
        templates = result.scalars().all()

        data = []
        for t in templates:
            active_periods = [p for p in t.periods if p.is_active]
            active_assignments = [a for a in t.assignments if a.is_active]
            unique_classes = set(str(a.class_id) for a in active_assignments)
            data.append({
                "id": str(t.id),
                "name": t.name,
                "description": t.description,
                "is_default": t.is_default,
                "period_count": len(active_periods),
                "assigned_class_count": len(unique_classes),
                "created_at": t.created_at.isoformat() if t.created_at else None,
            })

        return {"success": True, "templates": data}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# 2. POST /templates
@router.post("/templates")
async def create_template(data: TemplateCreate, request: Request, db: AsyncSession = Depends(get_db)):
    """Create a bell schedule template with optional inline periods. Auto-sets is_default if first template."""
    user = await verify_school_admin(request)
    branch_id = get_branch_id(user)

    try:
        # Check if this is the first template for the branch
        count_result = await db.execute(
            select(func.count(BellScheduleTemplate.id)).where(
                BellScheduleTemplate.branch_id == branch_id,
                BellScheduleTemplate.is_active == True,
            )
        )
        existing_count = count_result.scalar() or 0
        is_default = existing_count == 0

        template = BellScheduleTemplate(
            branch_id=branch_id,
            name=data.name,
            description=data.description,
            is_default=is_default,
            is_active=True,
        )
        db.add(template)
        await db.flush()  # get template.id

        # Create inline periods if provided
        if data.periods:
            for p in data.periods:
                period = PeriodDefinition(
                    branch_id=branch_id,
                    template_id=template.id,
                    period_number=p.period_number,
                    label=p.label,
                    start_time=_parse_time(p.start_time),
                    end_time=_parse_time(p.end_time),
                    period_type=PeriodType(p.period_type),
                    is_active=True,
                )
                db.add(period)

        return {
            "success": True,
            "message": "Template created",
            "template_id": str(template.id),
            "is_default": is_default,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# 3. GET /templates/{template_id}
@router.get("/templates/{template_id}")
async def get_template(template_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    """Get template with all its periods and assigned classes."""
    user = await verify_school_admin(request)
    branch_id = get_branch_id(user)

    try:
        result = await db.execute(
            select(BellScheduleTemplate)
            .where(
                BellScheduleTemplate.id == uuid.UUID(template_id),
                BellScheduleTemplate.branch_id == branch_id,
                BellScheduleTemplate.is_active == True,
            )
            .options(
                selectinload(BellScheduleTemplate.periods),
                selectinload(BellScheduleTemplate.assignments).selectinload(ClassScheduleAssignment.class_),
                selectinload(BellScheduleTemplate.assignments).selectinload(ClassScheduleAssignment.section),
            )
        )
        template = result.scalars().first()
        if not template:
            raise HTTPException(status_code=404, detail="Template not found")

        periods = sorted(
            [p for p in template.periods if p.is_active],
            key=lambda p: p.period_number,
        )
        assignments = [a for a in template.assignments if a.is_active]

        return {
            "success": True,
            "template": {
                "id": str(template.id),
                "name": template.name,
                "description": template.description,
                "is_default": template.is_default,
                "created_at": template.created_at.isoformat() if template.created_at else None,
                "periods": [
                    {
                        "id": str(p.id),
                        "period_number": p.period_number,
                        "label": p.label,
                        "start_time": p.start_time.strftime("%H:%M") if p.start_time else None,
                        "end_time": p.end_time.strftime("%H:%M") if p.end_time else None,
                        "period_type": p.period_type.value if p.period_type else "regular",
                    }
                    for p in periods
                ],
                "assignments": [
                    {
                        "id": str(a.id),
                        "class_id": str(a.class_id),
                        "class_name": a.class_.name if a.class_ else None,
                        "section_id": str(a.section_id) if a.section_id else None,
                        "section_name": a.section.name if a.section else None,
                        "day_of_week": a.day_of_week.value if a.day_of_week else None,
                    }
                    for a in assignments
                ],
            },
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# 4. PUT /templates/{template_id}
@router.put("/templates/{template_id}")
async def update_template(template_id: str, data: TemplateUpdate, request: Request, db: AsyncSession = Depends(get_db)):
    """Update template name/description."""
    user = await verify_school_admin(request)
    branch_id = get_branch_id(user)

    try:
        result = await db.execute(
            select(BellScheduleTemplate).where(
                BellScheduleTemplate.id == uuid.UUID(template_id),
                BellScheduleTemplate.branch_id == branch_id,
                BellScheduleTemplate.is_active == True,
            )
        )
        template = result.scalars().first()
        if not template:
            raise HTTPException(status_code=404, detail="Template not found")

        if data.name is not None:
            template.name = data.name
        if data.description is not None:
            template.description = data.description

        return {"success": True, "message": "Template updated"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# 5. DELETE /templates/{template_id}
@router.delete("/templates/{template_id}")
async def delete_template(template_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    """Soft-delete template. Block if any ClassScheduleAssignment references it."""
    user = await verify_school_admin(request)
    branch_id = get_branch_id(user)

    try:
        tid = uuid.UUID(template_id)

        # Check for active assignments
        assign_count = await db.execute(
            select(func.count(ClassScheduleAssignment.id)).where(
                ClassScheduleAssignment.template_id == tid,
                ClassScheduleAssignment.is_active == True,
            )
        )
        if (assign_count.scalar() or 0) > 0:
            raise HTTPException(
                status_code=409,
                detail="Cannot delete template — it is assigned to one or more classes. Remove assignments first.",
            )

        result = await db.execute(
            select(BellScheduleTemplate).where(
                BellScheduleTemplate.id == tid,
                BellScheduleTemplate.branch_id == branch_id,
                BellScheduleTemplate.is_active == True,
            )
        )
        template = result.scalars().first()
        if not template:
            raise HTTPException(status_code=404, detail="Template not found")

        template.is_active = False
        return {"success": True, "message": "Template deleted"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# 6. POST /templates/{template_id}/periods
@router.post("/templates/{template_id}/periods")
async def add_period(template_id: str, data: PeriodCreate, request: Request, db: AsyncSession = Depends(get_db)):
    """Add a single period to a template."""
    user = await verify_school_admin(request)
    branch_id = get_branch_id(user)

    try:
        tid = uuid.UUID(template_id)

        # Verify template exists and belongs to branch
        result = await db.execute(
            select(BellScheduleTemplate).where(
                BellScheduleTemplate.id == tid,
                BellScheduleTemplate.branch_id == branch_id,
                BellScheduleTemplate.is_active == True,
            )
        )
        if not result.scalars().first():
            raise HTTPException(status_code=404, detail="Template not found")

        period = PeriodDefinition(
            branch_id=branch_id,
            template_id=tid,
            period_number=data.period_number,
            label=data.label,
            start_time=_parse_time(data.start_time),
            end_time=_parse_time(data.end_time),
            period_type=PeriodType(data.period_type),
            is_active=True,
        )
        db.add(period)
        await db.flush()

        return {"success": True, "message": "Period added", "period_id": str(period.id)}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# 7. PUT /templates/{template_id}/periods/{period_id}
@router.put("/templates/{template_id}/periods/{period_id}")
async def update_period(
    template_id: str,
    period_id: str,
    data: PeriodUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Update a single period timing (non-destructive)."""
    user = await verify_school_admin(request)
    branch_id = get_branch_id(user)

    try:
        result = await db.execute(
            select(PeriodDefinition).where(
                PeriodDefinition.id == uuid.UUID(period_id),
                PeriodDefinition.template_id == uuid.UUID(template_id),
                PeriodDefinition.branch_id == branch_id,
                PeriodDefinition.is_active == True,
            )
        )
        period = result.scalars().first()
        if not period:
            raise HTTPException(status_code=404, detail="Period not found")

        if data.period_number is not None:
            period.period_number = data.period_number
        if data.label is not None:
            period.label = data.label
        if data.start_time is not None:
            period.start_time = _parse_time(data.start_time)
        if data.end_time is not None:
            period.end_time = _parse_time(data.end_time)
        if data.period_type is not None:
            period.period_type = PeriodType(data.period_type)

        return {"success": True, "message": "Period updated"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# 8. DELETE /templates/{template_id}/periods/{period_id}
@router.delete("/templates/{template_id}/periods/{period_id}")
async def delete_period(template_id: str, period_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    """Remove period. Block if any TimetableSlot references this period_id."""
    user = await verify_school_admin(request)
    branch_id = get_branch_id(user)

    try:
        pid = uuid.UUID(period_id)

        # Check for timetable slots referencing this period
        slot_count = await db.execute(
            select(func.count(TimetableSlot.id)).where(
                TimetableSlot.period_id == pid,
                TimetableSlot.is_active == True,
            )
        )
        if (slot_count.scalar() or 0) > 0:
            raise HTTPException(
                status_code=409,
                detail="Cannot delete period — it is referenced by timetable slots. Remove those slots first.",
            )

        result = await db.execute(
            select(PeriodDefinition).where(
                PeriodDefinition.id == pid,
                PeriodDefinition.template_id == uuid.UUID(template_id),
                PeriodDefinition.branch_id == branch_id,
                PeriodDefinition.is_active == True,
            )
        )
        period = result.scalars().first()
        if not period:
            raise HTTPException(status_code=404, detail="Period not found")

        period.is_active = False
        return {"success": True, "message": "Period deleted"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# 9. POST /templates/{template_id}/periods/bulk
@router.post("/templates/{template_id}/periods/bulk")
async def bulk_upsert_periods(
    template_id: str,
    data: BulkPeriodRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Smart bulk: update existing periods (by id), create new ones, then re-number sequentially."""
    user = await verify_school_admin(request)
    branch_id = get_branch_id(user)

    try:
        tid = uuid.UUID(template_id)

        # Verify template
        tmpl_result = await db.execute(
            select(BellScheduleTemplate).where(
                BellScheduleTemplate.id == tid,
                BellScheduleTemplate.branch_id == branch_id,
                BellScheduleTemplate.is_active == True,
            )
        )
        if not tmpl_result.scalars().first():
            raise HTTPException(status_code=404, detail="Template not found")

        processed_ids = []

        for item in data.periods:
            if item.id:
                # Update existing period
                pid = uuid.UUID(item.id)
                result = await db.execute(
                    select(PeriodDefinition).where(
                        PeriodDefinition.id == pid,
                        PeriodDefinition.template_id == tid,
                        PeriodDefinition.branch_id == branch_id,
                    )
                )
                period = result.scalars().first()
                if not period:
                    raise HTTPException(status_code=404, detail=f"Period {item.id} not found")
                period.label = item.label
                period.start_time = _parse_time(item.start_time)
                period.end_time = _parse_time(item.end_time)
                period.period_type = PeriodType(item.period_type)
                period.is_active = True
                processed_ids.append(period.id)
            else:
                # Create new period (period_number will be set during re-numbering)
                period = PeriodDefinition(
                    branch_id=branch_id,
                    template_id=tid,
                    period_number=0,  # temporary
                    label=item.label,
                    start_time=_parse_time(item.start_time),
                    end_time=_parse_time(item.end_time),
                    period_type=PeriodType(item.period_type),
                    is_active=True,
                )
                db.add(period)
                await db.flush()
                processed_ids.append(period.id)

        # Re-number all active periods sequentially by start_time
        all_periods_result = await db.execute(
            select(PeriodDefinition).where(
                PeriodDefinition.template_id == tid,
                PeriodDefinition.branch_id == branch_id,
                PeriodDefinition.is_active == True,
            )
        )
        all_periods = list(all_periods_result.scalars().all())
        all_periods.sort(key=lambda p: p.start_time)

        for idx, p in enumerate(all_periods, start=1):
            p.period_number = idx

        return {
            "success": True,
            "message": f"Bulk upsert complete — {len(all_periods)} periods re-numbered",
            "period_count": len(all_periods),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# 10. GET /assignments
@router.get("/assignments")
async def list_assignments(request: Request, db: AsyncSession = Depends(get_db)):
    """List all class-to-template assignments for the branch."""
    user = await verify_school_admin(request)
    branch_id = get_branch_id(user)

    try:
        result = await db.execute(
            select(ClassScheduleAssignment)
            .where(
                ClassScheduleAssignment.branch_id == branch_id,
                ClassScheduleAssignment.is_active == True,
            )
            .options(
                selectinload(ClassScheduleAssignment.template),
                selectinload(ClassScheduleAssignment.class_),
                selectinload(ClassScheduleAssignment.section),
            )
            .order_by(ClassScheduleAssignment.created_at.desc())
        )
        assignments = result.scalars().all()

        return {
            "success": True,
            "assignments": [
                {
                    "id": str(a.id),
                    "class_id": str(a.class_id),
                    "class_name": a.class_.name if a.class_ else None,
                    "section_id": str(a.section_id) if a.section_id else None,
                    "section_name": a.section.name if a.section else None,
                    "template_id": str(a.template_id),
                    "template_name": a.template.name if a.template else None,
                    "day_of_week": a.day_of_week.value if a.day_of_week else None,
                }
                for a in assignments
            ],
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# 11. POST /assignments
@router.post("/assignments")
async def create_assignment(data: AssignmentCreate, request: Request, db: AsyncSession = Depends(get_db)):
    """Assign a template to a class (optionally with section and day_of_week)."""
    user = await verify_school_admin(request)
    branch_id = get_branch_id(user)

    try:
        day = DayOfWeek(data.day_of_week) if data.day_of_week else None
        section_id = uuid.UUID(data.section_id) if data.section_id else None

        assignment = ClassScheduleAssignment(
            branch_id=branch_id,
            class_id=uuid.UUID(data.class_id),
            section_id=section_id,
            template_id=uuid.UUID(data.template_id),
            day_of_week=day,
            is_active=True,
        )
        db.add(assignment)
        await db.flush()

        return {"success": True, "message": "Assignment created", "assignment_id": str(assignment.id)}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# 12. POST /assignments/bulk
@router.post("/assignments/bulk")
async def bulk_create_assignments(data: BulkAssignmentCreate, request: Request, db: AsyncSession = Depends(get_db)):
    """Assign a template to multiple classes at once."""
    user = await verify_school_admin(request)
    branch_id = get_branch_id(user)

    try:
        day = DayOfWeek(data.day_of_week) if data.day_of_week else None
        template_id = uuid.UUID(data.template_id)
        created = []

        for cid in data.class_ids:
            assignment = ClassScheduleAssignment(
                branch_id=branch_id,
                class_id=uuid.UUID(cid),
                section_id=None,
                template_id=template_id,
                day_of_week=day,
                is_active=True,
            )
            db.add(assignment)
            await db.flush()
            created.append(str(assignment.id))

        return {
            "success": True,
            "message": f"{len(created)} assignments created",
            "assignment_ids": created,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# 13. DELETE /assignments/{assignment_id}
@router.delete("/assignments/{assignment_id}")
async def delete_assignment(assignment_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    """Remove a class-to-template assignment."""
    user = await verify_school_admin(request)
    branch_id = get_branch_id(user)

    try:
        result = await db.execute(
            select(ClassScheduleAssignment).where(
                ClassScheduleAssignment.id == uuid.UUID(assignment_id),
                ClassScheduleAssignment.branch_id == branch_id,
                ClassScheduleAssignment.is_active == True,
            )
        )
        assignment = result.scalars().first()
        if not assignment:
            raise HTTPException(status_code=404, detail="Assignment not found")

        assignment.is_active = False
        return {"success": True, "message": "Assignment removed"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ═══════════════════════════════════════════════════════════
# PHASE 2 — TEACHER VIEW + CONFLICTS
# ═══════════════════════════════════════════════════════════

# 14. GET /view/teacher/{teacher_id}
@router.get("/view/teacher/{teacher_id}")
async def teacher_timetable(teacher_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    """Full weekly timetable for a teacher across all classes."""
    user = await verify_school_admin(request)
    branch_id = get_branch_id(user)

    try:
        result = await db.execute(
            select(TimetableSlot)
            .where(
                TimetableSlot.branch_id == branch_id,
                TimetableSlot.teacher_id == uuid.UUID(teacher_id),
                TimetableSlot.is_active == True,
            )
            .options(
                selectinload(TimetableSlot.period_definition),
                selectinload(TimetableSlot.class_),
                selectinload(TimetableSlot.section),
                selectinload(TimetableSlot.subject),
            )
        )
        slots = result.scalars().all()

        timetable = {}
        for day in DayOfWeek:
            timetable[day.value] = []

        for slot in slots:
            day_key = slot.day_of_week.value
            pd = slot.period_definition
            timetable[day_key].append({
                "period_number": pd.period_number if pd else None,
                "label": pd.label if pd else None,
                "start_time": pd.start_time.strftime("%H:%M") if pd and pd.start_time else None,
                "end_time": pd.end_time.strftime("%H:%M") if pd and pd.end_time else None,
                "class_name": slot.class_.name if slot.class_ else None,
                "section_name": slot.section.name if slot.section else None,
                "subject_name": slot.subject.name if slot.subject else None,
                "room": slot.room,
            })

        # Sort each day by period_number
        for day_key in timetable:
            timetable[day_key].sort(key=lambda x: x["period_number"] or 0)

        return {"success": True, "teacher_id": teacher_id, "timetable": timetable}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# 15. GET /view/room
@router.get("/view/room")
async def room_timetable(room: str, request: Request, db: AsyncSession = Depends(get_db)):
    """Room-wise timetable. Returns {day: [{period info + class + teacher}]}."""
    user = await verify_school_admin(request)
    branch_id = get_branch_id(user)

    try:
        result = await db.execute(
            select(TimetableSlot)
            .where(
                TimetableSlot.branch_id == branch_id,
                TimetableSlot.room == room,
                TimetableSlot.is_active == True,
            )
            .options(
                selectinload(TimetableSlot.period_definition),
                selectinload(TimetableSlot.class_),
                selectinload(TimetableSlot.section),
                selectinload(TimetableSlot.subject),
                selectinload(TimetableSlot.teacher),
            )
        )
        slots = result.scalars().all()

        timetable = {}
        for day in DayOfWeek:
            timetable[day.value] = []

        for slot in slots:
            day_key = slot.day_of_week.value
            pd = slot.period_definition
            teacher = slot.teacher
            timetable[day_key].append({
                "period_number": pd.period_number if pd else None,
                "label": pd.label if pd else None,
                "start_time": pd.start_time.strftime("%H:%M") if pd and pd.start_time else None,
                "end_time": pd.end_time.strftime("%H:%M") if pd and pd.end_time else None,
                "class_name": slot.class_.name if slot.class_ else None,
                "section_name": slot.section.name if slot.section else None,
                "subject_name": slot.subject.name if slot.subject else None,
                "teacher_name": f"{teacher.first_name} {teacher.last_name or ''}".strip() if teacher else None,
            })

        for day_key in timetable:
            timetable[day_key].sort(key=lambda x: x["period_number"] or 0)

        return {"success": True, "room": room, "timetable": timetable}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# 16. GET /conflicts/teacher
@router.get("/conflicts/teacher")
async def teacher_conflicts(request: Request, db: AsyncSession = Depends(get_db)):
    """Find ALL teacher double-bookings (same teacher, same period_id, same day, different classes)."""
    user = await verify_school_admin(request)
    branch_id = get_branch_id(user)

    try:
        # Self-join to find conflicts: two different slots with same teacher, period, day
        s1 = TimetableSlot.__table__.alias("s1")
        s2 = TimetableSlot.__table__.alias("s2")

        stmt = (
            select(
                s1.c.teacher_id,
                s1.c.period_id,
                s1.c.day_of_week,
                s1.c.id.label("slot1_id"),
                s1.c.class_id.label("class1_id"),
                s1.c.section_id.label("section1_id"),
                s2.c.id.label("slot2_id"),
                s2.c.class_id.label("class2_id"),
                s2.c.section_id.label("section2_id"),
            )
            .select_from(s1.join(s2, and_(
                s1.c.teacher_id == s2.c.teacher_id,
                s1.c.period_id == s2.c.period_id,
                s1.c.day_of_week == s2.c.day_of_week,
                s1.c.id < s2.c.id,  # avoid duplicates
            )))
            .where(
                s1.c.branch_id == branch_id,
                s1.c.is_active == True,
                s2.c.is_active == True,
                s1.c.teacher_id.isnot(None),
            )
        )
        result = await db.execute(stmt)
        rows = result.fetchall()

        # Enrich with teacher and period names
        conflicts = []
        for row in rows:
            teacher_result = await db.execute(
                select(Teacher).where(Teacher.id == row.teacher_id)
            )
            teacher = teacher_result.scalars().first()

            period_result = await db.execute(
                select(PeriodDefinition).where(PeriodDefinition.id == row.period_id)
            )
            period = period_result.scalars().first()

            class1_result = await db.execute(select(Class).where(Class.id == row.class1_id))
            class1 = class1_result.scalars().first()

            class2_result = await db.execute(select(Class).where(Class.id == row.class2_id))
            class2 = class2_result.scalars().first()

            conflicts.append({
                "teacher_id": str(row.teacher_id),
                "teacher_name": f"{teacher.first_name} {teacher.last_name or ''}".strip() if teacher else None,
                "period_id": str(row.period_id),
                "period_label": period.label if period else None,
                "day_of_week": row.day_of_week.value if hasattr(row.day_of_week, 'value') else str(row.day_of_week),
                "slot1_id": str(row.slot1_id),
                "class1_name": class1.name if class1 else None,
                "slot2_id": str(row.slot2_id),
                "class2_name": class2.name if class2 else None,
            })

        return {"success": True, "conflicts": conflicts, "count": len(conflicts)}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# 17. GET /conflicts/room
@router.get("/conflicts/room")
async def room_conflicts(request: Request, db: AsyncSession = Depends(get_db)):
    """Find ALL room double-bookings (same room, same period_id, same day, different slots)."""
    user = await verify_school_admin(request)
    branch_id = get_branch_id(user)

    try:
        s1 = TimetableSlot.__table__.alias("s1")
        s2 = TimetableSlot.__table__.alias("s2")

        stmt = (
            select(
                s1.c.room,
                s1.c.period_id,
                s1.c.day_of_week,
                s1.c.id.label("slot1_id"),
                s1.c.class_id.label("class1_id"),
                s1.c.teacher_id.label("teacher1_id"),
                s2.c.id.label("slot2_id"),
                s2.c.class_id.label("class2_id"),
                s2.c.teacher_id.label("teacher2_id"),
            )
            .select_from(s1.join(s2, and_(
                s1.c.room == s2.c.room,
                s1.c.period_id == s2.c.period_id,
                s1.c.day_of_week == s2.c.day_of_week,
                s1.c.id < s2.c.id,
            )))
            .where(
                s1.c.branch_id == branch_id,
                s1.c.is_active == True,
                s2.c.is_active == True,
                s1.c.room.isnot(None),
                s1.c.room != "",
            )
        )
        result = await db.execute(stmt)
        rows = result.fetchall()

        conflicts = []
        for row in rows:
            period_result = await db.execute(
                select(PeriodDefinition).where(PeriodDefinition.id == row.period_id)
            )
            period = period_result.scalars().first()

            class1_result = await db.execute(select(Class).where(Class.id == row.class1_id))
            class1 = class1_result.scalars().first()

            class2_result = await db.execute(select(Class).where(Class.id == row.class2_id))
            class2 = class2_result.scalars().first()

            conflicts.append({
                "room": row.room,
                "period_id": str(row.period_id),
                "period_label": period.label if period else None,
                "day_of_week": row.day_of_week.value if hasattr(row.day_of_week, 'value') else str(row.day_of_week),
                "slot1_id": str(row.slot1_id),
                "class1_name": class1.name if class1 else None,
                "slot2_id": str(row.slot2_id),
                "class2_name": class2.name if class2 else None,
            })

        return {"success": True, "conflicts": conflicts, "count": len(conflicts)}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# 18. GET /workload
@router.get("/workload")
async def teacher_workload(request: Request, db: AsyncSession = Depends(get_db)):
    """Teacher workload summary: total periods/week, free periods, subjects taught."""
    user = await verify_school_admin(request)
    branch_id = get_branch_id(user)

    try:
        # Get all active teachers in branch
        teachers_result = await db.execute(
            select(Teacher).where(
                Teacher.branch_id == branch_id,
                Teacher.is_active == True,
            )
        )
        teachers = teachers_result.scalars().all()

        # Get total available periods count per week (distinct period_id x day combos across all active slots in branch)
        total_period_slots_result = await db.execute(
            select(func.count(func.distinct(
                func.concat(TimetableSlot.period_id, '-', TimetableSlot.day_of_week)
            ))).where(
                TimetableSlot.branch_id == branch_id,
                TimetableSlot.is_active == True,
            )
        )
        # We'll compute free periods per teacher as: unique (period, day) slots in branch minus teacher's assigned slots

        # Get distinct (period_id, day_of_week) combinations in branch
        all_slots_result = await db.execute(
            select(
                TimetableSlot.period_id,
                TimetableSlot.day_of_week,
            )
            .where(
                TimetableSlot.branch_id == branch_id,
                TimetableSlot.is_active == True,
            )
            .distinct()
        )
        all_period_day_combos = all_slots_result.fetchall()
        total_slots = len(all_period_day_combos)

        workload = []
        for teacher in teachers:
            # Count periods assigned to this teacher
            assigned_result = await db.execute(
                select(func.count(TimetableSlot.id)).where(
                    TimetableSlot.branch_id == branch_id,
                    TimetableSlot.teacher_id == teacher.id,
                    TimetableSlot.is_active == True,
                )
            )
            total_periods = assigned_result.scalar() or 0

            # Get subjects taught
            subjects_result = await db.execute(
                select(Subject.name)
                .join(TimetableSlot, TimetableSlot.subject_id == Subject.id)
                .where(
                    TimetableSlot.branch_id == branch_id,
                    TimetableSlot.teacher_id == teacher.id,
                    TimetableSlot.is_active == True,
                )
                .distinct()
            )
            subjects = [row[0] for row in subjects_result.fetchall()]

            free_periods = max(0, total_slots - total_periods)

            workload.append({
                "teacher_id": str(teacher.id),
                "teacher_name": f"{teacher.first_name} {teacher.last_name or ''}".strip(),
                "total_periods_per_week": total_periods,
                "free_periods": free_periods,
                "subjects_taught": subjects,
            })

        # Sort by total periods descending
        workload.sort(key=lambda x: x["total_periods_per_week"], reverse=True)

        return {"success": True, "workload": workload, "total_period_slots_in_branch": total_slots}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ═══════════════════════════════════════════════════════════
# PHASE 3 — SUBSTITUTION MANAGEMENT
# ═══════════════════════════════════════════════════════════

# 19. GET /substitutions
@router.get("/substitutions")
async def list_substitutions(date: date, request: Request, db: AsyncSession = Depends(get_db)):
    """List substitutions for a given date with teacher names and class info."""
    user = await verify_school_admin(request)
    branch_id = get_branch_id(user)

    try:
        result = await db.execute(
            select(Substitution)
            .where(
                Substitution.branch_id == branch_id,
                Substitution.date == date,
            )
            .options(
                selectinload(Substitution.timetable_slot).selectinload(TimetableSlot.class_),
                selectinload(Substitution.timetable_slot).selectinload(TimetableSlot.section),
                selectinload(Substitution.timetable_slot).selectinload(TimetableSlot.period_definition),
                selectinload(Substitution.timetable_slot).selectinload(TimetableSlot.subject),
                selectinload(Substitution.original_teacher),
                selectinload(Substitution.substitute_teacher),
            )
            .order_by(Substitution.created_at.desc())
        )
        subs = result.scalars().all()

        data = []
        for s in subs:
            slot = s.timetable_slot
            pd = slot.period_definition if slot else None
            data.append({
                "id": str(s.id),
                "date": s.date.isoformat(),
                "status": s.status.value if s.status else None,
                "reason": s.reason,
                "notes": s.notes,
                "original_teacher": {
                    "id": str(s.original_teacher.id),
                    "name": f"{s.original_teacher.first_name} {s.original_teacher.last_name or ''}".strip(),
                } if s.original_teacher else None,
                "substitute_teacher": {
                    "id": str(s.substitute_teacher.id),
                    "name": f"{s.substitute_teacher.first_name} {s.substitute_teacher.last_name or ''}".strip(),
                } if s.substitute_teacher else None,
                "slot": {
                    "class_name": slot.class_.name if slot and slot.class_ else None,
                    "section_name": slot.section.name if slot and slot.section else None,
                    "subject_name": slot.subject.name if slot and slot.subject else None,
                    "period_label": pd.label if pd else None,
                    "period_number": pd.period_number if pd else None,
                    "start_time": pd.start_time.strftime("%H:%M") if pd and pd.start_time else None,
                    "end_time": pd.end_time.strftime("%H:%M") if pd and pd.end_time else None,
                    "day_of_week": slot.day_of_week.value if slot and slot.day_of_week else None,
                } if slot else None,
            })

        return {"success": True, "substitutions": data, "count": len(data)}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# 20. POST /substitutions
@router.post("/substitutions")
async def create_substitution(data: SubstitutionCreate, request: Request, db: AsyncSession = Depends(get_db)):
    """Create substitution and send notification to substitute teacher."""
    user = await verify_school_admin(request)
    branch_id = get_branch_id(user)

    try:
        substitution = Substitution(
            branch_id=branch_id,
            date=data.date,
            timetable_slot_id=uuid.UUID(data.timetable_slot_id),
            original_teacher_id=uuid.UUID(data.original_teacher_id),
            substitute_teacher_id=uuid.UUID(data.substitute_teacher_id),
            reason=data.reason,
            status=SubstitutionStatus.PENDING,
            assigned_by=uuid.UUID(user.get("user_id")) if user.get("user_id") else None,
        )
        db.add(substitution)

        # Load slot info for notification message
        slot_result = await db.execute(
            select(TimetableSlot)
            .where(TimetableSlot.id == uuid.UUID(data.timetable_slot_id))
            .options(
                selectinload(TimetableSlot.class_),
                selectinload(TimetableSlot.section),
                selectinload(TimetableSlot.period_definition),
                selectinload(TimetableSlot.subject),
            )
        )
        slot = slot_result.scalars().first()

        # Load substitute teacher to get user_id for notification
        sub_teacher_result = await db.execute(
            select(Teacher).where(Teacher.id == uuid.UUID(data.substitute_teacher_id))
        )
        sub_teacher = sub_teacher_result.scalars().first()

        # Build notification message
        class_name = slot.class_.name if slot and slot.class_ else "Unknown"
        section_name = slot.section.name if slot and slot.section else ""
        period_label = slot.period_definition.label if slot and slot.period_definition else "Unknown Period"
        subject_name = slot.subject.name if slot and slot.subject else ""

        notif_title = f"Substitution Assignment — {data.date.isoformat()}"
        notif_message = (
            f"You have been assigned as a substitute teacher for {class_name}"
            f"{' ' + section_name if section_name else ''} during {period_label}"
            f"{' (' + subject_name + ')' if subject_name else ''} on {data.date.isoformat()}."
        )

        notification = Notification(
            branch_id=branch_id,
            user_id=sub_teacher.user_id if sub_teacher else None,
            type=NotificationType.ANNOUNCEMENT,
            title=notif_title,
            message=notif_message,
            is_read=False,
        )
        db.add(notification)
        await db.flush()

        return {
            "success": True,
            "message": "Substitution created and notification sent",
            "substitution_id": str(substitution.id),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# 21. PUT /substitutions/{sub_id}
@router.put("/substitutions/{sub_id}")
async def update_substitution(sub_id: str, data: SubstitutionUpdate, request: Request, db: AsyncSession = Depends(get_db)):
    """Update substitution status or notes."""
    user = await verify_school_admin(request)
    branch_id = get_branch_id(user)

    try:
        result = await db.execute(
            select(Substitution).where(
                Substitution.id == uuid.UUID(sub_id),
                Substitution.branch_id == branch_id,
            )
        )
        sub = result.scalars().first()
        if not sub:
            raise HTTPException(status_code=404, detail="Substitution not found")

        if data.status is not None:
            sub.status = SubstitutionStatus(data.status)
        if data.notes is not None:
            sub.notes = data.notes

        return {"success": True, "message": "Substitution updated"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# 22. DELETE /substitutions/{sub_id}
@router.delete("/substitutions/{sub_id}")
async def cancel_substitution(sub_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    """Cancel substitution by setting status to CANCELLED."""
    user = await verify_school_admin(request)
    branch_id = get_branch_id(user)

    try:
        result = await db.execute(
            select(Substitution).where(
                Substitution.id == uuid.UUID(sub_id),
                Substitution.branch_id == branch_id,
            )
        )
        sub = result.scalars().first()
        if not sub:
            raise HTTPException(status_code=404, detail="Substitution not found")

        sub.status = SubstitutionStatus.CANCELLED
        return {"success": True, "message": "Substitution cancelled"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# 23. GET /substitutions/absent-teachers
@router.get("/substitutions/absent-teachers")
async def absent_teachers(date: date, request: Request, db: AsyncSession = Depends(get_db)):
    """Find teachers with approved LeaveRequest covering the given date."""
    user = await verify_school_admin(request)
    branch_id = get_branch_id(user)

    try:
        result = await db.execute(
            select(LeaveRequest)
            .where(
                LeaveRequest.branch_id == branch_id,
                LeaveRequest.status == LeaveStatus.APPROVED,
                LeaveRequest.start_date <= date,
                LeaveRequest.end_date >= date,
            )
            .options(selectinload(LeaveRequest.teacher))
        )
        leaves = result.scalars().all()

        teachers = []
        for leave in leaves:
            t = leave.teacher
            if t:
                teachers.append({
                    "teacher_id": str(t.id),
                    "teacher_name": f"{t.first_name} {t.last_name or ''}".strip(),
                    "leave_type": leave.leave_type.value if leave.leave_type else None,
                    "start_date": leave.start_date.isoformat(),
                    "end_date": leave.end_date.isoformat(),
                })

        return {"success": True, "absent_teachers": teachers, "count": len(teachers)}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# 24. GET /substitutions/suggestions
@router.get("/substitutions/suggestions")
async def substitution_suggestions(slot_id: str, date: date, request: Request, db: AsyncSession = Depends(get_db)):
    """Find free teachers for a given slot. Rank by: 1) teaches same subject, 2) lowest workload."""
    user = await verify_school_admin(request)
    branch_id = get_branch_id(user)

    try:
        # Get the target slot info (period + day + subject)
        slot_result = await db.execute(
            select(TimetableSlot)
            .where(TimetableSlot.id == uuid.UUID(slot_id))
            .options(selectinload(TimetableSlot.subject))
        )
        slot = slot_result.scalars().first()
        if not slot:
            raise HTTPException(status_code=404, detail="Timetable slot not found")

        target_period_id = slot.period_id
        target_day = slot.day_of_week
        target_subject_id = slot.subject_id

        # Get all active teachers in branch
        all_teachers_result = await db.execute(
            select(Teacher).where(
                Teacher.branch_id == branch_id,
                Teacher.is_active == True,
            )
        )
        all_teachers = all_teachers_result.scalars().all()

        # Find teachers who are busy at this period + day
        busy_result = await db.execute(
            select(TimetableSlot.teacher_id).where(
                TimetableSlot.branch_id == branch_id,
                TimetableSlot.period_id == target_period_id,
                TimetableSlot.day_of_week == target_day,
                TimetableSlot.is_active == True,
                TimetableSlot.teacher_id.isnot(None),
            )
        )
        busy_teacher_ids = set(row[0] for row in busy_result.fetchall())

        # Find teachers on leave on this date
        leave_result = await db.execute(
            select(LeaveRequest.teacher_id).where(
                LeaveRequest.branch_id == branch_id,
                LeaveRequest.status == LeaveStatus.APPROVED,
                LeaveRequest.start_date <= date,
                LeaveRequest.end_date >= date,
            )
        )
        on_leave_ids = set(row[0] for row in leave_result.fetchall())

        # Filter to free teachers
        free_teachers = [
            t for t in all_teachers
            if t.id not in busy_teacher_ids and t.id not in on_leave_ids
        ]

        # Score each free teacher
        suggestions = []
        for teacher in free_teachers:
            # Check if teacher teaches the same subject (anywhere in their timetable)
            teaches_same_subject = False
            if target_subject_id:
                subj_check = await db.execute(
                    select(func.count(TimetableSlot.id)).where(
                        TimetableSlot.branch_id == branch_id,
                        TimetableSlot.teacher_id == teacher.id,
                        TimetableSlot.subject_id == target_subject_id,
                        TimetableSlot.is_active == True,
                    )
                )
                teaches_same_subject = (subj_check.scalar() or 0) > 0

            # Get workload (total periods per week)
            workload_result = await db.execute(
                select(func.count(TimetableSlot.id)).where(
                    TimetableSlot.branch_id == branch_id,
                    TimetableSlot.teacher_id == teacher.id,
                    TimetableSlot.is_active == True,
                )
            )
            workload = workload_result.scalar() or 0

            suggestions.append({
                "teacher_id": str(teacher.id),
                "teacher_name": f"{teacher.first_name} {teacher.last_name or ''}".strip(),
                "teaches_same_subject": teaches_same_subject,
                "workload": workload,
            })

        # Sort: teaches same subject first (desc), then lowest workload (asc)
        suggestions.sort(key=lambda x: (not x["teaches_same_subject"], x["workload"]))

        return {"success": True, "suggestions": suggestions, "count": len(suggestions)}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ═══════════════════════════════════════════════════════════
# PHASE 4 — SUBJECT HOURS + VALIDATION
# ═══════════════════════════════════════════════════════════

# 25. GET /subject-hours
@router.get("/subject-hours")
async def get_subject_hours(class_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    """Get configured periods_per_week for each subject in a class."""
    user = await verify_school_admin(request)
    branch_id = get_branch_id(user)

    try:
        result = await db.execute(
            select(SubjectHoursConfig)
            .where(
                SubjectHoursConfig.branch_id == branch_id,
                SubjectHoursConfig.class_id == uuid.UUID(class_id),
            )
            .options(
                selectinload(SubjectHoursConfig.subject),
                selectinload(SubjectHoursConfig.class_),
            )
        )
        configs = result.scalars().all()

        return {
            "success": True,
            "class_id": class_id,
            "subject_hours": [
                {
                    "id": str(c.id),
                    "subject_id": str(c.subject_id),
                    "subject_name": c.subject.name if c.subject else None,
                    "subject_code": c.subject.code if c.subject else None,
                    "periods_per_week": c.periods_per_week,
                }
                for c in configs
            ],
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# 26. POST /subject-hours
@router.post("/subject-hours")
async def upsert_subject_hours(data: SubjectHoursUpsert, request: Request, db: AsyncSession = Depends(get_db)):
    """Upsert subject hours config: create or update periods_per_week for each subject in a class."""
    user = await verify_school_admin(request)
    branch_id = get_branch_id(user)

    try:
        class_id = uuid.UUID(data.class_id)
        upserted = 0

        for item in data.items:
            subject_id = uuid.UUID(item.subject_id)

            # Check if config already exists
            existing_result = await db.execute(
                select(SubjectHoursConfig).where(
                    SubjectHoursConfig.branch_id == branch_id,
                    SubjectHoursConfig.class_id == class_id,
                    SubjectHoursConfig.subject_id == subject_id,
                )
            )
            existing = existing_result.scalars().first()

            if existing:
                existing.periods_per_week = item.periods_per_week
            else:
                config = SubjectHoursConfig(
                    branch_id=branch_id,
                    class_id=class_id,
                    subject_id=subject_id,
                    periods_per_week=item.periods_per_week,
                )
                db.add(config)

            upserted += 1

        return {"success": True, "message": f"{upserted} subject hours upserted"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# 27. GET /subject-hours/validate
@router.get("/subject-hours/validate")
async def validate_subject_hours(class_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    """Compare configured hours vs actual timetable slots for a class."""
    user = await verify_school_admin(request)
    branch_id = get_branch_id(user)

    try:
        cid = uuid.UUID(class_id)

        # Get configured hours
        config_result = await db.execute(
            select(SubjectHoursConfig)
            .where(
                SubjectHoursConfig.branch_id == branch_id,
                SubjectHoursConfig.class_id == cid,
            )
            .options(selectinload(SubjectHoursConfig.subject))
        )
        configs = config_result.scalars().all()

        # Get actual slot counts per subject for this class
        actual_result = await db.execute(
            select(
                TimetableSlot.subject_id,
                func.count(TimetableSlot.id).label("actual_count"),
            )
            .where(
                TimetableSlot.branch_id == branch_id,
                TimetableSlot.class_id == cid,
                TimetableSlot.is_active == True,
                TimetableSlot.subject_id.isnot(None),
            )
            .group_by(TimetableSlot.subject_id)
        )
        actual_map = {row.subject_id: row.actual_count for row in actual_result.fetchall()}

        validation = []
        for config in configs:
            actual = actual_map.get(config.subject_id, 0)
            configured = config.periods_per_week

            if actual == configured:
                status = "ok"
            elif actual < configured:
                status = "under"
            else:
                status = "over"

            validation.append({
                "subject_id": str(config.subject_id),
                "subject_name": config.subject.name if config.subject else None,
                "configured": configured,
                "actual": actual,
                "status": status,
            })

        return {"success": True, "class_id": class_id, "validation": validation}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
