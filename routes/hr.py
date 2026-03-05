"""HR & Employee Management — Employees, Payroll, Salary Slips, ID Cards"""
from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from database import get_db
from models.user import UserRole
from utils.permissions import require_role
from pydantic import BaseModel
from typing import Optional
import uuid

router = APIRouter(prefix="/school/hr")
templates = Jinja2Templates(directory="templates")


@router.get("/employees", response_class=HTMLResponse)
@require_role(UserRole.SCHOOL_ADMIN)
async def employees_page(request: Request, db: AsyncSession = Depends(get_db)):
    user = request.state.user
    branch_id = uuid.UUID(user["branch_id"])
    from models.mega_modules import Employee
    employees = (await db.execute(
        select(Employee).where(Employee.branch_id == branch_id, Employee.is_active == True)
        .order_by(Employee.first_name)
    )).scalars().all()
    return templates.TemplateResponse("school_admin/hr_employees.html", {
        "request": request, "user": user, "active_page": "employees",
        "employees": employees,
    })


@router.get("/payroll", response_class=HTMLResponse)
@require_role(UserRole.SCHOOL_ADMIN)
async def payroll_page(request: Request, db: AsyncSession = Depends(get_db)):
    user = request.state.user
    branch_id = uuid.UUID(user["branch_id"])
    from models.mega_modules import Employee, SalarySlip
    employees = (await db.execute(
        select(Employee).where(Employee.branch_id == branch_id, Employee.is_active == True)
    )).scalars().all()
    from datetime import datetime
    month = datetime.now().month
    year = datetime.now().year
    slips = (await db.execute(
        select(SalarySlip).where(SalarySlip.branch_id == branch_id, SalarySlip.month == month, SalarySlip.year == year)
    )).scalars().all()
    return templates.TemplateResponse("school_admin/hr_payroll.html", {
        "request": request, "user": user, "active_page": "payroll",
        "employees": employees, "slips": slips, "month": month, "year": year,
    })


@router.get("/id-cards", response_class=HTMLResponse)
@require_role(UserRole.SCHOOL_ADMIN)
async def id_cards_page(request: Request, db: AsyncSession = Depends(get_db)):
    user = request.state.user
    branch_id = uuid.UUID(user["branch_id"])
    from models.student import Student
    from models.mega_modules import Employee
    from models.academic import Class
    from models.teacher import Teacher
    from sqlalchemy.orm import selectinload
    classes = (await db.execute(
        select(Class).where(Class.branch_id == branch_id, Class.is_active == True)
    )).scalars().all()
    employees = (await db.execute(
        select(Employee).where(Employee.branch_id == branch_id, Employee.is_active == True)
    )).scalars().all()
    teachers = (await db.execute(
        select(Teacher).where(Teacher.branch_id == branch_id, Teacher.is_active == True)
        .order_by(Teacher.first_name)
    )).scalars().all()
    return templates.TemplateResponse("school_admin/id_cards.html", {
        "request": request, "user": user, "active_page": "id_cards",
        "classes": classes, "employees": employees, "teachers": teachers,
    })