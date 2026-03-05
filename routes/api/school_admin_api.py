from fastapi import APIRouter, Request, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, func, or_
from sqlalchemy.orm import selectinload
from database import get_db
from models.user import User, UserRole
from models.academic import AcademicYear, Class, Section, Subject, ClassSubject
from models.teacher import Teacher
from utils.auth import hash_password
from utils.permissions import get_current_user
from utils.student_id_generator import generate_student_registration_id
from pydantic import BaseModel
from typing import Optional, List
from datetime import date, timedelta
import uuid

router = APIRouter(prefix="/api/school")


async def verify_school_admin(request: Request):
    user = await get_current_user(request)
    if not user or user.get("role") != "school_admin":
        raise HTTPException(status_code=403, detail="Access denied")
    return user


def get_branch_id(user: dict) -> uuid.UUID:
    return uuid.UUID(user["branch_id"])


# ─── ACADEMIC YEAR ────────────────────────────────────────

class AcademicYearCreate(BaseModel):
    label: str
    start_date: date
    end_date: date
    is_current: bool = False


@router.post("/academic-years")
async def create_academic_year(data: AcademicYearCreate, request: Request, db: AsyncSession = Depends(get_db)):
    user = await verify_school_admin(request)
    branch_id = get_branch_id(user)

    if data.is_current:
        await db.execute(
            update(AcademicYear)
            .where(AcademicYear.branch_id == branch_id)
            .values(is_current=False)
        )

    ay = AcademicYear(
        branch_id=branch_id,
        label=data.label,
        start_date=data.start_date,
        end_date=data.end_date,
        is_current=data.is_current,
    )
    db.add(ay)
    return {"success": True, "message": "Academic year created"}


