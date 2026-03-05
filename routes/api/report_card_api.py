"""
Report Card Management System — All API Endpoints
Admin, Teacher, Class Teacher, Student roles all served from here.
"""
import uuid
import io
from datetime import datetime, date
from fastapi import APIRouter, Request, Depends, HTTPException, UploadFile, File, Query
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, update, delete
from sqlalchemy.orm import selectinload
from database import get_db
from models.user import UserRole
from models.academic import AcademicYear, Class, Section, Subject, ClassSubject
from models.student import Student
from models.teacher import Teacher
from models.branch import Branch
from models.notification import Notification
from models.report_card import (
    ReportCardTemplate, ExamGroup, ExamCycle, MarksUploadTracker,
    StudentMarks, StudentResult, MarksAuditLog, ReportCardPDF,
    ExamCycleStatus, UploadStatus, SpecialCode, ResultStatus, AuditAction
)
from utils.permissions import require_role, require_privilege, get_current_user
from utils.excel_handler import generate_marks_template, parse_marks_upload, calculate_grade

router = APIRouter(prefix="/api/report-card")


def get_client_ip(request: Request):
    return request.client.host if request.client else "unknown"


# ═══════════════════════════════════════════════════════════
#  ADMIN: EXAM GROUPS
# ═══════════════════════════════════════════════════════════

@router.get("/exam-groups")
@require_privilege("exam_management")
async def list_exam_groups(request: Request, db: AsyncSession = Depends(get_db)):
    user = request.state.user
    branch_id = uuid.UUID(user["branch_id"])
    ay = (await db.execute(
        select(AcademicYear).where(AcademicYear.branch_id == branch_id, AcademicYear.is_current == True)
    )).scalar_one_or_none()
    if not ay:
        return {"success": True, "groups": [], "academic_year": None}

    groups = (await db.execute(
        select(ExamGroup).where(ExamGroup.branch_id == branch_id, ExamGroup.academic_year_id == ay.id)
        .order_by(ExamGroup.display_order)
    )).scalars().all()

    return {
        "success": True,
        "academic_year": {"id": str(ay.id), "label": ay.label},
        "groups": [{"id": str(g.id), "name": g.name, "display_order": g.display_order} for g in groups]
    }


@router.post("/exam-groups")
@require_privilege("exam_management")
async def create_exam_group(request: Request, db: AsyncSession = Depends(get_db)):
    user = request.state.user
    branch_id = uuid.UUID(user["branch_id"])
    data = await request.json()
    ay = (await db.execute(
        select(AcademicYear).where(AcademicYear.branch_id == branch_id, AcademicYear.is_current == True)
    )).scalar_one_or_none()
    if not ay:
        return JSONResponse({"success": False, "error": "No active academic year found"}, 400)

    group = ExamGroup(
        branch_id=branch_id, academic_year_id=ay.id,
        name=data["name"], display_order=data.get("display_order", 1)
    )
    db.add(group)
    await db.commit()
    return {"success": True, "id": str(group.id)}


