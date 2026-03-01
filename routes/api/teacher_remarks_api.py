"""Teacher Remarks API — Quick tag-based feedback system.
Teachers tap tags (30 seconds) instead of typing paragraphs (5 minutes)."""
from fastapi import APIRouter, Request, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_
from database import get_db
from models.user import UserRole
from models.student import Student
from models.academic import Subject
from models.teacher import Teacher
from models.exam import Exam
from models.mega_modules import RemarkTag, StudentRemark, RemarkCategory
from utils.permissions import require_role
from datetime import datetime
import uuid, json

router = APIRouter(prefix="/api/teacher/remarks")


# ═══════════════════════════════════════════════════════════
# GET TAGS — Returns all available tags grouped by subject
# ═══════════════════════════════════════════════════════════
@router.get("/tags")
@require_role(UserRole.TEACHER)
async def get_remark_tags(request: Request, db: AsyncSession = Depends(get_db)):
    """Get all remark tags grouped by subject. Teachers see these as tap-to-select buttons."""
    user = request.state.user
    
    # Get global tags (branch_id=NULL) + branch-specific tags
    tags = (await db.execute(
        select(RemarkTag).where(
            RemarkTag.is_active == True,
            or_(RemarkTag.branch_id == None, RemarkTag.branch_id == uuid.UUID(user.get("branch_id", "00000000-0000-0000-0000-000000000000")))
        ).order_by(RemarkTag.subject_name, RemarkTag.sort_order)
    )).scalars().all()
    
    # Group by subject
    grouped = {}
    for tag in tags:
        subj = tag.subject_name
        if subj not in grouped:
            grouped[subj] = {"strengths": [], "concerns": [], "suggestions": []}
        item = {"id": str(tag.id), "text": tag.tag_text, "icon": tag.icon}
        if tag.category == RemarkCategory.STRENGTH:
            grouped[subj]["strengths"].append(item)
        elif tag.category == RemarkCategory.CONCERN:
            grouped[subj]["concerns"].append(item)
        else:
            grouped[subj]["suggestions"].append(item)
    
    return {"tags": grouped}


# ═══════════════════════════════════════════════════════════
# SUBMIT REMARK — Teacher submits feedback for a student
# ═══════════════════════════════════════════════════════════
@router.post("/submit")
@require_role(UserRole.TEACHER)
async def submit_remark(request: Request, db: AsyncSession = Depends(get_db)):
    """Submit a remark for a student. Body:
    {
        "student_id": "uuid",
        "subject_id": "uuid" or null,
        "exam_id": "uuid" or null,
        "tag_ids": ["uuid1", "uuid2"],
        "custom_remark": "Optional teacher comment",
        "category": "strength" | "concern" | "suggestion",
        "visible_to_parent": true,
        "visible_to_student": true
    }
    """
    user = request.state.user
    body = await request.json()
    
    # Get teacher
    teacher = (await db.execute(
        select(Teacher).where(Teacher.user_id == uuid.UUID(user["user_id"]))
    )).scalar_one_or_none()
    if not teacher:
        return {"error": "Teacher profile not found"}, 400
    
    student_id = body.get("student_id")
    if not student_id:
        return {"error": "student_id required"}, 400
    
    # Resolve tag texts for denormalization
    tag_ids = body.get("tag_ids", [])
    tag_texts = []
    if tag_ids:
        tags = (await db.execute(
            select(RemarkTag).where(RemarkTag.id.in_([uuid.UUID(t) for t in tag_ids]))
        )).scalars().all()
        tag_texts = [t.tag_text for t in tags]
    
    category = body.get("category", "suggestion")
    
    remark = StudentRemark(
        branch_id=teacher.branch_id,
        student_id=uuid.UUID(student_id),
        teacher_id=teacher.id,
        subject_id=uuid.UUID(body["subject_id"]) if body.get("subject_id") else None,
        exam_id=uuid.UUID(body["exam_id"]) if body.get("exam_id") else None,
        tags=json.dumps(tag_ids),
        tag_texts=json.dumps(tag_texts),
        custom_remark=body.get("custom_remark", ""),
        category=RemarkCategory(category),
        is_visible_to_parent=body.get("visible_to_parent", True),
        is_visible_to_student=body.get("visible_to_student", True),
    )
    db.add(remark)
    await db.commit()
    
    return {"success": True, "remark_id": str(remark.id), "message": "Feedback saved!"}


# ═══════════════════════════════════════════════════════════
# GET REMARKS FOR STUDENT — Used by student/parent analytics
# ═══════════════════════════════════════════════════════════
@router.get("/student/{student_id}")
@require_role(UserRole.TEACHER)
async def get_student_remarks(request: Request, student_id: str, db: AsyncSession = Depends(get_db)):
    """Get all remarks for a student (teacher view)."""
    remarks = (await db.execute(
        select(StudentRemark).where(
            StudentRemark.student_id == uuid.UUID(student_id)
        ).order_by(StudentRemark.created_at.desc()).limit(50)
    )).scalars().all()
    
    # Get teacher names
    teacher_ids = list(set(r.teacher_id for r in remarks))
    teachers = {}
    if teacher_ids:
        ts = (await db.execute(select(Teacher).where(Teacher.id.in_(teacher_ids)))).scalars().all()
        teachers = {t.id: t.full_name for t in ts}
    
    # Get subject names
    subject_ids = list(set(r.subject_id for r in remarks if r.subject_id))
    subjects = {}
    if subject_ids:
        ss = (await db.execute(select(Subject).where(Subject.id.in_(subject_ids)))).scalars().all()
        subjects = {s.id: s.name for s in ss}
    
    return {"remarks": [{
        "id": str(r.id),
        "teacher": teachers.get(r.teacher_id, "—"),
        "subject": subjects.get(r.subject_id, "General"),
        "tags": json.loads(r.tag_texts) if r.tag_texts else [],
        "custom_remark": r.custom_remark or "",
        "category": r.category.value,
        "date": r.created_at.strftime("%d %b %Y"),
        "parent_seen": r.parent_acknowledged,
    } for r in remarks]}
