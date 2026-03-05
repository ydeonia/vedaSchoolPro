"""Extended Modules API — Admissions, Homework, Library, Certificates"""
from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from database import get_db
from models.user import UserRole
from utils.permissions import require_role
from utils.audit import log_audit, AuditAction
from pydantic import BaseModel
from typing import Optional
import uuid
from datetime import date, datetime

router = APIRouter(prefix="/api/school")


# ─── ADMISSIONS API ───────────────────────────────────────
class AdmissionData(BaseModel):
    student_name: str
    date_of_birth: Optional[str] = None
    gender: Optional[str] = None
    applying_for_class: Optional[str] = None
    father_name: Optional[str] = None
    father_phone: Optional[str] = None
    father_email: Optional[str] = None
    mother_name: Optional[str] = None
    address: Optional[str] = None
    previous_school: Optional[str] = None
    academic_year: Optional[str] = "2025-26"


@router.post("/admissions/create")
@require_role(UserRole.SCHOOL_ADMIN)
async def create_admission(data: AdmissionData, request: Request, db: AsyncSession = Depends(get_db)):
    user = request.state.user
    from models.mega_modules import Admission
    adm = Admission(
        branch_id=uuid.UUID(user["branch_id"]),
        student_name=data.student_name, gender=data.gender,
        applying_for_class=data.applying_for_class,
        father_name=data.father_name, father_phone=data.father_phone,
        father_email=data.father_email, mother_name=data.mother_name,
        address=data.address, previous_school=data.previous_school,
        academic_year=data.academic_year,
    )
    if data.date_of_birth:
        try: adm.date_of_birth = date.fromisoformat(data.date_of_birth)
        except: pass
    db.add(adm)
    await log_audit(db, user["branch_id"], user, AuditAction.CREATE, "admission", str(adm.id),
                    f"New admission enquiry: {data.student_name}")
    await db.commit()
    return {"id": str(adm.id), "message": "Admission enquiry created"}


@router.put("/admissions/{aid}/status")
@require_role(UserRole.SCHOOL_ADMIN)
async def update_admission_status(aid: str, request: Request, db: AsyncSession = Depends(get_db)):
    from models.mega_modules import Admission, AdmissionStatus
    body = await request.json()
    status = body.get("status", "")
    adm = (await db.execute(select(Admission).where(Admission.id == uuid.UUID(aid)))).scalar_one_or_none()
    if not adm: raise HTTPException(404)
    try: adm.status = AdmissionStatus(status)
    except: raise HTTPException(400, "Invalid status")
    if status == "enrolled": adm.enrollment_date = date.today()
    elif status == "approved": adm.approval_date = date.today()
    elif status == "rejected": adm.rejection_reason = body.get("reason", "")
    adm.updated_at = datetime.utcnow()
    await db.commit()
    return {"message": f"Status updated to {status}"}


# ─── HOMEWORK API ──────────────────────────────────────────
class HomeworkData(BaseModel):
    class_id: str
    subject_id: str
    title: str
    description: Optional[str] = None
    due_date: str
    max_marks: Optional[int] = None


@router.post("/homework/create")
@require_role(UserRole.SCHOOL_ADMIN)
async def create_homework(data: HomeworkData, request: Request, db: AsyncSession = Depends(get_db)):
    user = request.state.user
    from models.mega_modules import Homework
    hw = Homework(
        branch_id=uuid.UUID(user["branch_id"]),
        teacher_id=uuid.UUID(user.get("teacher_id", user["user_id"])),
        class_id=uuid.UUID(data.class_id), subject_id=uuid.UUID(data.subject_id),
        title=data.title, description=data.description,
        due_date=date.fromisoformat(data.due_date),
        max_marks=data.max_marks,
    )
    db.add(hw)
    await db.commit()
    return {"id": str(hw.id), "message": "Homework assigned"}


# ─── LIBRARY API ───────────────────────────────────────────
class BookData(BaseModel):
    title: str
    author: Optional[str] = None
    isbn: Optional[str] = None
    publisher: Optional[str] = None
    category: Optional[str] = None
    rack_number: Optional[str] = None
    total_copies: Optional[int] = 1
    price: Optional[float] = None


