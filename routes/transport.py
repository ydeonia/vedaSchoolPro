"""Transport Management — Vehicles, Routes, Stops, Student Assignment"""
from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from database import get_db
from models.user import UserRole
from utils.permissions import require_role
from pydantic import BaseModel
from typing import Optional
import uuid

router = APIRouter(prefix="/school/transport")
templates = Jinja2Templates(directory="templates")


@router.get("/vehicles", response_class=HTMLResponse)
@require_role(UserRole.SCHOOL_ADMIN)
async def vehicles_page(request: Request, db: AsyncSession = Depends(get_db)):
    user = request.state.user
    branch_id = uuid.UUID(user["branch_id"])
    from models.mega_modules import Vehicle, TransportRoute, StudentTransport
    from models.student import Student
    from datetime import date
    vehicles = (await db.execute(
        select(Vehicle).where(Vehicle.branch_id == branch_id, Vehicle.is_active == True)
        .options(selectinload(Vehicle.routes).selectinload(TransportRoute.stops))
        .order_by(Vehicle.vehicle_number)
    )).scalars().all()
    # Build student map per vehicle
    student_map = {}
    assigned_counts = {}
    for v in vehicles:
        vid = str(v.id)
        student_map[vid] = []
        for r in v.routes:
            assignments = (await db.execute(
                select(StudentTransport).where(StudentTransport.route_id == r.id, StudentTransport.is_active == True)
            )).scalars().all()
            for a in assignments:
                s = (await db.execute(select(Student).where(Student.id == a.student_id))).scalar_one_or_none()
                if s: student_map[vid].append({"name": s.full_name, "id": str(s.id)})
        assigned_counts[vid] = len(student_map[vid])
    return templates.TemplateResponse("school_admin/transport_vehicles.html", {
        "request": request, "user": user, "active_page": "transport_vehicles",
        "vehicles": vehicles, "today": date.today(),
        "student_map": student_map, "assigned_counts": assigned_counts,
    })


@router.get("/routes", response_class=HTMLResponse)
@require_role(UserRole.SCHOOL_ADMIN)
async def routes_page(request: Request, db: AsyncSession = Depends(get_db)):
    user = request.state.user
    branch_id = uuid.UUID(user["branch_id"])
    from models.mega_modules import TransportRoute, Vehicle, RouteStop
    routes = (await db.execute(
        select(TransportRoute).where(TransportRoute.branch_id == branch_id, TransportRoute.is_active == True)
        .options(selectinload(TransportRoute.vehicle), selectinload(TransportRoute.stops))
        .order_by(TransportRoute.route_name)
    )).scalars().all()
    vehicles = (await db.execute(
        select(Vehicle).where(Vehicle.branch_id == branch_id, Vehicle.is_active == True)
    )).scalars().all()
    return templates.TemplateResponse("school_admin/transport_routes.html", {
        "request": request, "user": user, "active_page": "transport_routes",
        "routes": routes, "vehicles": vehicles,
    })


@router.get("/assignments", response_class=HTMLResponse)
@require_role(UserRole.SCHOOL_ADMIN)
async def assignments_page(request: Request, db: AsyncSession = Depends(get_db)):
    user = request.state.user
    branch_id = uuid.UUID(user["branch_id"])
    from models.mega_modules import TransportRoute, StudentTransport
    from models.student import Student
    routes = (await db.execute(
        select(TransportRoute).where(TransportRoute.branch_id == branch_id, TransportRoute.is_active == True)
        .options(selectinload(TransportRoute.stops))
    )).scalars().all()
    assignments = (await db.execute(
        select(StudentTransport).where(StudentTransport.is_active == True)
    )).scalars().all()
    students = (await db.execute(
        select(Student).where(Student.branch_id == branch_id, Student.is_active == True)
        .options(selectinload(Student.class_))
    )).scalars().all()
    return templates.TemplateResponse("school_admin/transport_assignments.html", {
        "request": request, "user": user, "active_page": "transport_assignments",
        "routes": routes, "assignments": assignments, "students": students,
    })