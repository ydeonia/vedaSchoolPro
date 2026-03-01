from fastapi import APIRouter, Request, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, func
from sqlalchemy.orm import selectinload
from database import get_db
from models.user import User, UserRole
from models.academic import AcademicYear, Class, Section, Subject, ClassSubject
from models.teacher import Teacher
from utils.auth import hash_password
from utils.permissions import get_current_user
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
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    pincode: Optional[str] = None
    medical_conditions: Optional[str] = None
    emergency_contact: Optional[str] = None
    uses_transport: bool = False


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
    )
    db.add(student)
    await db.flush()  # get the ID before commit
    return {"success": True, "id": str(student.id), "message": f"Student {data.first_name} enrolled"}


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
    return {"success": True, "message": "Student deactivated"}


# ─── ATTENDANCE ─────────────────────────────────────────

from models.attendance import Attendance, AttendanceStatus

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
    """Create/replace all period definitions for a branch"""
    user = await verify_school_admin(request)
    branch_id = get_branch_id(user)
    from datetime import time as time_type, datetime as dt

    # Delete existing periods
    existing = await db.execute(
        select(PeriodDefinition).where(PeriodDefinition.branch_id == branch_id)
    )
    for p in existing.scalars().all():
        await db.delete(p)
    await db.flush()

    # Create new ones
    for pd in data.periods:
        try:
            st = dt.strptime(pd.start_time, "%H:%M").time()
            et = dt.strptime(pd.end_time, "%H:%M").time()
        except:
            continue

        period = PeriodDefinition(
            branch_id=branch_id,
            period_number=pd.period_number,
            label=pd.label,
            start_time=st,
            end_time=et,
            period_type=PeriodType(pd.period_type) if pd.period_type in [e.value for e in PeriodType] else PeriodType.REGULAR,
        )
        db.add(period)

    await db.commit()
    return {"success": True, "message": f"{len(data.periods)} periods configured"}


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

    return {
        "subjects": [
            {"id": str(s.id), "subject_id": str(s.subject_id),
             "subject_name": sub_map.get(s.subject_id, ""),
             "class_id": str(s.class_id),
             "max_marks": s.max_marks, "passing_marks": s.passing_marks}
            for s in subjects
        ]
    }


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
            "roll": s.roll_number or "", "gender": s.gender or "",
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
        target_users = (await db.execute(users_q)).scalars().all()
        for u in target_users:
            notif = Notification(
                branch_id=branch_id, user_id=u.id,
                type=NotificationType.ANNOUNCEMENT,
                title=data.title, message=data.content[:200],
                priority=data.priority,
                action_url="/school/announcements" if u.role == UR.SCHOOL_ADMIN else None,
                action_label="View",
            )
            db.add(notif)

    await db.commit()
    icon = "🚨" if data.is_emergency else ("📌" if data.is_pinned else "📢")
    return {"success": True, "message": f"{icon} Announcement published to {data.target_role}!"}


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
            from datetime import datetime, timezone
            n.read_at = datetime.now(timezone.utc)
    else:
        # Mark all read
        from datetime import datetime, timezone
        branch_id = get_branch_id(user)
        result = await db.execute(
            select(Notification).where(
                Notification.branch_id == branch_id,
                (Notification.user_id == user_id) | (Notification.user_id == None),
                Notification.is_read == False
            ))
        for n in result.scalars().all():
            n.is_read = True
            n.read_at = datetime.now(timezone.utc)
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
        "sms_sender_id": config.sms_sender_id or "",
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
        ct = (await db.execute(select(Teacher).where(
            Teacher.class_teacher_of == student.section_id, Teacher.is_active == True))).scalar_one_or_none()
        if ct:
            class_teacher_sig = ct.signature_url

    student_data = {
        "name": student.full_name,
        "class_name": student.class_.name if student.class_ else "",
        "section": student.section.name if student.section else "",
        "roll": student.roll_number or "",
        "admission": student.admission_number or "",
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
        items.append({"id": str(a.id), "title": a.title, "activity_type": a.activity_type, "category": a.category or "",
                       "event_date": a.event_date.isoformat() if a.event_date else "", "venue": a.venue or "",
                       "status": a.status, "participant_count": count, "max_participants": a.max_participants})
    return {"activities": items}


@router.post("/activities")
async def create_activity(request: Request, db: AsyncSession = Depends(get_db)):
    user = await get_current_user(request)
    if not user: return {"error": "unauthorized"}
    branch_id = uuid.UUID(user["branch_id"])
    data = await request.json()
    act = Activity(branch_id=branch_id, name=data["title"], title=data["title"], activity_type=data["activity_type"],
                   category=data.get("category"), description=data.get("description"),
                   event_date=date.fromisoformat(data["event_date"]) if data.get("event_date") else None,
                   registration_deadline=date.fromisoformat(data["registration_deadline"]) if data.get("registration_deadline") else None,
                   venue=data.get("venue"), max_participants=data.get("max_participants"),
                   eligible_classes=data.get("eligible_classes"), status="open",
                   created_by=uuid.UUID(user["user_id"]))
    db.add(act)
    await db.commit()
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
            tc += 1
        elif action == "left":
            student.is_active = False
            student.admission_status = AdmissionStatus.LEFT
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

    # Mark present
    att = Attendance(
        student_id=student.id, branch_id=branch_id,
        class_id=student.class_id, section_id=student.section_id,
        date=today, status=AttendanceStatus.PRESENT
    )
    db.add(att)
    await db.commit()
    return {"success": True, "student_name": student.full_name, "roll": student.roll_number or "", "message": "Marked present"}


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

    return {"student": {
        "id": str(s.id), "first_name": s.first_name, "last_name": s.last_name or "",
        "full_name": s.full_name, "roll_number": s.roll_number or "",
        "admission_number": s.admission_number or "",
        "class_name": cls_name or "", "section_name": sec_name,
        "class_id": str(s.class_id) if s.class_id else "",
        "section_id": str(s.section_id) if s.section_id else "",
        "date_of_birth": s.date_of_birth.isoformat() if s.date_of_birth else "",
        "gender": s.gender or "", "blood_group": s.blood_group or "",
        "father_name": s.father_name or "", "mother_name": s.mother_name or "",
        "father_phone": s.father_phone or "", "mother_phone": s.mother_phone or "",
        "address": s.address or "", "photo_url": s.photo_url or "",
        "admission_status": s.admission_status.value if s.admission_status else "admitted",
        "house_name": house_name, "house_color": house_color,
        "roles": role_list, "documents": doc_list,
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
        class_teacher = await db.scalar(
            select(Teacher).where(
                Teacher.branch_id == branch_id,
                Teacher.is_class_teacher == True,
                Teacher.class_teacher_of == uuid.UUID(section_id),
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