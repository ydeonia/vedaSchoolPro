"""Onboarding & Setup Checklist API — GAP 1 from PO Review
Tracks school setup progress, generates smart recommendations, powers the onboarding widget"""
from fastapi import APIRouter, Request, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from database import get_db
from models.user import UserRole
from utils.permissions import require_role
import uuid

router = APIRouter(prefix="/api/school/onboarding")


async def get_branch(request):
    return uuid.UUID(request.state.user["branch_id"])


@router.get("/checklist")
@require_role(UserRole.SCHOOL_ADMIN)
async def setup_checklist(request: Request, db: AsyncSession = Depends(get_db)):
    """Returns school setup checklist with completion status and smart next-step"""
    branch_id = await get_branch(request)
    from models.academic import Class, Section
    from models.student import Student
    from models.teacher import Teacher
    from models.academic import Subject
    from models.attendance import Attendance
    from models.exam import Exam
    from models.fee import FeeStructure, FeeRecord
    from models.branch import Branch
    from models.timetable import TimetableSlot

    # Count all entities
    classes = await db.scalar(select(func.count()).select_from(Class).where(Class.branch_id == branch_id, Class.is_active == True)) or 0
    sections = await db.scalar(select(func.count()).select_from(Section).where(Section.is_active == True)) or 0
    students = await db.scalar(select(func.count()).select_from(Student).where(Student.branch_id == branch_id, Student.is_active == True)) or 0
    teachers = await db.scalar(select(func.count()).select_from(Teacher).where(Teacher.branch_id == branch_id, Teacher.is_active == True)) or 0
    subjects = await db.scalar(select(func.count()).select_from(Subject).where(Subject.branch_id == branch_id, Subject.is_active == True)) or 0
    att_days = await db.scalar(select(func.count(func.distinct(Attendance.date)))) or 0
    exams = await db.scalar(select(func.count()).select_from(Exam).where(Exam.branch_id == branch_id)) or 0
    fee_structs = await db.scalar(select(func.count()).select_from(FeeStructure).where(FeeStructure.branch_id == branch_id, FeeStructure.is_active == True)) or 0
    fee_collected = await db.scalar(select(func.count()).select_from(FeeRecord).where(FeeRecord.branch_id == branch_id, FeeRecord.status.in_(['paid', 'partial']))) or 0
    timetables = await db.scalar(select(func.count()).select_from(TimetableSlot).where(TimetableSlot.branch_id == branch_id)) or 0

    # Branch info
    branch = (await db.execute(select(Branch).where(Branch.id == branch_id))).scalar_one_or_none()
    has_logo = bool(branch and branch.logo_url)
    has_motto = bool(branch and hasattr(branch, 'motto') and branch.motto)

    # Build checklist steps
    steps = [
        {
            "id": "school_profile",
            "title": "Set up school profile",
            "desc": "Add school name, logo, motto, and contact details",
            "done": has_logo and has_motto,
            "link": "/school/data-safety",
            "icon": "fa-school",
            "priority": 1,
            "tip": "Your logo appears on all PDFs — receipts, report cards, ID cards, and certificates."
        },
        {
            "id": "classes",
            "title": "Create classes & sections",
            "desc": f"You have {classes} classes and {sections} sections" if classes > 0 else "Add your school classes (e.g., Class 1-A, 2-B)",
            "done": classes >= 1,
            "link": "/school/classes",
            "icon": "fa-chalkboard",
            "priority": 2,
            "tip": "Start with at least one class. You can always add more later — nothing is permanent!"
        },
        {
            "id": "subjects",
            "title": "Add subjects",
            "desc": f"{subjects} subjects added" if subjects > 0 else "Add subjects like English, Mathematics, Science",
            "done": subjects >= 3,
            "link": "/school/subjects",
            "icon": "fa-book",
            "priority": 3,
            "tip": "Subjects link to timetable, exams, and homework. Add at least your core subjects."
        },
        {
            "id": "teachers",
            "title": "Add teachers",
            "desc": f"{teachers} teachers added" if teachers > 0 else "Add your teaching staff with contact details",
            "done": teachers >= 1,
            "link": "/school/teachers",
            "icon": "fa-chalkboard-teacher",
            "priority": 4,
            "tip": "Teachers can log in with their own accounts to mark attendance and track periods."
        },
        {
            "id": "students",
            "title": "Add students",
            "desc": f"{students} students enrolled" if students > 0 else "Add students and assign them to classes",
            "done": students >= 1,
            "link": "/school/students",
            "icon": "fa-user-graduate",
            "priority": 5,
            "tip": "You can add students one by one or import from Excel later. Start with a few to test."
        },
        {
            "id": "timetable",
            "title": "Set up timetable",
            "desc": f"{timetables} period slots defined" if timetables > 0 else "Define daily period schedule for each class",
            "done": timetables >= 1,
            "link": "/school/timetable",
            "icon": "fa-calendar-week",
            "priority": 6,
            "tip": "The timetable auto-detects conflicts if a teacher is assigned to two classes at the same time."
        },
        {
            "id": "attendance",
            "title": "Mark first attendance",
            "desc": f"Attendance marked for {att_days} days" if att_days > 0 else "Try the one-tap attendance system — it takes 30 seconds!",
            "done": att_days >= 1,
            "link": "/school/attendance",
            "icon": "fa-clipboard-check",
            "priority": 7,
            "tip": "All students are marked Present by default — just tap the absent ones. You can undo mistakes!"
        },
        {
            "id": "fee_structure",
            "title": "Configure fee structure",
            "desc": f"{fee_structs} fee structures created" if fee_structs > 0 else "Set up monthly or term-wise fee amounts per class",
            "done": fee_structs >= 1,
            "link": "/school/fee-structure",
            "icon": "fa-indian-rupee-sign",
            "priority": 8,
            "tip": "You can define different fees for different classes, with breakup (Tuition, Bus, Lab, etc.)"
        },
        {
            "id": "exams",
            "title": "Create an exam",
            "desc": f"{exams} exams created" if exams > 0 else "Set up your first exam with subjects and max marks",
            "done": exams >= 1,
            "link": "/school/exams",
            "icon": "fa-file-alt",
            "priority": 9,
            "tip": "Exams auto-generate report cards with CBSE grading. You control when results are published."
        },
        {
            "id": "fee_collection",
            "title": "Collect first fee",
            "desc": f"{fee_collected} fees collected" if fee_collected > 0 else "Try collecting a fee — the receipt PDF is beautiful!",
            "done": fee_collected >= 1,
            "link": "/school/fee-collection",
            "icon": "fa-hand-holding-usd",
            "priority": 10,
            "tip": "Receipts include your school logo, watermark, and signature. Parents can download them too."
        },
    ]

    # Calculate progress
    done_count = sum(1 for s in steps if s["done"])
    total = len(steps)
    pct = round(done_count / total * 100) if total > 0 else 0

    # Smart recommendation: find the first undone step
    next_step = None
    for s in steps:
        if not s["done"]:
            next_step = s
            break

    return {
        "steps": steps,
        "done": done_count,
        "total": total,
        "pct": pct,
        "next_step": next_step,
        "is_complete": pct == 100,
    }


@router.post("/dismiss")
@require_role(UserRole.SCHOOL_ADMIN)
async def dismiss_onboarding(request: Request):
    """Dismiss onboarding banner (user chose to skip)"""
    # In production, store this in user preferences
    return {"dismissed": True}