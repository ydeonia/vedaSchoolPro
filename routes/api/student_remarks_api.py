"""Student Remarks API — Returns teacher feedback for student/parent analytics.
Combines marks data + teacher remarks into actionable insights."""
from fastapi import APIRouter, Request, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from database import get_db
from models.user import UserRole
from models.student import Student
from models.academic import Subject
from models.teacher import Teacher
from models.mega_modules import StudentRemark, RemarkCategory
from utils.permissions import require_role
from datetime import datetime
import uuid, json

router = APIRouter(prefix="/api/student")


async def _get_student(request, db):
    user = request.state.user
    uid = uuid.UUID(user["user_id"])
    result = await db.execute(
        select(Student).where(Student.user_id == uid, Student.is_active == True))
    return result.scalar_one_or_none(), user


@router.get("/remarks")
@require_role(UserRole.STUDENT)
async def get_my_remarks(request: Request, db: AsyncSession = Depends(get_db)):
    """Get all teacher remarks for the logged-in student."""
    student, user = await _get_student(request, db)
    if not student:
        return {"remarks": [], "summary": {}}
    
    remarks = (await db.execute(
        select(StudentRemark).where(
            StudentRemark.student_id == student.id,
            StudentRemark.is_visible_to_student == True,
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
    
    # Build response
    remark_list = []
    # Also build per-subject summary
    subject_feedback = {}  # subject_name -> {strengths: [], concerns: [], suggestions: []}
    
    for r in remarks:
        subj_name = subjects.get(r.subject_id, "General")
        tag_texts = json.loads(r.tag_texts) if r.tag_texts else []
        
        remark_list.append({
            "id": str(r.id),
            "teacher": teachers.get(r.teacher_id, "—"),
            "subject": subj_name,
            "tags": tag_texts,
            "custom_remark": r.custom_remark or "",
            "category": r.category.value,
            "date": r.created_at.strftime("%d %b %Y"),
            "parent_seen": r.parent_acknowledged,
        })
        
        # Accumulate per-subject
        if subj_name not in subject_feedback:
            subject_feedback[subj_name] = {"strengths": [], "concerns": [], "suggestions": []}
        
        for tag in tag_texts:
            if r.category == RemarkCategory.STRENGTH:
                subject_feedback[subj_name]["strengths"].append(tag)
            elif r.category == RemarkCategory.CONCERN:
                subject_feedback[subj_name]["concerns"].append(tag)
            else:
                subject_feedback[subj_name]["suggestions"].append(tag)
        
        if r.custom_remark:
            cat_key = "strengths" if r.category == RemarkCategory.STRENGTH else "concerns" if r.category == RemarkCategory.CONCERN else "suggestions"
            subject_feedback[subj_name][cat_key].append(r.custom_remark)
    
    # De-duplicate tags within each subject
    for subj in subject_feedback:
        for cat in ["strengths", "concerns", "suggestions"]:
            subject_feedback[subj][cat] = list(dict.fromkeys(subject_feedback[subj][cat]))
    
    return {
        "remarks": remark_list,
        "subject_feedback": subject_feedback,
        "total_remarks": len(remark_list),
        "total_strengths": sum(len(v["strengths"]) for v in subject_feedback.values()),
        "total_concerns": sum(len(v["concerns"]) for v in subject_feedback.values()),
    }