@router.post("/library/books/create")
@require_role(UserRole.SCHOOL_ADMIN)
async def create_book(data: BookData, request: Request, db: AsyncSession = Depends(get_db)):
    user = request.state.user
    from models.mega_modules import Book
    book = Book(
        branch_id=uuid.UUID(user["branch_id"]),
        title=data.title, author=data.author, isbn=data.isbn,
        publisher=data.publisher, category=data.category,
        rack_number=data.rack_number, total_copies=data.total_copies or 1,
        available_copies=data.total_copies or 1, price=data.price,
    )
    db.add(book)
    await db.commit()
    return {"id": str(book.id), "message": f"Book '{data.title}' added"}


class IssueBookData(BaseModel):
    book_id: str
    borrower_type: str  # student, teacher, employee
    borrower_id: str
    borrower_name: str
    due_date: str


@router.post("/library/issue")
@require_role(UserRole.SCHOOL_ADMIN)
async def issue_book(data: IssueBookData, request: Request, db: AsyncSession = Depends(get_db)):
    user = request.state.user
    from models.mega_modules import Book, BookIssue
    book = (await db.execute(select(Book).where(Book.id == uuid.UUID(data.book_id)))).scalar_one_or_none()
    if not book: raise HTTPException(404, "Book not found")
    if book.available_copies <= 0: raise HTTPException(400, "No copies available")
    issue = BookIssue(
        book_id=book.id, branch_id=book.branch_id,
        borrower_type=data.borrower_type, borrower_id=uuid.UUID(data.borrower_id),
        borrower_name=data.borrower_name, due_date=date.fromisoformat(data.due_date),
    )
    book.available_copies -= 1
    db.add(issue)
    await db.commit()
    return {"id": str(issue.id), "message": f"Book issued to {data.borrower_name}"}