@router.post("/academic-years/{year_id}/activate")
async def activate_academic_year(year_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    user = await verify_school_admin(request)
    branch_id = get_branch_id(user)

    await db.execute(
        update(AcademicYear).where(AcademicYear.branch_id == branch_id).values(is_current=False)
    )
    await db.execute(
        update(AcademicYear).where(AcademicYear.id == uuid.UUID(year_id)).values(is_current=True)
    )
    return {"success": True, "message": "Academic year activated"}


@router.delete("/academic-years/{year_id}")
async def delete_academic_year(year_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    user = await verify_school_admin(request)
    result = await db.execute(select(AcademicYear).where(AcademicYear.id == uuid.UUID(year_id)))
    ay = result.scalar_one_or_none()
    if not ay:
        raise HTTPException(status_code=404, detail="Not found")
    await db.delete(ay)
    return {"success": True, "message": "Deleted"}


# ─── CLASSES ──────────────────────────────────────────────

class ClassCreate(BaseModel):
    name: str
    numeric_order: int = 0
    sections: Optional[str] = "A"


@router.get("/classes")
async def list_classes(request: Request, db: AsyncSession = Depends(get_db)):
    """List all classes for this branch."""
    user = await get_current_user(request)
    if not user: return {"classes": []}
    branch_id = uuid.UUID(user["branch_id"])
    classes = (await db.execute(
        select(Class).where(Class.branch_id == branch_id, Class.is_active == True).order_by(Class.name)
    )).scalars().all()
    return {"classes": [{"id": str(c.id), "name": c.name} for c in classes]}


@router.get("/classes/{class_id}/sections")
async def list_sections(request: Request, class_id: str, db: AsyncSession = Depends(get_db)):
    """List sections for a class."""
    from models.academic import Section
    sections = (await db.execute(
        select(Section).where(Section.class_id == uuid.UUID(class_id), Section.is_active == True).order_by(Section.name)
    )).scalars().all()
    return {"sections": [{"id": str(s.id), "name": s.name} for s in sections]}


@router.post("/classes")
async def create_class(data: ClassCreate, request: Request, db: AsyncSession = Depends(get_db)):
    user = await verify_school_admin(request)
    branch_id = get_branch_id(user)

    cls = Class(branch_id=branch_id, name=data.name, numeric_order=data.numeric_order)
    db.add(cls)
    await db.flush()

    if data.sections:
        for sec_name in data.sections.split(","):
            sec_name = sec_name.strip().upper()
            if sec_name:
                db.add(Section(class_id=cls.id, name=sec_name))

    return {"success": True, "message": f"{data.name} created"}


@router.post("/classes/quick-setup")
async def quick_setup_classes(request: Request, db: AsyncSession = Depends(get_db)):
    user = await verify_school_admin(request)
    branch_id = get_branch_id(user)

    existing = await db.scalar(
        select(Class.id).where(Class.branch_id == branch_id).limit(1)
    )
    if existing:
        raise HTTPException(status_code=400, detail="Classes already exist. Delete them first to use Quick Setup.")

    standard_classes = [
        ("Nursery", -3), ("LKG", -2), ("UKG", -1),
        ("Class 1", 1), ("Class 2", 2), ("Class 3", 3),
        ("Class 4", 4), ("Class 5", 5), ("Class 6", 6),
        ("Class 7", 7), ("Class 8", 8), ("Class 9", 9),
        ("Class 10", 10), ("Class 11", 11), ("Class 12", 12),
    ]

    for name, order in standard_classes:
        cls = Class(branch_id=branch_id, name=name, numeric_order=order)
        db.add(cls)
        await db.flush()
        db.add(Section(class_id=cls.id, name="A"))

    return {"success": True, "message": "15 classes with Section A created"}


@router.delete("/classes/{class_id}")
async def delete_class(class_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    user = await verify_school_admin(request)
    result = await db.execute(select(Class).where(Class.id == uuid.UUID(class_id)))
    cls = result.scalar_one_or_none()
    if not cls:
        raise HTTPException(status_code=404, detail="Not found")
    cls.is_active = False
    return {"success": True, "message": "Class deleted"}


# ─── SECTIONS ─────────────────────────────────────────────

class SectionCreate(BaseModel):
    class_id: str
    name: str


@router.post("/sections")
async def create_section(data: SectionCreate, request: Request, db: AsyncSession = Depends(get_db)):
    await verify_school_admin(request)
    sec = Section(class_id=uuid.UUID(data.class_id), name=data.name.strip().upper())
    db.add(sec)
    return {"success": True, "message": f"Section {data.name} added"}


@router.delete("/sections/{section_id}")
async def delete_section(section_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    await verify_school_admin(request)
    result = await db.execute(select(Section).where(Section.id == uuid.UUID(section_id)))
    sec = result.scalar_one_or_none()
    if not sec:
        raise HTTPException(status_code=404, detail="Not found")
    await db.delete(sec)
    return {"success": True, "message": "Section deleted"}


# ─── SUBJECTS ─────────────────────────────────────────────

class SubjectCreate(BaseModel):
    name: str
    code: Optional[str] = None
    is_optional: bool = False


@router.post("/subjects")
async def create_subject(data: SubjectCreate, request: Request, db: AsyncSession = Depends(get_db)):
    user = await verify_school_admin(request)
    branch_id = get_branch_id(user)
    sub = Subject(branch_id=branch_id, name=data.name, code=data.code, is_optional=data.is_optional)
    db.add(sub)
    return {"success": True, "message": f"{data.name} created"}


@router.post("/subjects/quick-setup")
async def quick_setup_subjects(request: Request, db: AsyncSession = Depends(get_db)):
    user = await verify_school_admin(request)
    branch_id = get_branch_id(user)

    standard_subjects = [
        ("English", "ENG", False),
        ("Hindi", "HIN", False),
        ("Mathematics", "MATH", False),
        ("Science", "SCI", False),
        ("Social Science", "SST", False),
        ("Computer Science", "CS", False),
        ("Physical Education", "PE", False),
        ("Art & Craft", "ART", True),
        ("Music", "MUS", True),
        ("Sanskrit", "SKT", True),
    ]

    for name, code, is_optional in standard_subjects:
        db.add(Subject(branch_id=branch_id, name=name, code=code, is_optional=is_optional))

    return {"success": True, "message": "10 standard subjects created"}


@router.delete("/subjects/{subject_id}")
async def delete_subject(subject_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    await verify_school_admin(request)
    result = await db.execute(select(Subject).where(Subject.id == uuid.UUID(subject_id)))
    sub = result.scalar_one_or_none()
    if not sub:
        raise HTTPException(status_code=404, detail="Not found")
    sub.is_active = False
    return {"success": True, "message": "Subject deleted"}


# ─── CLASS-SUBJECT ASSIGNMENT ─────────────────────────────

class ClassSubjectAssign(BaseModel):
    class_id: str
    subject_ids: List[str]


@router.post("/class-subjects")
async def assign_class_subjects(data: ClassSubjectAssign, request: Request, db: AsyncSession = Depends(get_db)):
    await verify_school_admin(request)
    class_id = uuid.UUID(data.class_id)

    for sid in data.subject_ids:
        existing = await db.execute(
            select(ClassSubject).where(
                ClassSubject.class_id == class_id,
                ClassSubject.subject_id == uuid.UUID(sid)
            )
        )
        if not existing.scalar_one_or_none():
            db.add(ClassSubject(class_id=class_id, subject_id=uuid.UUID(sid)))

    return {"success": True, "message": f"{len(data.subject_ids)} subjects assigned"}


# ─── TEACHERS ─────────────────────────────────────────────

class TeacherCreate(BaseModel):
    first_name: str
    last_name: Optional[str] = None
    employee_id: Optional[str] = None
    designation: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    qualification: Optional[str] = None
    specialization: Optional[str] = None
    experience_years: Optional[int] = 0
    joining_date: Optional[date] = None
    address: Optional[str] = None
    password: str


@router.post("/teachers")
async def create_teacher(data: TeacherCreate, request: Request, db: AsyncSession = Depends(get_db)):
    user = await verify_school_admin(request)
    branch_id = get_branch_id(user)
    org_id = uuid.UUID(user["org_id"])

    # Check duplicate email
    if data.email:
        existing = await db.execute(select(User).where(User.email == data.email))
        if existing.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="Email already registered")

    # Create user account for teacher
    teacher_user = User(
        first_name=data.first_name,
        last_name=data.last_name,
        email=data.email,
        phone=data.phone,
        password_hash=hash_password(data.password),
        role=UserRole.TEACHER,
        org_id=org_id,
        branch_id=branch_id,
        is_active=True,
        is_verified=True,
    )
    db.add(teacher_user)
    await db.flush()

    # Create teacher profile
    teacher = Teacher(
        user_id=teacher_user.id,
        branch_id=branch_id,
        first_name=data.first_name,
        last_name=data.last_name,
        employee_id=data.employee_id,
        designation=data.designation,
        email=data.email,
        phone=data.phone,
        qualification=data.qualification,
        specialization=data.specialization,
        experience_years=data.experience_years or 0,
        joining_date=data.joining_date,
        address=data.address,
    )
    db.add(teacher)
    await db.flush()

    # Auto-create Employee record so teacher appears in payroll
    from models.employee import Employee, EmployeeType
    emp = Employee(
        branch_id=branch_id,
        user_id=teacher_user.id,
        teacher_id=teacher.id,
        employee_code=data.employee_id or f"T-{str(teacher.id)[:6].upper()}",
        first_name=data.first_name,
        last_name=data.last_name,
        email=data.email,
        phone=data.phone,
        employee_type=EmployeeType.TEACHING,
        designation=data.designation or "Teacher",
        department="Teaching",
        date_of_joining=data.joining_date,
    )
    db.add(emp)

    return {"success": True, "message": f"Teacher {data.first_name} added with login access"}


@router.delete("/teachers/{teacher_id}")
async def delete_teacher(teacher_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    await verify_school_admin(request)
    result = await db.execute(select(Teacher).where(Teacher.id == uuid.UUID(teacher_id)))
    teacher = result.scalar_one_or_none()
    if not teacher:
        raise HTTPException(status_code=404, detail="Not found")
    teacher.is_active = False
    if teacher.user_id:
        user_result = await db.execute(select(User).where(User.id == teacher.user_id))
        user = user_result.scalar_one_or_none()
        if user:
            user.is_active = False
    return {"success": True, "message": "Teacher deactivated"}

# ─── TEACHER UPDATE ──────────────────────────────────────

class TeacherUpdate(BaseModel):
    first_name: str
    last_name: Optional[str] = None
    employee_id: Optional[str] = None
    designation: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    qualification: Optional[str] = None
    specialization: Optional[str] = None
    experience_years: Optional[int] = 0
    joining_date: Optional[date] = None
    address: Optional[str] = None


@router.put("/teachers/{teacher_id}")
async def update_teacher(teacher_id: str, data: TeacherUpdate, request: Request, db: AsyncSession = Depends(get_db)):
    await verify_school_admin(request)
    result = await db.execute(select(Teacher).where(Teacher.id == uuid.UUID(teacher_id)))
    teacher = result.scalar_one_or_none()
    if not teacher:
        raise HTTPException(status_code=404, detail="Teacher not found")

    teacher.first_name = data.first_name
    teacher.last_name = data.last_name
    teacher.employee_id = data.employee_id
    teacher.designation = data.designation
    teacher.email = data.email
    teacher.phone = data.phone
    teacher.qualification = data.qualification
    teacher.specialization = data.specialization
    teacher.experience_years = data.experience_years or 0
    teacher.joining_date = data.joining_date
    teacher.address = data.address

    # Also update the linked User record
    if teacher.user_id:
        user_result = await db.execute(select(User).where(User.id == teacher.user_id))
        user_obj = user_result.scalar_one_or_none()
        if user_obj:
            user_obj.first_name = data.first_name
            user_obj.last_name = data.last_name
            if data.email:
                user_obj.email = data.email
            if data.phone:
                user_obj.phone = data.phone

    return {"success": True, "message": f"Teacher {data.first_name} updated"}


# ─── CLASS TEACHER ASSIGNMENT ────────────────────────────

class ClassTeacherAssign(BaseModel):
    section_id: Optional[str] = None


# ─── ASSIGN CLASS TEACHER (with constraint) ───────────────
@router.post("/teachers/{teacher_id}/class-teacher")
async def assign_class_teacher(teacher_id: str, data: ClassTeacherAssign, request: Request, db: AsyncSession = Depends(get_db)):
    """Assign teacher as class teacher of a section.
    Enforces: one class teacher per section. If another teacher was assigned, they lose it."""
    user = await verify_school_admin(request)
    branch_id = get_branch_id(user)
    from sqlalchemy import text as sql_text

    result = await db.execute(select(Teacher).where(Teacher.id == uuid.UUID(teacher_id)))
    teacher = result.scalar_one_or_none()
    if not teacher:
        raise HTTPException(status_code=404, detail="Teacher not found")

    warning = None

    if data.section_id:
        sid = data.section_id

        # Check if another teacher currently has this section
        existing = await db.execute(sql_text(
            "SELECT s.class_teacher_id, t.first_name || ' ' || COALESCE(t.last_name, '') as teacher_name "
            "FROM sections s LEFT JOIN teachers t ON t.id = s.class_teacher_id "
            "WHERE s.id = :sid AND s.class_teacher_id IS NOT NULL AND s.class_teacher_id != :tid"
        ), {"sid": sid, "tid": str(teacher.id)})
        old_row = existing.first()
        if old_row:
            warning = f"Reassigned from {old_row.teacher_name.strip()}"

        # Clear this section (enforce one teacher per section)
        await db.execute(sql_text(
            "UPDATE sections SET class_teacher_id = NULL WHERE id = :sid"
        ), {"sid": sid})

        # Assign this teacher to this section
        await db.execute(sql_text(
            "UPDATE sections SET class_teacher_id = :tid WHERE id = :sid"
        ), {"tid": str(teacher.id), "sid": sid})

    await db.commit()
    resp = {"success": True, "message": "Class teacher assigned"}
    if warning:
        resp["warning"] = warning
    return resp



# ─── REMOVE CLASS TEACHER FROM SECTION ─────────────────────
@router.post("/teachers/{teacher_id}/class-teacher-remove")
async def remove_class_teacher(teacher_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    """Remove a class teacher from a specific section or all sections."""
    user = await verify_school_admin(request)
    from sqlalchemy import text as sql_text

    body = await request.json()
    section_id = body.get("section_id")

    if section_id:
        await db.execute(sql_text(
            "UPDATE sections SET class_teacher_id = NULL "
            "WHERE id = :sid AND class_teacher_id = :tid"
        ), {"sid": section_id, "tid": teacher_id})
    else:
        await db.execute(sql_text(
            "UPDATE sections SET class_teacher_id = NULL "
            "WHERE class_teacher_id = :tid"
        ), {"tid": teacher_id})

    await db.commit()
    return {"success": True, "message": "Class teacher removed"}
# ─── 3. CHANGE WORK STATUS ───────────────────────────────────
# NEW endpoint

@router.post("/teachers/{teacher_id}/work-status")
async def change_teacher_work_status(teacher_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    """Change teacher work status: available, suspended, or resigned."""
    user = await verify_school_admin(request)
    branch_id = get_branch_id(user)
    from sqlalchemy import text as sql_text
    from datetime import datetime

    body = await request.json()
    new_status = body.get("work_status", "available")

    result = await db.execute(select(Teacher).where(Teacher.id == uuid.UUID(teacher_id)))
    teacher = result.scalar_one_or_none()
    if not teacher:
        raise HTTPException(status_code=404, detail="Teacher not found")

    if new_status == "resigned":
        teacher.is_active = False
        teacher.work_status = "resigned"
        # Disable linked User account login
        if teacher.user_id:
            linked_user = await db.scalar(select(User).where(User.id == teacher.user_id))
            if linked_user:
                linked_user.is_active = False
        # Remove class teacher assignments
        await db.execute(sql_text(
            "UPDATE sections SET class_teacher_id = NULL WHERE class_teacher_id = :tid"
        ), {"tid": teacher_id})
        # Deactivate teaching assignments
        try:
            await db.execute(sql_text(
                "UPDATE teacher_class_assignments SET is_active = false "
                "WHERE teacher_id = :tid AND branch_id = :bid"
            ), {"tid": teacher_id, "bid": str(branch_id)})
        except Exception:
            pass
    elif new_status == "available":
        teacher.is_active = True
        teacher.work_status = "available"
    elif new_status == "suspended":
        teacher.is_active = True
        teacher.work_status = "suspended"

    # Audit log
    print(f"[AUDIT] Teacher {teacher.first_name} {teacher.last_name or ''} "
          f"({teacher_id}) → {new_status} "
          f"by {user.get('name', 'admin')} at {datetime.now().isoformat()}")

    await db.commit()
    return {"success": True, "message": f"Status changed to {new_status}"}

# ─── SAVE TEACHING ASSIGNMENTS ─────────────────────────────
@router.post("/teachers/{teacher_id}/assignments")
async def save_teacher_assignments(teacher_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    """Save teaching class-section-subject assignments. Replaces all existing."""
    user = await verify_school_admin(request)
    branch_id = get_branch_id(user)
    from sqlalchemy import text as sql_text

    body = await request.json()
    assignments = body.get("assignments", [])

    # Deactivate all existing
    try:
        await db.execute(sql_text(
            "UPDATE teacher_class_assignments SET is_active = false "
            "WHERE teacher_id = :tid AND branch_id = :bid"
        ), {"tid": teacher_id, "bid": str(branch_id)})
    except Exception:
        pass

    # Insert/reactivate new
    for a in assignments:
        class_id = a.get("class_id")
        section_id = a.get("section_id")
        subject_id = a.get("subject_id")
        if not class_id or not subject_id:
            continue
        try:
            existing = await db.execute(sql_text(
                "SELECT id FROM teacher_class_assignments "
                "WHERE teacher_id = :tid AND class_id = :cid AND subject_id = :subid "
                "AND (section_id = :sid OR (section_id IS NULL AND :sid IS NULL)) "
                "AND branch_id = :bid"
            ), {"tid": teacher_id, "cid": class_id, "sid": section_id, "subid": subject_id, "bid": str(branch_id)})
            row = existing.first()
            if row:
                await db.execute(sql_text(
                    "UPDATE teacher_class_assignments SET is_active = true WHERE id = :id"
                ), {"id": str(row.id)})
            else:
                import uuid as uuid_mod
                await db.execute(sql_text(
                    "INSERT INTO teacher_class_assignments (id, teacher_id, class_id, section_id, subject_id, branch_id, is_active) "
                    "VALUES (:id, :tid, :cid, :sid, :subid, :bid, true)"
                ), {
                    "id": str(uuid_mod.uuid4()), "tid": teacher_id,
                    "cid": class_id, "sid": section_id,
                    "subid": subject_id, "bid": str(branch_id),
                })
        except Exception as e:
            print(f"TC assignment error: {e}")

    await db.commit()
    return {"success": True, "message": f"{len(assignments)} assignments saved"}

@router.get("/teachers/{teacher_id}/assignments")
async def get_teacher_assignments(teacher_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    user = await verify_school_admin(request)
    branch_id = get_branch_id(user)
    from sqlalchemy import text as sql_text

    # Get class teacher section(s) — now from sections table
    ct_section_id = None
    try:
        ct_row = await db.execute(sql_text(
            "SELECT id FROM sections WHERE class_teacher_id = :tid LIMIT 1"
        ), {"tid": teacher_id})
        ct_sec = ct_row.scalar_one_or_none()
        ct_section_id = str(ct_sec) if ct_sec else None
    except Exception:
        pass

    # Get teaching assignments
    assignments = []
    try:
        rows = await db.execute(sql_text("""
            SELECT tca.class_id, tca.section_id, tca.subject_id
            FROM teacher_class_assignments tca
            WHERE tca.teacher_id = :tid AND tca.branch_id = :bid AND tca.is_active = true
        """), {"tid": teacher_id, "bid": str(branch_id)})
        for row in rows:
            assignments.append({
                "class_id": str(row.class_id),
                "section_id": str(row.section_id) if row.section_id else None,
                "subject_id": str(row.subject_id),
            })
    except Exception:
        pass

    return {
        "class_teacher_of": ct_section_id,
        "assignments": assignments,
    }
# ─── TEACHING ASSIGNMENTS (GET + POST) ──────────────────

class TeachingAssignment(BaseModel):
    class_id: str
    section_id: Optional[str] = None
    subject_id: str


class TeachingAssignmentBulk(BaseModel):
    assignments: List[TeachingAssignment]


@router.get("/teachers/{teacher_id}/assignments")
async def get_teacher_assignments(teacher_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    user = await verify_school_admin(request)
    branch_id = get_branch_id(user)
    from sqlalchemy import text as sql_text

    # Get class teacher info
    result = await db.execute(select(Teacher).where(Teacher.id == uuid.UUID(teacher_id)))
    teacher = result.scalar_one_or_none()
    # Get section(s) where this teacher is class teacher
    ct_section_id = None
    try:
        ct_row = await db.execute(sql_text(
            "SELECT id FROM sections WHERE class_teacher_id = :tid LIMIT 1"
        ), {"tid": teacher_id})
        ct_sec = ct_row.scalar_one_or_none()
        ct_section_id = str(ct_sec) if ct_sec else None
    except Exception:
        pass

    # Get teaching assignments
    assignments = []
    try:
        rows = await db.execute(sql_text("""
            SELECT tca.class_id, tca.section_id, tca.subject_id
            FROM teacher_class_assignments tca
            WHERE tca.teacher_id = :tid AND tca.branch_id = :bid AND tca.is_active = true
        """), {"tid": teacher_id, "bid": str(branch_id)})
        for row in rows:
            assignments.append({
                "class_id": str(row.class_id),
                "section_id": str(row.section_id) if row.section_id else None,
                "subject_id": str(row.subject_id),
            })
    except Exception:
        pass

    return {
        "class_teacher_of": ct_section_id,
        "assignments": assignments,
    }


@router.post("/teachers/{teacher_id}/assignments")
async def save_teacher_assignments(teacher_id: str, data: TeachingAssignmentBulk, request: Request, db: AsyncSession = Depends(get_db)):
    user = await verify_school_admin(request)
    branch_id = get_branch_id(user)
    from sqlalchemy import text as sql_text

    # Delete existing assignments for this teacher
    try:
        await db.execute(sql_text(
            "DELETE FROM teacher_class_assignments WHERE teacher_id = :tid AND branch_id = :bid"
        ), {"tid": teacher_id, "bid": str(branch_id)})
    except Exception:
        pass

    # Insert new assignments
    for a in data.assignments:
        try:
            await db.execute(sql_text("""
                INSERT INTO teacher_class_assignments (teacher_id, class_id, section_id, subject_id, branch_id)
                VALUES (:tid, :cid, :sid, :subid, :bid)
                ON CONFLICT (teacher_id, class_id, section_id, subject_id) DO NOTHING
            """), {
                "tid": teacher_id,
                "cid": a.class_id,
                "sid": a.section_id if a.section_id else None,
                "subid": a.subject_id,
                "bid": str(branch_id),
            })
        except Exception:
            pass
    await db.commit()
    return {"success": True, "message": f"{len(data.assignments)} assignments saved"}

# ─── STUDENTS ─────────────────────────────────────────────

from models.student import Student, Gender, AdmissionStatus

class StudentCreate(BaseModel):
    first_name: str
    last_name: Optional[str] = None
    gender: Optional[str] = None
    date_of_birth: Optional[date] = None
    blood_group: Optional[str] = None
    aadhaar_number: Optional[str] = None
    class_id: str
    section_id: Optional[str] = None
    roll_number: Optional[str] = None
    admission_number: Optional[str] = None
    admission_date: Optional[date] = None
    father_name: Optional[str] = None
    father_phone: Optional[str] = None
    father_email: Optional[str] = None
    father_occupation: Optional[str] = None
    mother_name: Optional[str] = None
    mother_phone: Optional[str] = None
    mother_occupation: Optional[str] = None
    father_qualification: Optional[str] = None     
    mother_qualification: Optional[str] = None     
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    pincode: Optional[str] = None
    medical_conditions: Optional[str] = None
    emergency_contact: Optional[str] = None
    uses_transport: bool = False
    religion: Optional[str] = None
    category: Optional[str] = None
    nationality: Optional[str] = "Indian"
    admission_type: Optional[str] = "new"
    previous_school: Optional[str] = None
    previous_board: Optional[str] = None
    previous_class: Optional[str] = None
    father_aadhaar: Optional[str] = None
    mother_aadhaar: Optional[str] = None

@router.get("/students")
async def list_students(request: Request, class_id: str = "", section_id: str = "", class_level: str = "", db: AsyncSession = Depends(get_db)):
    """List students, optionally filtered by class/section/level."""
    user = await get_current_user(request)
    if not user: return {"students": []}
    branch_id = uuid.UUID(user["branch_id"])
    q = select(Student).where(Student.branch_id == branch_id, Student.is_active == True)
    if class_id:
        q = q.where(Student.class_id == uuid.UUID(class_id))
    if section_id:
        q = q.where(Student.section_id == uuid.UUID(section_id))
    if class_level:
        # Find classes matching level (10, 12, etc.)
        cls_ids = (await db.execute(select(Class.id).where(Class.branch_id == branch_id, Class.name.ilike(f"%{class_level}%")))).scalars().all()
        if cls_ids:
            q = q.where(Student.class_id.in_(cls_ids))
    students = (await db.execute(q.order_by(Student.first_name))).scalars().all()
    from models.mega_modules import StudentHouse, House
    items = []
    for s in students:
        cls_name = ""
        if s.class_id:
            cls_name = await db.scalar(select(Class.name).where(Class.id == s.class_id)) or ""
        # Get house info
        house_name, house_color = "", ""
        sh = await db.scalar(select(StudentHouse).where(StudentHouse.student_id == s.id))
        if sh:
            h = await db.scalar(select(House).where(House.id == sh.house_id))
            if h: house_name, house_color = h.name, h.color
        items.append({"id": str(s.id), "name": s.full_name, "roll": s.roll_number or "",
            "class_name": cls_name, "house_name": house_name, "house_color": house_color})
    return {"students": items}


@router.post("/students")
async def create_student(request: Request, data: StudentCreate, db: AsyncSession = Depends(get_db)):
    user = await verify_school_admin(request)
    branch_id = get_branch_id(user)

    # Check duplicate admission number
    if data.admission_number:
        existing = await db.execute(
            select(Student).where(
                Student.branch_id == branch_id,
                Student.admission_number == data.admission_number,
                Student.is_active == True
            )
        )
        if existing.scalar_one_or_none():
            raise HTTPException(status_code=400, detail=f"Admission number {data.admission_number} already exists")

    # ─── Auto-generate Student Login ID (PO-approved v3.0) ───
    from datetime import date as dt_date
    adm_year = data.admission_date.year if data.admission_date else dt_date.today().year

    cls_name = await db.scalar(select(Class.name).where(Class.id == uuid.UUID(data.class_id))) or ""

    student_login_id = await generate_student_registration_id(
        db=db, branch_id=str(branch_id),
        admission_year=adm_year, class_name=cls_name, gender=data.gender or "",
    )

    if not data.admission_number:
        data.admission_number = student_login_id

    # Auto roll number
    if not data.roll_number or data.roll_number.lower() == "auto":
        existing_count = await db.scalar(
            select(func.count(Student.id)).where(
                Student.branch_id == branch_id,
                Student.class_id == uuid.UUID(data.class_id),
                Student.is_active == True)) or 0
        data.roll_number = str(existing_count + 1)

    # Get current academic year
    ay_result = await db.execute(
        select(AcademicYear).where(AcademicYear.branch_id == branch_id, AcademicYear.is_current == True)
    )
    academic_year = ay_result.scalar_one_or_none()

    gender_val = None
    if data.gender:
        try:
            gender_val = Gender(data.gender)
        except ValueError:
            gender_val = None

    student = Student(
        branch_id=branch_id,
        student_login_id=student_login_id,
        class_id=uuid.UUID(data.class_id),
        section_id=uuid.UUID(data.section_id) if data.section_id else None,
        academic_year_id=academic_year.id if academic_year else None,
        first_name=data.first_name,
        last_name=data.last_name,
        gender=gender_val,
        date_of_birth=data.date_of_birth,
        blood_group=data.blood_group,
        aadhaar_number=data.aadhaar_number,
        roll_number=data.roll_number,
        admission_number=data.admission_number,
        admission_date=data.admission_date,
        admission_status=AdmissionStatus.ADMITTED,
        father_name=data.father_name,
        father_phone=data.father_phone,
        father_email=data.father_email,
        father_occupation=data.father_occupation,
        mother_name=data.mother_name,
        mother_phone=data.mother_phone,
        address=data.address,
        city=data.city,
        state=data.state,
        pincode=data.pincode,
        medical_conditions=data.medical_conditions,
        emergency_contact=data.emergency_contact,
        uses_transport=data.uses_transport,
        religion=data.religion,
        category=data.category,
        nationality=data.nationality or "Indian",
        admission_type=data.admission_type or "new",
        previous_school=data.previous_school,
        previous_board=data.previous_board,
        previous_class=data.previous_class,
        father_aadhaar=data.father_aadhaar,
        mother_aadhaar=data.mother_aadhaar,
        father_qualification=data.father_qualification,
        mother_qualification=data.mother_qualification,
    )
    db.add(student)
    await db.flush()

    # ─── Auto-create User account for student login ───
    default_password = student_login_id  # Initial password = login ID (parent changes later)
    student_user = User(
        org_id=uuid.UUID(user["org_id"]) if user.get("org_id") else None,
        branch_id=branch_id,
        email=None,
        phone=data.father_phone or data.mother_phone or None,
        first_name=data.first_name,
        last_name=data.last_name,
        role=UserRole.STUDENT,
        password_hash=hash_password(default_password),
        is_active=True,
    )
    db.add(student_user)
    await db.flush()
    student.user_id = student_user.id
    await db.flush()

    return {
        "success": True,
        "id": str(student.id),
        "student_login_id": student_login_id,
        "message": f"Student {data.first_name} enrolled. Login ID: {student_login_id}",
    }


class BulkImportData(BaseModel):
    students: List[StudentCreate]


@router.post("/students/bulk-import")
async def bulk_import_students(data: BulkImportData, request: Request, db: AsyncSession = Depends(get_db)):
    user = await verify_school_admin(request)
    branch_id = get_branch_id(user)

    # Get current academic year
    ay_result = await db.execute(
        select(AcademicYear).where(AcademicYear.branch_id == branch_id, AcademicYear.is_current == True)
    )
    academic_year = ay_result.scalar_one_or_none()

    imported = 0
    errors = []

    for i, s in enumerate(data.students):
        try:
            gender_val = None
            if s.gender:
                try:
                    gender_val = Gender(s.gender)
                except ValueError:
                    gender_val = None

            student = Student(
                branch_id=branch_id,
                class_id=uuid.UUID(s.class_id),
                section_id=uuid.UUID(s.section_id) if s.section_id else None,
                academic_year_id=academic_year.id if academic_year else None,
                first_name=s.first_name,
                last_name=s.last_name,
                gender=gender_val,
                date_of_birth=s.date_of_birth,
                roll_number=s.roll_number,
                admission_number=s.admission_number,
                admission_status=AdmissionStatus.ADMITTED,
                father_name=s.father_name,
                father_phone=s.father_phone,
                mother_name=s.mother_name,
                address=s.address,
                city=s.city,
            )
            db.add(student)
            imported += 1
        except Exception as e:
            errors.append(f"Row {i + 1}: {str(e)}")

    return {
        "success": True,
        "imported": imported,
        "errors": errors,
        "message": f"{imported} students imported successfully"
    }


@router.delete("/students/{student_id}")
async def delete_student(student_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    await verify_school_admin(request)
    result = await db.execute(select(Student).where(Student.id == uuid.UUID(student_id)))
    student = result.scalar_one_or_none()
    if not student:
        raise HTTPException(status_code=404, detail="Not found")
    student.is_active = False
    # Disable linked User account (student + parent logins)
    if student.user_id:
        linked_user = await db.scalar(select(User).where(User.id == student.user_id))
        if linked_user:
            linked_user.is_active = False
    await db.commit()
    return {"success": True, "message": "Student deactivated"}


# ─── ATTENDANCE ─────────────────────────────────────────

from models.attendance import Attendance, AttendanceStatus
from models.event import SchoolEvent

@router.get("/attendance/load")
async def load_attendance(request: Request, class_id: str, section_id: str, date: str, db: AsyncSession = Depends(get_db)):
    user = await verify_school_admin(request)
    branch_id = get_branch_id(user)

    from datetime import date as date_type, datetime

    att_date = datetime.strptime(date, "%Y-%m-%d").date()

    # Get students in this class/section
    students_q = select(Student).where(
        Student.branch_id == branch_id,
        Student.class_id == uuid.UUID(class_id),
        Student.is_active == True
    ).order_by(Student.roll_number, Student.first_name)

    if section_id:
        students_q = students_q.where(Student.section_id == uuid.UUID(section_id))

    students_result = await db.execute(students_q)
    students = students_result.scalars().all()

    # Get existing attendance records for this date
    existing_q = select(Attendance).where(
        Attendance.branch_id == branch_id,
        Attendance.class_id == uuid.UUID(class_id),
        Attendance.date == att_date,
    )
    if section_id:
        existing_q = existing_q.where(Attendance.section_id == uuid.UUID(section_id))

    existing_result = await db.execute(existing_q)
    existing_records = existing_result.scalars().all()

    existing_map = {}
    for r in existing_records:
        existing_map[str(r.student_id)] = r.status.value

    return {
        "students": [
            {
                "id": str(s.id),
                "first_name": s.first_name,
                "last_name": s.last_name or "",
                "roll_number": s.roll_number,
                "gender": s.gender.value if s.gender else None,
            }
            for s in students
        ],
        "existing": existing_map,
        "already_marked": len(existing_records) > 0,
    }


class AttendanceRecord(BaseModel):
    student_id: str
    status: str  # present, absent, late


class SaveAttendanceData(BaseModel):
    class_id: str
    section_id: Optional[str] = None
    date: str
    records: List[AttendanceRecord]


@router.post("/attendance/save")
async def save_attendance(data: SaveAttendanceData, request: Request, db: AsyncSession = Depends(get_db)):
    user = await verify_school_admin(request)
    branch_id = get_branch_id(user)

    from datetime import datetime as dt
    att_date = dt.strptime(data.date, "%Y-%m-%d").date()

    # Get current academic year
    ay_result = await db.execute(
        select(AcademicYear).where(AcademicYear.branch_id == branch_id, AcademicYear.is_current == True)
    )
    academic_year = ay_result.scalar_one_or_none()

    # Delete existing records for this date/class/section (upsert approach)
    existing_q = select(Attendance).where(
        Attendance.branch_id == branch_id,
        Attendance.class_id == uuid.UUID(data.class_id),
        Attendance.date == att_date,
    )
    if data.section_id:
        existing_q = existing_q.where(Attendance.section_id == uuid.UUID(data.section_id))

    existing_result = await db.execute(existing_q)
    for rec in existing_result.scalars().all():
        await db.delete(rec)

    # Insert new records
    marked_by_id = uuid.UUID(user["user_id"])
    saved = 0
    absent_students = []

    for r in data.records:
        try:
            status = AttendanceStatus(r.status)
        except ValueError:
            status = AttendanceStatus.PRESENT

        att = Attendance(
            branch_id=branch_id,
            student_id=uuid.UUID(r.student_id),
            class_id=uuid.UUID(data.class_id),
            section_id=uuid.UUID(data.section_id) if data.section_id else None,
            academic_year_id=academic_year.id if academic_year else None,
            date=att_date,
            status=status,
            marked_by=marked_by_id,
        )
        db.add(att)
        saved += 1

        if status == AttendanceStatus.ABSENT:
            absent_students.append(r.student_id)

    # TODO: Send WhatsApp/SMS notification to parents of absent students
    # This will be implemented in Sprint 9 (Communication)

    # Auto-detect: if a teacher (with teacher profile) marks attendance, auto-mark them present
    try:
        from models.teacher import Teacher as TeacherModel
        from utils.teacher_auto_attendance import auto_mark_teacher_present
        from models.teacher_attendance import CheckInSource
        teacher_result = await db.execute(
            select(TeacherModel).where(TeacherModel.user_id == marked_by_id, TeacherModel.is_active == True)
        )
        teacher = teacher_result.scalar_one_or_none()
        if teacher:
            await auto_mark_teacher_present(db, teacher.id, branch_id, CheckInSource.AUTO_STUDENT_ATTENDANCE, marked_by_id)
    except Exception:
        pass  # Don't fail attendance save if auto-detect fails

    await db.commit()

    return {
        "success": True,
        "saved": saved,
        "absent_count": len(absent_students),
        "message": f"Attendance saved for {saved} students",
    }


@router.get("/attendance/report")
async def attendance_report(
    request: Request,
    class_id: str,
    month: str,
    year: str,
    section_id: str = "",
    db: AsyncSession = Depends(get_db)
):
    user = await verify_school_admin(request)
    branch_id = get_branch_id(user)

    from datetime import date as date_type
    import calendar

    month_int = int(month)
    year_int = int(year)
    _, last_day = calendar.monthrange(year_int, month_int)
    start_date = date_type(year_int, month_int, 1)
    end_date = date_type(year_int, month_int, last_day)

    # Get students
    students_q = select(Student).where(
        Student.branch_id == branch_id,
        Student.class_id == uuid.UUID(class_id),
        Student.is_active == True
    ).order_by(Student.roll_number, Student.first_name)

    if section_id:
        students_q = students_q.where(Student.section_id == uuid.UUID(section_id))

    students_result = await db.execute(students_q)
    students = students_result.scalars().all()

    if not students:
        return {"students": [], "working_days": 0, "avg_attendance": 0, "below_75_count": 0}

    # Get all attendance records for the month
    att_q = select(Attendance).where(
        Attendance.branch_id == branch_id,
        Attendance.class_id == uuid.UUID(class_id),
        Attendance.date >= start_date,
        Attendance.date <= end_date,
    )
    if section_id:
        att_q = att_q.where(Attendance.section_id == uuid.UUID(section_id))

    att_result = await db.execute(att_q)
    all_records = att_result.scalars().all()

    # Calculate working days (distinct dates with any attendance)
    working_dates = set()
    for r in all_records:
        working_dates.add(r.date)
    working_days = len(working_dates)

    # Build per-student stats
    student_records = {}
    for r in all_records:
        sid = str(r.student_id)
        if sid not in student_records:
            student_records[sid] = {"present": 0, "absent": 0, "late": 0}
        student_records[sid][r.status.value] += 1

    report_students = []
    total_pct = 0
    below_75 = 0

    for s in students:
        sid = str(s.id)
        rec = student_records.get(sid, {"present": 0, "absent": 0, "late": 0})
        total_attended = rec["present"] + rec["late"]
        pct = round((total_attended / working_days * 100) if working_days > 0 else 0)
        total_pct += pct
        if pct < 75:
            below_75 += 1

        report_students.append({
            "name": f"{s.first_name} {s.last_name or ''}".strip(),
            "roll_number": s.roll_number,
            "present": rec["present"],
            "absent": rec["absent"],
            "late": rec["late"],
            "percentage": pct,
        })

    avg_attendance = round(total_pct / len(students)) if students else 0

    return {
        "students": report_students,
        "working_days": working_days,
        "avg_attendance": avg_attendance,
        "below_75_count": below_75,
    }


# ─── TIMETABLE APIs ──────────────────────────────────────────
from models.timetable import PeriodDefinition, TimetableSlot, PeriodType, DayOfWeek

class PeriodDefData(BaseModel):
    label: str
    period_number: int
    start_time: str  # HH:MM
    end_time: str  # HH:MM
    period_type: str = "regular"


class PeriodSetupData(BaseModel):
    periods: List[PeriodDefData]


@router.post("/timetable/periods/setup")
async def setup_periods(data: PeriodSetupData, request: Request, db: AsyncSession = Depends(get_db)):
    """Create/replace all period definitions for a branch (backward compat — auto-creates Default template)"""
    user = await verify_school_admin(request)
    branch_id = get_branch_id(user)
    from datetime import time as time_type, datetime as dt
    from models.timetable import BellScheduleTemplate

    # Find or create "Default Schedule" template for backward compat
    tmpl_result = await db.execute(
        select(BellScheduleTemplate).where(
            BellScheduleTemplate.branch_id == branch_id,
            BellScheduleTemplate.is_default == True,
            BellScheduleTemplate.is_active == True,
        )
    )
    default_template = tmpl_result.scalar_one_or_none()
    if not default_template:
        default_template = BellScheduleTemplate(
            branch_id=branch_id,
            name="Default Schedule",
            description="Auto-created default bell schedule",
            is_default=True,
        )
        db.add(default_template)
        await db.flush()

    # Delete existing periods for this template
    existing = await db.execute(
        select(PeriodDefinition).where(
            PeriodDefinition.branch_id == branch_id,
            PeriodDefinition.template_id == default_template.id,
        )
    )
    for p in existing.scalars().all():
        await db.delete(p)
    await db.flush()

    # Create new ones linked to default template
    for pd in data.periods:
        try:
            st = dt.strptime(pd.start_time, "%H:%M").time()
            et = dt.strptime(pd.end_time, "%H:%M").time()
        except:
            continue

        period = PeriodDefinition(
            branch_id=branch_id,
            template_id=default_template.id,
            period_number=pd.period_number,
            label=pd.label,
            start_time=st,
            end_time=et,
            period_type=PeriodType(pd.period_type) if pd.period_type in [e.value for e in PeriodType] else PeriodType.REGULAR,
        )
        db.add(period)

    await db.commit()
    return {"success": True, "message": f"{len(data.periods)} periods configured", "template_id": str(default_template.id)}


@router.get("/timetable/periods")
async def get_periods(request: Request, db: AsyncSession = Depends(get_db)):
    user = await verify_school_admin(request)
    branch_id = get_branch_id(user)

    result = await db.execute(
        select(PeriodDefinition)
        .where(PeriodDefinition.branch_id == branch_id, PeriodDefinition.is_active == True)
        .order_by(PeriodDefinition.period_number)
    )
    periods = result.scalars().all()

    return {
        "periods": [
            {"id": str(p.id), "number": p.period_number, "label": p.label,
             "start": p.start_time.strftime("%H:%M"), "end": p.end_time.strftime("%H:%M"),
             "type": p.period_type.value}
            for p in periods
        ]
    }


class TimetableSlotData(BaseModel):
    class_id: str
    section_id: Optional[str] = None
    period_id: str
    day: str
    subject_id: Optional[str] = None
    teacher_id: Optional[str] = None
    room: Optional[str] = None


@router.post("/timetable/slot")
async def save_timetable_slot(data: TimetableSlotData, request: Request, db: AsyncSession = Depends(get_db)):
    """Create or update a single timetable slot"""
    user = await verify_school_admin(request)
    branch_id = get_branch_id(user)

    day_enum = DayOfWeek(data.day)

    # Check for teacher conflict (same teacher, same period, same day, different class)
    if data.teacher_id:
        conflict_q = select(TimetableSlot).where(
            TimetableSlot.branch_id == branch_id,
            TimetableSlot.teacher_id == uuid.UUID(data.teacher_id),
            TimetableSlot.period_id == uuid.UUID(data.period_id),
            TimetableSlot.day_of_week == day_enum,
            TimetableSlot.is_active == True,
        )
        # Exclude same class+section slot (we're updating it)
        conflict_q = conflict_q.where(
            ~((TimetableSlot.class_id == uuid.UUID(data.class_id)) &
              (TimetableSlot.section_id == (uuid.UUID(data.section_id) if data.section_id else None)))
        )
        conflict_result = await db.execute(conflict_q)
        conflict = conflict_result.scalar_one_or_none()
        if conflict:
            # Get conflicting class name
            from models.academic import Class as ClassModel
            cls_result = await db.execute(select(ClassModel).where(ClassModel.id == conflict.class_id))
            cls = cls_result.scalar_one_or_none()
            cls_name = cls.name if cls else "another class"
            raise HTTPException(400, f"Teacher conflict: already assigned to {cls_name} at this time")

    # Check for room conflict (same room, same period, same day, different class)
    if data.room and data.room.strip():
        from models.academic import Class as ClassModel
        room_conflict_q = select(TimetableSlot).where(
            TimetableSlot.branch_id == branch_id,
            TimetableSlot.room == data.room.strip(),
            TimetableSlot.period_id == uuid.UUID(data.period_id),
            TimetableSlot.day_of_week == day_enum,
            TimetableSlot.is_active == True,
        )
        room_conflict_q = room_conflict_q.where(
            ~((TimetableSlot.class_id == uuid.UUID(data.class_id)) &
              (TimetableSlot.section_id == (uuid.UUID(data.section_id) if data.section_id else None)))
        )
        room_result = await db.execute(room_conflict_q)
        room_conflict = room_result.scalar_one_or_none()
        if room_conflict:
            rc_result = await db.execute(select(ClassModel).where(ClassModel.id == room_conflict.class_id))
            rc_cls = rc_result.scalar_one_or_none()
            rc_name = rc_cls.name if rc_cls else "another class"
            raise HTTPException(400, f"Room conflict: {data.room} already assigned to {rc_name} at this time")

    # Find existing slot or create new
    existing_q = select(TimetableSlot).where(
        TimetableSlot.branch_id == branch_id,
        TimetableSlot.class_id == uuid.UUID(data.class_id),
        TimetableSlot.period_id == uuid.UUID(data.period_id),
        TimetableSlot.day_of_week == day_enum,
    )
    if data.section_id:
        existing_q = existing_q.where(TimetableSlot.section_id == uuid.UUID(data.section_id))
    else:
        existing_q = existing_q.where(TimetableSlot.section_id == None)

    result = await db.execute(existing_q)
    slot = result.scalar_one_or_none()

    # Get current academic year
    ay_result = await db.execute(
        select(AcademicYear).where(AcademicYear.branch_id == branch_id, AcademicYear.is_current == True)
    )
    academic_year = ay_result.scalar_one_or_none()

    if slot:
        # Update
        slot.subject_id = uuid.UUID(data.subject_id) if data.subject_id else None
        slot.teacher_id = uuid.UUID(data.teacher_id) if data.teacher_id else None
        slot.room = data.room
    else:
        # Create
        slot = TimetableSlot(
            branch_id=branch_id,
            academic_year_id=academic_year.id if academic_year else None,
            class_id=uuid.UUID(data.class_id),
            section_id=uuid.UUID(data.section_id) if data.section_id else None,
            period_id=uuid.UUID(data.period_id),
            day_of_week=day_enum,
            subject_id=uuid.UUID(data.subject_id) if data.subject_id else None,
            teacher_id=uuid.UUID(data.teacher_id) if data.teacher_id else None,
            room=data.room,
        )
        db.add(slot)

    await db.commit()
    return {"success": True}


@router.get("/timetable/load")
async def load_timetable(request: Request, class_id: str, section_id: str = "", db: AsyncSession = Depends(get_db)):
    """Load full timetable for a class/section"""
    user = await verify_school_admin(request)
    branch_id = get_branch_id(user)

    q = select(TimetableSlot).where(
        TimetableSlot.branch_id == branch_id,
        TimetableSlot.class_id == uuid.UUID(class_id),
        TimetableSlot.is_active == True,
    )
    if section_id:
        q = q.where(TimetableSlot.section_id == uuid.UUID(section_id))

    result = await db.execute(q)
    slots = result.scalars().all()

    # Build a map: {day: {period_id: {subject_id, teacher_id, room}}}
    timetable = {}
    for slot in slots:
        day = slot.day_of_week.value
        if day not in timetable:
            timetable[day] = {}
        timetable[day][str(slot.period_id)] = {
            "subject_id": str(slot.subject_id) if slot.subject_id else None,
            "teacher_id": str(slot.teacher_id) if slot.teacher_id else None,
            "room": slot.room or "",
        }

    return {"timetable": timetable}


@router.delete("/timetable/slot")
async def delete_timetable_slot(
    request: Request, class_id: str, section_id: str, period_id: str, day: str,
    db: AsyncSession = Depends(get_db)
):
    user = await verify_school_admin(request)
    branch_id = get_branch_id(user)

    q = select(TimetableSlot).where(
        TimetableSlot.branch_id == branch_id,
        TimetableSlot.class_id == uuid.UUID(class_id),
        TimetableSlot.period_id == uuid.UUID(period_id),
        TimetableSlot.day_of_week == DayOfWeek(day),
    )
    if section_id:
        q = q.where(TimetableSlot.section_id == uuid.UUID(section_id))

    result = await db.execute(q)
    slot = result.scalar_one_or_none()
    if slot:
        await db.delete(slot)
        await db.commit()

    return {"success": True}


@router.get("/timetable/teacher-view")
async def teacher_timetable(request: Request, teacher_id: str, db: AsyncSession = Depends(get_db)):
    """Get timetable for a specific teacher (for free period detection)"""
    user = await verify_school_admin(request)
    branch_id = get_branch_id(user)

    from models.academic import Class as ClassModel, Subject as SubjectModel

    slots_result = await db.execute(
        select(TimetableSlot)
        .where(TimetableSlot.branch_id == branch_id,
               TimetableSlot.teacher_id == uuid.UUID(teacher_id),
               TimetableSlot.is_active == True)
    )
    slots = slots_result.scalars().all()

    # Get all class/subject names
    class_ids = {s.class_id for s in slots}
    subject_ids = {s.subject_id for s in slots if s.subject_id}

    classes_map = {}
    if class_ids:
        cls_result = await db.execute(select(ClassModel).where(ClassModel.id.in_(class_ids)))
        for c in cls_result.scalars().all():
            classes_map[str(c.id)] = c.name

    subjects_map = {}
    if subject_ids:
        sub_result = await db.execute(select(SubjectModel).where(SubjectModel.id.in_(subject_ids)))
        for s in sub_result.scalars().all():
            subjects_map[str(s.id)] = s.name

    timetable = {}
    for slot in slots:
        day = slot.day_of_week.value
        if day not in timetable:
            timetable[day] = {}
        timetable[day][str(slot.period_id)] = {
            "class": classes_map.get(str(slot.class_id), ""),
            "subject": subjects_map.get(str(slot.subject_id), "") if slot.subject_id else "",
            "room": slot.room or "",
        }

    return {"timetable": timetable}


@router.get("/timetable/free-teachers")
async def get_free_teachers(request: Request, period_id: str, day: str, db: AsyncSession = Depends(get_db)):
    """Get teachers who are FREE at a specific period+day"""
    user = await verify_school_admin(request)
    branch_id = get_branch_id(user)

    from models.teacher import Teacher as TeacherModel

    # Get all active teachers
    all_teachers_result = await db.execute(
        select(TeacherModel).where(TeacherModel.branch_id == branch_id, TeacherModel.is_active == True)
    )
    all_teachers = all_teachers_result.scalars().all()

    # Get busy teachers at this slot
    busy_result = await db.execute(
        select(TimetableSlot.teacher_id).where(
            TimetableSlot.branch_id == branch_id,
            TimetableSlot.period_id == uuid.UUID(period_id),
            TimetableSlot.day_of_week == DayOfWeek(day),
            TimetableSlot.teacher_id != None,
            TimetableSlot.is_active == True,
        )
    )
    busy_ids = {str(r[0]) for r in busy_result.all()}

    free = []
    busy = []
    for t in all_teachers:
        teacher_data = {"id": str(t.id), "name": f"{t.first_name} {t.last_name or ''}".strip()}
        if str(t.id) in busy_ids:
            busy.append(teacher_data)
        else:
            free.append(teacher_data)

    return {"free": free, "busy": busy, "total": len(all_teachers)}


# ─── TEACHER ATTENDANCE (Admin) ───────────────────────────
from models.teacher_attendance import (
    TeacherAttendance, TeacherAttendanceStatus, CheckInSource,
    LeaveRequest, LeaveType, LeaveStatus,
)


@router.get("/teacher-attendance/load")
async def load_teacher_attendance(request: Request, date: str, db: AsyncSession = Depends(get_db)):
    """Load all teachers + existing attendance for a date"""
    user = await verify_school_admin(request)
    branch_id = get_branch_id(user)
    from datetime import datetime as dt

    att_date = dt.strptime(date, "%Y-%m-%d").date()

    # Get all teachers
    teachers_result = await db.execute(
        select(Teacher).where(Teacher.branch_id == branch_id, Teacher.is_active == True).order_by(Teacher.first_name)
    )
    teachers = teachers_result.scalars().all()

    # Get existing attendance
    att_result = await db.execute(
        select(TeacherAttendance).where(
            TeacherAttendance.branch_id == branch_id,
            TeacherAttendance.date == att_date,
        )
    )
    existing = {str(a.teacher_id): a for a in att_result.scalars().all()}

    teacher_list = []
    for t in teachers:
        att = existing.get(str(t.id))
        teacher_list.append({
            "id": str(t.id), "name": t.full_name, "designation": t.designation or "",
            "status": att.status.value if att else None,
            "check_in": att.check_in_time.strftime("%H:%M") if att and att.check_in_time else "",
            "source": att.source.value if att and att.source else "",
        })

    already_marked = len(existing) > 0
    return {"teachers": teacher_list, "already_marked": already_marked}


class TeacherAttRecord(BaseModel):
    teacher_id: str
    status: str


class TeacherAttSaveData(BaseModel):
    date: str
    records: List[TeacherAttRecord]


@router.post("/teacher-attendance/save")
async def save_teacher_attendance(data: TeacherAttSaveData, request: Request, db: AsyncSession = Depends(get_db)):
    """Admin marks teacher attendance (manual)"""
    user = await verify_school_admin(request)
    branch_id = get_branch_id(user)
    from datetime import datetime as dt

    att_date = dt.strptime(data.date, "%Y-%m-%d").date()
    admin_id = uuid.UUID(user["user_id"])

    saved = 0
    for r in data.records:
        try:
            status = TeacherAttendanceStatus(r.status)
        except ValueError:
            status = TeacherAttendanceStatus.PRESENT

        # Upsert
        existing_result = await db.execute(
            select(TeacherAttendance).where(
                TeacherAttendance.teacher_id == uuid.UUID(r.teacher_id),
                TeacherAttendance.date == att_date,
            )
        )
        att = existing_result.scalar_one_or_none()

        if att:
            att.status = status
            att.source = CheckInSource.ADMIN_MANUAL
            att.marked_by = admin_id
        else:
            att = TeacherAttendance(
                branch_id=branch_id,
                teacher_id=uuid.UUID(r.teacher_id),
                date=att_date,
                status=status,
                source=CheckInSource.ADMIN_MANUAL,
                marked_by=admin_id,
            )
            db.add(att)
        saved += 1

    await db.commit()
    return {"success": True, "saved": saved, "message": f"Attendance saved for {saved} teachers"}


@router.get("/teacher-attendance/report")
async def teacher_attendance_report(
    request: Request, month: int, year: int, db: AsyncSession = Depends(get_db)
):
    """Monthly teacher attendance report"""
    user = await verify_school_admin(request)
    branch_id = get_branch_id(user)
    from calendar import monthrange
    from datetime import date as date_type

    _, days_in_month = monthrange(year, month)
    month_start = date_type(year, month, 1)
    month_end = date_type(year, month, days_in_month)

    # All teachers
    teachers_result = await db.execute(
        select(Teacher).where(Teacher.branch_id == branch_id, Teacher.is_active == True).order_by(Teacher.first_name)
    )
    teachers = teachers_result.scalars().all()

    # All attendance in month
    att_result = await db.execute(
        select(TeacherAttendance).where(
            TeacherAttendance.branch_id == branch_id,
            TeacherAttendance.date >= month_start,
            TeacherAttendance.date <= month_end,
        )
    )
    all_att = att_result.scalars().all()

    # Group by teacher
    att_by_teacher = {}
    for a in all_att:
        tid = str(a.teacher_id)
        if tid not in att_by_teacher:
            att_by_teacher[tid] = []
        att_by_teacher[tid].append(a)

    # Count working days (exclude Sundays)
    import calendar
    working_days = 0
    for day in range(1, days_in_month + 1):
        d = date_type(year, month, day)
        if d > date_type.today():
            break
        if d.weekday() != 6:  # Not Sunday
            working_days += 1

    report = []
    for t in teachers:
        records = att_by_teacher.get(str(t.id), [])
        present = sum(1 for r in records if r.status.value in ("present", "late"))
        absent = sum(1 for r in records if r.status.value == "absent")
        on_leave = sum(1 for r in records if r.status.value == "on_leave")
        half_day = sum(1 for r in records if r.status.value == "half_day")
        pct = round(present / working_days * 100) if working_days > 0 else 0

        report.append({
            "id": str(t.id), "name": t.full_name, "designation": t.designation or "",
            "present": present, "absent": absent, "on_leave": on_leave, "half_day": half_day,
            "percentage": pct,
        })

    return {"report": report, "working_days": working_days, "month": month, "year": year}


# ─── LEAVE MANAGEMENT (Admin) ────────────────────────────
@router.get("/leaves/pending")
async def get_pending_leaves(request: Request, db: AsyncSession = Depends(get_db)):
    user = await verify_school_admin(request)
    branch_id = get_branch_id(user)

    result = await db.execute(
        select(LeaveRequest)
        .where(LeaveRequest.branch_id == branch_id, LeaveRequest.status == LeaveStatus.PENDING)
        .order_by(LeaveRequest.created_at.desc())
    )
    leaves = result.scalars().all()

    # Get teacher names
    teacher_ids = {l.teacher_id for l in leaves}
    teachers_map = {}
    if teacher_ids:
        r = await db.execute(select(Teacher).where(Teacher.id.in_(teacher_ids)))
        teachers_map = {t.id: t.full_name for t in r.scalars().all()}

    return {
        "leaves": [
            {"id": str(l.id), "teacher_id": str(l.teacher_id),
             "teacher_name": teachers_map.get(l.teacher_id, ""),
             "type": l.leave_type.value, "start": l.start_date.isoformat(),
             "end": l.end_date.isoformat(), "days": (l.end_date - l.start_date).days + 1,
             "reason": l.reason, "status": l.status.value,
             "on_behalf": l.on_behalf_name or "" if hasattr(l, 'on_behalf_name') else "",
             "applied": l.created_at.strftime("%d %b %Y") if l.created_at else ""}
            for l in leaves
        ]
    }


@router.get("/leaves/all")
async def get_all_leaves(request: Request, db: AsyncSession = Depends(get_db)):
    user = await verify_school_admin(request)
    branch_id = get_branch_id(user)

    result = await db.execute(
        select(LeaveRequest)
        .where(LeaveRequest.branch_id == branch_id)
        .order_by(LeaveRequest.created_at.desc())
        .limit(100)
    )
    leaves = result.scalars().all()

    teacher_ids = {l.teacher_id for l in leaves}
    teachers_map = {}
    if teacher_ids:
        r = await db.execute(select(Teacher).where(Teacher.id.in_(teacher_ids)))
        teachers_map = {t.id: t.full_name for t in r.scalars().all()}

    return {
        "leaves": [
            {"id": str(l.id), "teacher_id": str(l.teacher_id),
             "teacher_name": teachers_map.get(l.teacher_id, ""),
             "type": l.leave_type.value, "start": l.start_date.isoformat(),
             "end": l.end_date.isoformat(), "days": (l.end_date - l.start_date).days + 1,
             "reason": l.reason, "status": l.status.value,
             "admin_remarks": l.admin_remarks or "",
             "on_behalf": l.on_behalf_name or "" if hasattr(l, 'on_behalf_name') else "",
             "applied": l.created_at.strftime("%d %b %Y") if l.created_at else ""}
            for l in leaves
        ]
    }


class LeaveActionData(BaseModel):
    action: str  # approve, reject
    remarks: Optional[str] = None


@router.post("/leaves/{leave_id}/action")
async def leave_action(leave_id: str, data: LeaveActionData, request: Request, db: AsyncSession = Depends(get_db)):
    user = await verify_school_admin(request)
    branch_id = get_branch_id(user)
    from datetime import datetime as dt

    result = await db.execute(
        select(LeaveRequest).where(
            LeaveRequest.id == uuid.UUID(leave_id),
            LeaveRequest.branch_id == branch_id,
        )
    )
    leave = result.scalar_one_or_none()
    if not leave:
        raise HTTPException(404, "Leave request not found")
    if leave.status != LeaveStatus.PENDING:
        raise HTTPException(400, f"Already {leave.status.value}")

    admin_id = uuid.UUID(user["user_id"])

    if data.action == "approve":
        leave.status = LeaveStatus.APPROVED
        leave.reviewed_by = admin_id
        leave.reviewed_at = dt.utcnow()
        leave.admin_remarks = data.remarks

        # Auto-mark teacher attendance as ON_LEAVE for leave dates
        current = leave.start_date
        while current <= leave.end_date:
            if current.weekday() != 6:  # Skip Sundays
                existing_result = await db.execute(
                    select(TeacherAttendance).where(
                        TeacherAttendance.teacher_id == leave.teacher_id,
                        TeacherAttendance.date == current,
                    )
                )
                existing_att = existing_result.scalar_one_or_none()
                if existing_att:
                    existing_att.status = TeacherAttendanceStatus.ON_LEAVE
                else:
                    att = TeacherAttendance(
                        branch_id=branch_id,
                        teacher_id=leave.teacher_id,
                        date=current,
                        status=TeacherAttendanceStatus.ON_LEAVE,
                        source=CheckInSource.ADMIN_MANUAL,
                        marked_by=admin_id,
                        remarks=f"Leave: {leave.leave_type.value}",
                    )
                    db.add(att)
            current = current + timedelta(days=1)

        msg = "Leave approved"
    elif data.action == "reject":
        leave.status = LeaveStatus.REJECTED
        leave.reviewed_by = admin_id
        leave.reviewed_at = dt.utcnow()
        leave.admin_remarks = data.remarks
        msg = "Leave rejected"
    else:
        raise HTTPException(400, "Invalid action")

    await db.commit()
    return {"success": True, "message": msg}


class LeaveOnBehalfData(BaseModel):
    teacher_id: str
    leave_type: str
    start_date: str
    end_date: str
    reason: str


@router.post("/leaves/on-behalf")
async def apply_leave_on_behalf(data: LeaveOnBehalfData, request: Request, db: AsyncSession = Depends(get_db)):
    """Admin applies leave on behalf of a teacher."""
    user = await verify_school_admin(request)
    branch_id = get_branch_id(user)
    from datetime import datetime as dt, date as dt_date

    start = dt_date.fromisoformat(data.start_date)
    end = dt_date.fromisoformat(data.end_date)
    if end < start:
        raise HTTPException(400, "End date must be after start date")

    admin_id = uuid.UUID(user["user_id"])
    admin_name = f"{user.get('first_name', '')} {user.get('last_name', '')}".strip() or "Admin"

    leave = LeaveRequest(
        branch_id=branch_id,
        teacher_id=uuid.UUID(data.teacher_id),
        leave_type=LeaveType(data.leave_type),
        start_date=start,
        end_date=end,
        reason=data.reason,
        status=LeaveStatus.PENDING,
        applied_on_behalf_by=admin_id,
        on_behalf_name=admin_name,
    )
    db.add(leave)
    await db.commit()
    days = (end - start).days + 1
    return {"success": True, "message": f"Leave applied on behalf for {days} day(s)", "id": str(leave.id)}


# ─── EXAM & RESULTS APIs ─────────────────────────────────
from models.exam import Exam, ExamSubject, Marks
from models.student import Student


class ExamSubjectData(BaseModel):
    subject_id: str
    class_id: str
    max_marks: float = 100
    passing_marks: float = 33


class CreateExamData(BaseModel):
    name: str
    description: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    applicable_classes: Optional[list] = None
    subjects: List[ExamSubjectData] = []


@router.post("/exams/create")
async def create_exam(data: CreateExamData, request: Request, db: AsyncSession = Depends(get_db)):
    user = await verify_school_admin(request)
    branch_id = get_branch_id(user)
    from datetime import datetime as dt

    ay_result = await db.execute(
        select(AcademicYear).where(AcademicYear.branch_id == branch_id, AcademicYear.is_current == True)
    )
    academic_year = ay_result.scalar_one_or_none()
    if not academic_year:
        raise HTTPException(400, "No active academic year")

    exam = Exam(
        branch_id=branch_id,
        academic_year_id=academic_year.id,
        name=data.name,
        description=data.description,
        start_date=dt.strptime(data.start_date, "%Y-%m-%d").date() if data.start_date else None,
        end_date=dt.strptime(data.end_date, "%Y-%m-%d").date() if data.end_date else None,
        applicable_classes=data.applicable_classes,
    )
    db.add(exam)
    await db.flush()

    for s in data.subjects:
        es = ExamSubject(
            exam_id=exam.id,
            subject_id=uuid.UUID(s.subject_id),
            class_id=uuid.UUID(s.class_id),
            max_marks=s.max_marks,
            passing_marks=s.passing_marks,
        )
        db.add(es)

    await db.commit()
    return {"success": True, "exam_id": str(exam.id), "message": f"Exam '{data.name}' created"}


@router.get("/exams/{exam_id}/subjects")
async def get_exam_subjects(exam_id: str, request: Request, class_id: str = "", db: AsyncSession = Depends(get_db)):
    user = await verify_school_admin(request)

    q = select(ExamSubject).where(ExamSubject.exam_id == uuid.UUID(exam_id))
    if class_id:
        q = q.where(ExamSubject.class_id == uuid.UUID(class_id))

    result = await db.execute(q)
    subjects = result.scalars().all()

    # Get subject names
    sub_ids = {s.subject_id for s in subjects}
    sub_map = {}
    if sub_ids:
        from models.academic import Subject as SubjectModel
        r = await db.execute(select(SubjectModel).where(SubjectModel.id.in_(sub_ids)))
        sub_map = {s.id: s.name for s in r.scalars().all()}

    # Get class names
    cls_ids = {s.class_id for s in subjects if s.class_id}
    cls_map = {}
    if cls_ids:
        cr = await db.execute(select(Class).where(Class.id.in_(cls_ids)))
        cls_map = {c.id: c.name for c in cr.scalars().all()}

    return {
        "subjects": [
            {"id": str(s.id), "subject_id": str(s.subject_id),
             "subject_name": sub_map.get(s.subject_id, ""),
             "class_id": str(s.class_id),
             "class_name": cls_map.get(s.class_id, ""),
             "max_marks": s.max_marks, "passing_marks": s.passing_marks}
            for s in subjects
        ]
    }


@router.delete("/exams/subject/{es_id}")
async def delete_exam_subject(es_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    user = await verify_school_admin(request)
    es = await db.get(ExamSubject, uuid.UUID(es_id))
    if not es:
        raise HTTPException(status_code=404, detail="Exam subject not found")
    await db.delete(es)
    await db.commit()
    return {"success": True, "message": "Subject removed from exam"}


class AddExamSubjectData(BaseModel):
    exam_id: str
    subject_id: str
    class_id: str
    max_marks: float = 100
    passing_marks: float = 33


@router.post("/exams/add-subject")
async def add_exam_subject(data: AddExamSubjectData, request: Request, db: AsyncSession = Depends(get_db)):
    user = await verify_school_admin(request)

    es = ExamSubject(
        exam_id=uuid.UUID(data.exam_id),
        subject_id=uuid.UUID(data.subject_id),
        class_id=uuid.UUID(data.class_id),
        max_marks=data.max_marks,
        passing_marks=data.passing_marks,
    )
    db.add(es)
    await db.commit()
    return {"success": True, "id": str(es.id)}


@router.delete("/exams/{exam_id}")
async def delete_exam(exam_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    user = await verify_school_admin(request)
    result = await db.execute(select(Exam).where(Exam.id == uuid.UUID(exam_id)))
    exam = result.scalar_one_or_none()
    if exam:
        await db.delete(exam)
        await db.commit()
    return {"success": True}


# ─── MARKS ENTRY ──────────────────────────────────────────
@router.get("/marks/load")
async def load_marks(
    request: Request, exam_id: str, class_id: str, subject_id: str,
    section_id: str = "", db: AsyncSession = Depends(get_db)
):
    user = await verify_school_admin(request)
    branch_id = get_branch_id(user)

    # Get exam subject
    es_result = await db.execute(
        select(ExamSubject).where(
            ExamSubject.exam_id == uuid.UUID(exam_id),
            ExamSubject.subject_id == uuid.UUID(subject_id),
            ExamSubject.class_id == uuid.UUID(class_id),
        )
    )
    exam_subject = es_result.scalar_one_or_none()
    if not exam_subject:
        raise HTTPException(404, "Exam subject not found for this class")

    # Get students
    q = select(Student).where(
        Student.branch_id == branch_id, Student.class_id == uuid.UUID(class_id),
        Student.is_active == True,
    )
    if section_id:
        q = q.where(Student.section_id == uuid.UUID(section_id))
    q = q.order_by(Student.roll_number, Student.first_name)

    students_result = await db.execute(q)
    students = students_result.scalars().all()

    # Get existing marks
    marks_result = await db.execute(
        select(Marks).where(Marks.exam_subject_id == exam_subject.id)
    )
    marks_map = {str(m.student_id): m for m in marks_result.scalars().all()}

    student_list = []
    for s in students:
        m = marks_map.get(str(s.id))
        student_list.append({
            "id": str(s.id), "name": s.full_name,
            "roll": s.roll_number or "", "gender": s.gender.value if s.gender else "",
            "marks": m.marks_obtained if m and not m.is_absent else None,
            "is_absent": m.is_absent if m else False,
            "grade": m.grade if m else "",
        })

    return {
        "students": student_list,
        "exam_subject_id": str(exam_subject.id),
        "max_marks": exam_subject.max_marks,
        "passing_marks": exam_subject.passing_marks,
    }


class MarkRecord(BaseModel):
    student_id: str
    marks: Optional[float] = None
    is_absent: bool = False


class SaveMarksData(BaseModel):
    exam_subject_id: str
    records: List[MarkRecord]


@router.post("/marks/save")
async def save_marks(data: SaveMarksData, request: Request, db: AsyncSession = Depends(get_db)):
    user = await verify_school_admin(request)
    entered_by = uuid.UUID(user["user_id"])

    es_id = uuid.UUID(data.exam_subject_id)

    # Get exam subject for max/passing
    es_result = await db.execute(select(ExamSubject).where(ExamSubject.id == es_id))
    exam_subject = es_result.scalar_one_or_none()
    if not exam_subject:
        raise HTTPException(404, "Exam subject not found")

    # Delete existing marks
    existing = await db.execute(select(Marks).where(Marks.exam_subject_id == es_id))
    for m in existing.scalars().all():
        await db.delete(m)
    await db.flush()

    saved = 0
    for r in data.records:
        grade = ""
        if not r.is_absent and r.marks is not None:
            pct = (r.marks / exam_subject.max_marks * 100) if exam_subject.max_marks > 0 else 0
            grade = calculate_grade(pct)

        mark = Marks(
            exam_subject_id=es_id,
            student_id=uuid.UUID(r.student_id),
            marks_obtained=r.marks if not r.is_absent else None,
            is_absent=r.is_absent,
            grade=grade,
            entered_by=entered_by,
        )
        db.add(mark)
        saved += 1

    await db.commit()
    return {"success": True, "saved": saved, "message": f"Marks saved for {saved} students"}


def calculate_grade(percentage):
    if percentage >= 91: return "A1"
    elif percentage >= 81: return "A2"
    elif percentage >= 71: return "B1"
    elif percentage >= 61: return "B2"
    elif percentage >= 51: return "C1"
    elif percentage >= 41: return "C2"
    elif percentage >= 33: return "D"
    else: return "E"


# ─── RESULTS ──────────────────────────────────────────────
@router.get("/results/load")
async def load_results(
    request: Request, exam_id: str, class_id: str, section_id: str = "",
    db: AsyncSession = Depends(get_db)
):
    """Load full results: all subjects, all students, with ranks and percentages"""
    user = await verify_school_admin(request)
    branch_id = get_branch_id(user)

    # Get exam subjects for this class
    es_result = await db.execute(
        select(ExamSubject).where(
            ExamSubject.exam_id == uuid.UUID(exam_id),
            ExamSubject.class_id == uuid.UUID(class_id),
        )
    )
    exam_subjects = es_result.scalars().all()

    if not exam_subjects:
        return {"subjects": [], "students": [], "has_data": False}

    # Subject names
    sub_ids = {es.subject_id for es in exam_subjects}
    from models.academic import Subject as SubjectModel
    sub_result = await db.execute(select(SubjectModel).where(SubjectModel.id.in_(sub_ids)))
    sub_map = {s.id: s.name for s in sub_result.scalars().all()}

    subjects_info = [
        {"id": str(es.id), "subject_id": str(es.subject_id),
         "name": sub_map.get(es.subject_id, ""), "max": es.max_marks, "pass": es.passing_marks}
        for es in exam_subjects
    ]

    # Get students
    q = select(Student).where(
        Student.branch_id == branch_id, Student.class_id == uuid.UUID(class_id), Student.is_active == True
    )
    if section_id:
        q = q.where(Student.section_id == uuid.UUID(section_id))
    students_result = await db.execute(q.order_by(Student.roll_number, Student.first_name))
    students = students_result.scalars().all()

    # Get all marks for these exam subjects
    es_ids = [es.id for es in exam_subjects]
    marks_result = await db.execute(
        select(Marks).where(Marks.exam_subject_id.in_(es_ids))
    )
    all_marks = marks_result.scalars().all()

    # Build marks map: {student_id: {exam_subject_id: marks_obj}}
    marks_map = {}
    for m in all_marks:
        sid = str(m.student_id)
        if sid not in marks_map:
            marks_map[sid] = {}
        marks_map[sid][str(m.exam_subject_id)] = m

    # Build student results
    student_results = []
    total_max = sum(es.max_marks for es in exam_subjects)

    for s in students:
        sid = str(s.id)
        student_marks = marks_map.get(sid, {})
        total_obtained = 0
        all_pass = True
        subject_data = []

        for es in exam_subjects:
            m = student_marks.get(str(es.id))
            obtained = m.marks_obtained if m and not m.is_absent else 0
            is_absent = m.is_absent if m else False
            grade = m.grade if m else ""
            passed = obtained >= es.passing_marks if not is_absent else False

            if not passed:
                all_pass = False
            total_obtained += obtained if not is_absent else 0

            subject_data.append({
                "marks": obtained if not is_absent else None,
                "absent": is_absent, "grade": grade, "passed": passed,
            })

        percentage = round(total_obtained / total_max * 100, 1) if total_max > 0 else 0
        overall_grade = calculate_grade(percentage)

        student_results.append({
            "id": sid, "name": s.full_name, "roll": s.roll_number or "",
            "subjects": subject_data, "total": total_obtained,
            "percentage": percentage, "grade": overall_grade,
            "result": "PASS" if all_pass else "FAIL",
        })

    # Calculate ranks
    student_results.sort(key=lambda x: x["percentage"], reverse=True)
    for i, sr in enumerate(student_results):
        sr["rank"] = i + 1

    # Re-sort by roll number
    student_results.sort(key=lambda x: (x["roll"] or "zzz", x["name"]))

    return {
        "subjects": subjects_info,
        "students": student_results,
        "total_max": total_max,
        "has_data": len(all_marks) > 0,
    }


@router.post("/exams/{exam_id}/publish")
async def toggle_publish(exam_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    user = await verify_school_admin(request)
    result = await db.execute(select(Exam).where(Exam.id == uuid.UUID(exam_id)))
    exam = result.scalar_one_or_none()
    if not exam:
        raise HTTPException(404, "Exam not found")
    exam.is_published = not exam.is_published
    await db.commit()
    return {"success": True, "published": exam.is_published,
            "message": f"Results {'published' if exam.is_published else 'unpublished'}"}




# ─── FEE MANAGEMENT APIs ─────────────────────────────────
from models.fee import FeeStructure, FeeRecord, FeeFrequency, PaymentStatus, PaymentMode
from models.branch import PaymentGatewayConfig


class PaymentSettingsData(BaseModel):
    online_payments_enabled: bool = False
    test_mode: bool = False
    selected_gateway: str = "manual"
    # Razorpay
    razorpay_key_id: Optional[str] = None
    razorpay_key_secret: Optional[str] = None
    razorpay_webhook_secret: Optional[str] = None
    # PayU
    payu_merchant_key: Optional[str] = None
    payu_merchant_salt: Optional[str] = None
    # Cashfree
    cashfree_app_id: Optional[str] = None
    cashfree_secret_key: Optional[str] = None
    # PhonePe
    phonepe_merchant_id: Optional[str] = None
    phonepe_salt_key: Optional[str] = None
    # Stripe
    stripe_publishable_key: Optional[str] = None
    stripe_secret_key: Optional[str] = None
    # Accepted methods
    accept_upi: bool = True
    accept_cards: bool = True
    accept_netbanking: bool = True
    accept_wallets: bool = False
    accept_emi: bool = False
    # UPI
    upi_enabled: bool = False
    upi_id: Optional[str] = None
    upi_display_name: Optional[str] = None
    show_upi_on_invoice: bool = True
    # Bank
    bank_transfer_enabled: bool = False
    bank_name: Optional[str] = None
    account_number: Optional[str] = None
    ifsc_code: Optional[str] = None
    account_holder: Optional[str] = None
    bank_branch: Optional[str] = None
    account_type: str = "current"
    show_bank_on_invoice: bool = True
    # WhatsApp
    whatsapp_number: Optional[str] = None


@router.post("/payment-settings/save")
async def save_payment_settings(data: PaymentSettingsData, request: Request, db: AsyncSession = Depends(get_db)):
    user = await verify_school_admin(request)
    branch_id = get_branch_id(user)

    result = await db.execute(select(PaymentGatewayConfig).where(PaymentGatewayConfig.branch_id == branch_id))
    config = result.scalar_one_or_none()

    if not config:
        config = PaymentGatewayConfig(branch_id=branch_id)
        db.add(config)

    # Update all fields
    for field, value in data.dict().items():
        if hasattr(config, field):
            # Don't overwrite secrets with empty strings
            if field.endswith('_secret') or field.endswith('_key') or field.endswith('_salt'):
                if value is not None and value.strip():
                    setattr(config, field, value)
            else:
                setattr(config, field, value)

    await db.commit()
    return {"success": True, "message": "Payment settings saved! ✅"}


@router.get("/payment-settings/load")
async def load_payment_settings(request: Request, db: AsyncSession = Depends(get_db)):
    user = await verify_school_admin(request)
    branch_id = get_branch_id(user)
    result = await db.execute(select(PaymentGatewayConfig).where(PaymentGatewayConfig.branch_id == branch_id))
    config = result.scalar_one_or_none()
    if not config:
        return {"config": None}

    return {"config": {
        "online_payments_enabled": config.online_payments_enabled,
        "test_mode": config.test_mode,
        "selected_gateway": config.selected_gateway or "manual",
        "razorpay_key_id": config.razorpay_key_id or "",
        "payu_merchant_key": config.payu_merchant_key or "",
        "cashfree_app_id": config.cashfree_app_id or "",
        "phonepe_merchant_id": config.phonepe_merchant_id or "",
        "stripe_publishable_key": config.stripe_publishable_key or "",
        "accept_upi": config.accept_upi, "accept_cards": config.accept_cards,
        "accept_netbanking": config.accept_netbanking, "accept_wallets": config.accept_wallets,
        "accept_emi": config.accept_emi,
        "upi_enabled": config.upi_enabled, "upi_id": config.upi_id or "",
        "upi_display_name": config.upi_display_name or "", "show_upi_on_invoice": config.show_upi_on_invoice,
        "bank_transfer_enabled": config.bank_transfer_enabled, "bank_name": config.bank_name or "",
        "account_number": config.account_number or "", "ifsc_code": config.ifsc_code or "",
        "account_holder": config.account_holder or "", "bank_branch": config.bank_branch or "",
        "account_type": config.account_type or "current", "show_bank_on_invoice": config.show_bank_on_invoice,
        "whatsapp_number": config.whatsapp_number or "",
    }}


# ─── FEE STRUCTURE ────────────────────────────────────────
class FeeStructureData(BaseModel):
    fee_name: str
    amount: float
    class_id: Optional[str] = None
    frequency: str = "monthly"
    due_day: int = 10
    description: Optional[str] = None
    is_mandatory: bool = True


@router.post("/fee-structure/create")
async def create_fee_structure(data: FeeStructureData, request: Request, db: AsyncSession = Depends(get_db)):
    user = await verify_school_admin(request)
    branch_id = get_branch_id(user)
    ay_result = await db.execute(select(AcademicYear).where(AcademicYear.branch_id == branch_id, AcademicYear.is_current == True))
    ay = ay_result.scalar_one_or_none()

    fee = FeeStructure(
        branch_id=branch_id, class_id=uuid.UUID(data.class_id) if data.class_id else None,
        academic_year_id=ay.id if ay else None,
        fee_name=data.fee_name, amount=data.amount,
        frequency=FeeFrequency(data.frequency), due_day=data.due_day,
        description=data.description, is_mandatory=data.is_mandatory,
    )
    db.add(fee)
    await db.commit()
    return {"success": True, "id": str(fee.id), "message": f"Fee '{data.fee_name}' created — ₹{data.amount}"}


@router.put("/fee-structure/{fee_id}")
async def update_fee_structure(fee_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    """Edit an existing fee structure."""
    user = await verify_school_admin(request)
    data = await request.json()
    result = await db.execute(select(FeeStructure).where(FeeStructure.id == uuid.UUID(fee_id)))
    fee = result.scalar_one_or_none()
    if not fee:
        raise HTTPException(404, "Fee structure not found")
    if data.get("fee_name"):
        fee.fee_name = data["fee_name"]
    if data.get("amount") is not None:
        fee.amount = float(data["amount"])
    if data.get("frequency"):
        fee.frequency = FeeFrequency(data["frequency"])
    if data.get("due_day") is not None:
        fee.due_day = int(data["due_day"])
    if "class_id" in data:
        fee.class_id = uuid.UUID(data["class_id"]) if data["class_id"] else None
    if "description" in data:
        fee.description = data.get("description")
    if "is_mandatory" in data:
        fee.is_mandatory = data["is_mandatory"]
    await db.commit()
    return {"success": True, "message": f"Fee '{fee.fee_name}' updated — ₹{fee.amount:,.0f}"}


@router.delete("/fee-structure/{fee_id}")
async def delete_fee_structure(fee_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    user = await verify_school_admin(request)
    result = await db.execute(select(FeeStructure).where(FeeStructure.id == uuid.UUID(fee_id)))
    fee = result.scalar_one_or_none()
    if fee:
        fee.is_active = False
        await db.commit()
    return {"success": True}


@router.get("/fee-structure/list")
async def list_fee_structures(request: Request, class_id: str = "", db: AsyncSession = Depends(get_db)):
    user = await verify_school_admin(request)
    branch_id = get_branch_id(user)
    q = select(FeeStructure).where(FeeStructure.branch_id == branch_id, FeeStructure.is_active == True)
    if class_id:
        q = q.where((FeeStructure.class_id == uuid.UUID(class_id)) | (FeeStructure.class_id == None))
    result = await db.execute(q.order_by(FeeStructure.fee_name))
    fees = result.scalars().all()

    # Class names
    class_ids = {f.class_id for f in fees if f.class_id}
    cls_map = {}
    if class_ids:
        from models.academic import Class as ClassModel
        r = await db.execute(select(ClassModel).where(ClassModel.id.in_(class_ids)))
        cls_map = {c.id: c.name for c in r.scalars().all()}

    return {"fees": [
        {"id": str(f.id), "name": f.fee_name, "amount": f.amount,
         "class_id": str(f.class_id) if f.class_id else None,
         "class_name": cls_map.get(f.class_id, "All Classes") if f.class_id else "All Classes",
         "frequency": f.frequency.value, "due_day": f.due_day,
         "mandatory": f.is_mandatory, "description": f.description or ""}
        for f in fees
    ]}


# ─── FEE COLLECTION ───────────────────────────────────────
@router.post("/fees/generate")
async def generate_fees(request: Request, class_id: str, month: int, year: int,
                        section_id: str = "", db: AsyncSession = Depends(get_db)):
    """Generate fee records for all students in a class for a given month"""
    user = await verify_school_admin(request)
    branch_id = get_branch_id(user)
    from datetime import date as d

    # Get fee structures for this class
    q = select(FeeStructure).where(
        FeeStructure.branch_id == branch_id, FeeStructure.is_active == True,
        (FeeStructure.class_id == uuid.UUID(class_id)) | (FeeStructure.class_id == None)
    )
    fees = (await db.execute(q)).scalars().all()

    # Get students
    sq = select(Student).where(Student.branch_id == branch_id, Student.class_id == uuid.UUID(class_id), Student.is_active == True)
    if section_id:
        sq = sq.where(Student.section_id == uuid.UUID(section_id))
    students = (await db.execute(sq)).scalars().all()

    generated = 0
    for student in students:
        # Check for active waivers
        from models.mega_modules import FeeWaiver
        active_waivers = (await db.execute(
            select(FeeWaiver).where(
                FeeWaiver.student_id == student.id, FeeWaiver.status == "active",
                (FeeWaiver.valid_to == None) | (FeeWaiver.valid_to >= d(year, month, 1))
            )
        )).scalars().all()

        for fee in fees:
            due_date = d(year, month, min(fee.due_day, 28))
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
            waiver_applied = ""
            for w in active_waivers:
                if w.discount_type == "percentage":
                    discount = amount * (w.discount_value / 100)
                    amount = amount - discount
                    waiver_applied = f"{w.title} (-{w.discount_value}%)"
                elif w.discount_type == "fixed":
                    amount = max(0, amount - w.discount_value)
                    waiver_applied = f"{w.title} (-₹{w.discount_value})"

            rec = FeeRecord(
                student_id=student.id, fee_structure_id=fee.id, branch_id=branch_id,
                amount_due=amount, due_date=due_date, status=PaymentStatus.PENDING,
            )
            db.add(rec)
            generated += 1

    await db.commit()
    return {"success": True, "generated": generated, "message": f"Generated {generated} fee records for {len(students)} students"}


@router.get("/fees/student-fees")
async def get_student_fees(request: Request, class_id: str, section_id: str = "",
                           status: str = "", db: AsyncSession = Depends(get_db)):
    user = await verify_school_admin(request)
    branch_id = get_branch_id(user)

    # Get students
    sq = select(Student).where(Student.branch_id == branch_id, Student.class_id == uuid.UUID(class_id), Student.is_active == True)
    if section_id:
        sq = sq.where(Student.section_id == uuid.UUID(section_id))
    students = (await db.execute(sq.order_by(Student.roll_number, Student.first_name))).scalars().all()

    student_data = []
    for s in students:
        fq = select(FeeRecord).where(FeeRecord.student_id == s.id)
        if status:
            fq = fq.where(FeeRecord.status == PaymentStatus(status))
        from sqlalchemy.orm import selectinload
        fees = (await db.execute(fq.options(selectinload(FeeRecord.fee_structure)).order_by(FeeRecord.due_date.desc()))).scalars().all()

        total_due = sum(f.amount_due for f in fees)
        total_paid = sum(f.amount_paid for f in fees)
        total_discount = sum(f.discount for f in fees)
        balance = total_due - total_paid - total_discount

        student_data.append({
            "id": str(s.id), "name": s.full_name, "roll": s.roll_number or "",
            "total_due": total_due, "total_paid": total_paid,
            "discount": total_discount, "balance": balance,
            "fees": [
                {"id": str(f.id), "name": f.fee_structure.fee_name if f.fee_structure else "",
                 "amount_due": f.amount_due, "amount_paid": f.amount_paid,
                 "discount": f.discount, "due_date": f.due_date.isoformat(),
                 "status": f.status.value, "payment_mode": f.payment_mode.value if f.payment_mode else "",
                 "receipt": f.receipt_number or ""}
                for f in fees
            ]
        })

    return {"students": student_data}


class CollectFeeData(BaseModel):
    fee_record_id: str
    amount: float
    payment_mode: str
    transaction_id: Optional[str] = None
    discount: float = 0
    remarks: Optional[str] = None


@router.post("/fees/collect")
async def collect_fee(data: CollectFeeData, request: Request, db: AsyncSession = Depends(get_db)):
    user = await verify_school_admin(request)
    from datetime import date as d
    import random, string

    result = await db.execute(select(FeeRecord).where(FeeRecord.id == uuid.UUID(data.fee_record_id)))
    rec = result.scalar_one_or_none()
    if not rec:
        raise HTTPException(404, "Fee record not found")

    rec.amount_paid = (rec.amount_paid or 0) + data.amount
    rec.discount = data.discount
    rec.payment_mode = PaymentMode(data.payment_mode)
    rec.transaction_id = data.transaction_id
    rec.payment_date = d.today()
    rec.remarks = data.remarks

    if rec.amount_paid + rec.discount >= rec.amount_due:
        rec.status = PaymentStatus.PAID
    elif rec.amount_paid > 0:
        rec.status = PaymentStatus.PARTIAL

    # Generate receipt number
    if not rec.receipt_number:
        rec.receipt_number = "RCP-" + "".join(random.choices(string.digits, k=8))

    await db.commit()
    return {"success": True, "message": f"₹{data.amount} collected", "receipt": rec.receipt_number, "status": rec.status.value}


@router.get("/fees/defaulters")
async def fee_defaulters(request: Request, class_id: str = "", db: AsyncSession = Depends(get_db)):
    user = await verify_school_admin(request)
    branch_id = get_branch_id(user)
    from datetime import date as d

    q = select(FeeRecord).where(
        FeeRecord.branch_id == branch_id,
        FeeRecord.status.in_([PaymentStatus.PENDING, PaymentStatus.PARTIAL, PaymentStatus.OVERDUE]),
        FeeRecord.due_date < d.today(),
    )
    overdue = (await db.execute(q)).scalars().all()

    # Update status to overdue
    for rec in overdue:
        if rec.status == PaymentStatus.PENDING:
            rec.status = PaymentStatus.OVERDUE
    await db.commit()

    # Group by student
    student_ids = {r.student_id for r in overdue}
    stu_map = {}
    if student_ids:
        r = await db.execute(select(Student).where(Student.id.in_(student_ids)))
        stu_map = {s.id: s for s in r.scalars().all()}

    defaulters = {}
    for rec in overdue:
        sid = str(rec.student_id)
        if sid not in defaulters:
            s = stu_map.get(rec.student_id)
            defaulters[sid] = {
                "id": sid, "name": s.full_name if s else "", "roll": s.roll_number if s else "",
                "total_overdue": 0, "records": 0,
            }
        defaulters[sid]["total_overdue"] += rec.amount_due - (rec.amount_paid or 0) - (rec.discount or 0)
        defaulters[sid]["records"] += 1

    return {"defaulters": sorted(defaulters.values(), key=lambda x: x["total_overdue"], reverse=True)}


# ─── COMMUNICATION APIs ───────────────────────────────────
from models.notification import Announcement, Notification, NotificationType, NotificationChannel, AnnouncementPriority
from models.branch import CommunicationConfig


class AnnouncementData(BaseModel):
    title: str
    content: str
    priority: str = "normal"
    target_role: str = "all"  # all, teacher, student, parent
    target_class_id: Optional[str] = None
    target_section_id: Optional[str] = None
    is_pinned: bool = False
    is_emergency: bool = False


@router.post("/announcements/create")
async def create_announcement(data: AnnouncementData, request: Request, db: AsyncSession = Depends(get_db)):
    user = await verify_school_admin(request)
    branch_id = get_branch_id(user)

    ann = Announcement(
        branch_id=branch_id, title=data.title, content=data.content,
        priority=AnnouncementPriority(data.priority),
        target_role=data.target_role,
        target_class_id=uuid.UUID(data.target_class_id) if data.target_class_id else None,
        is_pinned=data.is_pinned, is_emergency=data.is_emergency,
        published_by=uuid.UUID(user["user_id"]),
    )
    db.add(ann)
    await db.flush()

    # Create in-app notifications for target users
    from models.user import User, UserRole as UR
    target_roles = []
    if data.target_role == "all":
        target_roles = [UR.SCHOOL_ADMIN, UR.TEACHER, UR.STUDENT]
    elif data.target_role == "teacher":
        target_roles = [UR.TEACHER]
    elif data.target_role == "student":
        target_roles = [UR.STUDENT]

    if target_roles:
        users_q = select(User).where(User.branch_id == branch_id, User.role.in_(target_roles), User.is_active == True)

        # If targeting specific class/section, filter student/parent users
        if data.target_class_id and data.target_role in ("student", "parent"):
            from models.student import Student as StudentModel
            stu_q = select(StudentModel.user_id).where(
                StudentModel.branch_id == branch_id, StudentModel.is_active == True,
                StudentModel.class_id == uuid.UUID(data.target_class_id)
            )
            if data.target_section_id:
                stu_q = stu_q.where(StudentModel.section_id == uuid.UUID(data.target_section_id))
            student_user_ids = [r[0] for r in (await db.execute(stu_q)).all()]
            if student_user_ids:
                users_q = users_q.where(User.id.in_(student_user_ids))
            else:
                users_q = users_q.where(User.id == None)  # No students match

        target_users = (await db.execute(users_q)).scalars().all()
        notif_action = "/student/announcements"
        for u in target_users:
            if u.role == UR.SCHOOL_ADMIN:
                notif_action = "/school/announcements"
            elif u.role == UR.TEACHER:
                notif_action = "/teacher/dashboard"
            notif = Notification(
                branch_id=branch_id, user_id=u.id,
                type=NotificationType.ANNOUNCEMENT,
                title=data.title, message=data.content[:200],
                priority=data.priority,
                action_url=notif_action,
                action_label="View",
            )
            db.add(notif)

    await db.commit()
    count = len(target_users) if target_roles else 0
    icon = "🚨" if data.is_emergency else ("📌" if data.is_pinned else "📢")
    target_label = data.target_role
    if data.target_class_id:
        target_label += " (filtered by class/section)"
    return {"success": True, "message": f"{icon} Announcement sent to {count} {target_label}!"}


@router.get("/announcements/list")
async def list_announcements(request: Request, db: AsyncSession = Depends(get_db)):
    user = await verify_school_admin(request)
    branch_id = get_branch_id(user)
    result = await db.execute(
        select(Announcement).where(Announcement.branch_id == branch_id, Announcement.is_active == True)
        .order_by(Announcement.is_pinned.desc(), Announcement.created_at.desc()).limit(50))
    anns = result.scalars().all()
    return {"announcements": [
        {"id": str(a.id), "title": a.title, "content": a.content,
         "priority": a.priority.value if a.priority else "normal",
         "target": a.target_role or "all",
         "pinned": a.is_pinned, "emergency": a.is_emergency,
         "date": a.created_at.strftime("%d %b %Y, %I:%M %p") if a.created_at else ""}
        for a in anns
    ]}


@router.delete("/announcements/{ann_id}")
async def delete_announcement(ann_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    user = await verify_school_admin(request)
    result = await db.execute(select(Announcement).where(Announcement.id == uuid.UUID(ann_id)))
    ann = result.scalar_one_or_none()
    if ann:
        ann.is_active = False
        await db.commit()
    return {"success": True}


@router.post("/announcements/{ann_id}/pin")
async def toggle_pin(ann_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    user = await verify_school_admin(request)
    result = await db.execute(select(Announcement).where(Announcement.id == uuid.UUID(ann_id)))
    ann = result.scalar_one_or_none()
    if ann:
        ann.is_pinned = not ann.is_pinned
        await db.commit()
    return {"success": True, "pinned": ann.is_pinned if ann else False}


# ─── NOTIFICATIONS ─────────────────────────────────────────
@router.get("/notifications/list")
async def list_notifications(request: Request, unread_only: bool = False, db: AsyncSession = Depends(get_db)):
    user = await verify_school_admin(request)
    branch_id = get_branch_id(user)
    user_id = uuid.UUID(user["user_id"])
    # TIER 3: Only show notifications addressed to THIS user
    # Even first_admin cannot see other people's notifications
    q = select(Notification).where(
        Notification.branch_id == branch_id,
        (Notification.user_id == user_id) | (Notification.user_id == None)
    )
    if unread_only:
        q = q.where(Notification.is_read == False)
    result = await db.execute(q.order_by(Notification.created_at.desc()).limit(50))
    notifs = result.scalars().all()
    
    # TIER 2: Filter out sensitive notification types if user lacks privilege
    user_privs = user.get("privileges", {}) or {}
    is_first = user.get("is_first_admin", False)
    filtered = []
    for n in notifs:
        ntype = getattr(n, 'notification_type', None) or ''
        # Complaints — only if user has complaints privilege or is first admin
        if ntype == 'complaint' and not is_first and not user_privs.get('complaints'):
            continue
        # Salary related — only if user has salary_payroll privilege
        if ntype == 'salary' and not is_first and not user_privs.get('salary_payroll'):
            continue
        filtered.append(n)
    
    return {"notifications": [
        {"id": str(n.id), "type": n.type.value, "title": n.title, "message": n.message,
         "priority": n.priority or "normal",
         "action_url": n.action_url, "action_label": n.action_label,
         "is_read": n.is_read,
         "time": n.created_at.strftime("%d %b, %I:%M %p") if n.created_at else ""}
        for n in filtered
    ], "unread_count": sum(1 for n in filtered if not n.is_read)}


@router.post("/notifications/mark-read")
async def mark_notifications_read(request: Request, notification_id: str = "",
                                   db: AsyncSession = Depends(get_db)):
    user = await verify_school_admin(request)
    user_id = uuid.UUID(user["user_id"])
    if notification_id:
        result = await db.execute(select(Notification).where(Notification.id == uuid.UUID(notification_id)))
        n = result.scalar_one_or_none()
        if n:
            n.is_read = True
            from datetime import datetime
            n.read_at = datetime.utcnow()
    else:
        # Mark all read
        from datetime import datetime
        branch_id = get_branch_id(user)
        result = await db.execute(
            select(Notification).where(
                Notification.branch_id == branch_id,
                (Notification.user_id == user_id) | (Notification.user_id == None),
                Notification.is_read == False
            ))
        for n in result.scalars().all():
            n.is_read = True
            n.read_at = datetime.utcnow()
    await db.commit()
    return {"success": True}


@router.get("/notifications/unread-count")
async def unread_count(request: Request, db: AsyncSession = Depends(get_db)):
    try:
        user = await get_current_user(request)
        if not user or not user.get("branch_id"):
            return {"count": 0}
        branch_id = uuid.UUID(user["branch_id"])
        user_id = uuid.UUID(user["user_id"])
        count = await db.scalar(
            select(func.count(Notification.id)).where(
                Notification.branch_id == branch_id,
                (Notification.user_id == user_id) | (Notification.user_id == None),
                Notification.is_read == False
            ))
        return {"count": count or 0}
    except Exception:
        return {"count": 0}


# ─── COMMUNICATION SETTINGS ───────────────────────────────
class CommSettingsData(BaseModel):
    email_enabled: bool = False
    smtp_host: Optional[str] = None
    smtp_port: Optional[int] = None
    smtp_username: Optional[str] = None
    smtp_password: Optional[str] = None
    from_email: Optional[str] = None
    sms_enabled: bool = False
    sms_provider: Optional[str] = None
    sms_api_key: Optional[str] = None
    sms_sender_id: Optional[str] = None
    sms_route_id: Optional[str] = None
    whatsapp_enabled: bool = False
    whatsapp_api_token: Optional[str] = None
    whatsapp_phone_id: Optional[str] = None
    quiet_hours_enabled: bool = True
    quiet_start: str = "20:00"
    quiet_end: str = "07:00"
    allow_emergency_override: bool = True
    parent_teacher_chat_enabled: bool = False
    admin_moderated_messages: bool = True


@router.post("/communication-settings/save")
async def save_comm_settings(data: CommSettingsData, request: Request, db: AsyncSession = Depends(get_db)):
    user = await verify_school_admin(request)
    branch_id = get_branch_id(user)
    result = await db.execute(select(CommunicationConfig).where(CommunicationConfig.branch_id == branch_id))
    config = result.scalar_one_or_none()
    if not config:
        config = CommunicationConfig(branch_id=branch_id)
        db.add(config)
    for field, value in data.dict().items():
        if hasattr(config, field):
            if field.endswith('_password') or field.endswith('_key') or field.endswith('_token'):
                if value is not None and str(value).strip():
                    setattr(config, field, value)
            else:
                setattr(config, field, value)
    await db.commit()
    return {"success": True, "message": "Communication settings saved! ✅"}


@router.get("/communication-settings/load")
async def load_comm_settings(request: Request, db: AsyncSession = Depends(get_db)):
    user = await verify_school_admin(request)
    branch_id = get_branch_id(user)
    result = await db.execute(select(CommunicationConfig).where(CommunicationConfig.branch_id == branch_id))
    config = result.scalar_one_or_none()
    if not config:
        return {"config": None}
    return {"config": {
        "email_enabled": config.email_enabled, "smtp_host": config.smtp_host or "",
        "smtp_port": config.smtp_port or 587, "smtp_username": config.smtp_username or "",
        "from_email": config.from_email or "",
        "sms_enabled": config.sms_enabled, "sms_provider": config.sms_provider or "",
        "sms_api_key": config.sms_api_key or "",
        "sms_sender_id": config.sms_sender_id or "",
        "sms_route_id": getattr(config, 'sms_route_id', '') or "8",
        "whatsapp_enabled": config.whatsapp_enabled,
        "whatsapp_phone_id": config.whatsapp_phone_id or "",
        "quiet_hours_enabled": config.quiet_hours_enabled,
        "quiet_start": config.quiet_start or "20:00", "quiet_end": config.quiet_end or "07:00",
        "allow_emergency_override": config.allow_emergency_override,
        "parent_teacher_chat_enabled": config.parent_teacher_chat_enabled,
        "admin_moderated_messages": config.admin_moderated_messages,
    }}


# ─── PDF & EXPORT APIs ────────────────────────────────────
from fastapi.responses import StreamingResponse
from io import BytesIO
import csv

@router.get("/fees/receipt-pdf/{record_id}")
async def download_fee_receipt(record_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    user = await verify_school_admin(request)
    branch_id = get_branch_id(user)
    from utils.pdf_generator import generate_fee_receipt_pdf
    from models.branch import Branch, PaymentGatewayConfig as PGC

    rec = (await db.execute(
        select(FeeRecord).where(FeeRecord.id == uuid.UUID(record_id))
        .options(selectinload(FeeRecord.fee_structure), selectinload(FeeRecord.student))
    )).scalar_one_or_none()
    if not rec:
        raise HTTPException(404, "Fee record not found")

    student = rec.student
    branch = (await db.execute(select(Branch).where(Branch.id == branch_id))).scalar_one_or_none()
    school_name = branch.name if branch else "School"

    # Payment gateway for UPI/bank on receipt
    pgc = (await db.execute(select(PGC).where(PGC.branch_id == branch_id))).scalar_one_or_none()

    receipt_data = {
        "receipt_number": rec.receipt_number or "N/A",
        "date": rec.payment_date.strftime('%d %b %Y') if rec.payment_date else "",
        "student_name": student.full_name if student else "",
        "class_name": "",
        "roll_number": student.roll_number or "" if student else "",
        "admission_number": student.admission_number or "" if student else "",
        "student_login_id": student.student_login_id or "" if student else "",
        "father_name": student.father_name or "" if student else "",
        "fee_name": rec.fee_structure.fee_name if rec.fee_structure else "Fee",
        "amount_due": rec.amount_due, "amount_paid": rec.amount_paid,
        "discount": rec.discount, "balance": rec.amount_due - rec.amount_paid - rec.discount,
        "payment_mode": rec.payment_mode.value if rec.payment_mode else "cash",
        "transaction_id": rec.transaction_id or "",
        "upi_id": pgc.upi_id if pgc and pgc.show_upi_on_invoice else None,
        "bank_details": f"{pgc.bank_name} | A/C: {pgc.account_number} | IFSC: {pgc.ifsc_code}" if pgc and pgc.show_bank_on_invoice and pgc.account_number else None,
        "principal_signature_url": branch.principal_signature_url if branch else None,
        "school_stamp_url": branch.school_stamp_url if branch else None,
    }

    pdf_bytes = generate_fee_receipt_pdf(school_name, receipt_data)
    return StreamingResponse(
        BytesIO(pdf_bytes), media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=receipt_{rec.receipt_number or 'fee'}.pdf"}
    )


@router.get("/results/report-card-pdf")
async def download_report_card(request: Request, student_id: str, exam_id: str = "",
                                db: AsyncSession = Depends(get_db)):
    user = await verify_school_admin(request)
    branch_id = get_branch_id(user)
    from utils.pdf_generator import generate_report_card_pdf
    from models.branch import Branch
    from models.exam import Exam, ExamSubject, Marks

    student = (await db.execute(
        select(Student).where(Student.id == uuid.UUID(student_id))
        .options(selectinload(Student.class_), selectinload(Student.section))
    )).scalar_one_or_none()
    if not student:
        raise HTTPException(404, "Student not found")

    branch = (await db.execute(select(Branch).where(Branch.id == branch_id))).scalar_one_or_none()
    school_name = branch.name if branch else "School"

    ay = (await db.execute(select(AcademicYear).where(AcademicYear.branch_id == branch_id, AcademicYear.is_current == True))).scalar_one_or_none()

    # Get exams
    if exam_id:
        exams = [(await db.execute(select(Exam).where(Exam.id == uuid.UUID(exam_id)))).scalar_one_or_none()]
        exams = [e for e in exams if e]
    else:
        exams = (await db.execute(
            select(Exam).where(Exam.branch_id == branch_id, Exam.is_published == True)
            .order_by(Exam.start_date)
        )).scalars().all()

    exam_results = []
    for exam in exams:
        subjects = (await db.execute(
            select(ExamSubject).where(ExamSubject.exam_id == exam.id, ExamSubject.class_id == student.class_id)
        )).scalars().all()
        if not subjects:
            continue

        marks_map = {}
        for es in subjects:
            m = (await db.execute(select(Marks).where(Marks.exam_subject_id == es.id, Marks.student_id == student.id))).scalar_one_or_none()
            if m:
                marks_map[es.id] = m

        subj_list = []
        total_obt = 0
        total_max = 0
        all_pass = True
        for es in subjects:
            m = marks_map.get(es.id)
            obt = m.marks_obtained if m and not m.is_absent else 0
            passed = obt >= es.passing_marks if m and not m.is_absent else False
            subj_name = await db.scalar(select(Subject.name).where(Subject.id == es.subject_id)) or "?"
            subj_list.append({
                "name": subj_name,
                "max": es.max_marks, "obtained": obt,
                "grade": m.grade if m else "", "passed": passed,
                "absent": m.is_absent if m else False,
            })
            total_obt += obt
            total_max += es.max_marks
            if m and not m.is_absent and not passed:
                all_pass = False

        exam_results.append({
            "exam_name": exam.name,
            "subjects": subj_list,
            "total": total_obt, "max": total_max,
            "pct": round((total_obt / total_max * 100) if total_max > 0 else 0),
            "passed": all_pass,
        })

    # Get class teacher signature
    from models.teacher import Teacher
    class_teacher_sig = None
    if student.section_id:
        from sqlalchemy import text as sql_text
        ct_id = await db.scalar(sql_text(
            "SELECT class_teacher_id FROM sections WHERE id = :sid"
        ), {"sid": str(student.section_id)})
        if ct_id:
            ct = (await db.execute(select(Teacher).where(
                Teacher.id == ct_id, Teacher.is_active == True))).scalar_one_or_none()
            if ct:
                class_teacher_sig = ct.signature_url

    student_data = {
        "name": student.full_name,
        "class_name": student.class_.name if student.class_ else "",
        "section": student.section.name if student.section else "",
        "roll": student.roll_number or "",
        "admission": student.admission_number or "",
        "student_login_id": student.student_login_id or "",
        "father_name": student.father_name or "",
        "academic_year": ay.label if ay else "",
        "principal_signature_url": branch.principal_signature_url if branch else None,
        "class_teacher_signature_url": class_teacher_sig,
    }

    pdf_bytes = generate_report_card_pdf(school_name, student_data, exam_results)
    return StreamingResponse(
        BytesIO(pdf_bytes), media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=report_card_{student.first_name}.pdf"}
    )


# ─── CSV EXPORTS ───────────────────────────────────────────
@router.get("/export/attendance-csv")
async def export_attendance_csv(request: Request, class_id: str, month: int, year: int,
                                 section_id: str = "", db: AsyncSession = Depends(get_db)):
    user = await verify_school_admin(request)
    branch_id = get_branch_id(user)
    from models.attendance import Attendance as SA
    from datetime import date

    # Get students
    sq = select(Student).where(Student.branch_id == branch_id, Student.class_id == uuid.UUID(class_id), Student.is_active == True)
    if section_id:
        sq = sq.where(Student.section_id == uuid.UUID(section_id))
    students = (await db.execute(sq.order_by(Student.roll_number, Student.first_name))).scalars().all()

    # Get attendance
    import calendar
    days_in_month = calendar.monthrange(year, month)[1]

    output = BytesIO()
    import io
    text_output = io.StringIO()
    writer = csv.writer(text_output)

    header = ['Roll', 'Student Name']
    for d in range(1, days_in_month + 1):
        header.append(str(d))
    header.extend(['Present', 'Absent', 'Late', '%'])
    writer.writerow(header)

    for s in students:
        att_result = await db.execute(
            select(SA).where(SA.student_id == s.id,
                             func.extract('month', SA.date) == month,
                             func.extract('year', SA.date) == year))
        att_map = {a.date.day: a.status for a in att_result.scalars().all()}

        row = [s.roll_number or '', s.full_name]
        present = absent = late = 0
        for d in range(1, days_in_month + 1):
            status = att_map.get(d, '')
            if status == 'present':
                row.append('P'); present += 1
            elif status == 'absent':
                row.append('A'); absent += 1
            elif status == 'late':
                row.append('L'); late += 1
            else:
                row.append('')
        total = present + absent + late
        pct = round((present / total * 100) if total > 0 else 0)
        row.extend([present, absent, late, f"{pct}%"])
        writer.writerow(row)

    csv_bytes = text_output.getvalue().encode('utf-8')
    return StreamingResponse(
        BytesIO(csv_bytes), media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=attendance_{month}_{year}.csv"}
    )


@router.get("/export/fees-csv")
async def export_fees_csv(request: Request, class_id: str = "", db: AsyncSession = Depends(get_db)):
    user = await verify_school_admin(request)
    branch_id = get_branch_id(user)

    q = select(FeeRecord).where(FeeRecord.branch_id == branch_id).options(
        selectinload(FeeRecord.student), selectinload(FeeRecord.fee_structure))
    records = (await db.execute(q.order_by(FeeRecord.due_date.desc()))).scalars().all()

    import io
    text_output = io.StringIO()
    writer = csv.writer(text_output)
    writer.writerow(['Student', 'Roll', 'Fee Type', 'Due Date', 'Amount Due', 'Paid', 'Discount', 'Balance', 'Status', 'Receipt', 'Payment Mode'])

    for r in records:
        writer.writerow([
            r.student.full_name if r.student else '',
            r.student.roll_number if r.student else '',
            r.fee_structure.fee_name if r.fee_structure else '',
            r.due_date.strftime('%d-%m-%Y') if r.due_date else '',
            r.amount_due, r.amount_paid, r.discount,
            r.amount_due - r.amount_paid - r.discount,
            r.status.value, r.receipt_number or '',
            r.payment_mode.value if r.payment_mode else '',
        ])

    csv_bytes = text_output.getvalue().encode('utf-8')
    return StreamingResponse(
        BytesIO(csv_bytes), media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=fee_records.csv"}
    )


@router.get("/export/results-csv")
async def export_results_csv(request: Request, exam_id: str, class_id: str,
                              section_id: str = "", db: AsyncSession = Depends(get_db)):
    user = await verify_school_admin(request)
    branch_id = get_branch_id(user)
    from models.exam import Exam, ExamSubject, Marks

    # Get subjects for exam+class
    subjects = (await db.execute(
        select(ExamSubject).where(ExamSubject.exam_id == uuid.UUID(exam_id), ExamSubject.class_id == uuid.UUID(class_id))
    )).scalars().all()

    # Get students
    sq = select(Student).where(Student.branch_id == branch_id, Student.class_id == uuid.UUID(class_id), Student.is_active == True)
    if section_id:
        sq = sq.where(Student.section_id == uuid.UUID(section_id))
    students = (await db.execute(sq.order_by(Student.roll_number))).scalars().all()

    import io
    text_output = io.StringIO()
    writer = csv.writer(text_output)

    header = ['Roll', 'Student']
    for es in subjects:
        sname = await db.scalar(select(Subject.name).where(Subject.id == es.subject_id)) or '?'
        header.append(sname)
    header.extend(['Total', '%', 'Result'])
    writer.writerow(header)

    for s in students:
        row = [s.roll_number or '', s.full_name]
        total_obt = 0
        total_max = 0
        all_pass = True
        for es in subjects:
            m = (await db.execute(select(Marks).where(Marks.exam_subject_id == es.id, Marks.student_id == s.id))).scalar_one_or_none()
            if m and not m.is_absent:
                row.append(m.marks_obtained)
                total_obt += m.marks_obtained
                if m.marks_obtained < es.passing_marks:
                    all_pass = False
            elif m and m.is_absent:
                row.append('AB')
                all_pass = False
            else:
                row.append('')
            total_max += es.max_marks
        pct = round((total_obt / total_max * 100) if total_max > 0 else 0)
        row.extend([total_obt, f"{pct}%", 'PASS' if all_pass else 'FAIL'])
        writer.writerow(row)

    csv_bytes = text_output.getvalue().encode('utf-8')
    return StreamingResponse(
        BytesIO(csv_bytes), media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=results.csv"}
    )


@router.get("/export/students-csv")
async def export_students_csv(request: Request, class_id: str = "", db: AsyncSession = Depends(get_db)):
    user = await verify_school_admin(request)
    branch_id = get_branch_id(user)

    q = select(Student).where(Student.branch_id == branch_id, Student.is_active == True)
    if class_id:
        q = q.where(Student.class_id == uuid.UUID(class_id))
    q = q.options(selectinload(Student.class_), selectinload(Student.section))
    students = (await db.execute(q.order_by(Student.first_name))).scalars().all()

    import io
    text_output = io.StringIO()
    writer = csv.writer(text_output)
    writer.writerow(['Name', 'Class', 'Section', 'Roll No', 'Admission No', 'DOB', 'Gender',
                      'Father Name', 'Father Phone', 'Mother Name', 'Mother Phone', 'Address', 'City'])

    for s in students:
        writer.writerow([
            s.full_name,
            s.class_.name if s.class_ else '',
            s.section.name if s.section else '',
            s.roll_number or '', s.admission_number or '',
            s.date_of_birth.strftime('%d-%m-%Y') if s.date_of_birth else '',
            s.gender or '',
            s.father_name or '', s.father_phone or '',
            s.mother_name or '', s.mother_phone or '',
            s.address or '', s.city or '',
        ])

    csv_bytes = text_output.getvalue().encode('utf-8')
    return StreamingResponse(
        BytesIO(csv_bytes), media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=students.csv"}
    )


# ─── SIGNATURE UPLOADS ────────────────────────────────────
from fastapi import UploadFile, File
import shutil, os

UPLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "static", "uploads", "signatures")
os.makedirs(UPLOAD_DIR, exist_ok=True)


@router.post("/upload-signature")
async def upload_signature(
    request: Request,
    file: UploadFile = File(...),
    target: str = "principal",  # principal | stamp | teacher
    teacher_id: str = "",
    db: AsyncSession = Depends(get_db)
):
    """Upload signature/stamp image (PNG/JPG, max 500KB)"""
    user = await verify_school_admin(request)
    branch_id = get_branch_id(user)

    # Validate
    if file.content_type not in ["image/png", "image/jpeg", "image/jpg"]:
        raise HTTPException(400, "Only PNG or JPG files allowed")
    contents = await file.read()
    if len(contents) > 512000:
        raise HTTPException(400, "File too large (max 500KB)")

    # Save file
    ext = "png" if "png" in file.content_type else "jpg"
    if target == "teacher" and teacher_id:
        filename = f"teacher_{teacher_id}.{ext}"
    elif target == "stamp":
        filename = f"stamp_{branch_id}.{ext}"
    else:
        filename = f"principal_{branch_id}.{ext}"

    filepath = os.path.join(UPLOAD_DIR, filename)
    with open(filepath, "wb") as f:
        f.write(contents)

    url = f"/static/uploads/signatures/{filename}"

    # Update DB
    if target == "principal":
        from models.branch import Branch
        branch = (await db.execute(select(Branch).where(Branch.id == branch_id))).scalar_one_or_none()
        if branch:
            branch.principal_signature_url = url
            await db.commit()
    elif target == "stamp":
        from models.branch import Branch
        branch = (await db.execute(select(Branch).where(Branch.id == branch_id))).scalar_one_or_none()
        if branch:
            branch.school_stamp_url = url
            await db.commit()
    elif target == "teacher" and teacher_id:
        from models.teacher import Teacher
        teacher = (await db.execute(select(Teacher).where(Teacher.id == uuid.UUID(teacher_id)))).scalar_one_or_none()
        if teacher:
            teacher.signature_url = url
            await db.commit()

    return {"url": url, "message": "Signature uploaded successfully"}


@router.get("/signatures/info")
async def get_signatures_info(request: Request, db: AsyncSession = Depends(get_db)):
    user = await verify_school_admin(request)
    branch_id = get_branch_id(user)
    from models.branch import Branch
    from models.teacher import Teacher

    branch = (await db.execute(select(Branch).where(Branch.id == branch_id))).scalar_one_or_none()
    teachers = (await db.execute(
        select(Teacher).where(Teacher.branch_id == branch_id, Teacher.is_active == True, Teacher.is_class_teacher == True)
    )).scalars().all()

    return {
        "principal_name": branch.principal_name if branch else "",
        "principal_signature": branch.principal_signature_url if branch else None,
        "school_stamp": branch.school_stamp_url if branch else None,
        "class_teachers": [
            {"id": str(t.id), "name": t.full_name, "signature": t.signature_url}
            for t in teachers
        ],
    }


# ═══════════════════════════════════════════════════════════
# TIMEZONE & GENERAL SETTINGS
# ═══════════════════════════════════════════════════════════
from models.branch import BranchSettings


@router.get("/settings/timezone")
async def get_timezone(request: Request, db: AsyncSession = Depends(get_db)):
    user = await get_current_user(request)
    if not user: return {"error": "unauthorized"}
    branch_id = uuid.UUID(user["branch_id"])
    settings = (await db.execute(
        select(BranchSettings).where(BranchSettings.branch_id == branch_id)
    )).scalar_one_or_none()
    from utils.timezone import TIMEZONE_LABELS
    return {
        "current_timezone": settings.timezone if settings else "Asia/Kolkata",
        "available_timezones": [{"value": k, "label": v} for k, v in TIMEZONE_LABELS.items()],
    }


@router.post("/settings/timezone")
async def set_timezone(request: Request, db: AsyncSession = Depends(get_db)):
    user = await get_current_user(request)
    if not user: return {"error": "unauthorized"}
    branch_id = uuid.UUID(user["branch_id"])
    data = await request.json()
    tz = data.get("timezone", "Asia/Kolkata")
    settings = (await db.execute(
        select(BranchSettings).where(BranchSettings.branch_id == branch_id)
    )).scalar_one_or_none()
    if settings:
        settings.timezone = tz
    else:
        settings = BranchSettings(branch_id=branch_id, timezone=tz)
        db.add(settings)
    await db.commit()
    return {"status": "saved", "timezone": tz}


# ─── SCHOOL TIMING SETTINGS ────────────────────────────────

@router.get("/settings/school-timing")
async def get_school_timing(request: Request, db: AsyncSession = Depends(get_db)):
    """Load current school timing from BranchSettings.custom_data"""
    user = await get_current_user(request)
    if not user:
        return {"error": "unauthorized"}
    branch_id = uuid.UUID(user["branch_id"])
    from models.branch import BranchSettings
    from utils.timezone import TIMEZONE_LABELS
    settings = await db.scalar(select(BranchSettings).where(BranchSettings.branch_id == branch_id))

    timing = {}
    timezone_name = "Asia/Kolkata"
    if settings:
        timing = (settings.custom_data or {}).get("school_timing", {})
        timezone_name = settings.timezone or "Asia/Kolkata"

    # Defaults
    defaults = {
        "school_start_time": "07:30",
        "school_end_time": "14:30",
        "gate_open_time": "07:00",
        "late_grace_minutes": 15,
        "half_day_end_time": "12:00",
        "lunch_start_time": "12:30",
        "lunch_end_time": "13:00",
        "saturday_enabled": True,
        "saturday_start_time": "07:30",
        "saturday_end_time": "12:00",
        "effective_from": None,
        "last_changed_at": None,
        "last_changed_by": None,
    }
    for k, v in defaults.items():
        if k not in timing:
            timing[k] = v

    return {
        "timing": timing,
        "timezone": timezone_name,
        "timezone_label": TIMEZONE_LABELS.get(timezone_name, timezone_name),
    }


@router.post("/settings/school-timing")
async def save_school_timing(request: Request, db: AsyncSession = Depends(get_db)):
    """Save school timing. If timing changed + effective_from set, notify all users."""
    user = await verify_school_admin(request)
    branch_id = get_branch_id(user)
    data = await request.json()

    from models.branch import BranchSettings
    from sqlalchemy.orm.attributes import flag_modified
    from datetime import datetime as dt

    settings = await db.scalar(select(BranchSettings).where(BranchSettings.branch_id == branch_id))
    if not settings:
        settings = BranchSettings(branch_id=branch_id)
        db.add(settings)
        await db.flush()

    old_timing = (settings.custom_data or {}).get("school_timing", {})

    new_timing = {
        "school_start_time": data.get("school_start_time", "07:30"),
        "school_end_time": data.get("school_end_time", "14:30"),
        "gate_open_time": data.get("gate_open_time", "07:00"),
        "late_grace_minutes": int(data.get("late_grace_minutes", 15)),
        "half_day_end_time": data.get("half_day_end_time", "12:00"),
        "lunch_start_time": data.get("lunch_start_time", "12:30"),
        "lunch_end_time": data.get("lunch_end_time", "13:00"),
        "saturday_enabled": bool(data.get("saturday_enabled", True)),
        "saturday_start_time": data.get("saturday_start_time", "07:30"),
        "saturday_end_time": data.get("saturday_end_time", "12:00"),
        "effective_from": data.get("effective_from"),
        "last_changed_at": dt.utcnow().isoformat(),
        "last_changed_by": user.get("user_id"),
    }

    # Detect if timing actually changed (ignore meta fields)
    timing_fields = ["school_start_time", "school_end_time", "gate_open_time",
                     "late_grace_minutes", "half_day_end_time",
                     "lunch_start_time", "lunch_end_time",
                     "saturday_enabled", "saturday_start_time", "saturday_end_time"]
    timing_changed = any(
        str(old_timing.get(f, "")) != str(new_timing.get(f, ""))
        for f in timing_fields
    )

    # Save to custom_data
    cd = settings.custom_data or {}
    cd["school_timing"] = new_timing
    settings.custom_data = cd
    flag_modified(settings, "custom_data")

    notification_count = 0

    # If timing changed AND effective_from is set, create announcement + notifications
    if timing_changed and new_timing.get("effective_from"):
        effective = new_timing["effective_from"]
        content = (
            f"School timings will change effective {effective}.\n\n"
            f"New Schedule:\n"
            f"Gate Opens: {new_timing['gate_open_time']}\n"
            f"School Starts: {new_timing['school_start_time']}\n"
            f"School Ends: {new_timing['school_end_time']}\n"
            f"Lunch: {new_timing['lunch_start_time']} - {new_timing['lunch_end_time']}\n"
            f"Late Grace: {new_timing['late_grace_minutes']} minutes\n"
        )
        if new_timing.get("saturday_enabled"):
            content += f"Saturday: {new_timing['saturday_start_time']} - {new_timing['saturday_end_time']}\n"
        else:
            content += "Saturday: Off\n"

        # Create announcement
        from models.notification import Announcement, AnnouncementPriority, Notification, NotificationType
        ann = Announcement(
            branch_id=branch_id,
            title="School Timing Change",
            content=content,
            priority=AnnouncementPriority.IMPORTANT,
            target_role="all",
            is_pinned=True,
            published_by=uuid.UUID(user["user_id"]),
        )
        db.add(ann)
        await db.flush()

        # Bulk create notifications for all users
        from models.user import User, UserRole as UR
        target_users = (await db.execute(
            select(User).where(
                User.branch_id == branch_id,
                User.role.in_([UR.SCHOOL_ADMIN, UR.TEACHER, UR.STUDENT, UR.PARENT]),
                User.is_active == True,
            )
        )).scalars().all()

        for u in target_users:
            notif = Notification(
                branch_id=branch_id, user_id=u.id,
                type=NotificationType.ANNOUNCEMENT,
                title="School Timing Change",
                message=content[:200],
                priority="important",
                action_url="/school/school-timing" if u.role == UR.SCHOOL_ADMIN else None,
                action_label="View Details",
            )
            db.add(notif)
        notification_count = len(target_users)

    await db.commit()

    msg = "School timing saved"
    if notification_count > 0:
        msg += f" and {notification_count} notifications sent"
    return {"success": True, "message": msg, "notifications_sent": notification_count, "timing_changed": timing_changed}


# ═══════════════════════════════════════════════════════════
# MORNING BRIEF — Rule-based insights (ZERO AI, pure SQL)
# ═══════════════════════════════════════════════════════════
from models.attendance import Attendance, AttendanceStatus
from models.teacher_attendance import TeacherAttendance, TeacherAttendanceStatus, LeaveRequest, LeaveStatus
from models.fee import FeeRecord
from models.student import Student
from models.teacher import Teacher
from models.academic import Class


@router.get("/morning-brief")
async def morning_brief(request: Request, db: AsyncSession = Depends(get_db)):
    """Principal's daily intelligence brief — pure rule-based, zero AI cost."""
    user = await get_current_user(request)
    if not user:
        return {"error": "unauthorized"}
    branch_id = uuid.UUID(user["branch_id"])
    today = date.today()
    weekday = today.weekday()  # 0=Mon
    week_ago = today - timedelta(days=7)
    two_weeks_ago = today - timedelta(days=14)
    month_start = today.replace(day=1)

    actions = []
    predictions = []
    wins = []

    # ── 1. STUDENT ATTENDANCE TODAY ──
    total_students = await db.scalar(
        select(func.count(Student.id)).where(Student.branch_id == branch_id, Student.is_active == True)
    ) or 0
    att_today_count = await db.scalar(
        select(func.count(Attendance.id)).where(
            Attendance.date == today, Attendance.class_id.in_(
                select(Class.id).where(Class.branch_id == branch_id)
            ), Attendance.status == AttendanceStatus.PRESENT
        )
    ) or 0
    att_today_pct = round(att_today_count / total_students * 100) if total_students > 0 else 0

    # Compare with last week same day
    last_week_day = today - timedelta(days=7)
    att_last_week = await db.scalar(
        select(func.count(Attendance.id)).where(
            Attendance.date == last_week_day, Attendance.class_id.in_(
                select(Class.id).where(Class.branch_id == branch_id)
            ), Attendance.status == AttendanceStatus.PRESENT
        )
    ) or 0
    att_lw_pct = round(att_last_week / total_students * 100) if total_students > 0 else 0
    att_delta = att_today_pct - att_lw_pct

    # ── 2. TEACHER ATTENDANCE ──
    total_teachers = await db.scalar(
        select(func.count(Teacher.id)).where(Teacher.branch_id == branch_id, Teacher.is_active == True)
    ) or 0
    teachers_present = await db.scalar(
        select(func.count(TeacherAttendance.id)).where(
            TeacherAttendance.branch_id == branch_id,
            TeacherAttendance.date == today,
            TeacherAttendance.status == TeacherAttendanceStatus.PRESENT,
        )
    ) or 0
    teachers_absent = total_teachers - teachers_present

    # ── 3. FEE COLLECTION ──
    fee_due_month = await db.scalar(
        select(func.sum(FeeRecord.amount_due)).where(
            FeeRecord.branch_id == branch_id,
            FeeRecord.due_date >= month_start, FeeRecord.due_date <= today
        )
    ) or 0
    fee_paid_month = await db.scalar(
        select(func.sum(FeeRecord.amount_paid)).where(
            FeeRecord.branch_id == branch_id,
            FeeRecord.due_date >= month_start, FeeRecord.due_date <= today
        )
    ) or 0
    fee_pct = round(fee_paid_month / fee_due_month * 100) if fee_due_month > 0 else 0

    # ── 4. PENDING LEAVES ──
    pending_leaves = await db.scalar(
        select(func.count(LeaveRequest.id)).where(
            LeaveRequest.branch_id == branch_id,
            LeaveRequest.status == LeaveStatus.PENDING,
        )
    ) or 0

    # ── 5. OVERDUE FEES (students) ──
    overdue_count = await db.scalar(
        select(func.count(FeeRecord.id)).where(
            FeeRecord.branch_id == branch_id,
            FeeRecord.due_date < today,
            FeeRecord.amount_paid < FeeRecord.amount_due,
        )
    ) or 0
    overdue_amount = await db.scalar(
        select(func.sum(FeeRecord.amount_due - FeeRecord.amount_paid)).where(
            FeeRecord.branch_id == branch_id,
            FeeRecord.due_date < today,
            FeeRecord.amount_paid < FeeRecord.amount_due,
        )
    ) or 0

    # ══ CALCULATE SCHOOL PULSE (weighted score 0-100) ══
    pulse = 0
    if total_students > 0:
        pulse += min(att_today_pct, 100) * 0.3          # 30% weight: student attendance
    pulse += min(teachers_present / max(total_teachers, 1) * 100, 100) * 0.25  # 25%: teacher attendance
    pulse += min(fee_pct, 100) * 0.25                    # 25%: fee collection
    pulse += max(0, 100 - pending_leaves * 10) * 0.1     # 10%: pending leaves
    pulse += max(0, 100 - overdue_count * 2) * 0.1       # 10%: overdue fees
    pulse = round(min(pulse, 100))

    # ══ GENERATE RULE-BASED ACTIONS ══

    # Rule 1: Low attendance today
    if att_today_pct < 70 and total_students > 0:
        # Find which class has lowest attendance
        class_atts = (await db.execute(
            select(Attendance.class_id, func.count(Attendance.id))
            .where(Attendance.date == today, Attendance.status == AttendanceStatus.PRESENT,
                   Attendance.class_id.in_(select(Class.id).where(Class.branch_id == branch_id)))
            .group_by(Attendance.class_id)
        )).all()
        worst_class = None
        if class_atts:
            class_totals = {}
            for ca in class_atts:
                tc = await db.scalar(select(func.count(Student.id)).where(
                    Student.class_id == ca[0], Student.is_active == True))
                class_totals[ca[0]] = round(ca[1] / tc * 100) if tc > 0 else 0
            if class_totals:
                worst_cid = min(class_totals, key=class_totals.get)
                worst_cls = await db.scalar(select(Class.name).where(Class.id == worst_cid))
                worst_class = f"<strong>{worst_cls}</strong> has lowest at {class_totals[worst_cid]}%"

        why = f"Only <strong>{att_today_pct}%</strong> students present today (vs {att_lw_pct}% last {today.strftime('%A')})."
        if worst_class:
            why += f" {worst_class}."
        if weekday == 0 or weekday == 4:
            why += " Monday/Friday tend to have lower attendance."
        actions.append({"level": "urgent", "icon": "📉", "title": f"Student attendance critically low: {att_today_pct}%",
                        "why": why, "link": "/school/attendance", "link_text": "View Attendance →"})
    elif att_today_pct < 85 and total_students > 0:
        actions.append({"level": "warning", "icon": "⚠️", "title": f"Attendance below target: {att_today_pct}%",
                        "why": f"Target is 85%. Today: {att_today_pct}%. Last {today.strftime('%A')}: {att_lw_pct}%.",
                        "link": "/school/attendance", "link_text": "View Details →"})

    # Rule 2: Teachers absent
    if teachers_absent >= 3:
        actions.append({"level": "urgent", "icon": "🧑‍🏫", "title": f"{teachers_absent} teachers absent today",
                        "why": f"Only {teachers_present}/{total_teachers} teachers checked in. Substitute arrangements may be needed.",
                        "link": "/school/teacher-attendance", "link_text": "View Teacher Attendance →"})
    elif teachers_absent >= 1:
        actions.append({"level": "warning", "icon": "🧑‍🏫", "title": f"{teachers_absent} teacher(s) absent",
                        "why": f"{teachers_present}/{total_teachers} present. Check if substitutes are assigned.",
                        "link": "/school/teacher-attendance", "link_text": "View →"})

    # Rule 3: Pending leave approvals
    if pending_leaves >= 3:
        actions.append({"level": "warning", "icon": "📋", "title": f"{pending_leaves} leave requests waiting",
                        "why": "Delayed approvals affect teacher morale. Try to respond within 24 hours.",
                        "link": "/school/leave-management", "link_text": "Review Leaves →"})

    # Rule 4: Fee collection below target
    if fee_pct < 50 and today.day > 15:
        actions.append({"level": "urgent", "icon": "💰", "title": f"Fee collection at {fee_pct}% — below target",
                        "why": f"Only ₹{fee_paid_month:,.0f} collected out of ₹{fee_due_month:,.0f} due this month. Past mid-month, <strong>50%</strong> should be collected.",
                        "link": "/school/fee-collection", "link_text": "Send Reminders →"})

    # Rule 5: Overdue fees
    if overdue_count > 10:
        actions.append({"level": "warning", "icon": "🔴", "title": f"{overdue_count} students have overdue fees",
                        "why": f"Total overdue: <strong>₹{overdue_amount:,.0f}</strong>. Consider sending SMS reminders to parents.",
                        "link": "/school/fee-collection", "link_text": "View Overdue →"})

    # Rule 6: Attendance drop pattern
    if att_delta < -10:
        actions.append({"level": "warning", "icon": "📊", "title": f"Attendance dropped {abs(att_delta)}% vs last week",
                        "why": f"Was {att_lw_pct}% last {today.strftime('%A')}, now {att_today_pct}%. Check for seasonal illness or local event.",
                        "link": "/school/attendance-reports", "link_text": "Analyze →"})

    # ══ RULE-BASED PREDICTIONS ══

    # Prediction 1: Friday/Monday attendance drop
    if weekday == 3:  # Thursday
        predictions.append({"timeframe": "Tomorrow (Friday)",
                            "prediction": "Expect 5-10% lower attendance — Fridays historically have lower turnout.",
                            "reason": f"Your average {today.strftime('%A')} attendance is {att_today_pct}%. Fridays typically drop."})

    # Prediction 2: Fee crunch approaching
    if today.day >= 20 and fee_pct < 70:
        gap = fee_due_month - fee_paid_month
        predictions.append({"timeframe": "End of Month",
                            "prediction": f"₹{gap:,.0f} fee gap likely to carry over to next month.",
                            "reason": f"Only {fee_pct}% collected with {30-today.day} days left. Historical pattern shows last-week collections drop."})

    # Prediction 3: Teacher shortage
    if teachers_absent >= 2:
        predictions.append({"timeframe": "This Week",
                            "prediction": f"Possible substitution crisis — {teachers_absent} teachers out today.",
                            "reason": "Multiple absences on same day strain substitute pool. Check if any have extended leave pending."})

    # Prediction 4: Overdue fee escalation
    if overdue_count > 20:
        predictions.append({"timeframe": "Next 2 Weeks",
                            "prediction": f"Overdue count ({overdue_count}) may trigger parent complaints if left unaddressed.",
                            "reason": "Schools that delay follow-ups beyond 3 weeks see 40% lower recovery rates."})

    # ══ WINS (positive patterns) ══
    if att_today_pct >= 90:
        wins.append({"title": "🎯 Excellent attendance today!", "why": f"{att_today_pct}% students present — above 90% target."})
    if att_delta > 5 and att_delta > 0:
        wins.append({"title": "📈 Attendance improving!", "why": f"Up {att_delta}% compared to last {today.strftime('%A')}."})
    if fee_pct >= 80:
        wins.append({"title": "💰 Strong fee collection!", "why": f"{fee_pct}% of monthly target achieved."})
    if pending_leaves == 0:
        wins.append({"title": "✅ All leaves reviewed!", "why": "No pending leave requests. Great responsiveness."})
    if teachers_absent == 0 and total_teachers > 0:
        wins.append({"title": "🧑‍🏫 Full teacher strength!", "why": f"All {total_teachers} teachers present today."})

    return {
        "pulse": pulse,
        "att_today": att_today_pct,
        "att_delta": att_delta,
        "teachers_present": teachers_present,
        "teachers_total": total_teachers,
        "teachers_absent": teachers_absent,
        "fee_collected_month": fee_paid_month,
        "fee_pct": fee_pct,
        "pending_leaves": pending_leaves,
        "overdue_count": overdue_count,
        "actions": actions,
        "predictions": predictions,
        "wins": wins,
    }


# ═══════════════════════════════════════════════════════════
# BOARD RESULTS
# ═══════════════════════════════════════════════════════════
from models.mega_modules import BoardResult, TeacherAward
from models.activity import Activity, StudentActivity as ActivityParticipant


@router.get("/board-results")
async def get_board_results(request: Request, db: AsyncSession = Depends(get_db)):
    user = await get_current_user(request)
    if not user: return {"error": "unauthorized"}
    branch_id = uuid.UUID(user["branch_id"])
    results = (await db.execute(
        select(BoardResult).where(BoardResult.branch_id == branch_id).order_by(BoardResult.percentage.desc())
    )).scalars().all()
    items = [{"id": str(r.id), "student_name": r.student_name, "roll_number": r.roll_number, "class_level": r.class_level,
              "percentage": r.percentage, "grade": r.grade, "result_status": r.result_status, "board": r.board,
              "academic_year": r.academic_year, "total_marks": r.total_marks, "max_marks": r.max_marks} for r in results]
    total = len(items)
    passed = sum(1 for r in items if r["result_status"] == "pass")
    failed = sum(1 for r in items if r["result_status"] == "fail")
    distinction = sum(1 for r in items if (r["percentage"] or 0) >= 90)
    first_div = sum(1 for r in items if 75 <= (r["percentage"] or 0) < 90)
    avg_pct = round(sum(r["percentage"] or 0 for r in items) / total, 1) if total > 0 else 0
    return {"results": items, "summary": {"total": total, "pass_pct": round(passed / total * 100) if total > 0 else 0,
            "distinction": distinction, "first_div": first_div, "avg_pct": avg_pct, "fail": failed}}


@router.post("/board-results")
async def save_board_results(request: Request, db: AsyncSession = Depends(get_db)):
    user = await get_current_user(request)
    if not user: return {"error": "unauthorized"}
    branch_id = uuid.UUID(user["branch_id"])
    data = await request.json()
    saved = 0
    for e in data.get("entries", []):
        pct = round(e["total_marks"] / e["max_marks"] * 100, 1) if e["max_marks"] > 0 else 0
        # Get student name
        student = await db.scalar(select(Student).where(Student.id == uuid.UUID(e["student_id"])))
        name = student.full_name if student else "Unknown"
        roll = student.roll_number if student else ""
        br = BoardResult(branch_id=branch_id, academic_year=data["academic_year"], board=data["board"],
                         class_level=data["class_level"], student_id=uuid.UUID(e["student_id"]), student_name=name,
                         roll_number=str(roll), total_marks=e["total_marks"], max_marks=e["max_marks"],
                         percentage=pct, grade=e.get("grade",""), result_status=e.get("result_status","pass"),
                         is_distinction=pct >= 90)
        db.add(br)
        saved += 1
    await db.commit()
    return {"status": "saved", "count": saved}


@router.post("/board-results/import")
async def import_board_results(request: Request, db: AsyncSession = Depends(get_db)):
    """Import board results from CSV — uses name/roll directly (no student_id matching needed)."""
    user = await get_current_user(request)
    if not user: return {"error": "unauthorized"}
    branch_id = uuid.UUID(user["branch_id"])
    data = await request.json()
    saved = 0
    for e in data.get("entries", []):
        total = e.get("total_marks", 0)
        max_m = e.get("max_marks", 500)
        pct = round(total / max_m * 100, 1) if max_m > 0 else 0
        name = e.get("student_name_override", "Unknown")
        roll = e.get("roll_override", "")
        # Try to match student by name/roll
        student_id = None
        if roll:
            student = await db.scalar(select(Student).where(
                Student.branch_id == branch_id, Student.roll_number == str(roll), Student.is_active == True))
            if student: student_id = student.id; name = student.full_name
        br = BoardResult(branch_id=branch_id, academic_year=data["academic_year"], board=data["board"],
                         class_level=data["class_level"], student_id=student_id, student_name=name,
                         roll_number=str(roll), total_marks=total, max_marks=max_m,
                         percentage=pct, grade=e.get("grade", ""), result_status=e.get("result_status", "pass"),
                         is_distinction=pct >= 90)
        db.add(br)
        saved += 1
    await db.commit()
    return {"status": "imported", "count": saved}


# ═══════════════════════════════════════════════════════════
# ACTIVITIES & SPORTS
# ═══════════════════════════════════════════════════════════

@router.get("/activities")
async def get_activities(request: Request, db: AsyncSession = Depends(get_db)):
    user = await get_current_user(request)
    if not user: return {"error": "unauthorized"}
    branch_id = uuid.UUID(user["branch_id"])
    acts = (await db.execute(select(Activity).where(Activity.branch_id == branch_id).order_by(Activity.event_date.desc()))).scalars().all()
    items = []
    for a in acts:
        count = await db.scalar(select(func.count(ActivityParticipant.id)).where(ActivityParticipant.activity_id == a.id)) or 0
        items.append({"id": str(a.id), "title": a.title or a.name, "activity_type": a.activity_type, "category": a.category or "",
                       "event_date": a.event_date.isoformat() if a.event_date else "", "venue": a.venue or "",
                       "status": a.status, "participant_count": count, "max_participants": a.max_participants,
                       "target_audience": a.target_audience or [],
                       "published_at": a.published_at.strftime("%d %b %Y") if hasattr(a, 'published_at') and a.published_at else ""})
    return {"activities": items}


@router.post("/activities")
async def create_activity(request: Request, db: AsyncSession = Depends(get_db)):
    user = await get_current_user(request)
    if not user: return {"error": "unauthorized"}
    branch_id = uuid.UUID(user["branch_id"])
    data = await request.json()
    save_as = data.get("save_as", "draft")  # "draft" or "publish"
    act = Activity(branch_id=branch_id, name=data["title"], title=data["title"], activity_type=data["activity_type"],
                   category=data.get("category"), description=data.get("description"),
                   event_date=date.fromisoformat(data["event_date"]) if data.get("event_date") else None,
                   registration_deadline=date.fromisoformat(data["registration_deadline"]) if data.get("registration_deadline") else None,
                   venue=data.get("venue"), max_participants=data.get("max_participants"),
                   eligible_classes=data.get("eligible_classes"),
                   target_audience=data.get("target_audience"),
                   status="draft" if save_as == "draft" else "open",
                   created_by=uuid.UUID(user["user_id"]))
    if save_as != "draft":
        from datetime import datetime as dt
        act.published_at = dt.utcnow()
    db.add(act)
    await db.commit()
    # If publishing immediately, send notifications
    if save_as != "draft" and data.get("target_audience"):
        await _send_activity_notifications(db, act, branch_id, user)
    return {"status": "created", "id": str(act.id)}


@router.get("/activities/{activity_id}/participants")
async def get_participants(request: Request, activity_id: str, db: AsyncSession = Depends(get_db)):
    parts = (await db.execute(
        select(ActivityParticipant).where(ActivityParticipant.activity_id == uuid.UUID(activity_id))
    )).scalars().all()
    items = []
    for p in parts:
        student = await db.scalar(select(Student).where(Student.id == p.student_id))
        cls = await db.scalar(select(Class.name).where(Class.id == student.class_id)) if student else ""
        items.append({"id": str(p.id), "name": student.full_name if student else "?", "class_name": cls or "",
                       "position": p.position or "participant", "status": p.status})
    return {"participants": items}


@router.patch("/activities/{activity_id}/participants/{participant_id}")
async def update_participant(request: Request, activity_id: str, participant_id: str, db: AsyncSession = Depends(get_db)):
    data = await request.json()
    part = await db.scalar(select(ActivityParticipant).where(ActivityParticipant.id == uuid.UUID(participant_id)))
    if part:
        if "position" in data: part.position = data["position"]
        if "status" in data: part.status = data["status"]
        await db.commit()
    return {"status": "updated"}


@router.post("/activities/{activity_id}/publish")
async def publish_activity(request: Request, activity_id: str, db: AsyncSession = Depends(get_db)):
    """Publish a draft activity — sends notifications to target audience."""
    user = await verify_school_admin(request)
    branch_id = get_branch_id(user)
    from datetime import datetime as dt

    act = await db.scalar(select(Activity).where(Activity.id == uuid.UUID(activity_id)))
    if not act:
        raise HTTPException(404, "Activity not found")

    data = await request.json()
    target = data.get("target_audience", [])
    act.target_audience = target
    act.status = "open"
    act.published_at = dt.utcnow()
    await db.commit()

    # Send notifications
    if target:
        await _send_activity_notifications(db, act, branch_id, user)

    return {"status": "published", "message": f"'{act.title or act.name}' published and notifications sent"}


async def _send_activity_notifications(db, act, branch_id, user):
    """Send in-app notifications to selected target audience."""
    from models.notification import Notification, NotificationType
    from datetime import datetime as dt

    target = act.target_audience or []
    title = f"New Event: {act.title or act.name}"
    msg = f"{act.title or act.name}"
    if act.event_date:
        msg += f" on {act.event_date.strftime('%d %b %Y')}"
    if act.venue:
        msg += f" at {act.venue}"

    user_ids = set()

    if "all_students" in target:
        # Notify all students' user_ids
        from models.student import Student as St
        rows = (await db.execute(
            select(St.user_id).where(St.branch_id == branch_id, St.is_active == True, St.user_id.isnot(None))
        )).scalars().all()
        user_ids.update(rows)

    if "teachers" in target:
        from models.teacher import Teacher as Tc
        rows = (await db.execute(
            select(Tc.user_id).where(Tc.branch_id == branch_id, Tc.is_active == True, Tc.user_id.isnot(None))
        )).scalars().all()
        user_ids.update(rows)

    if "non_teaching_staff" in target:
        from models.mega_modules import Employee as Emp
        rows = (await db.execute(
            select(Emp.user_id).where(Emp.branch_id == branch_id, Emp.is_active == True, Emp.user_id.isnot(None))
        )).scalars().all()
        user_ids.update(rows)

    # Handle specific classes like "class_<id>"
    for t in target:
        if t.startswith("class_"):
            cls_id = t.replace("class_", "")
            try:
                from models.student import Student as St2
                rows = (await db.execute(
                    select(St2.user_id).where(
                        St2.branch_id == branch_id, St2.class_id == uuid.UUID(cls_id),
                        St2.is_active == True, St2.user_id.isnot(None)
                    )
                )).scalars().all()
                user_ids.update(rows)
            except Exception:
                pass

    # Create notifications
    for uid in user_ids:
        if uid:
            notif = Notification(
                user_id=uid, branch_id=branch_id,
                title=title, message=msg,
                notification_type=NotificationType.ALERT,
                action_url="/student/online-classes" if "student" in str(target) else None,
            )
            db.add(notif)

    try:
        await db.commit()
    except Exception:
        await db.rollback()


# ═══════════════════════════════════════════════════════════
# TEACHER AWARDS & LEADERBOARD
# ═══════════════════════════════════════════════════════════

@router.get("/teacher-awards/leaderboard")
async def teacher_leaderboard(request: Request, db: AsyncSession = Depends(get_db)):
    user = await get_current_user(request)
    if not user: return {"error": "unauthorized"}
    branch_id = uuid.UUID(user["branch_id"])
    today = date.today()
    month_start = today.replace(day=1)

    # Get all active teachers
    teachers = (await db.execute(
        select(Teacher).where(Teacher.branch_id == branch_id, Teacher.is_active == True)
    )).scalars().all()

    leaderboard = []
    for t in teachers:
        # Attendance score: % present this month
        total_days = await db.scalar(select(func.count(TeacherAttendance.id)).where(
            TeacherAttendance.teacher_id == t.id, TeacherAttendance.date >= month_start)) or 0
        present_days = await db.scalar(select(func.count(TeacherAttendance.id)).where(
            TeacherAttendance.teacher_id == t.id, TeacherAttendance.date >= month_start,
            TeacherAttendance.status == TeacherAttendanceStatus.PRESENT)) or 0
        att_score = round(present_days / total_days * 100) if total_days > 0 else 0

        # Performance score: syllabus completion (period logs)
        from models.period_log import PeriodLog
        periods_done = await db.scalar(select(func.count(PeriodLog.id)).where(
            PeriodLog.teacher_id == t.id, PeriodLog.completed_at >= month_start)) or 0
        perf_score = min(periods_done * 5, 100)  # 20 periods = 100%

        total_score = round(att_score * 0.5 + perf_score * 0.5)

        # Get subjects
        from models.academic import ClassSubject as CS2
        subs = (await db.execute(select(Subject.name).join(CS2, CS2.subject_id == Subject.id).where(CS2.teacher_id == t.id).distinct())).scalars().all()

        leaderboard.append({"id": str(t.id), "name": t.full_name, "subjects": ", ".join(subs) if subs else "—",
                             "attendance_score": att_score, "performance_score": perf_score, "total_score": total_score})

    leaderboard.sort(key=lambda x: x["total_score"], reverse=True)

    # Star of the month
    star = None
    star_award = (await db.execute(select(TeacherAward).where(
        TeacherAward.branch_id == branch_id, TeacherAward.status == "awarded",
        TeacherAward.month == today.month, TeacherAward.year == today.year
    ).order_by(TeacherAward.awarded_at.desc()))).scalars().first()
    if star_award:
        star = {"name": star_award.teacher.full_name, "title": star_award.title,
                "attendance": leaderboard[0]["attendance_score"] if leaderboard else 0,
                "periods": leaderboard[0]["performance_score"] if leaderboard else 0,
                "prize": star_award.prize_details}

    # Awards & nominations
    awards = (await db.execute(select(TeacherAward).where(
        TeacherAward.branch_id == branch_id, TeacherAward.status == "awarded"
    ).order_by(TeacherAward.awarded_at.desc()).limit(10))).scalars().all()
    nominations = (await db.execute(select(TeacherAward).where(
        TeacherAward.branch_id == branch_id, TeacherAward.status == "nominated"
    ).order_by(TeacherAward.created_at.desc()))).scalars().all()

    MONTHS = ['','January','February','March','April','May','June','July','August','September','October','November','December']
    return {
        "leaderboard": leaderboard[:20],
        "star_of_month": star,
        "awards": [{"id": str(a.id), "teacher_name": a.teacher.full_name, "title": a.title,
                     "month_label": MONTHS[a.month] if a.month else "", "year": a.year,
                     "prize_details": a.prize_details or ""} for a in awards],
        "nominations": [{"id": str(n.id), "teacher_name": n.teacher.full_name, "title": n.title,
                          "description": n.description or ""} for n in nominations],
        "teachers": [{"id": str(t.id), "name": t.full_name} for t in teachers],
    }


@router.post("/teacher-awards/nominate")
async def nominate_teacher(request: Request, db: AsyncSession = Depends(get_db)):
    user = await get_current_user(request)
    if not user: return {"error": "unauthorized"}
    branch_id = uuid.UUID(user["branch_id"])
    data = await request.json()
    today = date.today()
    TYPE_TITLES = {"star_of_month": "⭐ Star of the Month", "best_performance": "🎯 Best Performance",
                   "innovation": "💡 Innovation in Teaching", "punctuality": "⏰ Punctuality Award",
                   "parent_choice": "❤️ Parent's Choice"}
    award = TeacherAward(branch_id=branch_id, teacher_id=uuid.UUID(data["teacher_id"]),
                          award_type=data["award_type"], title=TYPE_TITLES.get(data["award_type"], data["award_type"]),
                          description=data.get("description"), month=today.month, year=today.year,
                          prize_details=data.get("prize_details"), nominated_by=uuid.UUID(user["user_id"]),
                          status="nominated")
    db.add(award)
    await db.commit()
    return {"status": "nominated", "id": str(award.id)}


@router.post("/teacher-awards/{award_id}/approve")
async def approve_award(request: Request, award_id: str, db: AsyncSession = Depends(get_db)):
    award = await db.scalar(select(TeacherAward).where(TeacherAward.id == uuid.UUID(award_id)))
    if award:
        award.status = "awarded"
        award.awarded_at = datetime.now(timezone.utc)
        await db.commit()
    return {"status": "approved"}


# ═══════════════════════════════════════════════════════════
# TEACHER HOVER CARD (global — used across all pages)
# ═══════════════════════════════════════════════════════════

@router.get("/teacher-hover/{teacher_id}")
async def teacher_hover_info(request: Request, teacher_id: str, db: AsyncSession = Depends(get_db)):
    """Quick teacher info for hover card — photo, phone, availability."""
    t = await db.scalar(select(Teacher).where(Teacher.id == uuid.UUID(teacher_id)))
    if not t:
        return {"name": "Unknown", "phone": "", "photo_url": "", "subjects": "", "is_present_today": False, "on_leave": False, "attendance_pct": 0}

    # Subjects
    subs = (await db.execute(
        select(Subject.name).join(ClassSubject, ClassSubject.subject_id == Subject.id)
        .where(ClassSubject.teacher_id == t.id).distinct()
    )).scalars().all()

    # Today's attendance
    today = date.today()
    att_today = await db.scalar(select(TeacherAttendance).where(
        TeacherAttendance.teacher_id == t.id, TeacherAttendance.date == today,
        TeacherAttendance.status == TeacherAttendanceStatus.PRESENT))
    is_present = att_today is not None

    # On leave?
    on_leave = await db.scalar(select(LeaveRequest).where(
        LeaveRequest.teacher_id == t.id, LeaveRequest.status == LeaveStatus.APPROVED,
        LeaveRequest.start_date <= today, LeaveRequest.end_date >= today))

    # Monthly attendance %
    month_start = today.replace(day=1)
    total = await db.scalar(select(func.count(TeacherAttendance.id)).where(
        TeacherAttendance.teacher_id == t.id, TeacherAttendance.date >= month_start)) or 0
    present = await db.scalar(select(func.count(TeacherAttendance.id)).where(
        TeacherAttendance.teacher_id == t.id, TeacherAttendance.date >= month_start,
        TeacherAttendance.status == TeacherAttendanceStatus.PRESENT)) or 0
    att_pct = round(present / total * 100) if total > 0 else 0

    return {
        "name": t.full_name,
        "phone": t.phone or "",
        "photo_url": t.photo_url or "",
        "subjects": ", ".join(subs) if subs else "",
        "is_present_today": is_present,
        "on_leave": on_leave is not None,
        "attendance_pct": att_pct,
    }


# ═══════════════════════════════════════════════════════════
# SPRINT 25 — STUDENT PROMOTION
# ═══════════════════════════════════════════════════════════

@router.post("/students/promote")
async def promote_students(request: Request, db: AsyncSession = Depends(get_db)):
    user = await get_current_user(request)
    if not user: return {"error": "unauthorized"}
    branch_id = uuid.UUID(user["branch_id"])
    data = await request.json()
    from models.mega_modules import StudentPromotion
    from models.student import AdmissionStatus
    promoted = detained = tc = left = 0
    for entry in data.get("students", []):
        student = await db.scalar(select(Student).where(Student.id == uuid.UUID(entry["student_id"])))
        if not student: continue
        # Skip students who already have TC or left
        if student.admission_status in (AdmissionStatus.TC_ISSUED, AdmissionStatus.LEFT, AdmissionStatus.WITHDRAWN):
            continue
        action = entry.get("action", "promoted")
        promo = StudentPromotion(
            branch_id=branch_id, student_id=student.id,
            from_class_id=student.class_id,
            to_class_id=uuid.UUID(data["to_class_id"]) if data.get("to_class_id") and action == "promoted" else None,
            from_section_id=student.section_id,
            to_section_id=uuid.UUID(data["to_section_id"]) if data.get("to_section_id") else student.section_id,
            academic_year_from=data["academic_year_from"], academic_year_to=data["academic_year_to"],
            action=action, remarks=entry.get("remarks", ""),
            promoted_by=uuid.UUID(user["user_id"])
        )
        db.add(promo)
        if action == "promoted" and data.get("to_class_id"):
            student.class_id = uuid.UUID(data["to_class_id"])
            if data.get("to_section_id"):
                student.section_id = uuid.UUID(data["to_section_id"])
            promoted += 1
        elif action == "detained":
            detained += 1  # stays in same class
        elif action == "tc_issued":
            student.is_active = False
            student.admission_status = AdmissionStatus.TC_ISSUED
            # Disable linked User account (student + parent logins)
            if student.user_id:
                linked_user = await db.scalar(select(User).where(User.id == student.user_id))
                if linked_user:
                    linked_user.is_active = False
            tc += 1
        elif action == "left":
            student.is_active = False
            student.admission_status = AdmissionStatus.LEFT
            # Disable linked User account (student + parent logins)
            if student.user_id:
                linked_user = await db.scalar(select(User).where(User.id == student.user_id))
                if linked_user:
                    linked_user.is_active = False
            left += 1
    await db.commit()
    return {"promoted": promoted, "detained": detained, "tc": tc, "left": left}


# ═══════════════════════════════════════════════════════════
# SPRINT 25 — ONLINE QUIZ
# ═══════════════════════════════════════════════════════════

@router.get("/quizzes")
async def get_quizzes(request: Request, db: AsyncSession = Depends(get_db)):
    user = await get_current_user(request)
    if not user: return {"quizzes": []}
    branch_id = uuid.UUID(user["branch_id"])
    from models.mega_modules import Quiz, QuizQuestion, QuizAttempt
    from sqlalchemy.orm import selectinload
    quizzes = (await db.execute(
        select(Quiz).where(Quiz.branch_id == branch_id)
        .options(selectinload(Quiz.questions))
        .order_by(Quiz.created_at.desc())
    )).scalars().all()
    items = []
    for q in quizzes:
        attempt_count = await db.scalar(select(func.count(QuizAttempt.id)).where(QuizAttempt.quiz_id == q.id)) or 0
        cls = await db.scalar(select(Class.name).where(Class.id == q.class_id)) if q.class_id else ""
        sub = await db.scalar(select(Subject.name).where(Subject.id == q.subject_id)) if q.subject_id else ""
        items.append({"id": str(q.id), "title": q.title, "class_name": cls or "", "subject_name": sub or "",
                       "time_limit_minutes": q.time_limit_minutes, "is_published": q.is_published,
                       "question_count": len(q.questions), "attempt_count": attempt_count})
    return {"quizzes": items}


@router.post("/quizzes")
async def create_quiz(request: Request, db: AsyncSession = Depends(get_db)):
    user = await get_current_user(request)
    if not user: return {"error": "unauthorized"}
    branch_id = uuid.UUID(user["branch_id"])
    data = await request.json()
    from models.mega_modules import Quiz, QuizQuestion
    quiz = Quiz(
        branch_id=branch_id, title=data["title"],
        class_id=uuid.UUID(data["class_id"]) if data.get("class_id") else None,
        subject_id=uuid.UUID(data["subject_id"]) if data.get("subject_id") else None,
        created_by=uuid.UUID(user.get("teacher_id", user["user_id"])) if user.get("teacher_id") else None,
        time_limit_minutes=data.get("time_limit_minutes", 30),
        pass_marks=data.get("pass_marks", 40),
        shuffle_questions=data.get("shuffle_questions", False),
        is_published=data.get("is_published", False),
        total_marks=sum(q.get("marks", 1) for q in data.get("questions", []))
    )
    db.add(quiz)
    await db.flush()
    for q in data.get("questions", []):
        qq = QuizQuestion(
            quiz_id=quiz.id, question_text=q["question_text"],
            option_a=q.get("option_a", ""), option_b=q.get("option_b", ""),
            option_c=q.get("option_c", ""), option_d=q.get("option_d", ""),
            correct_answer=q.get("correct_answer", "A"),
            marks=q.get("marks", 1), order_num=q.get("order_num", 0)
        )
        db.add(qq)
    await db.commit()
    return {"id": str(quiz.id), "status": "created"}


@router.post("/quizzes/{quiz_id}/publish")
async def publish_quiz(request: Request, quiz_id: str, db: AsyncSession = Depends(get_db)):
    from models.mega_modules import Quiz
    quiz = await db.scalar(select(Quiz).where(Quiz.id == uuid.UUID(quiz_id)))
    if quiz: quiz.is_published = True; await db.commit()
    return {"status": "published"}


@router.delete("/quizzes/{quiz_id}")
async def delete_quiz(request: Request, quiz_id: str, db: AsyncSession = Depends(get_db)):
    from models.mega_modules import Quiz, QuizQuestion
    await db.execute(select(QuizQuestion).where(QuizQuestion.quiz_id == uuid.UUID(quiz_id)))
    quiz = await db.scalar(select(Quiz).where(Quiz.id == uuid.UUID(quiz_id)))
    if quiz: await db.delete(quiz); await db.commit()
    return {"status": "deleted"}


# ═══════════════════════════════════════════════════════════
# SPRINT 25 — ACCOUNTS (INCOME / EXPENSE)
# ═══════════════════════════════════════════════════════════

@router.get("/accounts")
async def get_accounts(request: Request, type: str = "", category: str = "", month: str = "",
                       db: AsyncSession = Depends(get_db)):
    user = await get_current_user(request)
    if not user: return {"transactions": [], "summary": {}}
    branch_id = uuid.UUID(user["branch_id"])
    from models.mega_modules import AccountTransaction
    q = select(AccountTransaction).where(AccountTransaction.branch_id == branch_id)
    if type: q = q.where(AccountTransaction.transaction_type == type)
    if category: q = q.where(AccountTransaction.category == category)
    if month:
        from datetime import datetime as dt
        y, m = month.split("-")
        start = date(int(y), int(m), 1)
        end = date(int(y), int(m) + 1, 1) if int(m) < 12 else date(int(y) + 1, 1, 1)
        q = q.where(AccountTransaction.transaction_date >= start, AccountTransaction.transaction_date < end)
    txns = (await db.execute(q.order_by(AccountTransaction.transaction_date.desc()))).scalars().all()
    total_income = sum(t.amount for t in txns if t.transaction_type == "income")
    total_expense = sum(t.amount for t in txns if t.transaction_type == "expense")
    return {
        "transactions": [{"id": str(t.id), "transaction_type": t.transaction_type, "category": t.category,
                           "description": t.description or "", "amount": t.amount,
                           "transaction_date": t.transaction_date.isoformat(), "payment_mode": t.payment_mode or "",
                           "reference_number": t.reference_number or ""} for t in txns],
        "summary": {"total_income": total_income, "total_expense": total_expense,
                     "balance": total_income - total_expense, "count": len(txns)}
    }


@router.post("/accounts")
async def create_transaction(request: Request, db: AsyncSession = Depends(get_db)):
    user = await get_current_user(request)
    if not user: return {"error": "unauthorized"}
    branch_id = uuid.UUID(user["branch_id"])
    data = await request.json()
    from models.mega_modules import AccountTransaction
    txn = AccountTransaction(
        branch_id=branch_id, transaction_type=data["transaction_type"], category=data["category"],
        description=data.get("description"), amount=data["amount"],
        transaction_date=date.fromisoformat(data["transaction_date"]),
        payment_mode=data.get("payment_mode"), reference_number=data.get("reference_number"),
        created_by=uuid.UUID(user["user_id"])
    )
    db.add(txn)
    await db.commit()
    return {"id": str(txn.id), "status": "created"}


# ═══════════════════════════════════════════════════════════
# QR CODE ATTENDANCE
# ═══════════════════════════════════════════════════════════

@router.post("/attendance/qr-mark")
async def qr_mark_attendance(request: Request, db: AsyncSession = Depends(get_db)):
    """Mark attendance by scanning QR code or entering roll number / student ID."""
    user = await get_current_user(request)
    if not user: return {"success": False, "message": "Unauthorized"}
    branch_id = uuid.UUID(user["branch_id"])
    data = await request.json()
    identifier = data.get("student_identifier", "").strip()
    if not identifier: return {"success": False, "message": "No identifier"}

    # Try to find student by: UUID, roll number, or admission number
    student = None
    try:
        student = await db.scalar(select(Student).where(Student.id == uuid.UUID(identifier), Student.branch_id == branch_id))
    except (ValueError, Exception):
        pass
    if not student:
        student = await db.scalar(select(Student).where(Student.roll_number == identifier, Student.branch_id == branch_id, Student.is_active == True))
    if not student:
        student = await db.scalar(select(Student).where(Student.admission_number == identifier, Student.branch_id == branch_id, Student.is_active == True))
    if not student:
        return {"success": False, "message": f"Student not found: {identifier}"}

    # Check if already marked today
    today = date.today()
    existing = await db.scalar(
        select(Attendance).where(Attendance.student_id == student.id, Attendance.date == today)
    )
    if existing:
        return {"success": True, "student_name": student.full_name, "roll": student.roll_number or "", "message": "Already marked"}

    # Mark present with check-in time
    from utils.timezone import get_school_time
    try:
        now_time, _ = await get_school_time(db, branch_id)
    except Exception:
        from datetime import datetime as _dt
        now_time = _dt.utcnow().time()

    att = Attendance(
        student_id=student.id, branch_id=branch_id,
        class_id=student.class_id, section_id=student.section_id,
        date=today, status=AttendanceStatus.PRESENT,
        check_in_time=now_time,
    )
    db.add(att)
    await db.commit()
    time_str = now_time.strftime("%I:%M %p") if now_time else ""
    return {"success": True, "student_name": student.full_name, "roll": student.roll_number or "", "message": f"Marked present at {time_str}"}


# ═══════════════════════════════════════════════════════════
# FEE WAIVERS
# ═══════════════════════════════════════════════════════════

@router.get("/fee-waivers")
async def get_fee_waivers(request: Request, type: str = "", status: str = "",
                          db: AsyncSession = Depends(get_db)):
    user = await get_current_user(request)
    if not user: return {"waivers": []}
    branch_id = uuid.UUID(user["branch_id"])
    from models.mega_modules import FeeWaiver
    q = select(FeeWaiver).where(FeeWaiver.branch_id == branch_id)
    if type: q = q.where(FeeWaiver.waiver_type == type)
    if status: q = q.where(FeeWaiver.status == status)
    waivers = (await db.execute(q.order_by(FeeWaiver.created_at.desc()))).scalars().all()
    items = []
    for w in waivers:
        s = await db.scalar(select(Student).where(Student.id == w.student_id))
        cls_name = ""
        if s and s.class_id:
            cls_name = await db.scalar(select(Class.name).where(Class.id == s.class_id)) or ""
        items.append({"id": str(w.id), "student_name": s.full_name if s else "Unknown",
            "class_name": cls_name, "waiver_type": w.waiver_type,
            "title": w.title, "discount_type": w.discount_type, "discount_value": w.discount_value,
            "valid_from": w.valid_from.isoformat() if w.valid_from else None,
            "valid_to": w.valid_to.isoformat() if w.valid_to else None, "status": w.status,
            "remarks": w.remarks or ""})
    return {"waivers": items}


@router.post("/fee-waivers")
async def create_fee_waiver(request: Request, db: AsyncSession = Depends(get_db)):
    user = await get_current_user(request)
    if not user: return {"error": "unauthorized"}
    data = await request.json()
    from models.mega_modules import FeeWaiver
    w = FeeWaiver(branch_id=uuid.UUID(user["branch_id"]), student_id=uuid.UUID(data["student_id"]),
        waiver_type=data["waiver_type"], title=data["title"],
        discount_type=data.get("discount_type", "percentage"), discount_value=data["discount_value"],
        valid_from=date.fromisoformat(data["valid_from"]) if data.get("valid_from") else None,
        valid_to=date.fromisoformat(data["valid_to"]) if data.get("valid_to") else None,
        approved_by=uuid.UUID(user["user_id"]), remarks=data.get("remarks"))
    db.add(w)
    await db.commit()
    return {"id": str(w.id), "status": "created"}


@router.post("/fee-waivers/{waiver_id}/revoke")
async def revoke_fee_waiver(request: Request, waiver_id: str, db: AsyncSession = Depends(get_db)):
    from models.mega_modules import FeeWaiver
    w = await db.scalar(select(FeeWaiver).where(FeeWaiver.id == uuid.UUID(waiver_id)))
    if w: w.status = "revoked"; await db.commit()
    return {"status": "revoked"}


# ═══════════════════════════════════════════════════════════
# HOSTEL MANAGEMENT
# ═══════════════════════════════════════════════════════════

@router.get("/hostels")
async def get_hostels(request: Request, db: AsyncSession = Depends(get_db)):
    user = await get_current_user(request)
    if not user: return {"hostels": []}
    branch_id = uuid.UUID(user["branch_id"])
    from models.mega_modules import Hostel
    hostels = (await db.execute(select(Hostel).where(Hostel.branch_id == branch_id, Hostel.is_active == True))).scalars().all()
    return {"hostels": [{"id": str(h.id), "name": h.name, "hostel_type": h.hostel_type,
        "warden_name": h.warden_name, "warden_phone": h.warden_phone,
        "total_rooms": h.total_rooms, "total_beds": h.total_beds,
        "monthly_fee": float(h.monthly_fee or 0), "mess_fee": float(h.mess_fee or 0)} for h in hostels]}


@router.post("/hostels")
async def create_hostel(request: Request, db: AsyncSession = Depends(get_db)):
    user = await get_current_user(request)
    if not user: return {"error": "unauthorized"}
    data = await request.json()
    from models.mega_modules import Hostel
    h = Hostel(branch_id=uuid.UUID(user["branch_id"]), name=data["name"], hostel_type=data.get("hostel_type", "boys"),
        warden_name=data.get("warden_name"), warden_phone=data.get("warden_phone"),
        total_rooms=data.get("total_rooms", 0), total_beds=data.get("total_beds", 0),
        monthly_fee=data.get("monthly_fee", 0), mess_fee=data.get("mess_fee", 0))
    db.add(h)
    await db.commit()
    return {"id": str(h.id)}


@router.get("/hostel-rooms")
async def get_hostel_rooms(request: Request, hostel_id: str = "", db: AsyncSession = Depends(get_db)):
    from models.mega_modules import HostelRoom
    q = select(HostelRoom)
    if hostel_id: q = q.where(HostelRoom.hostel_id == uuid.UUID(hostel_id))
    rooms = (await db.execute(q.order_by(HostelRoom.room_number))).scalars().all()
    return {"rooms": [{"id": str(r.id), "room_number": r.room_number, "floor": r.floor,
        "bed_count": r.bed_count, "occupied_beds": r.occupied_beds, "status": r.status} for r in rooms]}


@router.post("/hostel-rooms")
async def create_hostel_room(request: Request, db: AsyncSession = Depends(get_db)):
    data = await request.json()
    from models.mega_modules import HostelRoom
    r = HostelRoom(hostel_id=uuid.UUID(data["hostel_id"]), room_number=data["room_number"],
        floor=data.get("floor"), bed_count=data.get("bed_count", 4))
    db.add(r)
    await db.commit()
    return {"id": str(r.id)}


@router.post("/hostel-allocations")
async def allocate_hostel(request: Request, db: AsyncSession = Depends(get_db)):
    data = await request.json()
    from models.mega_modules import HostelAllocation, HostelRoom
    room = await db.scalar(select(HostelRoom).where(HostelRoom.id == uuid.UUID(data["room_id"])))
    if room and room.occupied_beds >= room.bed_count:
        return {"error": "Room is full"}
    a = HostelAllocation(student_id=uuid.UUID(data["student_id"]), hostel_id=uuid.UUID(data["hostel_id"]),
        room_id=uuid.UUID(data["room_id"]), bed_number=data.get("bed_number"),
        check_in_date=date.today())
    db.add(a)
    if room: room.occupied_beds = (room.occupied_beds or 0) + 1
    if room and room.occupied_beds >= room.bed_count: room.status = "full"
    await db.commit()
    return {"id": str(a.id)}


# ═══════════════════════════════════════════════════════════
# ID CARD DESIGNER
# ═══════════════════════════════════════════════════════════

@router.post("/id-card-design")
async def save_id_card_design(request: Request, db: AsyncSession = Depends(get_db)):
    """Save ID card design JSON for the branch."""
    user = await get_current_user(request)
    if not user: return {"error": "unauthorized"}
    data = await request.json()
    from models.branch import BranchSettings
    branch_id = uuid.UUID(user["branch_id"])
    settings = await db.scalar(select(BranchSettings).where(BranchSettings.branch_id == branch_id))
    import json
    if settings:
        cd = settings.custom_data or {}
        cd["id_card_design"] = data
        settings.custom_data = cd
        from sqlalchemy.orm.attributes import flag_modified
        flag_modified(settings, "custom_data")
    else:
        settings = BranchSettings(branch_id=branch_id, custom_data={"id_card_design": data})
        db.add(settings)
    await db.commit()
    return {"status": "saved"}


@router.get("/id-card-design")
async def get_id_card_design(request: Request, db: AsyncSession = Depends(get_db)):
    user = await get_current_user(request)
    if not user: return {"design": None}
    from models.branch import BranchSettings
    settings = await db.scalar(
        select(BranchSettings).where(BranchSettings.branch_id == uuid.UUID(user["branch_id"]))
    )
    design = (settings.custom_data or {}).get("id_card_design") if settings else None
    return {"design": design}


# ═══════════════════════════════════════════════════════════
# HOUSE SYSTEM
# ═══════════════════════════════════════════════════════════

@router.get("/houses")
async def get_houses(request: Request, db: AsyncSession = Depends(get_db)):
    user = await get_current_user(request)
    if not user: return {"houses": []}
    branch_id = uuid.UUID(user["branch_id"])
    from models.mega_modules import House, StudentHouse
    houses_list = (await db.execute(select(House).where(House.branch_id == branch_id, House.is_active == True))).scalars().all()
    items = []
    for h in houses_list:
        sc = await db.scalar(select(func.count(StudentHouse.id)).where(StudentHouse.house_id == h.id)) or 0
        master_name = ""
        if h.house_master_id:
            from models.teacher import Teacher
            t = await db.scalar(select(Teacher).where(Teacher.id == h.house_master_id))
            master_name = t.full_name if t else ""
        items.append({"id": str(h.id), "name": h.name, "color": h.color, "tagline": h.tagline or "",
            "points": h.points or 0, "student_count": sc, "master_name": master_name})
    return {"houses": items}


@router.post("/houses")
async def create_house(request: Request, db: AsyncSession = Depends(get_db)):
    user = await get_current_user(request)
    if not user: return {"error": "unauthorized"}
    data = await request.json()
    from models.mega_modules import House
    h = House(branch_id=uuid.UUID(user["branch_id"]), name=data["name"], color=data.get("color", "#DC2626"),
        tagline=data.get("tagline"), house_master_id=uuid.UUID(data["house_master_id"]) if data.get("house_master_id") else None)
    db.add(h)
    await db.commit()
    return {"id": str(h.id)}


@router.put("/houses/{house_id}")
async def update_house(request: Request, house_id: str, db: AsyncSession = Depends(get_db)):
    from models.mega_modules import House
    user = await get_current_user(request)
    data = await request.json()
    h = await db.scalar(select(House).where(House.id == uuid.UUID(house_id)))
    if not h:
        return {"error": "House not found"}
    if data.get("name"): h.name = data["name"]
    if "color" in data: h.color = data["color"]
    if "tagline" in data: h.tagline = data["tagline"]
    if "house_master_id" in data:
        h.house_master_id = uuid.UUID(data["house_master_id"]) if data["house_master_id"] else None
    await db.commit()
    return {"success": True, "message": "House updated"}


@router.delete("/houses/{house_id}")
async def delete_house(request: Request, house_id: str, db: AsyncSession = Depends(get_db)):
    from models.mega_modules import House
    h = await db.scalar(select(House).where(House.id == uuid.UUID(house_id)))
    if h: h.is_active = False; await db.commit()
    return {"status": "deleted"}


@router.post("/houses/assign")
async def assign_students_to_house(request: Request, db: AsyncSession = Depends(get_db)):
    user = await get_current_user(request)
    data = await request.json()
    from models.mega_modules import StudentHouse
    house_id = uuid.UUID(data["house_id"])
    count = 0
    for sid in data.get("student_ids", []):
        # Remove old assignment
        old = await db.scalar(select(StudentHouse).where(StudentHouse.student_id == uuid.UUID(sid)))
        if old:
            old.house_id = house_id
        else:
            db.add(StudentHouse(student_id=uuid.UUID(sid), house_id=house_id,
                assigned_by=uuid.UUID(user["user_id"])))
        count += 1
    await db.commit()
    return {"assigned": count}


@router.post("/houses/{house_id}/points")
async def award_house_points(request: Request, house_id: str, db: AsyncSession = Depends(get_db)):
    data = await request.json()
    from models.mega_modules import House
    h = await db.scalar(select(House).where(House.id == uuid.UUID(house_id)))
    if h:
        h.points = (h.points or 0) + data.get("points", 0)
        await db.commit()
    return {"points": h.points if h else 0}


# ═══════════════════════════════════════════════════════════
# STUDENT ROLES
# ═══════════════════════════════════════════════════════════

@router.get("/student-roles")
async def get_student_roles(request: Request, db: AsyncSession = Depends(get_db)):
    user = await get_current_user(request)
    if not user: return {"roles": []}
    branch_id = uuid.UUID(user["branch_id"])
    from models.mega_modules import StudentRole, House
    roles = (await db.execute(
        select(StudentRole).where(StudentRole.branch_id == branch_id, StudentRole.is_active == True)
        .order_by(StudentRole.created_at.desc())
    )).scalars().all()
    items = []
    for r in roles:
        s = await db.scalar(select(Student).where(Student.id == r.student_id))
        cls = await db.scalar(select(Class.name).where(Class.id == r.class_id)) if r.class_id else ""
        house_name, house_color = "", ""
        if r.house_id:
            h = await db.scalar(select(House).where(House.id == r.house_id))
            if h: house_name, house_color = h.name, h.color
        items.append({"id": str(r.id), "student_name": s.full_name if s else "?", "role_type": r.role_type,
            "title": r.title, "class_name": cls or "", "house_name": house_name, "house_color": house_color})
    return {"roles": items}


@router.post("/student-roles")
async def create_student_role(request: Request, db: AsyncSession = Depends(get_db)):
    user = await get_current_user(request)
    data = await request.json()
    from models.mega_modules import StudentRole
    r = StudentRole(branch_id=uuid.UUID(user["branch_id"]), student_id=uuid.UUID(data["student_id"]),
        role_type=data["role_type"], title=data["title"],
        house_id=uuid.UUID(data["house_id"]) if data.get("house_id") else None,
        class_id=uuid.UUID(data["class_id"]) if data.get("class_id") else None,
        awarded_by=uuid.UUID(user["user_id"]))
    db.add(r)
    await db.commit()
    return {"id": str(r.id)}


@router.delete("/student-roles/{role_id}")
async def delete_student_role(request: Request, role_id: str, db: AsyncSession = Depends(get_db)):
    from models.mega_modules import StudentRole
    r = await db.scalar(select(StudentRole).where(StudentRole.id == uuid.UUID(role_id)))
    if r: r.is_active = False; await db.commit()
    return {"status": "deleted"}


@router.get("/teachers-list")
async def get_teachers_list(request: Request, db: AsyncSession = Depends(get_db)):
    """Simple teacher list for dropdowns."""
    user = await get_current_user(request)
    if not user: return {"teachers": []}
    from models.teacher import Teacher
    teachers = (await db.execute(
        select(Teacher).where(Teacher.branch_id == uuid.UUID(user["branch_id"]), Teacher.is_active == True)
    )).scalars().all()
    return {"teachers": [{"id": str(t.id), "name": t.full_name} for t in teachers]}


# ═══════════════════════════════════════════════════════════
# DIGITAL LIBRARY — Magazines, Textbooks, PDF tracking
# ═══════════════════════════════════════════════════════════

@router.get("/digital-library")
async def list_digital_content(request: Request, db: AsyncSession = Depends(get_db)):
    user = await get_current_user(request)
    if not user: return {"contents": []}
    branch_id = uuid.UUID(user["branch_id"])
    from models.mega_modules import DigitalContent, ContentView
    items = (await db.execute(
        select(DigitalContent).where(DigitalContent.branch_id == branch_id, DigitalContent.is_active == True)
        .order_by(DigitalContent.created_at.desc())
    )).scalars().all()
    results = []
    for c in items:
        views = await db.scalar(select(func.count(ContentView.id)).where(ContentView.content_id == c.id)) or 0
        unique = await db.scalar(select(func.count(func.distinct(ContentView.user_id))).where(ContentView.content_id == c.id)) or 0
        cls_name = await db.scalar(select(Class.name).where(Class.id == c.class_id)) if c.class_id else ""
        sub_name = ""
        if c.subject_id:
            sub_name = await db.scalar(select(Subject.name).where(Subject.id == c.subject_id)) or ""
        uploader = await db.scalar(select(User.email).where(User.id == c.uploaded_by)) or ""
        size_str = f"{c.file_size_kb/1024:.1f} MB" if c.file_size_kb > 1024 else f"{c.file_size_kb} KB"
        results.append({
            "id": str(c.id), "title": c.title, "content_type": c.content_type,
            "file_url": c.file_url, "file_size": size_str, "class_name": cls_name or "",
            "subject_name": sub_name, "uploaded_by_name": uploader,
            "date": c.created_at.strftime('%d %b %Y') if c.created_at else "",
            "views": views, "unique_viewers": unique, "visibility": c.visibility,
        })
    return {"contents": results}


@router.post("/digital-library/upload")
async def upload_digital_content(request: Request, db: AsyncSession = Depends(get_db)):
    user = await get_current_user(request)
    if not user: return {"error": "unauthorized"}
    import aiofiles
    form = await request.form()
    file = form.get("file")
    if not file: return {"error": "No file selected"}

    # Save file
    upload_dir = os.path.join("static", "uploads", "library")
    os.makedirs(upload_dir, exist_ok=True)
    filename = f"{uuid.uuid4().hex[:8]}_{file.filename}"
    filepath = os.path.join(upload_dir, filename)
    contents = await file.read()
    async with aiofiles.open(filepath, 'wb') as f:
        await f.write(contents)

    from models.mega_modules import DigitalContent
    dc = DigitalContent(
        branch_id=uuid.UUID(user["branch_id"]),
        title=form.get("title", "Untitled"),
        description=form.get("description", ""),
        content_type=form.get("content_type", "notes"),
        file_url=f"/{filepath}",
        file_size_kb=len(contents) // 1024,
        class_id=uuid.UUID(form.get("class_id")) if form.get("class_id") else None,
        subject_id=uuid.UUID(form.get("subject_id")) if form.get("subject_id") else None,
        uploaded_by=uuid.UUID(user["user_id"]),
        visibility=form.get("visibility", "students_parents"),
    )
    db.add(dc)
    await db.commit()
    return {"id": str(dc.id)}


@router.delete("/digital-library/{content_id}")
async def delete_digital_content(request: Request, content_id: str, db: AsyncSession = Depends(get_db)):
    from models.mega_modules import DigitalContent
    c = await db.scalar(select(DigitalContent).where(DigitalContent.id == uuid.UUID(content_id)))
    if c: c.is_active = False; await db.commit()
    return {"status": "deleted"}


@router.get("/digital-library/{content_id}/analytics")
async def content_analytics(request: Request, content_id: str, db: AsyncSession = Depends(get_db)):
    from models.mega_modules import ContentView
    cid = uuid.UUID(content_id)
    total = await db.scalar(select(func.count(ContentView.id)).where(ContentView.content_id == cid)) or 0
    unique = await db.scalar(select(func.count(func.distinct(ContentView.user_id))).where(ContentView.content_id == cid)) or 0
    avg_dur = await db.scalar(select(func.avg(ContentView.duration_seconds)).where(ContentView.content_id == cid)) or 0
    views = (await db.execute(
        select(ContentView).where(ContentView.content_id == cid).order_by(ContentView.viewed_at.desc()).limit(100)
    )).scalars().all()
    view_list = []
    for v in views:
        sname = ""
        if v.student_id:
            s = await db.scalar(select(Student.first_name).where(Student.id == v.student_id))
            sname = s or ""
        else:
            u = await db.scalar(select(User.email).where(User.id == v.user_id))
            sname = u or "User"
        view_list.append({
            "student_name": sname, "user_name": sname,
            "viewed_at": v.viewed_at.strftime('%d %b %Y %H:%M') if v.viewed_at else "",
            "duration": v.duration_seconds or 0
        })
    return {"total_views": total, "unique_viewers": unique, "avg_duration": round(float(avg_dur)), "views": view_list}


@router.get("/subjects-list")
async def subjects_list(request: Request, db: AsyncSession = Depends(get_db)):
    user = await get_current_user(request)
    if not user: return {"subjects": []}
    subs = (await db.execute(select(Subject).where(Subject.branch_id == uuid.UUID(user["branch_id"])))).scalars().all()
    return {"subjects": [{"id": str(s.id), "name": s.name} for s in subs]}


# ═══════════════════════════════════════════════════════════
# STUDENT PROFILE, EDIT, DOCUMENTS
# ═══════════════════════════════════════════════════════════

@router.get("/students/{student_id}/profile")
async def student_profile(request: Request, student_id: str, db: AsyncSession = Depends(get_db)):
    """Full student profile with class, section, house, roles, documents."""
    s = await db.scalar(select(Student).where(Student.id == uuid.UUID(student_id)))
    if not s: return {"error": "not found"}
    cls_name = await db.scalar(select(Class.name).where(Class.id == s.class_id)) if s.class_id else ""
    sec_name = ""
    if s.section_id:
        from models.academic import Section
        sec_name = await db.scalar(select(Section.name).where(Section.id == s.section_id)) or ""
    # House
    from models.mega_modules import StudentHouse, House, StudentRole
    house_name, house_color = "", ""
    sh = await db.scalar(select(StudentHouse).where(StudentHouse.student_id == s.id))
    if sh:
        h = await db.scalar(select(House).where(House.id == sh.house_id))
        if h: house_name, house_color = h.name, h.color
    # Roles
    roles = (await db.execute(select(StudentRole).where(StudentRole.student_id == s.id, StudentRole.is_active == True))).scalars().all()
    role_list = [{"title": r.title, "role_type": r.role_type} for r in roles]
    # Documents
    from models.student import StudentDocument
    docs = (await db.execute(select(StudentDocument).where(StudentDocument.student_id == s.id).order_by(StudentDocument.uploaded_at.desc()))).scalars().all()
    doc_list = [{"id": str(d.id), "doc_type": d.doc_type, "doc_name": d.doc_name,
                 "file_url": d.file_url, "uploaded_at": d.uploaded_at.strftime('%d %b %Y') if d.uploaded_at else ""} for d in docs]

    # Transport info
    transport_info = {"route_name": "", "vehicle_number": "", "stop_name": ""}
    if s.uses_transport:
        try:
            from models.transport import StudentTransport, TransportRoute, RouteStop, Vehicle
            st = await db.scalar(select(StudentTransport).where(
                StudentTransport.student_id == s.id, StudentTransport.is_active == True))
            if st:
                route = await db.scalar(select(TransportRoute).where(TransportRoute.id == st.route_id))
                if route:
                    transport_info["route_name"] = route.route_name or ""
                    if route.vehicle_id:
                        veh = await db.scalar(select(Vehicle).where(Vehicle.id == route.vehicle_id))
                        if veh: transport_info["vehicle_number"] = veh.vehicle_number or ""
                stop = await db.scalar(select(RouteStop).where(RouteStop.id == st.stop_id)) if st.stop_id else None
                if stop: transport_info["stop_name"] = stop.stop_name or ""
        except Exception:
            pass
    elif s.transport_route:
        transport_info["route_name"] = s.transport_route

    return {"student": {
        "id": str(s.id), "first_name": s.first_name, "last_name": s.last_name or "",
        "full_name": s.full_name, "roll_number": s.roll_number or "",
        "admission_number": s.admission_number or "",
        "student_login_id": s.student_login_id or "",
        "class_name": cls_name or "", "section_name": sec_name,
        "class_id": str(s.class_id) if s.class_id else "",
        "section_id": str(s.section_id) if s.section_id else "",
        "date_of_birth": s.date_of_birth.isoformat() if s.date_of_birth else "",
        "gender": s.gender.value if s.gender else "", "blood_group": s.blood_group or "",
        "aadhaar_number": s.aadhaar_number or "",
        "admission_date": s.admission_date.isoformat() if s.admission_date else "",
        "admission_type": s.admission_type or "",
        "admission_status": s.admission_status.value if s.admission_status else "admitted",
        # Parent / Guardian
        "father_name": s.father_name or "", "father_phone": s.father_phone or "",
        "father_email": s.father_email or "", "father_occupation": s.father_occupation or "",
        "father_qualification": s.father_qualification or "",
        "mother_name": s.mother_name or "", "mother_phone": s.mother_phone or "",
        "mother_email": s.mother_email or "", "mother_occupation": s.mother_occupation or "",
        "mother_qualification": s.mother_qualification or "",
        "guardian_name": s.guardian_name or "", "guardian_phone": s.guardian_phone or "",
        # Address
        "address": s.address or "", "city": s.city or "", "state": s.state or "", "pincode": s.pincode or "",
        # Medical
        "medical_conditions": s.medical_conditions or "", "emergency_contact": s.emergency_contact or "",
        # Background
        "religion": s.religion or "", "category": s.category or "", "nationality": s.nationality or "",
        "previous_school": s.previous_school or "", "previous_board": s.previous_board or "",
        "previous_class": s.previous_class or "",
        # Transport
        "uses_transport": s.uses_transport or False,
        "transport_route": transport_info["route_name"],
        "transport_vehicle": transport_info["vehicle_number"],
        "transport_stop": transport_info["stop_name"],
        # House & Photo
        "photo_url": s.photo_url or "",
        "house_name": house_name, "house_color": house_color,
        "roles": role_list, "documents": doc_list,
        "updated_at": s.updated_at.strftime("%d %b %Y %I:%M %p") if s.updated_at else "",
        "created_at": s.created_at.strftime("%d %b %Y") if s.created_at else "",
    }}


@router.put("/students/{student_id}")
async def update_student(request: Request, student_id: str, db: AsyncSession = Depends(get_db)):
    """Edit student details including roll number."""
    user = await get_current_user(request)
    if not user: return {"error": "unauthorized"}
    data = await request.json()
    s = await db.scalar(select(Student).where(Student.id == uuid.UUID(student_id)))
    if not s: return {"error": "not found"}
    # Update fields
    for field in ['first_name','last_name','roll_number','gender','blood_group',
                  'father_name','mother_name','father_phone','mother_phone','address']:
        if field in data:
            setattr(s, field, data[field])
    if 'date_of_birth' in data and data['date_of_birth']:
        from datetime import date as dt_date
        s.date_of_birth = dt_date.fromisoformat(data['date_of_birth'])
    if 'class_id' in data and data['class_id']:
        s.class_id = uuid.UUID(data['class_id'])
    if 'section_id' in data and data['section_id']:
        s.section_id = uuid.UUID(data['section_id'])
    if 'admission_status' in data:
        from models.student import AdmissionStatus
        try: s.admission_status = AdmissionStatus(data['admission_status'])
        except: pass
    await db.commit()
    return {"status": "updated"}


@router.post("/students/{student_id}/documents")
async def upload_student_document(request: Request, student_id: str, db: AsyncSession = Depends(get_db)):
    """Upload document for a student (birth cert, TC, marksheet, etc.)"""
    user = await get_current_user(request)
    if not user: return {"error": "unauthorized"}
    import aiofiles
    form = await request.form()
    file = form.get("file")
    if not file: return {"error": "No file"}
    doc_type = form.get("doc_type", "other")
    doc_name = form.get("doc_name", file.filename)

    upload_dir = os.path.join("static", "uploads", "student_docs", student_id)
    os.makedirs(upload_dir, exist_ok=True)
    filename = f"{uuid.uuid4().hex[:8]}_{file.filename}"
    filepath = os.path.join(upload_dir, filename)
    contents = await file.read()
    async with aiofiles.open(filepath, 'wb') as f:
        await f.write(contents)

    from models.student import StudentDocument
    doc = StudentDocument(student_id=uuid.UUID(student_id), doc_type=doc_type,
                          doc_name=doc_name, file_url=f"/{filepath}")
    db.add(doc)
    await db.commit()
    return {"id": str(doc.id), "file_url": doc.file_url}


@router.delete("/students/{student_id}/documents/{doc_id}")
async def delete_student_document(request: Request, student_id: str, doc_id: str, db: AsyncSession = Depends(get_db)):
    from models.student import StudentDocument
    doc = await db.scalar(select(StudentDocument).where(StudentDocument.id == uuid.UUID(doc_id)))
    if doc:
        await db.delete(doc)
        await db.commit()
    return {"status": "deleted"}


# ═══════════════════════════════════════════════════════════
# ADMISSION NOTIFICATIONS — Teacher, Transport, Hostel
# ═══════════════════════════════════════════════════════════

@router.post("/admission-notify")
async def admission_notify(request: Request, db: AsyncSession = Depends(get_db)):
    """Send notifications on new admission to class teacher, transport, hostel."""
    user = await get_current_user(request)
    if not user: return {"error": "unauthorized"}
    data = await request.json()
    from models.notification import Notification, NotificationType
    from models.teacher import Teacher
    branch_id = uuid.UUID(user["branch_id"])
    student_name = data.get("student_name", "New Student")
    class_id = data.get("class_id")
    section_id = data.get("section_id")
    notified = []

    cls_name = ""
    if class_id:
        cls_name = await db.scalar(select(Class.name).where(Class.id == uuid.UUID(class_id))) or ""
    sec_name = ""
    if section_id:
        from models.academic import Section
        sec_name = await db.scalar(select(Section.name).where(Section.id == uuid.UUID(section_id))) or ""

    # 1. Notify class teacher of this specific section
    class_teacher = None
    if section_id:
        from sqlalchemy import text as sql_text
        ct_teacher_id = await db.scalar(sql_text(
            "SELECT class_teacher_id FROM sections WHERE id = :sid"
        ), {"sid": section_id})
        class_teacher = None
        if ct_teacher_id:
            class_teacher = await db.scalar(
                select(Teacher).where(
                    Teacher.id == ct_teacher_id,
                    Teacher.is_active == True
                )
            )
    if class_teacher and class_teacher.user_id:
        n = Notification(
            branch_id=branch_id, user_id=class_teacher.user_id,
            type=NotificationType.ADMISSION,
            title="📋 New Admission in Your Class",
            message=f"New student {student_name} admitted to {cls_name} {sec_name}. Please acknowledge.",
            notification_type="admission",
            reference_id=data.get("student_id"),
            requires_ack=True,
        )
        db.add(n)
        notified.append("class_teacher")
    else:
        # No class teacher assigned — notify all admins
        notified.append("no_class_teacher")

    # 2. Notify transport (if uses_transport)
    if data.get("uses_transport"):
        n = Notification(
            branch_id=branch_id, user_id=uuid.UUID(user["user_id"]),
            type=NotificationType.TRANSPORT,
            title="🚌 Transport Assignment",
            message=f"Student {student_name} ({cls_name}) requires school bus. Route assignment pending.",
            notification_type="transport",
            reference_id=data.get("student_id"),
        )
        db.add(n)
        notified.append("transport")

    # 3. Notify hostel (if hostel student)
    if data.get("hostel"):
        n = Notification(
            branch_id=branch_id, user_id=uuid.UUID(user["user_id"]),
            type=NotificationType.HOSTEL,
            title="🏠 Hostel Assignment",
            message=f"Student {student_name} ({cls_name}) is a hostel student. Room assignment pending.",
            notification_type="hostel",
            reference_id=data.get("student_id"),
        )
        db.add(n)
        notified.append("hostel")

    await db.commit()
    return {"notified": notified}


@router.post("/notifications/{notif_id}/acknowledge")
async def acknowledge_notification(request: Request, notif_id: str, db: AsyncSession = Depends(get_db)):
    """Teacher/staff acknowledges a notification — saves timestamp."""
    user = await get_current_user(request)
    if not user: return {"error": "unauthorized"}
    from models.notification import Notification, NotificationType
    n = await db.scalar(select(Notification).where(Notification.id == uuid.UUID(notif_id)))
    if not n: return {"error": "not found"}
    n.is_read = True
    n.read_at = datetime.utcnow()
    n.acknowledged = True
    n.acknowledged_at = datetime.utcnow()
    n.acknowledged_by = uuid.UUID(user["user_id"])
    await db.commit()

    # Notify admin about acknowledgement
    admins = (await db.execute(
        select(User).where(User.branch_id == n.branch_id, User.role == UserRole.SCHOOL_ADMIN, User.is_active == True)
    )).scalars().all()
    for admin in admins:
        admin_notif = Notification(
            branch_id=n.branch_id, user_id=admin.id,
            type=NotificationType.ACK,
            title="✅ Acknowledgement Received",
            message=f"{user.get('email','')} acknowledged: {n.title}",
            notification_type="ack",
        )
        db.add(admin_notif)
    await db.commit()
    return {"status": "acknowledged", "at": n.acknowledged_at.isoformat() if n.acknowledged_at else ""}


@router.get("/transport/routes-list")
async def list_transport_routes(request: Request, db: AsyncSession = Depends(get_db)):
    """List transport routes for admission wizard dropdown."""
    user = await get_current_user(request)
    if not user: return {"routes": []}
    branch_id = uuid.UUID(user["branch_id"])
    from models.mega_modules import TransportRoute
    routes = (await db.execute(
        select(TransportRoute).where(TransportRoute.branch_id == branch_id, TransportRoute.is_active == True)
        .order_by(TransportRoute.route_name)
    )).scalars().all()
    return {"routes": [{"id": str(r.id), "name": r.route_name, "description": r.route_number or ""} for r in routes]}


# ═══════════════════════════════════════════════════════════
# AUTO-CREATE PARENT ACCOUNT ON ADMISSION
# ═══════════════════════════════════════════════════════════

@router.post("/admission-create-parent")
async def admission_create_parent(request: Request, db: AsyncSession = Depends(get_db)):
    """Auto-create parent login when student is admitted."""
    user = await get_current_user(request)
    if not user: return {"error": "unauthorized"}
    data = await request.json()
    branch_id = uuid.UUID(user["branch_id"])
    father_email = data.get("father_email", "").strip()
    mother_email = data.get("mother_email", "").strip()
    father_name = data.get("father_name", "")
    father_phone = data.get("father_phone", "")
    student_id = data.get("student_id")
    managed = data.get("managed_by_parent", True)
    created = []

    # Create parent user with father's email (primary)
    email = father_email or mother_email
    if email:
        # Check if parent already exists
        existing = await db.scalar(select(User).where(User.email == email))
        if not existing:
            import secrets
            temp_password = f"Parent@{secrets.token_hex(3)}"
            parent_user = User(
                email=email,
                phone=father_phone,
                full_name=father_name,
                password_hash=User.hash_password(temp_password) if hasattr(User, 'hash_password') else temp_password,
                role=UserRole.PARENT,
                branch_id=branch_id,
                is_active=True,
            )
            db.add(parent_user)
            await db.flush()
            created.append({"email": email, "temp_password": temp_password, "user_id": str(parent_user.id)})

            # Link parent to student
            student = await db.scalar(select(Student).where(Student.id == uuid.UUID(student_id)))
            if student:
                student.user_id = parent_user.id if managed else None

    await db.commit()
    return {"created": created, "managed_by_parent": managed}


# ═══════════════════════════════════════════════════════════
# STAFF MANAGEMENT & PRIVILEGE SYSTEM
# ═══════════════════════════════════════════════════════════

@router.get("/staff-list")
async def staff_list(request: Request, db: AsyncSession = Depends(get_db)):
    """List all school_admin users for this branch — for privilege management."""
    user = await get_current_user(request)
    if not user: return {"error": "unauthorized"}
    branch_id = uuid.UUID(user["branch_id"])
    staff = (await db.execute(
        select(User).where(
            User.branch_id == branch_id,
            User.role == UserRole.SCHOOL_ADMIN,
            User.is_active == True
        ).order_by(User.created_at)
    )).scalars().all()
    return {"staff": [{
        "id": str(s.id), "first_name": s.first_name, "last_name": s.last_name or "",
        "email": s.email, "phone": s.phone,
        "designation": getattr(s, 'designation', None),
        "is_first_admin": getattr(s, 'is_first_admin', False) or False,
        "privileges": getattr(s, 'privileges', {}) or {},
        "last_login": s.last_login.isoformat() if s.last_login else None,
    } for s in staff]}


@router.post("/staff-create")
async def staff_create(request: Request, db: AsyncSession = Depends(get_db)):
    """Create a new school_admin staff member — only first admin can do this."""
    user = await get_current_user(request)
    if not user: return {"error": "unauthorized"}
    # Only first admin or someone with manage_staff privilege can create staff
    is_first = user.get("is_first_admin", False)
    privs = user.get("privileges", {}) or {}
    if not is_first and not privs.get("manage_staff"):
        return {"error": "You don't have permission to manage staff"}

    data = await request.json()
    email = data.get("email", "").strip()
    if not email: return {"error": "Email is required for staff login"}

    # Check duplicate
    existing = await db.scalar(select(User).where(User.email == email))
    if existing: return {"error": f"Email {email} already exists"}

    from utils.auth import hash_password
    branch_id = uuid.UUID(user["branch_id"])
    org_id = uuid.UUID(user["org_id"]) if user.get("org_id") else None
    new_user = User(
        first_name=data.get("first_name", "Staff"),
        last_name=data.get("last_name", ""),
        email=email,
        phone=data.get("phone"),
        password_hash=hash_password(data.get("password", "Staff@123")),
        role=UserRole.SCHOOL_ADMIN,
        branch_id=branch_id,
        org_id=org_id,
        is_active=True,
        is_first_admin=False,
        designation=data.get("designation"),
        privileges={},  # Empty — principal will set checkboxes
    )
    db.add(new_user)
    await db.flush()
    await db.commit()
    return {"success": True, "user_id": str(new_user.id), "message": f"Staff account created for {email}"}


@router.put("/staff/{staff_id}/privileges")
async def update_staff_privileges(request: Request, staff_id: str, db: AsyncSession = Depends(get_db)):
    """Update privilege checkboxes for a staff member."""
    user = await get_current_user(request)
    if not user: return {"error": "unauthorized"}
    is_first = user.get("is_first_admin", False)
    privs = user.get("privileges", {}) or {}
    if not is_first and not privs.get("manage_staff"):
        return {"error": "You don't have permission to manage staff privileges"}

    data = await request.json()
    new_privileges = data.get("privileges", {})

    staff = await db.scalar(select(User).where(User.id == uuid.UUID(staff_id)))
    if not staff: return {"error": "Staff member not found"}
    if getattr(staff, 'is_first_admin', False):
        return {"error": "Cannot modify first admin privileges"}

    staff.privileges = new_privileges
    await db.commit()
    return {"success": True, "message": f"Privileges updated for {staff.first_name}"}


# ─── Sprint 26: PUT endpoint for notification settings ───

@router.put("/notification-settings")
async def update_notification_settings(request: Request, db: AsyncSession = Depends(get_db)):
    """Update communication/notification settings from the new notification_settings page."""
    user = await verify_school_admin(request)
    branch_id = get_branch_id(user)
    data = await request.json()

    result = await db.execute(select(CommunicationConfig).where(CommunicationConfig.branch_id == branch_id))
    config = result.scalar_one_or_none()
    if not config:
        config = CommunicationConfig(branch_id=branch_id)
        db.add(config)

    # Map fields
    field_map = {
        "whatsapp_enabled": "whatsapp_enabled",
        "whatsapp_api_token": "whatsapp_api_token",
        "whatsapp_phone_id": "whatsapp_phone_id",
        "sms_enabled": "sms_enabled",
        "sms_provider": "sms_provider",
        "sms_api_key": "sms_api_key",
        "sms_sender_id": "sms_sender_id",
        "email_enabled": "email_enabled",
        "smtp_host": "smtp_host",
        "smtp_port": "smtp_port",
        "smtp_username": "smtp_username",
        "smtp_password": "smtp_password",
        "from_email": "from_email",
        "tathaastu_enabled": "tathaastu_enabled",
        "tathaastu_school_id": "tathaastu_school_id",
        "tathaastu_api_key": "tathaastu_api_key",
        "quiet_hours_enabled": "quiet_hours_enabled",
        "quiet_start": "quiet_start",
        "quiet_end": "quiet_end",
    }
    for json_key, db_field in field_map.items():
        if json_key in data and hasattr(config, db_field):
            value = data[json_key]
            # Skip masked passwords
            if value is None:
                continue
            if isinstance(value, str) and "••••" in value:
                continue
            setattr(config, db_field, value)

    await db.commit()
    return {"success": True, "message": "Notification settings saved!"}

# ═══════════════════════════════════════════════════════════
# REGISTRATION ID CONFIG — Admin-configurable student ID format
# ═══════════════════════════════════════════════════════════
from models.registration_config import RegistrationNumberConfig


@router.get("/registration-config")
async def get_registration_config(request: Request, db: AsyncSession = Depends(get_db)):
    """Get current registration ID format config + presets."""
    user = await verify_school_admin(request)
    branch_id = get_branch_id(user)
    config = await db.scalar(
        select(RegistrationNumberConfig).where(RegistrationNumberConfig.branch_id == branch_id))
    presets = [
        {"label": "School + Year + Sequence", "format": "{SCHOOL4}{YY}{SEQ4}", "example": "GNK261"},
        {"label": "Code + Year + Class + Seq", "format": "{CODE}{YY}{CLASS}{SEQ3}", "example": "GNK2604123"},
        {"label": "Code + Year + Gender + Seq", "format": "{CODE}{YY}{GENDER}{SEQ4}", "example": "GNK26M1"},
        {"label": "Year + Code + Base36 Seq", "format": "{YY}{CODE}{SEQ4}", "example": "26GNK001"},
        {"label": "Code + Random 6", "format": "{CODE}{RAND6}", "example": "GNK7X9K2M"},
        {"label": "Full Year + School + Class + Seq", "format": "{YYYY}{SCHOOL3}{CLASS}{SEQ4}", "example": "2026GNK041"},
    ]
    if config:
        return {"config": {
            "format_template": config.format_template,
            "school_code": config.school_code or "",
            "use_base36": config.use_base36,
            "current_sequence": config.current_sequence or 0,
            "current_year": config.current_year,
        }, "presets": presets}
    return {"config": None, "presets": presets}


@router.post("/registration-config")
async def save_registration_config(request: Request, db: AsyncSession = Depends(get_db)):
    """Save registration ID format and generate a preview."""
    user = await verify_school_admin(request)
    branch_id = get_branch_id(user)
    data = await request.json()

    config = await db.scalar(
        select(RegistrationNumberConfig).where(RegistrationNumberConfig.branch_id == branch_id))
    if not config:
        config = RegistrationNumberConfig(branch_id=branch_id)
        db.add(config)

    config.format_template = data.get("format_template", "{SCHOOL4}{YY}{SEQ4}")
    if data.get("school_code"):
        config.school_code = data["school_code"].upper().strip()
    config.use_base36 = data.get("use_base36", False)
    await db.flush()

    # Generate preview (creates a temp ID then rolls back sequence)
    preview = await generate_student_registration_id(
        db=db, branch_id=str(branch_id),
        admission_year=date.today().year, class_name="Class 4", gender="male")
    # Roll back the sequence bump from preview
    config.current_sequence = max((config.current_sequence or 1) - 1, 0)
    await db.commit()
    return {"success": True, "preview": preview, "message": f"Format saved. Preview: {preview}"}


# ─── 3. Add this endpoint for student photo upload ───

@router.post("/students/{student_id}/photo")
async def upload_student_photo(request: Request, student_id: str, db: AsyncSession = Depends(get_db)):
    """Upload student profile photo — stored as photo_url on student record."""
    user = await get_current_user(request)
    if not user: return {"error": "unauthorized"}
    import aiofiles
    form = await request.form()
    file = form.get("file")
    if not file: return {"error": "No file"}
    
    contents = await file.read()
    if len(contents) > 512000:
        raise HTTPException(400, "Photo must be under 500KB")
    
    upload_dir = os.path.join("static", "uploads", "student_photos")
    os.makedirs(upload_dir, exist_ok=True)
    ext = "jpg" if "jpeg" in (file.content_type or "") else "png"
    filename = f"{student_id}.{ext}"
    filepath = os.path.join(upload_dir, filename)
    
    async with aiofiles.open(filepath, 'wb') as f:
        await f.write(contents)
    
    # Update student record
    student = await db.scalar(select(Student).where(Student.id == uuid.UUID(student_id)))
    if student:
        student.photo_url = f"/{filepath}"
        await db.commit()
    
    return {"photo_url": f"/{filepath}", "message": "Photo uploaded"}

class EmployeeOnboardData(BaseModel):
    first_name: str
    last_name: Optional[str] = ""
    date_of_birth: Optional[str] = None
    gender: Optional[str] = None
    blood_group: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    aadhaar_number: Optional[str] = None
    pan_number: Optional[str] = None
    address: Optional[str] = None
    employee_type: Optional[str] = "teaching"
    designation: Optional[str] = None
    department: Optional[str] = None
    date_of_joining: Optional[str] = None
    employment_type: Optional[str] = "Permanent"
    qualification: Optional[str] = None
    specialization: Optional[str] = None
    university: Optional[str] = None
    bed: Optional[str] = None
    ctet: Optional[str] = None
    net: Optional[str] = None
    previous_experience: Optional[int] = 0
    previous_school: Optional[str] = None
    basic_salary: Optional[int] = 0
    hra: Optional[int] = 0
    da: Optional[int] = 0
    bank_name: Optional[str] = None
    bank_account: Optional[str] = None
    bank_ifsc: Optional[str] = None
    emergency_contact_name: Optional[str] = None

@router.post("/hr/employees")
async def create_employee_from_onboarding(data: EmployeeOnboardData, request: Request, db: AsyncSession = Depends(get_db)):
    try:
        await db.rollback()
    except Exception:
        pass

    user = await verify_school_admin(request)
    branch_id = get_branch_id(user)

    from sqlalchemy import text as sql_text
    from datetime import date, datetime
    import uuid as uuid_mod

    # 1. Generate Employee ID
    branch_prefix = "EMP"
    try:
        br_row = await db.execute(sql_text("SELECT name, short_code FROM branches WHERE id = :bid"), {"bid": str(branch_id)})
        br = br_row.first()
        if br:
            if hasattr(br, 'short_code') and br.short_code:
                branch_prefix = br.short_code.upper()
            elif br.name:
                words = br.name.strip().split()
                branch_prefix = ''.join(w[0].upper() for w in words[:3])
    except Exception:
        pass

    type_prefix = {"teaching":"T","non_teaching":"N","admin":"A","support":"S"}.get(data.employee_type, "T")
    seq = await db.execute(sql_text("SELECT COUNT(*) FROM teachers WHERE branch_id = :bid"), {"bid": str(branch_id)})
    next_num = (seq.scalar() or 0) + 1
    employee_id = f"{branch_prefix}-{type_prefix}-{next_num:03d}"
    while True:
        chk = await db.execute(sql_text("SELECT id FROM teachers WHERE employee_id = :eid AND branch_id = :bid"), {"eid": employee_id, "bid": str(branch_id)})
        if not chk.first(): break
        next_num += 1
        employee_id = f"{branch_prefix}-{type_prefix}-{next_num:03d}"

    # 2. Short designation
    short_desig = data.designation or "Teacher"
    if data.designation and "(" in data.designation:
        short_desig = data.designation.split("(")[0].strip()

    # 3. Employment type mapping
    emp_map = {"Permanent":"permanent","Contractual":"contractual","Probation":"contractual","Part-Time":"contractual","Guest Faculty":"guest"}
    mapped_emp = emp_map.get(data.employment_type, "permanent")

    # 4. Parse joining date
    joining_date = None
    if data.date_of_joining:
        try: joining_date = datetime.strptime(data.date_of_joining, "%Y-%m-%d").date()
        except: joining_date = date.today()

    # 5. Qualification string
    qp = []
    if data.qualification: qp.append(data.qualification)
    if data.bed and data.bed not in ("","no"): qp.append("B.Ed")
    if data.ctet and data.ctet not in ("","no"):
        cm = {"ctet1":"CTET-I","ctet2":"CTET-II","both":"CTET (I+II)","stet":"STET"}
        qp.append(cm.get(data.ctet, data.ctet))
    if data.net and data.net not in ("","None"): qp.append(data.net)
    qual_str = ", ".join(qp) if qp else data.qualification

    # 6. Phone — frontend now sends ISD code prefix (+91XXXXXXXXXX)
    phone = data.phone or ""
    if phone and not phone.startswith("+"):
        phone = "+91" + phone

    # 7. Create Teacher
    teacher_id = str(uuid_mod.uuid4())
    try:
        await db.execute(sql_text("""
            INSERT INTO teachers (id, branch_id, first_name, last_name, employee_id,
                designation, email, phone, qualification, specialization,
                experience_years, joining_date, address, is_active,
                work_status, employment_type, created_at, updated_at)
            VALUES (:id, :bid, :fname, :lname, :eid, :desig, :email, :phone,
                :qual, :spec, :exp, :doj, :address, true, 'available', :emp_type, NOW(), NOW())
        """), {"id": teacher_id, "bid": str(branch_id), "fname": data.first_name, "lname": data.last_name or "",
               "eid": employee_id, "desig": short_desig, "email": data.email or None, "phone": phone,
               "qual": qual_str, "spec": data.specialization or data.department,
               "exp": data.previous_experience or 0, "doj": joining_date,
               "address": data.address or "", "emp_type": mapped_emp})
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed: {str(e)}")

    # 8. Create User for login
    try:
        user_id = str(uuid_mod.uuid4())
        role = "school_admin" if data.employee_type == "admin" else "teacher"
        await db.execute(sql_text("""
            INSERT INTO users (id, name, email, phone, role, branch_id, is_active, created_at, updated_at)
            VALUES (:id, :name, :email, :phone, :role, :bid, true, NOW(), NOW())
        """), {"id": user_id, "name": f"{data.first_name} {data.last_name or ''}".strip(),
               "email": data.email or None, "phone": phone, "role": role, "bid": str(branch_id)})
        await db.execute(sql_text("UPDATE teachers SET user_id = :uid WHERE id = :tid"), {"uid": user_id, "tid": teacher_id})
    except Exception as e:
        print(f"[WARN] User creation failed for {data.first_name}: {e}")

    await db.commit()
    return {"success": True, "id": teacher_id, "employee_id": employee_id,
            "message": f"Employee {data.first_name} onboarded as {employee_id}"}


# ═══════════════════════════════════════════════════════════
# FEE AUTOMATION SETTINGS
# ═══════════════════════════════════════════════════════════

@router.get("/settings/fee-automation")
async def get_fee_automation_settings(request: Request, db: AsyncSession = Depends(get_db)):
    """Get fee automation configuration for the branch."""
    user = await verify_school_admin(request)
    branch_id = get_branch_id(user)
    from models.branch import BranchSettings

    bs = (await db.execute(
        select(BranchSettings).where(BranchSettings.branch_id == branch_id)
    )).scalar_one_or_none()

    if not bs:
        return {
            "fee_reminder_days": [7, 3, 1],
            "late_fee_percentage": 0,
            "late_fee_after_days": 15,
            "auto_generate_enabled": False,
            "notify_fee_reminder": True,
            "fee_alert_day": 1,
        }

    custom = bs.custom_data or {}
    return {
        "fee_reminder_days": bs.fee_reminder_days or [7, 3, 1],
        "late_fee_percentage": bs.late_fee_percentage or 0,
        "late_fee_after_days": bs.late_fee_after_days or 15,
        "auto_generate_enabled": custom.get("auto_generate_fees", False),
        "notify_fee_reminder": bs.notify_fee_reminder if bs.notify_fee_reminder is not None else True,
        "fee_alert_day": custom.get("fee_alert_day", 1),
    }


@router.post("/settings/fee-automation")
async def save_fee_automation_settings(request: Request, db: AsyncSession = Depends(get_db)):
    """Save fee automation configuration."""
    user = await verify_school_admin(request)
    branch_id = get_branch_id(user)
    body = await request.json()
    from models.branch import BranchSettings
    from sqlalchemy.orm.attributes import flag_modified

    bs = (await db.execute(
        select(BranchSettings).where(BranchSettings.branch_id == branch_id)
    )).scalar_one_or_none()

    if not bs:
        bs = BranchSettings(branch_id=branch_id)
        db.add(bs)

    # Update standard columns
    reminder_days = body.get("fee_reminder_days", [7, 3, 1])
    if isinstance(reminder_days, list) and all(isinstance(d, int) for d in reminder_days):
        bs.fee_reminder_days = sorted(reminder_days, reverse=True)
    bs.late_fee_percentage = max(0, min(100, body.get("late_fee_percentage", 0)))
    bs.late_fee_after_days = max(1, body.get("late_fee_after_days", 15))
    bs.notify_fee_reminder = body.get("notify_fee_reminder", True)

    # Store auto-generate flag + fee alert day in custom_data (no migration)
    custom = bs.custom_data or {}
    custom["auto_generate_fees"] = body.get("auto_generate_enabled", False)
    custom["fee_alert_day"] = body.get("fee_alert_day", 1)
    bs.custom_data = custom
    flag_modified(bs, "custom_data")

    await db.commit()
    return {"success": True, "message": "Fee automation settings saved"}


# ═══════════════════════════════════════════════════════════
# STUDENT ATTENDANCE CALENDAR (for profile page)
# ═══════════════════════════════════════════════════════════

@router.get("/students/{student_id}/attendance-calendar")
async def student_attendance_calendar(
    request: Request, student_id: str,
    month: int = 0, year: int = 0,
    db: AsyncSession = Depends(get_db),
):
    """Day-by-day attendance for a student in a given month. Used by profile calendar widget."""
    user = await get_current_user(request)
    if not user:
        return {"error": "unauthorized"}
    branch_id = uuid.UUID(user["branch_id"])

    from calendar import monthrange
    today = date.today()
    m = month or today.month
    y = year or today.year
    _, days_in_month = monthrange(y, m)
    start_date = date(y, m, 1)
    end_date = date(y, m, days_in_month)

    # Student info
    student = await db.scalar(select(Student).where(Student.id == uuid.UUID(student_id)))
    if not student:
        return {"error": "Student not found"}

    # All attendance records for this student in the month
    records = (await db.execute(
        select(Attendance).where(
            Attendance.student_id == student.id,
            Attendance.date >= start_date,
            Attendance.date <= end_date,
        )
    )).scalars().all()
    att_map = {r.date: r for r in records}

    # Holidays in this month
    holidays_q = (await db.execute(
        select(SchoolEvent).where(
            SchoolEvent.branch_id == branch_id,
            SchoolEvent.is_holiday == True,
            SchoolEvent.start_date <= end_date,
            or_(SchoolEvent.end_date >= start_date, SchoolEvent.end_date == None),
        )
    )).scalars().all()
    holiday_dates = set()
    for h in holidays_q:
        d = max(h.start_date, start_date)
        end_h = min(h.end_date or h.start_date, end_date)
        while d <= end_h:
            holiday_dates.add(d)
            d += timedelta(days=1)

    WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    days = []
    summary = {"present": 0, "absent": 0, "late": 0, "half_day": 0, "excused": 0, "holidays": 0, "total_working": 0}

    for day_num in range(1, days_in_month + 1):
        d = date(y, m, day_num)
        weekday = WEEKDAYS[d.weekday()]
        is_sunday = d.weekday() == 6

        if is_sunday:
            days.append({"day": day_num, "weekday": weekday, "status": None, "is_weekend": True})
            continue

        if d in holiday_dates:
            days.append({"day": day_num, "weekday": weekday, "status": "holiday", "is_holiday": True})
            summary["holidays"] += 1
            continue

        # Future dates
        if d > today:
            days.append({"day": day_num, "weekday": weekday, "status": None, "is_future": True})
            continue

        summary["total_working"] += 1
        rec = att_map.get(d)
        if rec:
            status = rec.status.value
            summary[status] = summary.get(status, 0) + 1
            check_in = rec.check_in_time.strftime("%I:%M %p") if rec.check_in_time else None
            check_out = rec.check_out_time.strftime("%I:%M %p") if rec.check_out_time else None
            days.append({
                "day": day_num, "weekday": weekday, "status": status,
                "check_in": check_in, "check_out": check_out,
                "remarks": rec.remarks,
            })
        else:
            # No record = absent (if school day in the past)
            summary["absent"] += 1
            days.append({"day": day_num, "weekday": weekday, "status": "absent"})

    pct = round(summary["present"] / summary["total_working"] * 100, 1) if summary["total_working"] > 0 else 0
    summary["percentage"] = pct

    return {
        "student_name": student.full_name,
        "month": m, "year": y,
        "summary": summary,
        "days": days,
    }


# ═══════════════════════════════════════════════════════════
# TEACHER FULL PROFILE API (for profile page)
# ═══════════════════════════════════════════════════════════

@router.get("/teachers/{teacher_id}/profile-full")
async def teacher_profile_full(
    request: Request, teacher_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Comprehensive teacher profile: details + assignments + awards + attendance summary."""
    user = await get_current_user(request)
    if not user:
        return {"error": "unauthorized"}
    branch_id = uuid.UUID(user["branch_id"])

    try:
        teacher = await db.scalar(select(Teacher).where(Teacher.id == uuid.UUID(teacher_id)))
    except Exception:
        return {"error": "Invalid teacher ID"}
    if not teacher:
        return {"error": "Teacher not found"}

    # Class teacher of
    ct_label = ""
    if teacher.class_teacher_of:
        from models.academic import Section as Sec2
        sec = await db.scalar(select(Sec2).where(Sec2.id == teacher.class_teacher_of))
        if sec:
            cls = await db.scalar(select(Class.name).where(Class.id == sec.class_id))
            ct_label = f"{cls or ''}-{sec.name}"

    # Teaching assignments (use raw SQL — same pattern as existing get_teacher_assignments)
    from sqlalchemy import text as sql_text
    assignments = []
    try:
        rows = await db.execute(sql_text("""
            SELECT c.name as class_name, sec.name as section_name, sub.name as subject_name
            FROM teacher_class_assignments tca
            JOIN classes c ON c.id = tca.class_id
            LEFT JOIN sections sec ON sec.id = tca.section_id
            LEFT JOIN subjects sub ON sub.id = tca.subject_id
            WHERE tca.teacher_id = :tid AND tca.branch_id = :bid AND tca.is_active = true
            ORDER BY c.name, sec.name
        """), {"tid": str(teacher.id), "bid": str(branch_id)})
        for r in rows.mappings():
            assignments.append({
                "class_name": r["class_name"] or "",
                "section_name": r["section_name"] or "",
                "subject_name": r["subject_name"] or "",
            })
    except Exception as e:
        print(f"[WARN] Teacher assignments query failed: {e}")
        # Fallback: try class_subjects table
        try:
            from models.academic import ClassSubject, Subject as Subj2
            cs_rows = (await db.execute(
                select(ClassSubject).where(ClassSubject.teacher_id == teacher.id)
            )).scalars().all()
            for cs in cs_rows:
                cls_name = await db.scalar(select(Class.name).where(Class.id == cs.class_id)) or ""
                sub_name = await db.scalar(select(Subj2.name).where(Subj2.id == cs.subject_id)) or ""
                assignments.append({"class_name": cls_name, "section_name": "", "subject_name": sub_name})
        except Exception:
            pass

    # House (if teacher is a house master)
    house_name, house_color = "", ""
    try:
        from models.mega_modules import House
        house = await db.scalar(select(House).where(
            House.house_master_id == teacher.id, House.is_active == True))
        if house:
            house_name, house_color = house.name or "", house.color or ""
    except Exception:
        pass

    # Awards
    from models.teacher_award import TeacherAward
    MONTHS = ['', 'January', 'February', 'March', 'April', 'May', 'June',
              'July', 'August', 'September', 'October', 'November', 'December']
    awards_raw = (await db.execute(
        select(TeacherAward).where(
            TeacherAward.teacher_id == teacher.id,
            TeacherAward.status == "awarded",
        ).order_by(TeacherAward.awarded_at.desc()).limit(10)
    )).scalars().all()
    awards = [{
        "title": a.title, "award_type": a.award_type,
        "month": MONTHS[a.month] if a.month else "", "year": a.year,
        "prize": a.prize_details or "", "description": a.description or "",
    } for a in awards_raw]

    # Attendance summary — this month
    today = date.today()
    month_start = today.replace(day=1)
    from models.teacher_attendance import TeacherAttendance, TeacherAttendanceStatus
    month_att = (await db.execute(
        select(TeacherAttendance).where(
            TeacherAttendance.teacher_id == teacher.id,
            TeacherAttendance.date >= month_start,
            TeacherAttendance.date <= today,
        )
    )).scalars().all()

    this_month = {"present": 0, "absent": 0, "late": 0, "on_leave": 0, "half_day": 0}
    for a in month_att:
        this_month[a.status.value] = this_month.get(a.status.value, 0) + 1
    total_m = sum(this_month.values())
    this_month["percentage"] = round(this_month["present"] / total_m * 100, 1) if total_m > 0 else 0

    # Overall attendance (all time)
    overall_total = await db.scalar(
        select(func.count(TeacherAttendance.id)).where(TeacherAttendance.teacher_id == teacher.id)
    ) or 0
    overall_present = await db.scalar(
        select(func.count(TeacherAttendance.id)).where(
            TeacherAttendance.teacher_id == teacher.id,
            TeacherAttendance.status == TeacherAttendanceStatus.PRESENT,
        )
    ) or 0

    return {
        "teacher": {
            "id": str(teacher.id), "full_name": teacher.full_name,
            "employee_id": teacher.employee_id or "",
            "designation": teacher.designation or "",
            "qualification": teacher.qualification or "",
            "specialization": teacher.specialization or "",
            "experience_years": teacher.experience_years or 0,
            "joining_date": teacher.joining_date.isoformat() if teacher.joining_date else "",
            "phone": teacher.phone or "", "email": teacher.email or "",
            "photo_url": teacher.photo_url or "",
            "address": teacher.address or "",
            "city": getattr(teacher, 'city', '') or "",
            "state": getattr(teacher, 'state', '') or "",
            "pincode": getattr(teacher, 'pincode', '') or "",
            "emergency_contact": getattr(teacher, 'emergency_contact', '') or "",
            "emergency_contact_name": getattr(teacher, 'emergency_contact_name', '') or "",
            "uses_transport": getattr(teacher, 'uses_transport', False) or False,
            "transport_route": getattr(teacher, 'transport_route', '') or "",
            "is_class_teacher": teacher.is_class_teacher,
            "class_teacher_of": ct_label,
            "work_status": teacher.work_status or "available",
            "is_active": teacher.is_active,
            "house_name": house_name, "house_color": house_color,
            "updated_at": teacher.updated_at.strftime("%d %b %Y %I:%M %p") if teacher.updated_at else "",
            "created_at": teacher.created_at.strftime("%d %b %Y") if teacher.created_at else "",
        },
        "assignments": assignments,
        "awards": awards,
        "attendance_summary": {
            "this_month": this_month,
            "overall": {
                "total_days": overall_total, "present": overall_present,
                "percentage": round(overall_present / overall_total * 100, 1) if overall_total > 0 else 0,
            },
        },
    }


# ═══════════════════════════════════════════════════════════
# TEACHER ATTENDANCE CALENDAR (for profile page)
# ═══════════════════════════════════════════════════════════

@router.get("/teachers/{teacher_id}/attendance-calendar")
async def teacher_attendance_calendar(
    request: Request, teacher_id: str,
    month: int = 0, year: int = 0,
    db: AsyncSession = Depends(get_db),
):
    """Day-by-day teacher attendance for calendar widget. Includes check-in/check-out times."""
    user = await get_current_user(request)
    if not user:
        return {"error": "unauthorized"}
    branch_id = uuid.UUID(user["branch_id"])

    from calendar import monthrange
    from models.teacher_attendance import TeacherAttendance
    today = date.today()
    m = month or today.month
    y = year or today.year
    _, days_in_month = monthrange(y, m)
    start_date = date(y, m, 1)
    end_date = date(y, m, days_in_month)

    teacher = await db.scalar(select(Teacher).where(Teacher.id == uuid.UUID(teacher_id)))
    if not teacher:
        return {"error": "Teacher not found"}

    records = (await db.execute(
        select(TeacherAttendance).where(
            TeacherAttendance.teacher_id == teacher.id,
            TeacherAttendance.date >= start_date,
            TeacherAttendance.date <= end_date,
        )
    )).scalars().all()
    att_map = {r.date: r for r in records}

    # Holidays
    holidays_q = (await db.execute(
        select(SchoolEvent).where(
            SchoolEvent.branch_id == branch_id,
            SchoolEvent.is_holiday == True,
            SchoolEvent.start_date <= end_date,
            or_(SchoolEvent.end_date >= start_date, SchoolEvent.end_date == None),
        )
    )).scalars().all()
    holiday_dates = set()
    for h in holidays_q:
        d = max(h.start_date, start_date)
        end_h = min(h.end_date or h.start_date, end_date)
        while d <= end_h:
            holiday_dates.add(d)
            d += timedelta(days=1)

    WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    days = []
    summary = {"present": 0, "absent": 0, "late": 0, "half_day": 0, "on_leave": 0, "holidays": 0, "total_working": 0}

    for day_num in range(1, days_in_month + 1):
        d = date(y, m, day_num)
        weekday = WEEKDAYS[d.weekday()]
        is_sunday = d.weekday() == 6

        if is_sunday:
            days.append({"day": day_num, "weekday": weekday, "status": None, "is_weekend": True})
            continue
        if d in holiday_dates:
            days.append({"day": day_num, "weekday": weekday, "status": "holiday", "is_holiday": True})
            summary["holidays"] += 1
            continue
        if d > today:
            days.append({"day": day_num, "weekday": weekday, "status": None, "is_future": True})
            continue

        summary["total_working"] += 1
        rec = att_map.get(d)
        if rec:
            status = rec.status.value
            summary[status] = summary.get(status, 0) + 1
            check_in = rec.check_in_time.strftime("%I:%M %p") if rec.check_in_time else None
            check_out = rec.check_out_time.strftime("%I:%M %p") if rec.check_out_time else None
            days.append({
                "day": day_num, "weekday": weekday, "status": status,
                "check_in": check_in, "check_out": check_out,
                "remarks": rec.remarks, "source": rec.source.value if rec.source else None,
            })
        else:
            summary["absent"] += 1
            days.append({"day": day_num, "weekday": weekday, "status": "absent"})

    pct = round(summary["present"] / summary["total_working"] * 100, 1) if summary["total_working"] > 0 else 0
    summary["percentage"] = pct

    return {
        "teacher_name": teacher.full_name,
        "month": m, "year": y,
        "summary": summary,
        "days": days,
    }


# ═══════════════════════════════════════════════════════════
# PHOTO UPLOAD WITH APPROVAL WORKFLOW
# ═══════════════════════════════════════════════════════════

@router.post("/teachers/{teacher_id}/photo")
async def upload_teacher_photo(request: Request, teacher_id: str, db: AsyncSession = Depends(get_db)):
    """Upload teacher profile photo — stored as photo_url on teacher record."""
    user = await get_current_user(request)
    if not user:
        raise HTTPException(401, "Unauthorized")
    import aiofiles
    form = await request.form()
    file = form.get("file")
    if not file:
        raise HTTPException(400, "No file")

    contents = await file.read()
    if len(contents) > 512000:
        raise HTTPException(400, "Photo must be under 500KB")

    upload_dir = os.path.join("static", "uploads", "teacher_photos")
    os.makedirs(upload_dir, exist_ok=True)
    ext = "jpg" if "jpeg" in (file.content_type or "") else "png"
    filename = f"{teacher_id}.{ext}"
    filepath = os.path.join(upload_dir, filename)

    async with aiofiles.open(filepath, 'wb') as f:
        await f.write(contents)

    teacher = await db.scalar(select(Teacher).where(Teacher.id == uuid.UUID(teacher_id)))
    if teacher:
        teacher.photo_url = f"/{filepath}"
        await db.commit()

    return {"photo_url": f"/{filepath}", "message": "Photo uploaded"}


@router.post("/employees/{employee_id}/photo")
async def upload_employee_photo(request: Request, employee_id: str, db: AsyncSession = Depends(get_db)):
    """Upload employee (non-teaching staff) profile photo."""
    user = await get_current_user(request)
    if not user:
        raise HTTPException(401, "Unauthorized")
    from models.employee import Employee
    import aiofiles
    form = await request.form()
    file = form.get("file")
    if not file:
        raise HTTPException(400, "No file")

    contents = await file.read()
    if len(contents) > 512000:
        raise HTTPException(400, "Photo must be under 500KB")

    upload_dir = os.path.join("static", "uploads", "employee_photos")
    os.makedirs(upload_dir, exist_ok=True)
    ext = "jpg" if "jpeg" in (file.content_type or "") else "png"
    filename = f"{employee_id}.{ext}"
    filepath = os.path.join(upload_dir, filename)

    async with aiofiles.open(filepath, 'wb') as f:
        await f.write(contents)

    emp = await db.scalar(select(Employee).where(Employee.id == uuid.UUID(employee_id)))
    if emp:
        emp.photo_url = f"/{filepath}"
        await db.commit()

    return {"photo_url": f"/{filepath}", "message": "Photo uploaded"}


@router.post("/photo-request")
async def submit_photo_change_request(request: Request, db: AsyncSession = Depends(get_db)):
    """Student/Teacher/Staff submits a photo for admin approval."""
    user = await get_current_user(request)
    if not user:
        raise HTTPException(401, "Unauthorized")
    from models.photo_request import PhotoChangeRequest, PhotoApprovalStatus
    import aiofiles

    form = await request.form()
    file = form.get("file")
    entity_type = form.get("entity_type", "student")  # student, teacher, employee
    entity_id = form.get("entity_id", "")
    if not file or not entity_id:
        raise HTTPException(400, "Missing file or entity_id")

    contents = await file.read()
    if len(contents) > 512000:
        raise HTTPException(400, "Photo must be under 500KB")

    branch_id = uuid.UUID(user["branch_id"])

    # Get current photo
    current_photo = None
    if entity_type == "student":
        s = await db.scalar(select(Student).where(Student.id == uuid.UUID(entity_id)))
        current_photo = s.photo_url if s else None
    elif entity_type == "teacher":
        t = await db.scalar(select(Teacher).where(Teacher.id == uuid.UUID(entity_id)))
        current_photo = t.photo_url if t else None
    else:
        from models.employee import Employee
        e = await db.scalar(select(Employee).where(Employee.id == uuid.UUID(entity_id)))
        current_photo = e.photo_url if e else None

    upload_dir = os.path.join("static", "uploads", "photo_requests")
    os.makedirs(upload_dir, exist_ok=True)
    ext = "jpg" if "jpeg" in (file.content_type or "") else "png"
    filename = f"{entity_type}_{entity_id}_{uuid.uuid4().hex[:8]}.{ext}"
    filepath = os.path.join(upload_dir, filename)

    async with aiofiles.open(filepath, 'wb') as f:
        await f.write(contents)

    req = PhotoChangeRequest(
        branch_id=branch_id,
        entity_type=entity_type,
        entity_id=uuid.UUID(entity_id),
        requested_by=uuid.UUID(user["id"]),
        current_photo_url=current_photo,
        new_photo_url=f"/{filepath}",
    )
    db.add(req)
    await db.commit()

    return {"success": True, "message": "Photo change request submitted for admin approval", "request_id": str(req.id)}


@router.get("/photo-requests")
async def list_photo_requests(request: Request, db: AsyncSession = Depends(get_db)):
    """Admin: list pending photo change requests."""
    user = await verify_school_admin(request)
    branch_id = get_branch_id(user)
    from models.photo_request import PhotoChangeRequest, PhotoApprovalStatus

    result = await db.execute(
        select(PhotoChangeRequest)
        .where(PhotoChangeRequest.branch_id == branch_id, PhotoChangeRequest.status == PhotoApprovalStatus.PENDING)
        .order_by(PhotoChangeRequest.created_at.desc())
    )
    reqs = result.scalars().all()

    items = []
    for r in reqs:
        name = ""
        if r.entity_type == "student":
            s = await db.scalar(select(Student).where(Student.id == r.entity_id))
            name = s.full_name if s else "Unknown"
        elif r.entity_type == "teacher":
            t = await db.scalar(select(Teacher).where(Teacher.id == r.entity_id))
            name = t.full_name if t else "Unknown"
        else:
            from models.employee import Employee
            e = await db.scalar(select(Employee).where(Employee.id == r.entity_id))
            name = f"{e.first_name} {e.last_name or ''}".strip() if e else "Unknown"

        items.append({
            "id": str(r.id),
            "entity_type": r.entity_type,
            "entity_id": str(r.entity_id),
            "name": name,
            "current_photo_url": r.current_photo_url or "",
            "new_photo_url": r.new_photo_url,
            "created_at": r.created_at.strftime("%d %b %Y %I:%M %p") if r.created_at else "",
        })

    return {"requests": items, "count": len(items)}


@router.post("/photo-requests/{request_id}/approve")
async def approve_photo_request(request_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    """Admin approves photo change — updates the entity's photo_url."""
    user = await verify_school_admin(request)
    from models.photo_request import PhotoChangeRequest, PhotoApprovalStatus
    from datetime import datetime

    req = await db.scalar(select(PhotoChangeRequest).where(PhotoChangeRequest.id == uuid.UUID(request_id)))
    if not req:
        raise HTTPException(404, "Request not found")

    req.status = PhotoApprovalStatus.APPROVED
    req.reviewed_by = uuid.UUID(user["id"])
    req.reviewed_at = datetime.utcnow()

    # Apply the new photo to the entity
    if req.entity_type == "student":
        s = await db.scalar(select(Student).where(Student.id == req.entity_id))
        if s:
            s.photo_url = req.new_photo_url
    elif req.entity_type == "teacher":
        t = await db.scalar(select(Teacher).where(Teacher.id == req.entity_id))
        if t:
            t.photo_url = req.new_photo_url
    else:
        from models.employee import Employee
        e = await db.scalar(select(Employee).where(Employee.id == req.entity_id))
        if e:
            e.photo_url = req.new_photo_url

    await db.commit()
    return {"success": True, "message": "Photo approved and updated"}


@router.post("/photo-requests/{request_id}/reject")
async def reject_photo_request(request_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    """Admin rejects photo change."""
    user = await verify_school_admin(request)
    from models.photo_request import PhotoChangeRequest, PhotoApprovalStatus
    from datetime import datetime

    req = await db.scalar(select(PhotoChangeRequest).where(PhotoChangeRequest.id == uuid.UUID(request_id)))
    if not req:
        raise HTTPException(404, "Request not found")

    body = await request.json()
    req.status = PhotoApprovalStatus.REJECTED
    req.reviewed_by = uuid.UUID(user["id"])
    req.reviewed_at = datetime.utcnow()
    req.rejection_reason = body.get("reason", "")
    await db.commit()
    return {"success": True, "message": "Photo request rejected"}


# ═══════════════════════════════════════════════════════════
# SCHOOL BRANDING — LOGO UPLOAD & THEME COLOR
# ═══════════════════════════════════════════════════════════

@router.post("/branding/logo")
async def upload_school_logo(request: Request, db: AsyncSession = Depends(get_db)):
    """Upload/update school logo for the branch."""
    user = await verify_school_admin(request)
    branch_id = get_branch_id(user)
    from models.branch import Branch
    import aiofiles

    form = await request.form()
    file = form.get("file")
    if not file:
        raise HTTPException(400, "No file")

    contents = await file.read()
    if len(contents) > 1024000:
        raise HTTPException(400, "Logo must be under 1MB")

    upload_dir = os.path.join("static", "uploads", "logos")
    os.makedirs(upload_dir, exist_ok=True)
    ext = "png" if "png" in (file.content_type or "") else "jpg"
    filename = f"logo_{branch_id}.{ext}"
    filepath = os.path.join(upload_dir, filename)

    async with aiofiles.open(filepath, 'wb') as f:
        await f.write(contents)

    branch = await db.scalar(select(Branch).where(Branch.id == branch_id))
    if branch:
        branch.logo_url = f"/{filepath}"
        await db.commit()

    return {"logo_url": f"/{filepath}", "message": "Logo uploaded"}


@router.get("/branding")
async def get_branding(request: Request, db: AsyncSession = Depends(get_db)):
    """Get current branding settings (logo, theme color, school details)."""
    user = await get_current_user(request)
    if not user:
        return {"error": "unauthorized"}
    branch_id = uuid.UUID(user["branch_id"])
    from models.branch import Branch, BranchSettings

    branch = await db.scalar(select(Branch).where(Branch.id == branch_id))
    settings = await db.scalar(select(BranchSettings).where(BranchSettings.branch_id == branch_id))

    return {
        "logo_url": branch.logo_url or "" if branch else "",
        "school_name": branch.name if branch else "",
        "motto": branch.motto or "" if branch else "",
        "theme_color": settings.theme_color if settings else "#4F46E5",
        "language": settings.language if settings else "en",
    }


@router.put("/branding/theme")
async def update_theme_color(request: Request, db: AsyncSession = Depends(get_db)):
    """Update the school's theme color."""
    user = await verify_school_admin(request)
    branch_id = get_branch_id(user)
    from models.branch import BranchSettings

    body = await request.json()
    color = body.get("theme_color", "#4F46E5")

    # Validate hex color
    import re
    if not re.match(r'^#[0-9A-Fa-f]{6}$', color):
        raise HTTPException(400, "Invalid color format. Use #RRGGBB")

    settings = await db.scalar(select(BranchSettings).where(BranchSettings.branch_id == branch_id))
    if settings:
        settings.theme_color = color
    else:
        settings = BranchSettings(branch_id=branch_id, theme_color=color)
        db.add(settings)
    await db.commit()
    return {"success": True, "theme_color": color}


# ══════════════════════════════════════════════════════════════
#   REPORTS CENTER — All report generation endpoints
# ══════════════════════════════════════════════════════════════

@router.get("/reports/student-attendance")
async def report_student_attendance(
    request: Request,
    class_id: str = None, section_id: str = None,
    month: int = None, year: int = None,
    db: AsyncSession = Depends(get_db),
):
    """Student attendance report: per-student present/absent/late counts for a month."""
    user = await verify_school_admin(request)
    branch_id = user.get("branch_id")
    from datetime import datetime
    import calendar
    now = datetime.utcnow()
    m = month or now.month
    y = year or now.year
    first_day = date(y, m, 1)
    last_day = date(y, m, calendar.monthrange(y, m)[1])

    from models.student import Student as S
    from models.academic import Class as Cls, Section as Sec

    # Build student query
    sq = select(S).where(S.branch_id == branch_id, S.is_active == True)
    if class_id:
        sq = sq.where(S.class_id == class_id)
    if section_id:
        sq = sq.where(S.section_id == section_id)
    sq = sq.order_by(S.class_id, S.roll_number)
    students = (await db.execute(sq)).scalars().all()

    if not students:
        return {"report_name": "Student Attendance Report", "month": m, "year": y,
                "summary": {}, "columns": [], "rows": [], "total": 0}

    sids = [s.id for s in students]

    # Fetch attendance records
    att_q = select(Attendance).where(
        Attendance.branch_id == branch_id,
        Attendance.date >= first_day,
        Attendance.date <= last_day,
        Attendance.student_id.in_(sids),
    )
    atts = (await db.execute(att_q)).scalars().all()

    # Build lookup: student_id → list of statuses
    att_map = {}
    for a in atts:
        att_map.setdefault(str(a.student_id), []).append(a.status.value if a.status else "present")

    # Fetch class/section names
    cls_map = {}
    sec_map = {}
    cls_ids = set(str(s.class_id) for s in students if s.class_id)
    sec_ids = set(str(s.section_id) for s in students if s.section_id)
    if cls_ids:
        for c in (await db.execute(select(Cls).where(Cls.id.in_([uuid.UUID(x) for x in cls_ids])))).scalars().all():
            cls_map[str(c.id)] = c.name
    if sec_ids:
        for s in (await db.execute(select(Sec).where(Sec.id.in_([uuid.UUID(x) for x in sec_ids])))).scalars().all():
            sec_map[str(s.id)] = s.name

    working_days = len(set(str(a.student_id) + str(a.date) for a in atts)) // max(len(sids), 1) if atts else 0
    # Better: count distinct dates
    distinct_dates = set(a.date for a in atts)
    working_days = len(distinct_dates)

    rows = []
    total_present = 0
    total_absent = 0
    for st in students:
        sid = str(st.id)
        statuses = att_map.get(sid, [])
        present = sum(1 for s in statuses if s == "present")
        absent = sum(1 for s in statuses if s == "absent")
        late = sum(1 for s in statuses if s == "late")
        half_day = sum(1 for s in statuses if s == "half_day")
        excused = sum(1 for s in statuses if s == "excused")
        total = present + absent + late + half_day + excused
        pct = round((present + late + half_day) / total * 100, 1) if total else 0
        total_present += present + late + half_day
        total_absent += absent
        rows.append({
            "name": st.full_name,
            "roll_no": st.roll_number or "",
            "class": cls_map.get(str(st.class_id), ""),
            "section": sec_map.get(str(st.section_id), ""),
            "present": present,
            "absent": absent,
            "late": late,
            "half_day": half_day,
            "excused": excused,
            "total_days": total,
            "percentage": pct,
        })

    overall_pct = round(total_present / (total_present + total_absent) * 100, 1) if (total_present + total_absent) else 0

    return {
        "report_name": "Student Attendance Report",
        "month": m, "year": y, "working_days": working_days,
        "summary": {"total_students": len(rows), "avg_attendance": overall_pct},
        "columns": ["Name", "Roll No", "Class", "Section", "Present", "Absent", "Late", "Half Day", "Excused", "Total Days", "Attendance %"],
        "rows": rows,
        "total": len(rows),
    }


@router.get("/reports/teacher-attendance")
async def report_teacher_attendance(
    request: Request,
    month: int = None, year: int = None,
    db: AsyncSession = Depends(get_db),
):
    """Teacher attendance report: per-teacher present/absent/late/leave counts."""
    user = await verify_school_admin(request)
    branch_id = user.get("branch_id")
    from datetime import datetime
    import calendar
    from models.teacher_attendance import TeacherAttendance as TA
    from models.teacher import Teacher as T

    now = datetime.utcnow()
    m = month or now.month
    y = year or now.year
    first_day = date(y, m, 1)
    last_day = date(y, m, calendar.monthrange(y, m)[1])

    teachers = (await db.execute(
        select(T).where(T.branch_id == branch_id, T.is_active == True).order_by(T.first_name)
    )).scalars().all()

    if not teachers:
        return {"report_name": "Teacher Attendance Report", "month": m, "year": y,
                "summary": {}, "columns": [], "rows": [], "total": 0}

    tids = [t.id for t in teachers]
    atts = (await db.execute(
        select(TA).where(TA.branch_id == branch_id, TA.date >= first_day, TA.date <= last_day, TA.teacher_id.in_(tids))
    )).scalars().all()

    att_map = {}
    for a in atts:
        att_map.setdefault(str(a.teacher_id), []).append(a.status.value if a.status else "present")

    rows = []
    for t in teachers:
        tid = str(t.id)
        statuses = att_map.get(tid, [])
        present = sum(1 for s in statuses if s == "present")
        absent = sum(1 for s in statuses if s == "absent")
        late = sum(1 for s in statuses if s == "late")
        on_leave = sum(1 for s in statuses if s == "on_leave")
        half_day = sum(1 for s in statuses if s == "half_day")
        total = present + absent + late + on_leave + half_day
        pct = round((present + late + half_day) / total * 100, 1) if total else 0
        rows.append({
            "name": t.full_name,
            "employee_id": t.employee_id or "",
            "designation": t.designation or "",
            "present": present,
            "absent": absent,
            "late": late,
            "on_leave": on_leave,
            "half_day": half_day,
            "total_days": total,
            "percentage": pct,
        })

    return {
        "report_name": "Teacher Attendance Report",
        "month": m, "year": y,
        "summary": {"total_teachers": len(rows)},
        "columns": ["Name", "Employee ID", "Designation", "Present", "Absent", "Late", "On Leave", "Half Day", "Total Days", "Attendance %"],
        "rows": rows,
        "total": len(rows),
    }


@router.get("/reports/academic-performance")
async def report_academic_performance(
    request: Request,
    exam_id: str = None, class_id: str = None, section_id: str = None,
    threshold: str = "all",
    db: AsyncSession = Depends(get_db),
):
    """Academic performance report: marks, percentages, toppers, below-threshold students.
    threshold: 'all', 'below70', 'below80', 'above90', 'toppers'
    """
    user = await verify_school_admin(request)
    branch_id = user.get("branch_id")
    from models.exam import Exam, ExamSubject, Marks as M
    from models.student import Student as S
    from models.academic import Class as Cls, Section as Sec, Subject as Sub

    # Find latest published exam if none specified
    if not exam_id:
        latest = await db.scalar(
            select(Exam).where(Exam.branch_id == branch_id, Exam.is_published == True)
            .order_by(Exam.start_date.desc())
        )
        if not latest:
            return {"report_name": "Academic Performance Report", "summary": {},
                    "columns": [], "rows": [], "total": 0, "exam_name": "No exams found"}
        exam_id = str(latest.id)

    exam = await db.scalar(select(Exam).where(Exam.id == uuid.UUID(exam_id)))
    exam_name = exam.name if exam else "Exam"

    # Get exam subjects
    es_q = select(ExamSubject).where(ExamSubject.exam_id == uuid.UUID(exam_id))
    if class_id:
        es_q = es_q.where(ExamSubject.class_id == uuid.UUID(class_id))
    exam_subjects = (await db.execute(es_q)).scalars().all()

    if not exam_subjects:
        return {"report_name": "Academic Performance Report", "exam_name": exam_name,
                "summary": {}, "columns": [], "rows": [], "total": 0}

    es_ids = [es.id for es in exam_subjects]

    # Get all marks
    marks = (await db.execute(
        select(M).where(M.exam_subject_id.in_(es_ids))
    )).scalars().all()

    # Build subject name map
    sub_ids = set(es.subject_id for es in exam_subjects if es.subject_id)
    sub_map = {}
    if sub_ids:
        for s in (await db.execute(select(Sub).where(Sub.id.in_(list(sub_ids))))).scalars().all():
            sub_map[str(s.id)] = s.name

    # Build exam_subject map: es_id -> {subject_name, max_marks, class_id}
    es_map = {}
    for es in exam_subjects:
        es_map[str(es.id)] = {
            "subject": sub_map.get(str(es.subject_id), "Unknown"),
            "max_marks": float(es.max_marks) if es.max_marks else 100,
            "class_id": str(es.class_id) if es.class_id else "",
        }

    # Aggregate per student: total marks, total max, subject-wise
    student_data = {}
    for mk in marks:
        sid = str(mk.student_id)
        esid = str(mk.exam_subject_id)
        es_info = es_map.get(esid, {})
        if sid not in student_data:
            student_data[sid] = {"marks_total": 0, "max_total": 0, "subjects": [], "is_absent_any": False}
        obtained = float(mk.marks_obtained) if mk.marks_obtained and not mk.is_absent else 0
        max_m = es_info.get("max_marks", 100)
        student_data[sid]["marks_total"] += obtained
        student_data[sid]["max_total"] += max_m
        student_data[sid]["subjects"].append({
            "subject": es_info.get("subject", ""),
            "obtained": obtained, "max": max_m,
        })
        if mk.is_absent:
            student_data[sid]["is_absent_any"] = True

    # Get student info
    sids_uuid = [uuid.UUID(sid) for sid in student_data.keys()]
    st_q = select(S).where(S.id.in_(sids_uuid))
    if section_id:
        st_q = st_q.where(S.section_id == uuid.UUID(section_id))
    students_list = (await db.execute(st_q)).scalars().all()
    st_map = {str(s.id): s for s in students_list}

    # Class/section maps
    cls_map = {}
    sec_map = {}
    cls_ids = set(str(s.class_id) for s in students_list if s.class_id)
    sec_ids_set = set(str(s.section_id) for s in students_list if s.section_id)
    if cls_ids:
        for c in (await db.execute(select(Cls).where(Cls.id.in_([uuid.UUID(x) for x in cls_ids])))).scalars().all():
            cls_map[str(c.id)] = c.name
    if sec_ids_set:
        for s in (await db.execute(select(Sec).where(Sec.id.in_([uuid.UUID(x) for x in sec_ids_set])))).scalars().all():
            sec_map[str(s.id)] = s.name

    rows = []
    for sid, data in student_data.items():
        st = st_map.get(sid)
        if not st:
            continue
        pct = round(data["marks_total"] / data["max_total"] * 100, 1) if data["max_total"] else 0

        # Apply threshold filter
        if threshold == "below70" and pct >= 70:
            continue
        elif threshold == "below80" and pct >= 80:
            continue
        elif threshold == "above90" and pct < 90:
            continue

        rows.append({
            "name": st.full_name,
            "roll_no": st.roll_number or "",
            "class": cls_map.get(str(st.class_id), ""),
            "section": sec_map.get(str(st.section_id), ""),
            "marks_obtained": round(data["marks_total"], 1),
            "max_marks": round(data["max_total"], 1),
            "percentage": pct,
            "grade": _calc_grade(pct),
            "subjects": data["subjects"],
        })

    # Sort by percentage descending
    rows.sort(key=lambda r: r["percentage"], reverse=True)

    # Add rank
    for i, r in enumerate(rows):
        r["rank"] = i + 1

    # If toppers, limit to top 10
    if threshold == "toppers":
        rows = rows[:10]

    summary = {
        "total_students": len(rows),
        "avg_percentage": round(sum(r["percentage"] for r in rows) / len(rows), 1) if rows else 0,
        "highest": rows[0]["percentage"] if rows else 0,
        "lowest": rows[-1]["percentage"] if rows else 0,
    }

    return {
        "report_name": "Academic Performance Report",
        "exam_name": exam_name,
        "threshold": threshold,
        "summary": summary,
        "columns": ["Rank", "Name", "Roll No", "Class", "Section", "Marks", "Max Marks", "Percentage", "Grade"],
        "rows": rows,
        "total": len(rows),
    }


def _calc_grade(pct):
    if pct >= 90: return "A+"
    if pct >= 80: return "A"
    if pct >= 70: return "B+"
    if pct >= 60: return "B"
    if pct >= 50: return "C"
    if pct >= 40: return "D"
    return "F"


@router.get("/reports/fee-collection")
async def report_fee_collection(
    request: Request,
    class_id: str = None, status: str = "all",
    month: int = None, year: int = None,
    db: AsyncSession = Depends(get_db),
):
    """Fee collection report: student-wise fee status, outstanding, paid amounts.
    status: 'all', 'pending', 'paid', 'overdue', 'partial'
    """
    user = await verify_school_admin(request)
    branch_id = user.get("branch_id")
    from models.fee import FeeRecord as FR, FeeStructure as FS
    from models.student import Student as S
    from models.academic import Class as Cls, Section as Sec

    fr_q = select(FR).where(FR.branch_id == branch_id)
    if status != "all":
        from models.fee import PaymentStatus
        status_map = {"pending": PaymentStatus.PENDING, "paid": PaymentStatus.PAID,
                      "overdue": PaymentStatus.OVERDUE, "partial": PaymentStatus.PARTIAL}
        if status in status_map:
            fr_q = fr_q.where(FR.status == status_map[status])
    if month and year:
        import calendar
        first_day = date(year, month, 1)
        last_day = date(year, month, calendar.monthrange(year, month)[1])
        fr_q = fr_q.where(FR.due_date >= first_day, FR.due_date <= last_day)

    records = (await db.execute(fr_q.order_by(FR.due_date.desc()).limit(1000))).scalars().all()

    # Get student info
    sids = list(set(r.student_id for r in records if r.student_id))
    st_map = {}
    if sids:
        for s in (await db.execute(select(S).where(S.id.in_(sids)))).scalars().all():
            st_map[str(s.id)] = s

    cls_map = {}
    sec_map = {}
    cls_ids = set(str(s.class_id) for s in st_map.values() if s.class_id)
    sec_ids_set = set(str(s.section_id) for s in st_map.values() if s.section_id)
    if cls_ids:
        for c in (await db.execute(select(Cls).where(Cls.id.in_([uuid.UUID(x) for x in cls_ids])))).scalars().all():
            cls_map[str(c.id)] = c.name
    if sec_ids_set:
        for s in (await db.execute(select(Sec).where(Sec.id.in_([uuid.UUID(x) for x in sec_ids_set])))).scalars().all():
            sec_map[str(s.id)] = s.name

    # Get fee structure names
    fs_ids = list(set(str(r.fee_structure_id) for r in records if r.fee_structure_id))
    fs_map = {}
    if fs_ids:
        for f in (await db.execute(select(FS).where(FS.id.in_([uuid.UUID(x) for x in fs_ids])))).scalars().all():
            fs_map[str(f.id)] = f.fee_name

    total_due = 0
    total_paid = 0
    total_outstanding = 0
    rows = []
    for r in records:
        st = st_map.get(str(r.student_id))
        if not st:
            continue
        if class_id and str(st.class_id) != class_id:
            continue
        due = float(r.amount_due or 0)
        paid = float(r.amount_paid or 0)
        outstanding = due - paid
        total_due += due
        total_paid += paid
        total_outstanding += outstanding
        rows.append({
            "name": st.full_name,
            "roll_no": st.roll_number or "",
            "class": cls_map.get(str(st.class_id), ""),
            "section": sec_map.get(str(st.section_id), ""),
            "fee_name": fs_map.get(str(r.fee_structure_id), ""),
            "amount_due": due,
            "amount_paid": paid,
            "outstanding": round(outstanding, 2),
            "status": r.status.value if r.status else "pending",
            "due_date": r.due_date.strftime("%d %b %Y") if r.due_date else "",
            "payment_date": r.payment_date.strftime("%d %b %Y") if r.payment_date else "",
            "payment_mode": r.payment_mode.value if r.payment_mode else "",
        })

    return {
        "report_name": "Fee Collection Report",
        "summary": {
            "total_records": len(rows),
            "total_due": round(total_due, 2),
            "total_collected": round(total_paid, 2),
            "total_outstanding": round(total_outstanding, 2),
            "collection_rate": round(total_paid / total_due * 100, 1) if total_due else 0,
        },
        "columns": ["Name", "Roll No", "Class", "Section", "Fee", "Due", "Paid", "Outstanding", "Status", "Due Date", "Paid Date", "Mode"],
        "rows": rows,
        "total": len(rows),
    }


@router.get("/reports/transport")
async def report_transport(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Transport report: route-wise student assignments, vehicle details."""
    user = await verify_school_admin(request)
    branch_id = user.get("branch_id")
    from models.transport import TransportRoute, Vehicle, StudentTransport, RouteStop
    from models.student import Student as S
    from models.academic import Class as Cls

    routes = (await db.execute(
        select(TransportRoute).where(TransportRoute.branch_id == branch_id, TransportRoute.is_active == True)
    )).scalars().all()

    # Vehicle map
    v_ids = [r.vehicle_id for r in routes if r.vehicle_id]
    v_map = {}
    if v_ids:
        for v in (await db.execute(select(Vehicle).where(Vehicle.id.in_(v_ids)))).scalars().all():
            v_map[str(v.id)] = v

    # Student transport assignments
    r_ids = [r.id for r in routes]
    assignments = []
    if r_ids:
        assignments = (await db.execute(
            select(StudentTransport).where(StudentTransport.route_id.in_(r_ids), StudentTransport.is_active == True)
        )).scalars().all()

    # Route stops
    stop_map = {}
    if r_ids:
        stops = (await db.execute(select(RouteStop).where(RouteStop.route_id.in_(r_ids)))).scalars().all()
        for s in stops:
            stop_map[str(s.id)] = s.stop_name

    # Student info
    s_ids = [a.student_id for a in assignments if a.student_id]
    st_map = {}
    if s_ids:
        for s in (await db.execute(select(S).where(S.id.in_(s_ids)))).scalars().all():
            st_map[str(s.id)] = s
    cls_map = {}
    cls_ids = set(str(s.class_id) for s in st_map.values() if s.class_id)
    if cls_ids:
        for c in (await db.execute(select(Cls).where(Cls.id.in_([uuid.UUID(x) for x in cls_ids])))).scalars().all():
            cls_map[str(c.id)] = c.name

    # Route to student assignments map
    route_students = {}
    for a in assignments:
        rid = str(a.route_id)
        route_students.setdefault(rid, []).append(a)

    rows = []
    total_students = 0
    for r in routes:
        rid = str(r.id)
        vehicle = v_map.get(str(r.vehicle_id)) if r.vehicle_id else None
        assigned = route_students.get(rid, [])
        total_students += len(assigned)

        student_names = []
        for a in assigned:
            st = st_map.get(str(a.student_id))
            if st:
                cls_name = cls_map.get(str(st.class_id), "")
                pickup = stop_map.get(str(a.pickup_stop_id), "") if a.pickup_stop_id else ""
                student_names.append({"name": st.full_name, "class": cls_name, "stop": pickup})

        rows.append({
            "route_name": r.route_name or "",
            "route_number": r.route_number or "",
            "vehicle_number": vehicle.vehicle_number if vehicle else "",
            "vehicle_type": vehicle.vehicle_type if vehicle else "",
            "driver_name": vehicle.driver_name if vehicle else "",
            "driver_phone": vehicle.driver_phone if vehicle else "",
            "capacity": vehicle.capacity if vehicle else 0,
            "students_assigned": len(assigned),
            "monthly_fee": float(r.monthly_fee) if r.monthly_fee else 0,
            "students": student_names,
        })

    return {
        "report_name": "Transport Report",
        "summary": {"total_routes": len(rows), "total_students": total_students},
        "columns": ["Route", "Route No", "Vehicle", "Type", "Driver", "Phone", "Capacity", "Students", "Monthly Fee"],
        "rows": rows,
        "total": len(rows),
    }


@router.get("/reports/houses")
async def report_houses(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """House report: house-wise student count and points."""
    user = await verify_school_admin(request)
    branch_id = user.get("branch_id")
    from models.mega_modules import House, StudentHouse
    from models.student import Student as S
    from models.academic import Class as Cls

    houses = (await db.execute(
        select(House).where(House.branch_id == branch_id, House.is_active == True)
    )).scalars().all()

    if not houses:
        return {"report_name": "House Report", "summary": {}, "columns": [], "rows": [], "total": 0}

    h_ids = [h.id for h in houses]
    sh_all = (await db.execute(
        select(StudentHouse).where(StudentHouse.house_id.in_(h_ids))
    )).scalars().all()

    # Get student info
    s_ids = [sh.student_id for sh in sh_all if sh.student_id]
    st_map = {}
    if s_ids:
        for s in (await db.execute(select(S).where(S.id.in_(s_ids), S.is_active == True))).scalars().all():
            st_map[str(s.id)] = s
    cls_map = {}
    cls_ids = set(str(s.class_id) for s in st_map.values() if s.class_id)
    if cls_ids:
        for c in (await db.execute(select(Cls).where(Cls.id.in_([uuid.UUID(x) for x in cls_ids])))).scalars().all():
            cls_map[str(c.id)] = c.name

    # Build house → students map
    h_students = {}
    for sh in sh_all:
        hid = str(sh.house_id)
        st = st_map.get(str(sh.student_id))
        if st:
            h_students.setdefault(hid, []).append(st)

    rows = []
    for h in houses:
        hid = str(h.id)
        students = h_students.get(hid, [])
        student_list = [{"name": s.full_name, "class": cls_map.get(str(s.class_id), ""), "roll_no": s.roll_number or ""} for s in students]
        rows.append({
            "house_name": h.name,
            "color": h.color or "",
            "points": h.points or 0,
            "student_count": len(students),
            "students": student_list,
        })

    rows.sort(key=lambda r: r["points"], reverse=True)

    return {
        "report_name": "House Report",
        "summary": {"total_houses": len(rows), "total_students": sum(r["student_count"] for r in rows)},
        "columns": ["House", "Color", "Points", "Students"],
        "rows": rows,
        "total": len(rows),
    }


@router.get("/reports/tc-alumni")
async def report_tc_alumni(
    request: Request,
    action: str = "all",
    db: AsyncSession = Depends(get_db),
):
    """TC/Alumni/Separation report: students who left, got TC, dropped out.
    action: 'all', 'tc_issued', 'dropout', 'promoted', 'detained'
    """
    user = await verify_school_admin(request)
    branch_id = user.get("branch_id")
    from models.mega_modules import StudentPromotion
    from models.student import Student as S
    from models.academic import Class as Cls, Section as Sec

    q = select(StudentPromotion).where(StudentPromotion.branch_id == branch_id)
    if action != "all":
        q = q.where(StudentPromotion.action == action)
    q = q.order_by(StudentPromotion.promoted_at.desc())

    promos = (await db.execute(q)).scalars().all()

    s_ids = list(set(p.student_id for p in promos if p.student_id))
    st_map = {}
    if s_ids:
        for s in (await db.execute(select(S).where(S.id.in_(s_ids)))).scalars().all():
            st_map[str(s.id)] = s

    cls_map = {}
    all_cls = set()
    for p in promos:
        if p.from_class_id: all_cls.add(p.from_class_id)
        if p.to_class_id: all_cls.add(p.to_class_id)
    if all_cls:
        for c in (await db.execute(select(Cls).where(Cls.id.in_(list(all_cls))))).scalars().all():
            cls_map[str(c.id)] = c.name

    rows = []
    tc_count = 0
    dropout_count = 0
    for p in promos:
        st = st_map.get(str(p.student_id))
        act = p.action or ""
        if act == "tc_issued": tc_count += 1
        elif act == "dropout": dropout_count += 1
        rows.append({
            "name": st.full_name if st else "Unknown",
            "admission_number": st.admission_number if st else "",
            "from_class": cls_map.get(str(p.from_class_id), "") if p.from_class_id else "",
            "to_class": cls_map.get(str(p.to_class_id), "") if p.to_class_id else "",
            "action": act,
            "academic_year": p.academic_year_from or "",
            "remarks": p.remarks or "",
            "date": p.promoted_at.strftime("%d %b %Y") if p.promoted_at else "",
        })

    return {
        "report_name": "TC / Alumni / Separation Report",
        "summary": {"total": len(rows), "tc_issued": tc_count, "dropouts": dropout_count},
        "columns": ["Name", "Adm No", "From Class", "To Class", "Action", "Year", "Remarks", "Date"],
        "rows": rows,
        "total": len(rows),
    }


@router.get("/reports/login-history")
async def report_login_history(
    request: Request,
    role: str = "all",
    days: int = 7,
    db: AsyncSession = Depends(get_db),
):
    """Login history report: recent login activity by role."""
    user = await verify_school_admin(request)
    branch_id = user.get("branch_id")
    from models.user import User as U

    since = date.today() - timedelta(days=days)

    q = select(U).where(U.branch_id == branch_id)
    if role != "all":
        from models.user import UserRole as UR
        role_map = {"student": UR.STUDENT, "teacher": UR.TEACHER, "school_admin": UR.SCHOOL_ADMIN}
        if role in role_map:
            q = q.where(U.role == role_map[role])
    q = q.order_by(U.last_login.desc().nullslast()).limit(500)

    users = (await db.execute(q)).scalars().all()

    rows = []
    active_count = 0
    inactive_count = 0
    for u in users:
        last = u.last_login
        is_active = last and last.date() >= since if last else False
        if is_active:
            active_count += 1
        else:
            inactive_count += 1
        rows.append({
            "name": u.full_name,
            "email": u.email or u.phone or "",
            "role": u.role.value if u.role else "",
            "last_login": last.strftime("%d %b %Y %I:%M %p") if last else "Never",
            "is_active": is_active,
            "status": "Active" if is_active else "Inactive",
        })

    return {
        "report_name": "Login History Report",
        "days": days,
        "summary": {"total_users": len(rows), "active": active_count, "inactive": inactive_count},
        "columns": ["Name", "Email", "Role", "Last Login", "Status"],
        "rows": rows,
        "total": len(rows),
    }


@router.get("/reports/student-directory")
async def report_student_directory(
    request: Request,
    class_id: str = None, section_id: str = None,
    filter_type: str = "all",
    limit: int = 500,
    db: AsyncSession = Depends(get_db),
):
    """Student directory report: comprehensive student list with parent contacts.
    filter_type: 'all', 'transport', 'medical', 'new_admissions'
    """
    user = await verify_school_admin(request)
    branch_id = user.get("branch_id")
    from models.student import Student as S
    from models.academic import Class as Cls, Section as Sec

    q = select(S).where(S.branch_id == branch_id, S.is_active == True)
    if class_id:
        q = q.where(S.class_id == uuid.UUID(class_id))
    if section_id:
        q = q.where(S.section_id == uuid.UUID(section_id))
    if filter_type == "transport":
        q = q.where(S.uses_transport == True)
    elif filter_type == "medical":
        q = q.where(S.medical_conditions.isnot(None), S.medical_conditions != "")
    elif filter_type == "new_admissions":
        from datetime import datetime
        current_year = datetime.utcnow().year
        q = q.where(S.admission_date >= date(current_year, 1, 1))
    q = q.order_by(S.class_id, S.roll_number).limit(min(limit, 1000))

    students = (await db.execute(q)).scalars().all()

    cls_map = {}
    sec_map = {}
    cls_ids = set(str(s.class_id) for s in students if s.class_id)
    sec_ids_set = set(str(s.section_id) for s in students if s.section_id)
    if cls_ids:
        for c in (await db.execute(select(Cls).where(Cls.id.in_([uuid.UUID(x) for x in cls_ids])))).scalars().all():
            cls_map[str(c.id)] = c.name
    if sec_ids_set:
        for s in (await db.execute(select(Sec).where(Sec.id.in_([uuid.UUID(x) for x in sec_ids_set])))).scalars().all():
            sec_map[str(s.id)] = s.name

    rows = []
    for s in students:
        rows.append({
            "name": s.full_name,
            "admission_number": s.admission_number or "",
            "roll_no": s.roll_number or "",
            "class": cls_map.get(str(s.class_id), ""),
            "section": sec_map.get(str(s.section_id), ""),
            "gender": s.gender.value if s.gender else "",
            "dob": s.date_of_birth.strftime("%d %b %Y") if s.date_of_birth else "",
            "father_name": s.father_name or "",
            "father_phone": s.father_phone or "",
            "mother_name": s.mother_name or "",
            "mother_phone": s.mother_phone or "",
            "address": s.address or "",
            "transport": "Yes" if s.uses_transport else "No",
            "medical": s.medical_conditions or "",
            "admission_date": s.admission_date.strftime("%d %b %Y") if s.admission_date else "",
        })

    return {
        "report_name": "Student Directory",
        "filter": filter_type,
        "summary": {"total_students": len(rows)},
        "columns": ["Name", "Adm No", "Roll No", "Class", "Section", "Gender", "DOB", "Father", "Father Phone", "Mother", "Mother Phone", "Address", "Transport", "Medical", "Admission Date"],
        "rows": rows,
        "total": len(rows),
    }


@router.get("/reports/student-leaves")
async def report_student_leaves(
    request: Request,
    class_id: str = None, month: int = None, year: int = None,
    status: str = "all",
    db: AsyncSession = Depends(get_db),
):
    """Student leave report: leave applications with status."""
    user = await verify_school_admin(request)
    branch_id = user.get("branch_id")
    from models.student_leave import StudentLeave as SL
    from models.student import Student as S
    from models.academic import Class as Cls, Section as Sec
    from datetime import datetime
    import calendar

    q = select(SL).where(SL.branch_id == branch_id)
    if month and year:
        first_day = date(year, month, 1)
        last_day = date(year, month, calendar.monthrange(year, month)[1])
        q = q.where(SL.start_date >= first_day, SL.start_date <= last_day)
    if status != "all":
        from models.student_leave import ApprovalStatus
        status_map = {"pending": ApprovalStatus.PENDING, "approved": ApprovalStatus.APPROVED, "rejected": ApprovalStatus.REJECTED}
        if status in status_map:
            q = q.where(SL.teacher_status == status_map[status])
    q = q.order_by(SL.created_at.desc())

    leaves = (await db.execute(q)).scalars().all()

    s_ids = list(set(l.student_id for l in leaves if l.student_id))
    st_map = {}
    if s_ids:
        st_q = select(S).where(S.id.in_(s_ids))
        if class_id:
            st_q = st_q.where(S.class_id == uuid.UUID(class_id))
        for s in (await db.execute(st_q)).scalars().all():
            st_map[str(s.id)] = s

    cls_map = {}
    sec_map = {}
    cls_ids = set(str(s.class_id) for s in st_map.values() if s.class_id)
    sec_ids_set = set(str(s.section_id) for s in st_map.values() if s.section_id)
    if cls_ids:
        for c in (await db.execute(select(Cls).where(Cls.id.in_([uuid.UUID(x) for x in cls_ids])))).scalars().all():
            cls_map[str(c.id)] = c.name
    if sec_ids_set:
        for s in (await db.execute(select(Sec).where(Sec.id.in_([uuid.UUID(x) for x in sec_ids_set])))).scalars().all():
            sec_map[str(s.id)] = s.name

    rows = []
    for l in leaves:
        st = st_map.get(str(l.student_id))
        if not st:
            continue
        rows.append({
            "name": st.full_name,
            "class": cls_map.get(str(st.class_id), ""),
            "section": sec_map.get(str(st.section_id), ""),
            "start_date": l.start_date.strftime("%d %b %Y") if l.start_date else "",
            "end_date": l.end_date.strftime("%d %b %Y") if l.end_date else "",
            "total_days": l.total_days or 0,
            "reason_type": l.reason_type.value if l.reason_type else "",
            "reason": l.reason_text or "",
            "teacher_status": l.teacher_status.value if l.teacher_status else "pending",
            "applied_on": l.created_at.strftime("%d %b %Y") if l.created_at else "",
        })

    return {
        "report_name": "Student Leave Report",
        "summary": {"total_leaves": len(rows)},
        "columns": ["Name", "Class", "Section", "From", "To", "Days", "Type", "Reason", "Status", "Applied On"],
        "rows": rows,
        "total": len(rows),
    }


@router.get("/reports/exams-list")
async def report_exams_list(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Get list of exams for report filter dropdowns."""
    user = await verify_school_admin(request)
    branch_id = user.get("branch_id")
    from models.exam import Exam

    exams = (await db.execute(
        select(Exam).where(Exam.branch_id == branch_id).order_by(Exam.start_date.desc())
    )).scalars().all()

    return {"exams": [{"id": str(e.id), "name": e.name, "published": e.is_published,
                        "start_date": e.start_date.strftime("%d %b %Y") if e.start_date else ""}
                       for e in exams]}