@router.delete("/exam-groups/{group_id}")
@require_privilege("exam_management")
async def delete_exam_group(group_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    gid = uuid.UUID(group_id)
    group = (await db.execute(select(ExamGroup).where(ExamGroup.id == gid))).scalar_one_or_none()
    if not group:
        return JSONResponse({"success": False, "error": "Group not found"}, 404)
    cycles = (await db.execute(
        select(func.count(ExamCycle.id)).where(ExamCycle.exam_group_id == gid)
    )).scalar() or 0
    if cycles > 0:
        return JSONResponse({"success": False, "error": "Cannot delete group with exam cycles. Remove cycles first."}, 400)
    await db.delete(group)
    await db.commit()
    return {"success": True}


# ═══════════════════════════════════════════════════════════
#  ADMIN: EXAM CYCLES
# ═══════════════════════════════════════════════════════════

@router.get("/exam-cycles")
@require_privilege("exam_management")
async def list_exam_cycles(request: Request, db: AsyncSession = Depends(get_db)):
    user = request.state.user
    branch_id = uuid.UUID(user["branch_id"])
    ay = (await db.execute(
        select(AcademicYear).where(AcademicYear.branch_id == branch_id, AcademicYear.is_current == True)
    )).scalar_one_or_none()
    if not ay:
        return {"success": True, "cycles": []}

    cycles = (await db.execute(
        select(ExamCycle).where(ExamCycle.branch_id == branch_id, ExamCycle.academic_year_id == ay.id)
        .order_by(ExamCycle.created_at.desc())
    )).scalars().all()

    # Get class names
    class_ids = list({c.class_id for c in cycles})
    classes_map = {}
    if class_ids:
        classes = (await db.execute(select(Class).where(Class.id.in_(class_ids)))).scalars().all()
        classes_map = {c.id: c.name for c in classes}

    section_ids = list({c.section_id for c in cycles if c.section_id})
    sections_map = {}
    if section_ids:
        sections = (await db.execute(select(Section).where(Section.id.in_(section_ids)))).scalars().all()
        sections_map = {s.id: s.name for s in sections}

    # Get upload progress for each cycle
    result = []
    for c in cycles:
        trackers = (await db.execute(
            select(MarksUploadTracker).where(MarksUploadTracker.exam_cycle_id == c.id)
        )).scalars().all()
        total_t = len(trackers)
        submitted_t = sum(1 for t in trackers if t.status == UploadStatus.SUBMITTED.value)
        draft_t = sum(1 for t in trackers if t.status == UploadStatus.DRAFT.value and t.uploaded_at is not None)

        result.append({
            "id": str(c.id),
            "name": c.name,
            "class_name": classes_map.get(c.class_id, ""),
            "class_id": str(c.class_id),
            "section_name": sections_map.get(c.section_id, "") if c.section_id else "All",
            "section_id": str(c.section_id) if c.section_id else "",
            "marks_deadline": c.marks_deadline.isoformat() if c.marks_deadline else None,
            "result_date": c.result_date.isoformat() if c.result_date else None,
            "status": c.status,
            "max_marks": c.max_marks_default,
            "passing_marks": c.passing_marks_default,
            "weightage": c.weightage_percent,
            "exam_group_id": str(c.exam_group_id) if c.exam_group_id else "",
            "total_teachers": total_t,
            "submitted_teachers": submitted_t,
            "draft_teachers": draft_t,
            "created_at": c.created_at.isoformat() if c.created_at else None,
        })

    return {"success": True, "cycles": result}


@router.post("/exam-cycles")
@require_privilege("exam_management")
async def create_exam_cycle(request: Request, db: AsyncSession = Depends(get_db)):
    user = request.state.user
    branch_id = uuid.UUID(user["branch_id"])
    user_id = uuid.UUID(user["user_id"])
    data = await request.json()

    ay = (await db.execute(
        select(AcademicYear).where(AcademicYear.branch_id == branch_id, AcademicYear.is_current == True)
    )).scalar_one_or_none()
    if not ay:
        return JSONResponse({"success": False, "error": "No active academic year"}, 400)

    class_id = uuid.UUID(data["class_id"])
    section_id = uuid.UUID(data["section_id"]) if data.get("section_id") else None

    cycle = ExamCycle(
        branch_id=branch_id,
        academic_year_id=ay.id,
        exam_group_id=uuid.UUID(data["exam_group_id"]) if data.get("exam_group_id") else None,
        name=data["name"],
        class_id=class_id,
        section_id=section_id,
        marks_deadline=date.fromisoformat(data["marks_deadline"]) if data.get("marks_deadline") else None,
        result_date=date.fromisoformat(data["result_date"]) if data.get("result_date") else None,
        max_marks_default=float(data.get("max_marks", 100)),
        passing_marks_default=float(data.get("passing_marks", 33)),
        weightage_percent=float(data.get("weightage", 100)),
        template_id=uuid.UUID(data["template_id"]) if data.get("template_id") else None,
        rank_scope=data.get("rank_scope", "section"),
        created_by=user_id,
        status=ExamCycleStatus.OPEN.value,
    )
    db.add(cycle)
    await db.flush()

    # Auto-create upload trackers from class_subjects
    class_subjects = (await db.execute(
        select(ClassSubject).where(ClassSubject.class_id == class_id)
    )).scalars().all()

    teacher_count = 0
    for cs in class_subjects:
        if cs.teacher_id and cs.subject_id:
            tracker = MarksUploadTracker(
                exam_cycle_id=cycle.id,
                teacher_id=cs.teacher_id,
                subject_id=cs.subject_id,
                status=UploadStatus.DRAFT.value,
            )
            db.add(tracker)
            teacher_count += 1

    await db.commit()

    # Send notifications to all assigned teachers
    teacher_ids = list({cs.teacher_id for cs in class_subjects if cs.teacher_id})
    if teacher_ids:
        teachers = (await db.execute(
            select(Teacher).where(Teacher.id.in_(teacher_ids))
        )).scalars().all()
        class_obj = (await db.execute(select(Class).where(Class.id == class_id))).scalar_one_or_none()
        class_name = class_obj.name if class_obj else ""

        for t in teachers:
            if t.user_id:
                notif = Notification(
                    branch_id=branch_id, user_id=t.user_id,
                    type="ANNOUNCEMENT",
                    title="Marks Upload Required",
                    message=f"Please upload marks for '{cycle.name}' — {class_name}. Deadline: {data.get('marks_deadline', 'Not set')}",
                    channel="IN_APP", priority="high",
                    action_url="/teacher/upload-marks",
                    action_label="Upload Marks",
                )
                db.add(notif)
        await db.commit()

    return {"success": True, "id": str(cycle.id), "trackers_created": teacher_count}


@router.delete("/exam-cycles/{cycle_id}")
@require_privilege("exam_management")
async def delete_exam_cycle(cycle_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    cid = uuid.UUID(cycle_id)
    cycle = (await db.execute(select(ExamCycle).where(ExamCycle.id == cid))).scalar_one_or_none()
    if not cycle:
        return JSONResponse({"success": False, "error": "Exam cycle not found"}, 404)
    if cycle.status == ExamCycleStatus.PUBLISHED.value:
        return JSONResponse({"success": False, "error": "Cannot delete published exam cycle"}, 400)

    # Delete child records
    await db.execute(delete(MarksAuditLog).where(MarksAuditLog.exam_cycle_id == cid))
    await db.execute(delete(StudentResult).where(StudentResult.exam_cycle_id == cid))
    await db.execute(delete(StudentMarks).where(StudentMarks.exam_cycle_id == cid))
    await db.execute(delete(MarksUploadTracker).where(MarksUploadTracker.exam_cycle_id == cid))
    await db.execute(delete(ReportCardPDF).where(ReportCardPDF.exam_cycle_id == cid))
    await db.delete(cycle)
    await db.commit()
    return {"success": True}


@router.post("/exam-cycles/{cycle_id}/reopen")
@require_privilege("exam_management")
async def reopen_exam_cycle(cycle_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    """Admin reopens a published/locked exam cycle with mandatory reason."""
    user = request.state.user
    cid = uuid.UUID(cycle_id)
    data = await request.json()
    reason = data.get("reason", "").strip()
    if not reason:
        return JSONResponse({"success": False, "error": "Reason is required to reopen"}, 400)

    cycle = (await db.execute(select(ExamCycle).where(ExamCycle.id == cid))).scalar_one_or_none()
    if not cycle:
        return JSONResponse({"success": False, "error": "Exam cycle not found"}, 404)

    old_status = cycle.status
    cycle.status = ExamCycleStatus.REOPENED.value
    cycle.updated_at = datetime.utcnow()

    # Reset all trackers to draft
    await db.execute(
        update(MarksUploadTracker)
        .where(MarksUploadTracker.exam_cycle_id == cid)
        .values(status=UploadStatus.DRAFT.value)
    )

    # Audit log
    audit = MarksAuditLog(
        exam_cycle_id=cid,
        changed_by=uuid.UUID(user["user_id"]),
        action=AuditAction.REOPEN.value,
        field_name="status",
        old_value=old_status,
        new_value=ExamCycleStatus.REOPENED.value,
        ip_address=get_client_ip(request),
        reason=reason,
    )
    db.add(audit)
    await db.commit()
    return {"success": True, "status": cycle.status}


# ═══════════════════════════════════════════════════════════
#  ADMIN: REPORT CARD TEMPLATES
# ═══════════════════════════════════════════════════════════

@router.get("/templates")
@require_privilege("results")
async def list_templates(request: Request, db: AsyncSession = Depends(get_db)):
    user = request.state.user
    branch_id = uuid.UUID(user["branch_id"])
    templates = (await db.execute(
        select(ReportCardTemplate).where(
            ReportCardTemplate.branch_id == branch_id, ReportCardTemplate.is_active == True
        ).order_by(ReportCardTemplate.created_at.desc())
    )).scalars().all()
    return {
        "success": True,
        "templates": [{
            "id": str(t.id), "name": t.name, "is_default": t.is_default,
            "page_size": t.page_size, "orientation": t.orientation,
            "show_rank": t.show_rank, "show_attendance": t.show_attendance,
            "show_remarks": t.show_remarks, "show_grade": t.show_grade,
            "layout_json": t.layout_json, "header_config": t.header_config,
            "footer_config": t.footer_config, "grading_scale": t.grading_scale,
        } for t in templates]
    }


@router.post("/templates")
@require_privilege("results")
async def save_template(request: Request, db: AsyncSession = Depends(get_db)):
    user = request.state.user
    branch_id = uuid.UUID(user["branch_id"])
    data = await request.json()

    template_id = data.get("id")
    if template_id:
        template = (await db.execute(
            select(ReportCardTemplate).where(ReportCardTemplate.id == uuid.UUID(template_id))
        )).scalar_one_or_none()
        if not template:
            return JSONResponse({"success": False, "error": "Template not found"}, 404)
    else:
        template = ReportCardTemplate(branch_id=branch_id, created_by=uuid.UUID(user["user_id"]))
        db.add(template)

    template.name = data.get("name", template.name if template_id else "Untitled")
    template.layout_json = data.get("layout_json")
    template.page_size = data.get("page_size", "A4")
    template.orientation = data.get("orientation", "portrait")
    template.header_config = data.get("header_config")
    template.footer_config = data.get("footer_config")
    template.grading_scale = data.get("grading_scale")
    template.show_rank = data.get("show_rank", True)
    template.show_attendance = data.get("show_attendance", True)
    template.show_remarks = data.get("show_remarks", True)
    template.show_grade = data.get("show_grade", True)
    template.updated_at = datetime.utcnow()

    if data.get("is_default"):
        await db.execute(
            update(ReportCardTemplate)
            .where(ReportCardTemplate.branch_id == branch_id)
            .values(is_default=False)
        )
        template.is_default = True

    await db.commit()
    return {"success": True, "id": str(template.id)}


@router.delete("/templates/{template_id}")
@require_privilege("results")
async def delete_template(template_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    tid = uuid.UUID(template_id)
    template = (await db.execute(select(ReportCardTemplate).where(ReportCardTemplate.id == tid))).scalar_one_or_none()
    if not template:
        return JSONResponse({"success": False, "error": "Template not found"}, 404)
    template.is_active = False
    await db.commit()
    return {"success": True}


# ═══════════════════════════════════════════════════════════
#  TEACHER: UPLOAD MARKS
# ═══════════════════════════════════════════════════════════

@router.get("/teacher/my-cycles")
@require_role(UserRole.TEACHER)
async def teacher_my_cycles(request: Request, db: AsyncSession = Depends(get_db)):
    """Get exam cycles where this teacher has upload assignments."""
    user = request.state.user
    user_id = uuid.UUID(user["user_id"])
    teacher = (await db.execute(
        select(Teacher).where(Teacher.user_id == user_id, Teacher.is_active == True)
    )).scalar_one_or_none()
    if not teacher:
        return {"success": True, "cycles": []}

    trackers = (await db.execute(
        select(MarksUploadTracker).where(MarksUploadTracker.teacher_id == teacher.id)
    )).scalars().all()

    cycle_ids = list({t.exam_cycle_id for t in trackers})
    if not cycle_ids:
        return {"success": True, "cycles": []}

    cycles = (await db.execute(
        select(ExamCycle).where(
            ExamCycle.id.in_(cycle_ids),
            ExamCycle.status.in_([ExamCycleStatus.OPEN.value, ExamCycleStatus.REOPENED.value])
        ).order_by(ExamCycle.created_at.desc())
    )).scalars().all()

    # Map names
    class_ids = list({c.class_id for c in cycles})
    classes_map = {}
    if class_ids:
        classes = (await db.execute(select(Class).where(Class.id.in_(class_ids)))).scalars().all()
        classes_map = {c.id: c.name for c in classes}

    subject_ids = list({t.subject_id for t in trackers})
    subjects_map = {}
    if subject_ids:
        subjects = (await db.execute(select(Subject).where(Subject.id.in_(subject_ids)))).scalars().all()
        subjects_map = {s.id: s.name for s in subjects}

    result = []
    for c in cycles:
        my_trackers = [t for t in trackers if t.exam_cycle_id == c.id]
        subjects_list = []
        for t in my_trackers:
            subjects_list.append({
                "tracker_id": str(t.id),
                "subject_id": str(t.subject_id),
                "subject_name": subjects_map.get(t.subject_id, ""),
                "status": t.status,
                "uploaded_at": t.uploaded_at.isoformat() if t.uploaded_at else None,
                "submitted_at": t.submitted_at.isoformat() if t.submitted_at else None,
                "row_count": t.row_count,
            })
        result.append({
            "id": str(c.id),
            "name": c.name,
            "class_name": classes_map.get(c.class_id, ""),
            "class_id": str(c.class_id),
            "section_id": str(c.section_id) if c.section_id else "",
            "marks_deadline": c.marks_deadline.isoformat() if c.marks_deadline else None,
            "status": c.status,
            "max_marks": c.max_marks_default,
            "passing_marks": c.passing_marks_default,
            "subjects": subjects_list,
        })

    return {"success": True, "cycles": result}


@router.get("/teacher/download-template")
@require_role(UserRole.TEACHER)
async def download_marks_template(
    request: Request,
    cycle_id: str = Query(...),
    subject_id: str = Query(...),
    db: AsyncSession = Depends(get_db)
):
    """Generate and return Excel template pre-filled with student names."""
    user = request.state.user
    user_id = uuid.UUID(user["user_id"])
    teacher = (await db.execute(
        select(Teacher).where(Teacher.user_id == user_id, Teacher.is_active == True)
    )).scalar_one_or_none()
    if not teacher:
        raise HTTPException(403, "Teacher profile not found")

    cid = uuid.UUID(cycle_id)
    sid = uuid.UUID(subject_id)
    cycle = (await db.execute(select(ExamCycle).where(ExamCycle.id == cid))).scalar_one_or_none()
    if not cycle:
        raise HTTPException(404, "Exam cycle not found")

    # Verify teacher has this assignment
    tracker = (await db.execute(
        select(MarksUploadTracker).where(
            MarksUploadTracker.exam_cycle_id == cid,
            MarksUploadTracker.teacher_id == teacher.id,
            MarksUploadTracker.subject_id == sid,
        )
    )).scalar_one_or_none()
    if not tracker:
        raise HTTPException(403, "You are not assigned to this subject for this exam")

    # Get students
    query = select(Student).where(
        Student.class_id == cycle.class_id, Student.is_active == True
    )
    if cycle.section_id:
        query = query.where(Student.section_id == cycle.section_id)
    query = query.order_by(Student.roll_number, Student.first_name)
    students = (await db.execute(query)).scalars().all()

    student_list = [{
        "id": str(s.id), "first_name": s.first_name, "last_name": s.last_name or "",
        "roll_number": s.roll_number or "",
    } for s in students]

    # Get names
    subject = (await db.execute(select(Subject).where(Subject.id == sid))).scalar_one_or_none()
    class_obj = (await db.execute(select(Class).where(Class.id == cycle.class_id))).scalar_one_or_none()

    excel_bytes = generate_marks_template(
        student_list, subject.name if subject else "Subject",
        cycle.name, class_obj.name if class_obj else "Class",
        max_marks=cycle.max_marks_default
    )

    filename = f"marks_{cycle.name}_{subject.name if subject else 'subject'}_{class_obj.name if class_obj else 'class'}.xlsx"
    return StreamingResponse(
        io.BytesIO(excel_bytes),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@router.post("/teacher/upload-marks")
@require_role(UserRole.TEACHER)
async def upload_marks(
    request: Request,
    cycle_id: str = Query(...),
    subject_id: str = Query(...),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db)
):
    """Upload marks from Excel file. Replaces existing draft marks (idempotent)."""
    user = request.state.user
    user_id = uuid.UUID(user["user_id"])
    teacher = (await db.execute(
        select(Teacher).where(Teacher.user_id == user_id, Teacher.is_active == True)
    )).scalar_one_or_none()
    if not teacher:
        return JSONResponse({"success": False, "error": "Teacher profile not found"}, 403)

    cid = uuid.UUID(cycle_id)
    sid = uuid.UUID(subject_id)
    cycle = (await db.execute(select(ExamCycle).where(ExamCycle.id == cid))).scalar_one_or_none()
    if not cycle:
        return JSONResponse({"success": False, "error": "Exam cycle not found"}, 404)

    if cycle.status not in (ExamCycleStatus.OPEN.value, ExamCycleStatus.REOPENED.value):
        return JSONResponse({"success": False, "error": "Exam cycle is not open for uploads"}, 400)

    # Verify assignment
    tracker = (await db.execute(
        select(MarksUploadTracker).where(
            MarksUploadTracker.exam_cycle_id == cid,
            MarksUploadTracker.teacher_id == teacher.id,
            MarksUploadTracker.subject_id == sid,
        )
    )).scalar_one_or_none()
    if not tracker:
        return JSONResponse({"success": False, "error": "Not assigned to this subject"}, 403)

    if tracker.status == UploadStatus.SUBMITTED.value:
        return JSONResponse({"success": False, "error": "Marks already submitted. Retract submission first to re-upload."}, 400)

    # Parse Excel
    file_bytes = await file.read()
    records, errors = parse_marks_upload(file_bytes, max_marks=cycle.max_marks_default)

    if errors:
        return JSONResponse({"success": False, "errors": errors}, 400)

    if not records:
        return JSONResponse({"success": False, "error": "No valid records found in the file"}, 400)

    # Delete existing draft marks for this cycle+subject+teacher (idempotent)
    existing_marks = (await db.execute(
        select(StudentMarks).where(
            StudentMarks.exam_cycle_id == cid,
            StudentMarks.subject_id == sid,
            StudentMarks.teacher_id == teacher.id,
            StudentMarks.is_retest == False,
        )
    )).scalars().all()

    for em in existing_marks:
        await db.delete(em)
    await db.flush()

    # Insert new marks
    saved_count = 0
    for rec in records:
        marks_obtained = rec.get("marks_obtained")
        special_code = rec.get("special_code")
        grace = 0
        final = marks_obtained

        if special_code:
            final = None

        grade = None
        if final is not None and cycle.max_marks_default > 0:
            pct = (final / cycle.max_marks_default) * 100
            grade = calculate_grade(pct)

        mark = StudentMarks(
            exam_cycle_id=cid,
            student_id=uuid.UUID(rec["student_id"]),
            subject_id=sid,
            teacher_id=teacher.id,
            marks_obtained=marks_obtained,
            max_marks=cycle.max_marks_default,
            special_code=special_code,
            grace_marks=grace,
            final_marks=final,
            grade=grade,
            remarks=rec.get("remarks"),
            is_retest=False,
        )
        db.add(mark)
        saved_count += 1

    # Update tracker
    tracker.status = UploadStatus.DRAFT.value
    tracker.uploaded_at = datetime.utcnow()
    tracker.file_name = file.filename
    tracker.row_count = saved_count

    # Audit log
    audit = MarksAuditLog(
        exam_cycle_id=cid,
        changed_by=user_id,
        action=AuditAction.UPLOAD.value,
        field_name="bulk_upload",
        new_value=f"{saved_count} records from {file.filename}",
        ip_address=get_client_ip(request),
    )
    db.add(audit)

    await db.commit()
    return {"success": True, "saved": saved_count, "file": file.filename}


@router.post("/teacher/save-marks-manual")
@require_role(UserRole.TEACHER)
async def save_marks_manual(request: Request, db: AsyncSession = Depends(get_db)):
    """Save marks entered manually (not via Excel)."""
    user = request.state.user
    user_id = uuid.UUID(user["user_id"])
    teacher = (await db.execute(
        select(Teacher).where(Teacher.user_id == user_id, Teacher.is_active == True)
    )).scalar_one_or_none()
    if not teacher:
        return JSONResponse({"success": False, "error": "Teacher profile not found"}, 403)

    data = await request.json()
    cid = uuid.UUID(data["cycle_id"])
    sid = uuid.UUID(data["subject_id"])
    records = data.get("records", [])

    cycle = (await db.execute(select(ExamCycle).where(ExamCycle.id == cid))).scalar_one_or_none()
    if not cycle or cycle.status not in (ExamCycleStatus.OPEN.value, ExamCycleStatus.REOPENED.value):
        return JSONResponse({"success": False, "error": "Exam cycle not open"}, 400)

    tracker = (await db.execute(
        select(MarksUploadTracker).where(
            MarksUploadTracker.exam_cycle_id == cid,
            MarksUploadTracker.teacher_id == teacher.id,
            MarksUploadTracker.subject_id == sid,
        )
    )).scalar_one_or_none()
    if not tracker:
        return JSONResponse({"success": False, "error": "Not assigned"}, 403)
    if tracker.status == UploadStatus.SUBMITTED.value:
        return JSONResponse({"success": False, "error": "Already submitted"}, 400)

    saved = 0
    for rec in records:
        student_id = uuid.UUID(rec["student_id"])
        marks_obtained = rec.get("marks_obtained")
        special_code = rec.get("special_code")
        remarks = rec.get("remarks")

        # Upsert
        existing = (await db.execute(
            select(StudentMarks).where(
                StudentMarks.exam_cycle_id == cid,
                StudentMarks.student_id == student_id,
                StudentMarks.subject_id == sid,
                StudentMarks.is_retest == False,
            )
        )).scalar_one_or_none()

        final = None
        grade = None
        if special_code:
            marks_obtained = None
        else:
            if marks_obtained is not None:
                final = float(marks_obtained)
                if cycle.max_marks_default > 0:
                    grade = calculate_grade((final / cycle.max_marks_default) * 100)

        if existing:
            # Audit old values
            if existing.marks_obtained != marks_obtained or existing.special_code != special_code:
                audit = MarksAuditLog(
                    student_marks_id=existing.id, exam_cycle_id=cid,
                    changed_by=user_id, action=AuditAction.EDIT.value,
                    field_name="marks_obtained",
                    old_value=str(existing.marks_obtained) if existing.marks_obtained is not None else existing.special_code,
                    new_value=str(marks_obtained) if marks_obtained is not None else special_code,
                    ip_address=get_client_ip(request),
                )
                db.add(audit)
            existing.marks_obtained = marks_obtained
            existing.special_code = special_code
            existing.final_marks = final
            existing.grade = grade
            existing.remarks = remarks
            existing.updated_at = datetime.utcnow()
        else:
            mark = StudentMarks(
                exam_cycle_id=cid, student_id=student_id, subject_id=sid,
                teacher_id=teacher.id, marks_obtained=marks_obtained,
                max_marks=cycle.max_marks_default, special_code=special_code,
                grace_marks=0, final_marks=final, grade=grade,
                remarks=remarks, is_retest=False,
            )
            db.add(mark)
        saved += 1

    tracker.uploaded_at = datetime.utcnow()
    tracker.row_count = saved
    await db.commit()
    return {"success": True, "saved": saved}


@router.get("/teacher/load-marks")
@require_role(UserRole.TEACHER)
async def load_marks_for_entry(
    request: Request,
    cycle_id: str = Query(...),
    subject_id: str = Query(...),
    db: AsyncSession = Depends(get_db)
):
    """Load existing marks for manual entry view."""
    user = request.state.user
    user_id = uuid.UUID(user["user_id"])
    teacher = (await db.execute(
        select(Teacher).where(Teacher.user_id == user_id, Teacher.is_active == True)
    )).scalar_one_or_none()
    if not teacher:
        return {"success": True, "students": []}

    cid = uuid.UUID(cycle_id)
    sid = uuid.UUID(subject_id)
    cycle = (await db.execute(select(ExamCycle).where(ExamCycle.id == cid))).scalar_one_or_none()
    if not cycle:
        return {"success": True, "students": []}

    # Get students
    query = select(Student).where(Student.class_id == cycle.class_id, Student.is_active == True)
    if cycle.section_id:
        query = query.where(Student.section_id == cycle.section_id)
    students = (await db.execute(query.order_by(Student.roll_number, Student.first_name))).scalars().all()

    # Get existing marks
    marks = (await db.execute(
        select(StudentMarks).where(
            StudentMarks.exam_cycle_id == cid,
            StudentMarks.subject_id == sid,
            StudentMarks.is_retest == False,
        )
    )).scalars().all()
    marks_map = {m.student_id: m for m in marks}

    result = []
    for s in students:
        m = marks_map.get(s.id)
        result.append({
            "student_id": str(s.id),
            "name": f"{s.first_name} {s.last_name or ''}".strip(),
            "roll": s.roll_number or "",
            "marks_obtained": m.marks_obtained if m else None,
            "special_code": m.special_code if m else None,
            "grade": m.grade if m else None,
            "remarks": m.remarks if m else None,
        })

    return {"success": True, "students": result, "max_marks": cycle.max_marks_default}


@router.post("/teacher/submit-marks")
@require_role(UserRole.TEACHER)
async def submit_marks(request: Request, db: AsyncSession = Depends(get_db)):
    """Teacher clicks Submit Final — marks become submitted."""
    user = request.state.user
    user_id = uuid.UUID(user["user_id"])
    data = await request.json()
    teacher = (await db.execute(
        select(Teacher).where(Teacher.user_id == user_id, Teacher.is_active == True)
    )).scalar_one_or_none()
    if not teacher:
        return JSONResponse({"success": False, "error": "Teacher profile not found"}, 403)

    cid = uuid.UUID(data["cycle_id"])
    sid = uuid.UUID(data["subject_id"])

    tracker = (await db.execute(
        select(MarksUploadTracker).where(
            MarksUploadTracker.exam_cycle_id == cid,
            MarksUploadTracker.teacher_id == teacher.id,
            MarksUploadTracker.subject_id == sid,
        )
    )).scalar_one_or_none()
    if not tracker:
        return JSONResponse({"success": False, "error": "Tracker not found"}, 404)
    if not tracker.uploaded_at:
        return JSONResponse({"success": False, "error": "No marks uploaded yet"}, 400)

    tracker.status = UploadStatus.SUBMITTED.value
    tracker.submitted_at = datetime.utcnow()

    # Audit
    audit = MarksAuditLog(
        exam_cycle_id=cid, changed_by=user_id,
        action=AuditAction.SUBMIT.value,
        field_name="tracker_status", old_value="draft", new_value="submitted",
        ip_address=get_client_ip(request),
    )
    db.add(audit)

    # Check if all teachers submitted → auto move to VERIFICATION_PENDING
    all_trackers = (await db.execute(
        select(MarksUploadTracker).where(MarksUploadTracker.exam_cycle_id == cid)
    )).scalars().all()
    all_submitted = all(t.status == UploadStatus.SUBMITTED.value for t in all_trackers)

    cycle = (await db.execute(select(ExamCycle).where(ExamCycle.id == cid))).scalar_one_or_none()
    if all_submitted and cycle:
        cycle.status = ExamCycleStatus.VERIFICATION_PENDING.value
        cycle.updated_at = datetime.utcnow()

        # Notify class teacher
        section = None
        if cycle.section_id:
            section = (await db.execute(
                select(Section).where(Section.id == cycle.section_id)
            )).scalar_one_or_none()
        if section and section.class_teacher_id:
            ct = (await db.execute(
                select(Teacher).where(Teacher.id == section.class_teacher_id)
            )).scalar_one_or_none()
            if ct and ct.user_id:
                class_obj = (await db.execute(select(Class).where(Class.id == cycle.class_id))).scalar_one_or_none()
                notif = Notification(
                    branch_id=cycle.branch_id, user_id=ct.user_id,
                    type="ANNOUNCEMENT",
                    title="All Marks Uploaded — Review Required",
                    message=f"All teachers have submitted marks for '{cycle.name}' — {class_obj.name if class_obj else ''}. Please review and publish.",
                    channel="IN_APP", priority="urgent",
                    action_url="/teacher/class-review",
                    action_label="Review & Publish",
                )
                db.add(notif)

    await db.commit()
    return {"success": True, "all_submitted": all_submitted, "status": cycle.status if cycle else ""}


@router.post("/teacher/retract-submission")
@require_role(UserRole.TEACHER)
async def retract_submission(request: Request, db: AsyncSession = Depends(get_db)):
    """Teacher retracts a submission back to draft (only before lock)."""
    user = request.state.user
    user_id = uuid.UUID(user["user_id"])
    data = await request.json()
    teacher = (await db.execute(
        select(Teacher).where(Teacher.user_id == user_id, Teacher.is_active == True)
    )).scalar_one_or_none()
    if not teacher:
        return JSONResponse({"success": False, "error": "Not found"}, 403)

    cid = uuid.UUID(data["cycle_id"])
    sid = uuid.UUID(data["subject_id"])

    cycle = (await db.execute(select(ExamCycle).where(ExamCycle.id == cid))).scalar_one_or_none()
    if not cycle or cycle.status in (ExamCycleStatus.LOCKED.value, ExamCycleStatus.PUBLISHED.value):
        return JSONResponse({"success": False, "error": "Cannot retract — exam cycle is locked or published"}, 400)

    tracker = (await db.execute(
        select(MarksUploadTracker).where(
            MarksUploadTracker.exam_cycle_id == cid,
            MarksUploadTracker.teacher_id == teacher.id,
            MarksUploadTracker.subject_id == sid,
        )
    )).scalar_one_or_none()
    if not tracker:
        return JSONResponse({"success": False, "error": "Tracker not found"}, 404)

    tracker.status = UploadStatus.DRAFT.value
    tracker.submitted_at = None

    # Reset cycle status if it was verification_pending
    if cycle.status == ExamCycleStatus.VERIFICATION_PENDING.value:
        cycle.status = ExamCycleStatus.OPEN.value
        cycle.updated_at = datetime.utcnow()

    await db.commit()
    return {"success": True}


# ═══════════════════════════════════════════════════════════
#  CLASS TEACHER: REVIEW & PUBLISH
# ═══════════════════════════════════════════════════════════

@router.get("/class-teacher/my-reviews")
@require_role(UserRole.TEACHER)
async def class_teacher_reviews(request: Request, db: AsyncSession = Depends(get_db)):
    """Get cycles pending review for the class teacher."""
    user = request.state.user
    user_id = uuid.UUID(user["user_id"])
    teacher = (await db.execute(
        select(Teacher).where(Teacher.user_id == user_id, Teacher.is_active == True)
    )).scalar_one_or_none()
    if not teacher or not teacher.is_class_teacher or not teacher.class_teacher_of:
        return {"success": True, "cycles": [], "is_class_teacher": False}

    section = (await db.execute(
        select(Section).where(Section.id == teacher.class_teacher_of)
    )).scalar_one_or_none()
    if not section:
        return {"success": True, "cycles": [], "is_class_teacher": True}

    cycles = (await db.execute(
        select(ExamCycle).where(
            ExamCycle.class_id == section.class_id,
            ExamCycle.status.in_([
                ExamCycleStatus.VERIFICATION_PENDING.value,
                ExamCycleStatus.LOCKED.value,
                ExamCycleStatus.PUBLISHED.value,
            ])
        ).order_by(ExamCycle.created_at.desc())
    )).scalars().all()

    class_obj = (await db.execute(select(Class).where(Class.id == section.class_id))).scalar_one_or_none()

    result = []
    for c in cycles:
        result.append({
            "id": str(c.id), "name": c.name,
            "class_name": class_obj.name if class_obj else "",
            "section_name": section.name,
            "status": c.status,
            "marks_deadline": c.marks_deadline.isoformat() if c.marks_deadline else None,
        })
    return {"success": True, "cycles": result, "is_class_teacher": True,
            "class_name": class_obj.name if class_obj else "", "section_name": section.name}


@router.get("/class-teacher/review-data")
@require_role(UserRole.TEACHER)
async def get_review_data(
    request: Request,
    cycle_id: str = Query(...),
    db: AsyncSession = Depends(get_db)
):
    """Get compiled marks for all students for class teacher review."""
    cid = uuid.UUID(cycle_id)
    cycle = (await db.execute(select(ExamCycle).where(ExamCycle.id == cid))).scalar_one_or_none()
    if not cycle:
        return JSONResponse({"success": False, "error": "Not found"}, 404)

    # Get students
    query = select(Student).where(Student.class_id == cycle.class_id, Student.is_active == True)
    if cycle.section_id:
        query = query.where(Student.section_id == cycle.section_id)
    students = (await db.execute(query.order_by(Student.roll_number, Student.first_name))).scalars().all()

    # Get all marks for this cycle
    all_marks = (await db.execute(
        select(StudentMarks).where(StudentMarks.exam_cycle_id == cid, StudentMarks.is_retest == False)
    )).scalars().all()

    # Get subjects
    subject_ids = list({m.subject_id for m in all_marks})
    subjects_map = {}
    if subject_ids:
        subjects = (await db.execute(select(Subject).where(Subject.id.in_(subject_ids)))).scalars().all()
        subjects_map = {s.id: s.name for s in subjects}

    # Get upload trackers for teacher names
    trackers = (await db.execute(
        select(MarksUploadTracker).where(MarksUploadTracker.exam_cycle_id == cid)
    )).scalars().all()
    teacher_ids = list({t.teacher_id for t in trackers})
    teachers_map = {}
    if teacher_ids:
        teachers = (await db.execute(select(Teacher).where(Teacher.id.in_(teacher_ids)))).scalars().all()
        teachers_map = {t.id: f"{t.first_name} {t.last_name or ''}".strip() for t in teachers}

    subjects_info = []
    for t in trackers:
        subjects_info.append({
            "subject_id": str(t.subject_id),
            "subject_name": subjects_map.get(t.subject_id, ""),
            "teacher_name": teachers_map.get(t.teacher_id, ""),
            "status": t.status,
        })

    # Build marks matrix
    marks_by_student = {}
    for m in all_marks:
        if m.student_id not in marks_by_student:
            marks_by_student[m.student_id] = {}
        marks_by_student[m.student_id][m.subject_id] = m

    student_data = []
    for s in students:
        student_marks = marks_by_student.get(s.id, {})
        total = 0
        max_total = 0
        subjects_result = []
        all_pass = True

        for sid_key in subject_ids:
            m = student_marks.get(sid_key)
            if m:
                if m.special_code:
                    subjects_result.append({
                        "subject_id": str(sid_key),
                        "marks": None, "special_code": m.special_code,
                        "final": None, "grade": "-", "grace": 0,
                    })
                    if m.special_code not in ("NA", "EX"):
                        all_pass = False
                else:
                    final = m.final_marks or m.marks_obtained or 0
                    subjects_result.append({
                        "subject_id": str(sid_key),
                        "marks": m.marks_obtained, "special_code": None,
                        "final": final, "grade": m.grade or "",
                        "grace": m.grace_marks or 0,
                    })
                    total += final
                    max_total += m.max_marks
                    if final < cycle.passing_marks_default:
                        all_pass = False
            else:
                subjects_result.append({
                    "subject_id": str(sid_key), "marks": None,
                    "special_code": None, "final": None, "grade": "-", "grace": 0,
                })

        pct = round((total / max_total * 100) if max_total > 0 else 0, 1)
        student_data.append({
            "student_id": str(s.id),
            "name": f"{s.first_name} {s.last_name or ''}".strip(),
            "roll": s.roll_number or "",
            "subjects": subjects_result,
            "total": total, "max_total": max_total,
            "percentage": pct, "grade": calculate_grade(pct),
            "passed": all_pass,
        })

    # Sort by percentage desc for ranking
    student_data.sort(key=lambda x: x["percentage"], reverse=True)
    rank = 0
    prev_pct = None
    for idx, sd in enumerate(student_data):
        if sd["percentage"] != prev_pct:
            rank = idx + 1
        sd["rank"] = rank
        prev_pct = sd["percentage"]

    return {
        "success": True,
        "cycle": {
            "id": str(cycle.id), "name": cycle.name, "status": cycle.status,
            "max_marks": cycle.max_marks_default, "passing_marks": cycle.passing_marks_default,
        },
        "subjects": subjects_info,
        "students": student_data,
    }


@router.post("/class-teacher/lock")
@require_role(UserRole.TEACHER)
async def lock_exam_cycle(request: Request, db: AsyncSession = Depends(get_db)):
    """Class teacher locks marks after verification."""
    user = request.state.user
    user_id = uuid.UUID(user["user_id"])
    data = await request.json()
    cid = uuid.UUID(data["cycle_id"])

    teacher = (await db.execute(
        select(Teacher).where(Teacher.user_id == user_id, Teacher.is_active == True)
    )).scalar_one_or_none()
    if not teacher or not teacher.is_class_teacher:
        return JSONResponse({"success": False, "error": "Only class teacher can lock"}, 403)

    cycle = (await db.execute(select(ExamCycle).where(ExamCycle.id == cid))).scalar_one_or_none()
    if not cycle or cycle.status != ExamCycleStatus.VERIFICATION_PENDING.value:
        return JSONResponse({"success": False, "error": "Cycle must be in verification_pending state to lock"}, 400)

    cycle.status = ExamCycleStatus.LOCKED.value
    cycle.updated_at = datetime.utcnow()

    # Compute and save student results
    await _compute_results(db, cycle, user_id, data.get("remarks", {}))

    # Audit
    audit = MarksAuditLog(
        exam_cycle_id=cid, changed_by=user_id,
        action=AuditAction.LOCK.value,
        field_name="status", old_value="verification_pending", new_value="locked",
        ip_address=get_client_ip(request),
    )
    db.add(audit)
    await db.commit()
    return {"success": True, "status": "locked"}


@router.post("/class-teacher/publish")
@require_role(UserRole.TEACHER)
async def publish_results(request: Request, db: AsyncSession = Depends(get_db)):
    """Class teacher publishes results — students get notified."""
    user = request.state.user
    user_id = uuid.UUID(user["user_id"])
    data = await request.json()
    cid = uuid.UUID(data["cycle_id"])

    teacher = (await db.execute(
        select(Teacher).where(Teacher.user_id == user_id, Teacher.is_active == True)
    )).scalar_one_or_none()
    if not teacher or not teacher.is_class_teacher:
        return JSONResponse({"success": False, "error": "Only class teacher can publish"}, 403)

    cycle = (await db.execute(select(ExamCycle).where(ExamCycle.id == cid))).scalar_one_or_none()
    if not cycle or cycle.status != ExamCycleStatus.LOCKED.value:
        return JSONResponse({"success": False, "error": "Cycle must be locked before publishing"}, 400)

    cycle.status = ExamCycleStatus.PUBLISHED.value
    cycle.published_at = datetime.utcnow()
    cycle.published_by = user_id
    cycle.updated_at = datetime.utcnow()

    # Audit
    audit = MarksAuditLog(
        exam_cycle_id=cid, changed_by=user_id,
        action=AuditAction.PUBLISH.value,
        field_name="status", old_value="locked", new_value="published",
        ip_address=get_client_ip(request),
    )
    db.add(audit)

    # Notify all students
    query = select(Student).where(Student.class_id == cycle.class_id, Student.is_active == True)
    if cycle.section_id:
        query = query.where(Student.section_id == cycle.section_id)
    students = (await db.execute(query)).scalars().all()

    class_obj = (await db.execute(select(Class).where(Class.id == cycle.class_id))).scalar_one_or_none()
    class_name = class_obj.name if class_obj else ""

    for s in students:
        if s.user_id:
            notif = Notification(
                branch_id=cycle.branch_id, user_id=s.user_id,
                type="RESULT_PUBLISHED",
                title="Results Declared!",
                message=f"Results for '{cycle.name}' — {class_name} have been published. View your report card now.",
                channel="IN_APP", priority="high",
                action_url="/student/report-card",
                action_label="View Report Card",
            )
            db.add(notif)

    await db.commit()
    return {"success": True, "status": "published", "students_notified": len(students)}


async def _compute_results(db, cycle, user_id, remarks_map=None):
    """Compute aggregated results for all students in an exam cycle."""
    if remarks_map is None:
        remarks_map = {}

    cid = cycle.id
    query = select(Student).where(Student.class_id == cycle.class_id, Student.is_active == True)
    if cycle.section_id:
        query = query.where(Student.section_id == cycle.section_id)
    students = (await db.execute(query)).scalars().all()

    all_marks = (await db.execute(
        select(StudentMarks).where(StudentMarks.exam_cycle_id == cid, StudentMarks.is_retest == False)
    )).scalars().all()

    marks_by_student = {}
    for m in all_marks:
        if m.student_id not in marks_by_student:
            marks_by_student[m.student_id] = []
        marks_by_student[m.student_id].append(m)

    # Delete existing results
    await db.execute(delete(StudentResult).where(StudentResult.exam_cycle_id == cid))

    results_data = []
    for s in students:
        smarks = marks_by_student.get(s.id, [])
        total = 0
        max_total = 0
        failed_subjects = 0

        for m in smarks:
            if m.special_code in ("NA", "EX"):
                continue
            if m.special_code in ("AB", "ML"):
                max_total += m.max_marks
                failed_subjects += 1
                continue
            final = m.final_marks or m.marks_obtained or 0
            total += final
            max_total += m.max_marks
            if final < cycle.passing_marks_default:
                failed_subjects += 1

        pct = round((total / max_total * 100) if max_total > 0 else 0, 1)
        grade = calculate_grade(pct)

        if failed_subjects == 0:
            status = ResultStatus.PROMOTED.value
        elif failed_subjects <= 2:
            status = ResultStatus.COMPARTMENT.value
        else:
            status = ResultStatus.DETAINED.value

        results_data.append({
            "student_id": s.id, "total": total, "max_total": max_total,
            "pct": pct, "grade": grade, "status": status,
        })

    # Sort by pct desc for ranking
    results_data.sort(key=lambda x: x["pct"], reverse=True)
    rank = 0
    prev_pct = None
    for idx, rd in enumerate(results_data):
        if rd["pct"] != prev_pct:
            rank = idx + 1
        rd["rank"] = rank
        prev_pct = rd["pct"]

    for rd in results_data:
        result = StudentResult(
            exam_cycle_id=cid, student_id=rd["student_id"],
            total_marks=rd["total"], max_total=rd["max_total"],
            percentage=rd["pct"], grade=rd["grade"], rank=rd["rank"],
            result_status=rd["status"],
            class_teacher_remarks=remarks_map.get(str(rd["student_id"]), ""),
            verified_by=user_id, verified_at=datetime.utcnow(),
        )
        db.add(result)

    await db.flush()


# ═══════════════════════════════════════════════════════════
#  ADMIN: BULK GRACE MARKS & MODERATION
# ═══════════════════════════════════════════════════════════

@router.post("/admin/apply-grace")
@require_privilege("exam_management")
async def apply_grace_marks(request: Request, db: AsyncSession = Depends(get_db)):
    """Apply grace marks in bulk."""
    user = request.state.user
    user_id = uuid.UUID(user["user_id"])
    data = await request.json()
    cid = uuid.UUID(data["cycle_id"])
    subject_id = uuid.UUID(data["subject_id"]) if data.get("subject_id") else None
    grace_amount = float(data.get("grace_marks", 0))
    reason = data.get("reason", "")

    if grace_amount <= 0:
        return JSONResponse({"success": False, "error": "Grace marks must be positive"}, 400)

    query = select(StudentMarks).where(
        StudentMarks.exam_cycle_id == cid, StudentMarks.is_retest == False,
        StudentMarks.special_code.is_(None),
    )
    if subject_id:
        query = query.where(StudentMarks.subject_id == subject_id)

    marks = (await db.execute(query)).scalars().all()
    updated = 0
    for m in marks:
        old_grace = m.grace_marks or 0
        m.grace_marks = old_grace + grace_amount
        m.final_marks = (m.marks_obtained or 0) + m.grace_marks
        if m.max_marks > 0:
            m.grade = calculate_grade((m.final_marks / m.max_marks) * 100)
        m.updated_at = datetime.utcnow()

        audit = MarksAuditLog(
            student_marks_id=m.id, exam_cycle_id=cid,
            changed_by=user_id, action=AuditAction.GRACE.value,
            field_name="grace_marks",
            old_value=str(old_grace), new_value=str(m.grace_marks),
            ip_address=get_client_ip(request), reason=reason,
        )
        db.add(audit)
        updated += 1

    await db.commit()
    return {"success": True, "updated": updated}


# ═══════════════════════════════════════════════════════════
#  ADMIN: AUDIT LOG
# ═══════════════════════════════════════════════════════════

@router.get("/admin/audit-log")
@require_privilege("exam_management")
async def get_audit_log(
    request: Request,
    cycle_id: str = Query(...),
    db: AsyncSession = Depends(get_db)
):
    cid = uuid.UUID(cycle_id)
    logs = (await db.execute(
        select(MarksAuditLog).where(MarksAuditLog.exam_cycle_id == cid)
        .order_by(MarksAuditLog.changed_at.desc())
        .limit(200)
    )).scalars().all()

    user_ids = list({l.changed_by for l in logs})
    from models.user import User
    users_map = {}
    if user_ids:
        users = (await db.execute(select(User).where(User.id.in_(user_ids)))).scalars().all()
        users_map = {u.id: f"{u.first_name} {u.last_name or ''}".strip() for u in users}

    return {
        "success": True,
        "logs": [{
            "id": str(l.id),
            "action": l.action,
            "field_name": l.field_name,
            "old_value": l.old_value,
            "new_value": l.new_value,
            "changed_by": users_map.get(l.changed_by, "Unknown"),
            "changed_at": l.changed_at.isoformat() if l.changed_at else None,
            "ip_address": l.ip_address,
            "reason": l.reason,
        } for l in logs]
    }


# ═══════════════════════════════════════════════════════════
#  STUDENT: VIEW RESULTS & DOWNLOAD PDF
# ═══════════════════════════════════════════════════════════

@router.get("/student/my-results")
@require_role(UserRole.STUDENT)
async def student_my_results(request: Request, db: AsyncSession = Depends(get_db)):
    user = request.state.user
    user_id = uuid.UUID(user["user_id"])
    student = (await db.execute(
        select(Student).where(Student.user_id == user_id, Student.is_active == True)
        .options(selectinload(Student.class_), selectinload(Student.section))
    )).scalar_one_or_none()
    if not student:
        return {"success": True, "results": []}

    # Get published cycles for student's class
    cycles = (await db.execute(
        select(ExamCycle).where(
            ExamCycle.class_id == student.class_id,
            ExamCycle.status == ExamCycleStatus.PUBLISHED.value,
        ).order_by(ExamCycle.published_at.desc())
    )).scalars().all()

    results = []
    for cycle in cycles:
        if cycle.section_id and cycle.section_id != student.section_id:
            continue

        # Get student result
        sr = (await db.execute(
            select(StudentResult).where(
                StudentResult.exam_cycle_id == cycle.id,
                StudentResult.student_id == student.id,
            )
        )).scalar_one_or_none()

        # Get marks
        marks = (await db.execute(
            select(StudentMarks).where(
                StudentMarks.exam_cycle_id == cycle.id,
                StudentMarks.student_id == student.id,
                StudentMarks.is_retest == False,
            )
        )).scalars().all()

        subject_ids = [m.subject_id for m in marks]
        subjects_map = {}
        if subject_ids:
            subjects = (await db.execute(select(Subject).where(Subject.id.in_(subject_ids)))).scalars().all()
            subjects_map = {s.id: s.name for s in subjects}

        subjects_data = []
        for m in marks:
            subjects_data.append({
                "subject": subjects_map.get(m.subject_id, "?"),
                "max_marks": m.max_marks,
                "marks_obtained": m.marks_obtained,
                "special_code": m.special_code,
                "grace_marks": m.grace_marks or 0,
                "final_marks": m.final_marks,
                "grade": m.grade or "-",
            })

        results.append({
            "cycle_id": str(cycle.id),
            "exam_name": cycle.name,
            "published_at": cycle.published_at.isoformat() if cycle.published_at else None,
            "subjects": subjects_data,
            "total": sr.total_marks if sr else 0,
            "max_total": sr.max_total if sr else 0,
            "percentage": sr.percentage if sr else 0,
            "grade": sr.grade if sr else "",
            "rank": sr.rank if sr else None,
            "result_status": sr.result_status if sr else "",
            "remarks": sr.class_teacher_remarks if sr else "",
        })

    return {
        "success": True, "results": results,
        "student": {
            "name": f"{student.first_name} {student.last_name or ''}".strip(),
            "class_name": student.class_.name if student.class_ else "",
            "section": student.section.name if student.section else "",
            "roll": student.roll_number or "",
            "admission": student.admission_number or "",
            "father_name": student.father_name or "",
            "mother_name": student.mother_name or "",
        }
    }


@router.get("/student/download-pdf")
@require_role(UserRole.STUDENT)
async def download_report_card_pdf(
    request: Request,
    cycle_id: str = Query(...),
    db: AsyncSession = Depends(get_db)
):
    """Generate and download report card PDF on demand."""
    user = request.state.user
    user_id = uuid.UUID(user["user_id"])
    student = (await db.execute(
        select(Student).where(Student.user_id == user_id, Student.is_active == True)
        .options(selectinload(Student.class_), selectinload(Student.section))
    )).scalar_one_or_none()
    if not student:
        raise HTTPException(404, "Student not found")

    cid = uuid.UUID(cycle_id)
    cycle = (await db.execute(select(ExamCycle).where(ExamCycle.id == cid))).scalar_one_or_none()
    if not cycle or cycle.status != ExamCycleStatus.PUBLISHED.value:
        raise HTTPException(400, "Results not published yet")

    # Get branch info
    branch = (await db.execute(select(Branch).where(Branch.id == student.branch_id))).scalar_one_or_none()
    ay = (await db.execute(
        select(AcademicYear).where(AcademicYear.id == cycle.academic_year_id)
    )).scalar_one_or_none()

    # Get marks & result
    marks = (await db.execute(
        select(StudentMarks).where(
            StudentMarks.exam_cycle_id == cid,
            StudentMarks.student_id == student.id,
            StudentMarks.is_retest == False,
        )
    )).scalars().all()

    subject_ids = [m.subject_id for m in marks]
    subjects_map = {}
    if subject_ids:
        subjects = (await db.execute(select(Subject).where(Subject.id.in_(subject_ids)))).scalars().all()
        subjects_map = {s.id: s.name for s in subjects}

    sr = (await db.execute(
        select(StudentResult).where(
            StudentResult.exam_cycle_id == cid, StudentResult.student_id == student.id
        )
    )).scalar_one_or_none()

    from utils.report_card_pdf import generate_report_card_pdf

    school_info = {
        "name": branch.name if branch else "School",
        "address": f"{branch.address or ''}, {branch.city or ''}, {branch.state or ''}".strip(", ") if branch else "",
        "affiliation": branch.affiliation_number if branch else None,
    }
    student_info = {
        "name": f"{student.first_name} {student.last_name or ''}".strip(),
        "class_name": student.class_.name if student.class_ else "",
        "section": student.section.name if student.section else "",
        "roll": student.roll_number or "",
        "admission": student.admission_number or "",
        "father_name": student.father_name or "",
        "mother_name": student.mother_name or "",
        "dob": student.date_of_birth.strftime("%d %b %Y") if student.date_of_birth else "",
    }
    subjects_marks = [{
        "subject": subjects_map.get(m.subject_id, "?"),
        "max_marks": m.max_marks,
        "marks_obtained": m.marks_obtained or 0,
        "special_code": m.special_code,
        "grace_marks": m.grace_marks or 0,
        "final_marks": m.final_marks or 0,
        "grade": m.grade or "-",
    } for m in marks]

    result_info = {
        "exam_name": cycle.name,
        "academic_year": ay.label if ay else "",
        "total": sr.total_marks if sr else 0,
        "max_total": sr.max_total if sr else 0,
        "percentage": sr.percentage if sr else 0,
        "grade": sr.grade if sr else "",
        "rank": sr.rank if sr else None,
        "result_status": sr.result_status if sr else "",
        "remarks": sr.class_teacher_remarks if sr else "",
    }

    pdf_bytes = generate_report_card_pdf(school_info, student_info, subjects_marks, result_info)

    filename = f"report_card_{student.first_name}_{cycle.name.replace(' ', '_')}.pdf"
    return StreamingResponse(
        io.BytesIO(pdf_bytes), media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


# ═══════════════════════════════════════════════════════════
#  SHARED: HELPER DATA ENDPOINTS
# ═══════════════════════════════════════════════════════════

@router.get("/classes")
@require_privilege("exam_management")
async def get_classes(request: Request, db: AsyncSession = Depends(get_db)):
    branch_id = uuid.UUID(request.state.user["branch_id"])
    classes = (await db.execute(
        select(Class).where(Class.branch_id == branch_id, Class.is_active == True)
        .order_by(Class.numeric_order)
    )).scalars().all()
    result = []
    for c in classes:
        sections = (await db.execute(
            select(Section).where(Section.class_id == c.id, Section.is_active == True)
        )).scalars().all()
        result.append({
            "id": str(c.id), "name": c.name,
            "sections": [{"id": str(s.id), "name": s.name} for s in sections],
        })
    return {"success": True, "classes": result}


@router.get("/upload-progress/{cycle_id}")
async def get_upload_progress(cycle_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    """Get upload progress for an exam cycle."""
    cid = uuid.UUID(cycle_id)
    trackers = (await db.execute(
        select(MarksUploadTracker).where(MarksUploadTracker.exam_cycle_id == cid)
    )).scalars().all()

    subject_ids = [t.subject_id for t in trackers]
    teacher_ids = [t.teacher_id for t in trackers]

    subjects_map, teachers_map = {}, {}
    if subject_ids:
        subjects = (await db.execute(select(Subject).where(Subject.id.in_(subject_ids)))).scalars().all()
        subjects_map = {s.id: s.name for s in subjects}
    if teacher_ids:
        teachers = (await db.execute(select(Teacher).where(Teacher.id.in_(teacher_ids)))).scalars().all()
        teachers_map = {t.id: f"{t.first_name} {t.last_name or ''}".strip() for t in teachers}

    return {
        "success": True,
        "trackers": [{
            "id": str(t.id),
            "subject_name": subjects_map.get(t.subject_id, ""),
            "teacher_name": teachers_map.get(t.teacher_id, ""),
            "status": t.status,
            "uploaded_at": t.uploaded_at.isoformat() if t.uploaded_at else None,
            "submitted_at": t.submitted_at.isoformat() if t.submitted_at else None,
            "row_count": t.row_count,
        } for t in trackers]
    }