@router.post("/library/return/{issue_id}")
@require_role(UserRole.SCHOOL_ADMIN)
async def return_book(issue_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    from models.mega_modules import Book, BookIssue
    issue = (await db.execute(select(BookIssue).where(BookIssue.id == uuid.UUID(issue_id)))).scalar_one_or_none()
    if not issue: raise HTTPException(404)
    issue.return_date = date.today()
    issue.status = "returned"
    # Calculate fine (₹2/day late)
    if issue.return_date > issue.due_date:
        days_late = (issue.return_date - issue.due_date).days
        issue.fine_amount = days_late * 2
    book = (await db.execute(select(Book).where(Book.id == issue.book_id))).scalar_one_or_none()
    if book: book.available_copies += 1
    await db.commit()
    return {"message": "Book returned", "fine": float(issue.fine_amount)}


class BookUpdateData(BaseModel):
    title: Optional[str] = None
    author: Optional[str] = None
    isbn: Optional[str] = None
    publisher: Optional[str] = None
    category: Optional[str] = None
    rack_number: Optional[str] = None
    total_copies: Optional[int] = None
    price: Optional[float] = None


@router.put("/library/books/{book_id}")
@require_role(UserRole.SCHOOL_ADMIN)
async def update_book(book_id: str, data: BookUpdateData, request: Request, db: AsyncSession = Depends(get_db)):
    from models.mega_modules import Book
    book = (await db.execute(select(Book).where(Book.id == uuid.UUID(book_id)))).scalar_one_or_none()
    if not book: raise HTTPException(404, "Book not found")
    for field in ["title", "author", "isbn", "publisher", "category", "rack_number", "price"]:
        val = getattr(data, field)
        if val is not None:
            setattr(book, field, val)
    if data.total_copies is not None:
        diff = data.total_copies - book.total_copies
        book.total_copies = data.total_copies
        book.available_copies = max(0, book.available_copies + diff)
    await db.commit()
    return {"id": str(book.id), "message": f"Book '{book.title}' updated"}


@router.delete("/library/books/{book_id}")
@require_role(UserRole.SCHOOL_ADMIN)
async def delete_book(book_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    from models.mega_modules import Book
    book = (await db.execute(select(Book).where(Book.id == uuid.UUID(book_id)))).scalar_one_or_none()
    if not book: raise HTTPException(404, "Book not found")
    book.is_active = False
    await db.commit()
    return {"message": f"Book '{book.title}' deleted"}


@router.post("/library/fine/{issue_id}/pay")
@require_role(UserRole.SCHOOL_ADMIN)
async def pay_fine(issue_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    from models.mega_modules import BookIssue
    issue = (await db.execute(select(BookIssue).where(BookIssue.id == uuid.UUID(issue_id)))).scalar_one_or_none()
    if not issue: raise HTTPException(404, "Issue record not found")
    if issue.fine_amount <= 0: raise HTTPException(400, "No fine to pay")
    if issue.fine_paid: raise HTTPException(400, "Fine already paid")
    issue.fine_paid = True
    await db.commit()
    return {"message": "Fine marked as paid", "fine_amount": float(issue.fine_amount)}


# ─── CERTIFICATES API ─────────────────────────────────────
class CertificateData(BaseModel):
    student_id: str
    cert_type: str
    reason: Optional[str] = None
    destination_school: Optional[str] = None
    conduct: Optional[str] = "Good"


@router.post("/certificates/generate")
@require_role(UserRole.SCHOOL_ADMIN)
async def generate_certificate(data: CertificateData, request: Request, db: AsyncSession = Depends(get_db)):
    user = request.state.user
    from models.mega_modules import Certificate, CertificateType
    cert = Certificate(
        branch_id=uuid.UUID(user["branch_id"]),
        student_id=uuid.UUID(data.student_id),
        cert_type=CertificateType(data.cert_type),
        reason=data.reason, destination_school=data.destination_school,
        conduct=data.conduct, generated_by=uuid.UUID(user["user_id"]),
        certificate_number=f"CERT-{datetime.now().strftime('%Y%m%d')}-{str(uuid.uuid4())[:4].upper()}",
    )
    db.add(cert)
    await log_audit(db, user["branch_id"], user, AuditAction.CREATE, "certificate", str(cert.id),
                    f"Generated {data.cert_type} for student {data.student_id[:8]}")
    await db.commit()
    return {"id": str(cert.id), "number": cert.certificate_number, "message": "Certificate generated"}


@router.get("/certificates/pdf/{cert_id}")
@require_role(UserRole.SCHOOL_ADMIN)
async def certificate_pdf(cert_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    from models.mega_modules import Certificate
    from models.student import Student
    from models.branch import Branch
    from utils.id_card_generator import generate_certificate_pdf
    from sqlalchemy.orm import selectinload

    cert = (await db.execute(select(Certificate).where(Certificate.id == uuid.UUID(cert_id)))).scalar_one_or_none()
    if not cert: raise HTTPException(404)
    student = (await db.execute(
        select(Student).where(Student.id == cert.student_id)
        .options(selectinload(Student.class_))
    )).scalar_one_or_none()
    branch = (await db.execute(select(Branch).where(Branch.id == cert.branch_id))).scalar_one_or_none()

    school_data = {
        "name": branch.name if branch else "", "logo_url": branch.logo_url if branch else "",
        "motto": branch.motto if branch else "", "accreditation": branch.accreditation if branch else "",
        "address": branch.address if branch else "",
    }
    cert_data = {
        "cert_type": cert.cert_type.value, "certificate_number": cert.certificate_number or "",
        "student_name": student.full_name if student else "", "father_name": student.father_name if student else "",
        "class_name": student.class_.name if student and student.class_ else "",
        "dob": student.dob.strftime('%d %b %Y') if student and student.dob else "",
        "admission_number": student.admission_number if student else "",
        "reason": cert.reason or "", "conduct": cert.conduct or "Good",
        "destination_school": cert.destination_school or "",
        "issue_date": cert.issue_date.strftime('%d %b %Y') if cert.issue_date else "",
    }
    pdf_bytes = generate_certificate_pdf(school_data, cert_data)
    return Response(content=pdf_bytes, media_type="application/pdf",
                    headers={"Content-Disposition": f"inline; filename=certificate_{cert.certificate_number}.pdf"})


# ─── ACTIVITIES API ──────────────────────────────────────
class ActivityData(BaseModel):
    name: str
    title: Optional[str] = None
    activity_type: Optional[str] = None
    category: Optional[str] = None
    description: Optional[str] = None
    event_date: Optional[str] = None
    registration_deadline: Optional[str] = None
    venue: Optional[str] = None
    max_participants: Optional[int] = None
    eligible_classes: Optional[list] = None
    status: Optional[str] = "upcoming"


class ActivityUpdateData(BaseModel):
    name: Optional[str] = None
    title: Optional[str] = None
    activity_type: Optional[str] = None
    category: Optional[str] = None
    description: Optional[str] = None
    event_date: Optional[str] = None
    registration_deadline: Optional[str] = None
    venue: Optional[str] = None
    max_participants: Optional[int] = None
    eligible_classes: Optional[list] = None
    status: Optional[str] = None


class EnrollStudentData(BaseModel):
    student_ids: list[str]
    nomination_type: Optional[str] = "self"
    team_name: Optional[str] = None


class StudentParticipationData(BaseModel):
    participation: Optional[str] = None
    achievement: Optional[str] = None
    remarks: Optional[str] = None
    position: Optional[str] = None
    score: Optional[float] = None
    status: Optional[str] = None


@router.post("/activities/create")
@require_role(UserRole.SCHOOL_ADMIN)
async def create_activity(data: ActivityData, request: Request, db: AsyncSession = Depends(get_db)):
    user = request.state.user
    from models.activity import Activity
    activity = Activity(
        branch_id=uuid.UUID(user["branch_id"]),
        name=data.name, title=data.title or data.name,
        activity_type=data.activity_type, category=data.category,
        description=data.description, venue=data.venue,
        max_participants=data.max_participants,
        eligible_classes=data.eligible_classes,
        status=data.status or "upcoming",
        created_by=uuid.UUID(user["user_id"]),
    )
    if data.event_date:
        try: activity.event_date = date.fromisoformat(data.event_date)
        except: pass
    if data.registration_deadline:
        try: activity.registration_deadline = date.fromisoformat(data.registration_deadline)
        except: pass
    db.add(activity)
    await log_audit(db, user["branch_id"], user, AuditAction.CREATE, "activity", str(activity.id),
                    f"Created activity: {data.name}")
    await db.commit()
    return {"id": str(activity.id), "message": "Activity created"}


@router.put("/activities/{aid}")
@require_role(UserRole.SCHOOL_ADMIN)
async def update_activity(aid: str, data: ActivityUpdateData, request: Request, db: AsyncSession = Depends(get_db)):
    from models.activity import Activity
    activity = (await db.execute(select(Activity).where(Activity.id == uuid.UUID(aid)))).scalar_one_or_none()
    if not activity: raise HTTPException(404, "Activity not found")
    for field in ["name", "title", "activity_type", "category", "description",
                  "venue", "max_participants", "eligible_classes", "status"]:
        val = getattr(data, field, None)
        if val is not None:
            setattr(activity, field, val)
    if data.event_date:
        try: activity.event_date = date.fromisoformat(data.event_date)
        except: pass
    if data.registration_deadline:
        try: activity.registration_deadline = date.fromisoformat(data.registration_deadline)
        except: pass
    await db.commit()
    return {"message": "Activity updated"}


@router.delete("/activities/{aid}")
@require_role(UserRole.SCHOOL_ADMIN)
async def delete_activity(aid: str, request: Request, db: AsyncSession = Depends(get_db)):
    from models.activity import Activity
    activity = (await db.execute(select(Activity).where(Activity.id == uuid.UUID(aid)))).scalar_one_or_none()
    if not activity: raise HTTPException(404, "Activity not found")
    activity.is_active = False
    user = request.state.user
    await log_audit(db, user["branch_id"], user, AuditAction.DELETE, "activity", str(activity.id),
                    f"Soft-deleted activity: {activity.name}")
    await db.commit()
    return {"message": "Activity deleted"}


@router.get("/activities/{aid}/participants")
@require_role(UserRole.SCHOOL_ADMIN)
async def get_activity_participants(aid: str, request: Request, db: AsyncSession = Depends(get_db)):
    from models.activity import Activity, StudentActivity
    from models.student import Student
    from sqlalchemy.orm import selectinload
    activity = (await db.execute(select(Activity).where(Activity.id == uuid.UUID(aid)))).scalar_one_or_none()
    if not activity: raise HTTPException(404, "Activity not found")
    rows = (await db.execute(
        select(StudentActivity).where(StudentActivity.activity_id == uuid.UUID(aid))
        .options(selectinload(StudentActivity.student))
    )).scalars().all()
    participants = []
    for sa in rows:
        participants.append({
            "id": str(sa.id),
            "student_id": str(sa.student_id),
            "student_name": sa.student.full_name if sa.student else "",
            "participation": sa.participation,
            "achievement": sa.achievement,
            "remarks": sa.remarks,
            "team_name": sa.team_name,
            "position": sa.position,
            "score": sa.score,
            "status": sa.status,
        })
    return {"activity_id": str(activity.id), "activity_name": activity.name, "participants": participants}


@router.post("/activities/{aid}/enroll")
@require_role(UserRole.SCHOOL_ADMIN)
async def enroll_students(aid: str, data: EnrollStudentData, request: Request, db: AsyncSession = Depends(get_db)):
    from models.activity import Activity, StudentActivity
    user = request.state.user
    activity = (await db.execute(select(Activity).where(Activity.id == uuid.UUID(aid)))).scalar_one_or_none()
    if not activity: raise HTTPException(404, "Activity not found")
    if not activity.is_active: raise HTTPException(400, "Activity is not active")
    enrolled = []
    for sid in data.student_ids:
        # Check if already enrolled
        existing = (await db.execute(
            select(StudentActivity).where(
                StudentActivity.activity_id == uuid.UUID(aid),
                StudentActivity.student_id == uuid.UUID(sid),
            )
        )).scalar_one_or_none()
        if existing:
            continue
        sa = StudentActivity(
            student_id=uuid.UUID(sid),
            activity_id=uuid.UUID(aid),
            nomination_type=data.nomination_type or "self",
            team_name=data.team_name,
            nominated_by=uuid.UUID(user["user_id"]),
            date=date.today(),
        )
        db.add(sa)
        enrolled.append(sid)
    await log_audit(db, user["branch_id"], user, AuditAction.CREATE, "student_activity", aid,
                    f"Enrolled {len(enrolled)} student(s) in activity {activity.name}")
    await db.commit()
    return {"enrolled": len(enrolled), "skipped_duplicates": len(data.student_ids) - len(enrolled),
            "message": f"{len(enrolled)} student(s) enrolled"}


@router.put("/activities/{aid}/student/{sid}")
@require_role(UserRole.SCHOOL_ADMIN)
async def update_student_participation(aid: str, sid: str, data: StudentParticipationData,
                                       request: Request, db: AsyncSession = Depends(get_db)):
    from models.activity import StudentActivity
    sa = (await db.execute(
        select(StudentActivity).where(
            StudentActivity.activity_id == uuid.UUID(aid),
            StudentActivity.student_id == uuid.UUID(sid),
        )
    )).scalar_one_or_none()
    if not sa: raise HTTPException(404, "Student not enrolled in this activity")
    for field in ["participation", "achievement", "remarks", "position", "score", "status"]:
        val = getattr(data, field, None)
        if val is not None:
            setattr(sa, field, val)
    await db.commit()
    return {"message": "Participation updated"}


@router.delete("/activities/{aid}/student/{sid}")
@require_role(UserRole.SCHOOL_ADMIN)
async def remove_student_from_activity(aid: str, sid: str, request: Request, db: AsyncSession = Depends(get_db)):
    from models.activity import StudentActivity
    sa = (await db.execute(
        select(StudentActivity).where(
            StudentActivity.activity_id == uuid.UUID(aid),
            StudentActivity.student_id == uuid.UUID(sid),
        )
    )).scalar_one_or_none()
    if not sa: raise HTTPException(404, "Student not enrolled in this activity")
    user = request.state.user
    await log_audit(db, user["branch_id"], user, AuditAction.DELETE, "student_activity", str(sa.id),
                    f"Removed student {sid[:8]} from activity {aid[:8]}")
    await db.delete(sa)
    await db.commit()
    return {"message": "Student removed from activity"}