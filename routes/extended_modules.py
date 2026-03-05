"""Extended Modules — Admission, Homework, Library, Certificates"""
from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from database import get_db
from models.user import UserRole
from utils.permissions import require_role
import uuid

router = APIRouter(prefix="/school")
templates = Jinja2Templates(directory="templates")


# ═══════════════════════════════════════════════════════════
# ADMISSIONS
# ═══════════════════════════════════════════════════════════
@router.get("/admissions", response_class=HTMLResponse)
@require_role(UserRole.SCHOOL_ADMIN)
async def admissions_page(request: Request, db: AsyncSession = Depends(get_db)):
    user = request.state.user
    branch_id = uuid.UUID(user["branch_id"])
    from models.mega_modules import Admission
    from models.academic import Class

    admissions = (await db.execute(
        select(Admission).where(Admission.branch_id == branch_id)
        .order_by(Admission.created_at.desc())
    )).scalars().all()
    classes = (await db.execute(
        select(Class).where(Class.branch_id == branch_id, Class.is_active == True)
    )).scalars().all()

    stats = {}
    for status in ['inquiry', 'applied', 'document_pending', 'interview', 'admitted', 'enrolled', 'rejected', 'withdrawn']:
        stats[status] = sum(1 for a in admissions if a.status.value == status)
    stats['total'] = len(admissions)

    return templates.TemplateResponse("school_admin/admissions.html", {
        "request": request, "user": user, "active_page": "admissions",
        "admissions": admissions, "classes": classes, "stats": stats,
    })


# ═══════════════════════════════════════════════════════════
# HOMEWORK
# ═══════════════════════════════════════════════════════════
@router.get("/homework", response_class=HTMLResponse)
@require_role(UserRole.SCHOOL_ADMIN)
async def homework_page(request: Request, db: AsyncSession = Depends(get_db)):
    user = request.state.user
    branch_id = uuid.UUID(user["branch_id"])
    from models.mega_modules import Homework
    from models.academic import Class
    from models.academic import Subject

    homework_list = (await db.execute(
        select(Homework).where(Homework.branch_id == branch_id, Homework.is_active == True)
        .order_by(Homework.due_date.desc()).limit(50)
    )).scalars().all()
    classes = (await db.execute(select(Class).where(Class.branch_id == branch_id, Class.is_active == True))).scalars().all()
    subjects = (await db.execute(select(Subject).where(Subject.branch_id == branch_id, Subject.is_active == True))).scalars().all()

    return templates.TemplateResponse("school_admin/homework.html", {
        "request": request, "user": user, "active_page": "homework",
        "homework_list": homework_list, "classes": classes, "subjects": subjects,
    })


# ═══════════════════════════════════════════════════════════
# LIBRARY
# ═══════════════════════════════════════════════════════════
@router.get("/library", response_class=HTMLResponse)
@require_role(UserRole.SCHOOL_ADMIN)
async def library_page(request: Request, db: AsyncSession = Depends(get_db)):
    user = request.state.user
    branch_id = uuid.UUID(user["branch_id"])
    from models.mega_modules import Book, BookIssue

    books = (await db.execute(
        select(Book).where(Book.branch_id == branch_id, Book.is_active == True)
        .order_by(Book.title)
    )).scalars().all()
    issues = (await db.execute(
        select(BookIssue).where(BookIssue.branch_id == branch_id, BookIssue.status == "issued")
    )).scalars().all()

    total_books = sum(b.total_copies for b in books)
    available = sum(b.available_copies for b in books)
    issued_count = len(issues)

    return templates.TemplateResponse("school_admin/library.html", {
        "request": request, "user": user, "active_page": "library",
        "books": books, "issues": issues,
        "total_books": total_books, "available": available, "issued_count": issued_count,
    })


# ═══════════════════════════════════════════════════════════
# CERTIFICATES
# ═══════════════════════════════════════════════════════════
@router.get("/certificates", response_class=HTMLResponse)
@require_role(UserRole.SCHOOL_ADMIN)
async def certificates_page(request: Request, db: AsyncSession = Depends(get_db)):
    user = request.state.user
    branch_id = uuid.UUID(user["branch_id"])
    from models.mega_modules import Certificate
    from models.student import Student
    from models.academic import Class

    certificates = (await db.execute(
        select(Certificate).where(Certificate.branch_id == branch_id)
        .order_by(Certificate.created_at.desc()).limit(50)
    )).scalars().all()
    classes = (await db.execute(select(Class).where(Class.branch_id == branch_id, Class.is_active == True))).scalars().all()

    return templates.TemplateResponse("school_admin/certificates.html", {
        "request": request, "user": user, "active_page": "certificates",
        "certificates": certificates, "classes": classes,
    })