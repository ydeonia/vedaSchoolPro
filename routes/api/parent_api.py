"""Parent APIs — Child analytics mirror, remarks, leave approval, diary view"""
from fastapi import APIRouter, Request, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_
from database import get_db
from models.user import UserRole, User
from models.student import Student
from models.academic import Class, Section, Subject, ClassSubject
from models.attendance import Attendance
from models.exam import Exam, ExamSubject, Marks
from models.fee import FeeRecord
from models.teacher import Teacher
from models.mega_modules import StudentRemark, RemarkCategory, StudentLeave, ApprovalStatus
from utils.permissions import require_role
from datetime import date, timedelta, datetime
import uuid, json

router = APIRouter(prefix="/api/parent")


async def _verify_parent_child(request, db, student_id):
    user = request.state.user
    u = (await db.execute(select(User).where(User.id == uuid.UUID(user["user_id"])))).scalar_one_or_none()
    if not u: return None
    phone = u.phone or ""
    return (await db.execute(
        select(Student).where(Student.id == uuid.UUID(student_id), Student.is_active == True,
            or_(Student.father_phone == phone, Student.mother_phone == phone, Student.guardian_phone == phone))
    )).scalar_one_or_none()


@router.get("/child-analytics/{student_id}")
@require_role(UserRole.PARENT)
async def child_analytics(request: Request, student_id: str, db: AsyncSession = Depends(get_db)):
    student = await _verify_parent_child(request, db, student_id)
    if not student: return {"error": "Access denied"}

    today = date.today()
    branch_id, class_id, section_id = student.branch_id, student.class_id, student.section_id

    # Attendance
    att_records = (await db.execute(select(Attendance.date, Attendance.status).where(Attendance.student_id == student.id).order_by(Attendance.date.desc()))).all()
    total_days = len(att_records)
    present_days = sum(1 for _, s in att_records if s.value == 'present')
    absent_days = sum(1 for _, s in att_records if s.value == 'absent')
    late_days = sum(1 for _, s in att_records if s.value == 'late')
    att_pct = round((present_days / total_days * 100) if total_days > 0 else 0)
    att_trend = []
    for days_ago in range(29, -1, -1):
        d = today - timedelta(days=days_ago)
        if d.weekday() == 6: continue
        status = "none"
        for rd, rs in att_records:
            if rd == d: status = rs.value; break
        att_trend.append({"date": d.strftime("%d %b"), "status": status})

    # Exams
    exams = (await db.execute(select(Exam).where(Exam.branch_id == branch_id, Exam.is_published == True).order_by(Exam.start_date))).scalars().all()
    all_subjects = (await db.execute(select(Subject).where(Subject.branch_id == branch_id))).scalars().all()
    subj_map = {s.id: s.name for s in all_subjects}
    classmate_ids = list((await db.execute(select(Student.id).where(Student.class_id == class_id, Student.section_id == section_id, Student.is_active == True))).scalars().all())
    class_strength = len(classmate_ids)

    exam_analytics, subject_totals, progress = [], {}, []
    for exam in exams:
        esubs = (await db.execute(select(ExamSubject).where(ExamSubject.exam_id == exam.id, ExamSubject.class_id == class_id))).scalars().all()
        if not esubs: continue
        sdata, etm, etx = [], 0, 0
        for es in esubs:
            sn = subj_map.get(es.subject_id, "?")
            mm = (await db.execute(select(Marks).where(Marks.exam_subject_id == es.id, Marks.student_id == student.id))).scalar_one_or_none()
            mo = mm.marks_obtained if mm and not mm.is_absent else 0
            ca = round(float((await db.execute(select(func.avg(Marks.marks_obtained)).where(Marks.exam_subject_id == es.id, Marks.is_absent == False))).scalar() or 0), 1)
            ch = float((await db.execute(select(func.max(Marks.marks_obtained)).where(Marks.exam_subject_id == es.id, Marks.is_absent == False))).scalar() or 0)
            mp = round((mo / es.max_marks * 100) if es.max_marks > 0 else 0)
            ap = round((ca / es.max_marks * 100) if es.max_marks > 0 else 0)
            sdata.append({"subject": sn, "my_marks": mo, "max_marks": es.max_marks, "my_pct": mp, "class_avg": ca, "class_avg_pct": ap, "class_highest": ch, "grade": mm.grade if mm else ""})
            etm += mo; etx += es.max_marks
            if sn not in subject_totals: subject_totals[sn] = {"my": 0, "max": 0, "avg": 0, "count": 0}
            subject_totals[sn]["my"] += mo; subject_totals[sn]["max"] += es.max_marks; subject_totals[sn]["avg"] += ca; subject_totals[sn]["count"] += 1

        ep = round((etm / etx * 100) if etx > 0 else 0)
        progress.append({"exam": exam.name, "pct": ep})
        sb = sum(1 for cid in classmate_ids if cid != student.id and sum(((await db.execute(select(Marks.marks_obtained).where(Marks.exam_subject_id == es.id, Marks.student_id == cid, Marks.is_absent == False))).scalar() or 0) for es in esubs) < etm)
        pctile = round((sb / max(class_strength - 1, 1)) * 100)
        exam_analytics.append({"exam_name": exam.name, "subjects": sdata, "total": etm, "max": etx, "pct": ep, "percentile": pctile})

    radar = [{"subject": sn, "my_pct": round((v["my"]/v["max"]*100) if v["max"]>0 else 0), "class_avg_pct": round((v["avg"]/v["count"]/(v["max"]/v["count"])*100) if v["count"]>0 and v["max"]>0 else 0)} for sn, v in subject_totals.items()]

    class_obj = (await db.execute(select(Class).where(Class.id == class_id))).scalar_one_or_none()
    section_obj = (await db.execute(select(Section).where(Section.id == section_id))).scalar_one_or_none()

    cs_list = (await db.execute(select(ClassSubject).where(ClassSubject.class_id == class_id))).scalars().all()
    tids = [cs.teacher_id for cs in cs_list if cs.teacher_id]
    tmap = {t.id: {"name": t.full_name, "designation": t.designation or ""} for t in (await db.execute(select(Teacher).where(Teacher.id.in_(tids)))).scalars().all()} if tids else {}
    teachers = [{"subject": subj_map.get(cs.subject_id, "?"), "teacher": tmap.get(cs.teacher_id, {}).get("name", "—"), "designation": tmap.get(cs.teacher_id, {}).get("designation", "")} for cs in cs_list]

    fees = (await db.execute(select(FeeRecord).where(FeeRecord.student_id == student.id))).scalars().all()
    td = sum(f.amount_due for f in fees); tp = sum(f.amount_paid for f in fees); tdisc = sum(f.discount for f in fees)

    return {
        "student": {"name": student.full_name, "class": class_obj.name if class_obj else "", "section": section_obj.name if section_obj else "", "roll": student.roll_number or "", "admission": student.admission_number or ""},
        "attendance": {"total": total_days, "present": present_days, "absent": absent_days, "late": late_days, "pct": att_pct, "trend": att_trend},
        "exams": exam_analytics, "progress_trend": progress, "radar": radar,
        "class_info": {"strength": class_strength, "class_name": class_obj.name if class_obj else "", "section_name": section_obj.name if section_obj else "", "teachers": teachers},
        "fees": {"total_due": round(td), "total_paid": round(tp), "balance": round(td - tp - tdisc)},
    }


@router.get("/child-remarks/{student_id}")
@require_role(UserRole.PARENT)
async def child_remarks(request: Request, student_id: str, db: AsyncSession = Depends(get_db)):
    student = await _verify_parent_child(request, db, student_id)
    if not student: return {"remarks": [], "subject_feedback": {}}
    remarks = (await db.execute(select(StudentRemark).where(StudentRemark.student_id == student.id, StudentRemark.is_visible_to_parent == True).order_by(StudentRemark.created_at.desc()).limit(50))).scalars().all()
    tids = list(set(r.teacher_id for r in remarks))
    tmap = {t.id: t.full_name for t in (await db.execute(select(Teacher).where(Teacher.id.in_(tids)))).scalars().all()} if tids else {}
    sids = list(set(r.subject_id for r in remarks if r.subject_id))
    smap = {s.id: s.name for s in (await db.execute(select(Subject).where(Subject.id.in_(sids)))).scalars().all()} if sids else {}

    rlist, sfb = [], {}
    for r in remarks:
        sn = smap.get(r.subject_id, "General")
        tags = json.loads(r.tag_texts) if r.tag_texts else []
        rlist.append({"id": str(r.id), "teacher": tmap.get(r.teacher_id, "—"), "subject": sn, "tags": tags, "custom_remark": r.custom_remark or "", "category": r.category.value, "date": r.created_at.strftime("%d %b %Y")})
        if sn not in sfb: sfb[sn] = {"strengths": [], "concerns": [], "suggestions": []}
        ck = "strengths" if r.category == RemarkCategory.STRENGTH else "concerns" if r.category == RemarkCategory.CONCERN else "suggestions"
        for t in tags: sfb[sn][ck].append(t)
        if r.custom_remark: sfb[sn][ck].append(r.custom_remark)
    for sn in sfb:
        for c in ["strengths", "concerns", "suggestions"]: sfb[sn][c] = list(dict.fromkeys(sfb[sn][c]))
    return {"remarks": rlist, "subject_feedback": sfb, "total_remarks": len(rlist), "total_strengths": sum(len(v["strengths"]) for v in sfb.values()), "total_concerns": sum(len(v["concerns"]) for v in sfb.values())}


@router.get("/child-leaves/{student_id}")
@require_role(UserRole.PARENT)
async def child_leaves(request: Request, student_id: str, db: AsyncSession = Depends(get_db)):
    student = await _verify_parent_child(request, db, student_id)
    if not student: return {"leaves": []}
    leaves = (await db.execute(select(StudentLeave).where(StudentLeave.student_id == student.id, StudentLeave.is_cancelled == False).order_by(StudentLeave.created_at.desc()).limit(20))).scalars().all()
    return {"leaves": [{"id": str(l.id), "start_date": l.start_date.isoformat(), "end_date": l.end_date.isoformat(), "total_days": l.total_days, "reason_type": l.reason_type.value, "reason_text": l.reason_text or "", "parent_status": l.parent_status.value, "teacher_status": l.teacher_status.value, "has_exam_conflict": l.has_exam_conflict, "conflict_details": l.conflict_details or "", "applied_on": l.created_at.strftime("%d %b %Y")} for l in leaves]}