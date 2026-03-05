"""Transport API — CRUD for Vehicles, Routes, Stops, Student Assignments"""
from fastapi import APIRouter, Request, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from database import get_db
from models.user import UserRole
from utils.permissions import require_role
from utils.audit import log_audit, AuditAction
from pydantic import BaseModel
from typing import Optional, List
from datetime import time, date
import uuid

router = APIRouter(prefix="/api/school/transport")


class VehicleData(BaseModel):
    vehicle_number: str
    vehicle_type: Optional[str] = "bus"
    capacity: Optional[int] = 40
    make_model: Optional[str] = None
    driver_name: Optional[str] = None
    driver_phone: Optional[str] = None
    driver_license: Optional[str] = None
    conductor_name: Optional[str] = None
    conductor_phone: Optional[str] = None
    insurance_number: Optional[str] = None
    insurance_expiry: Optional[str] = None
    fitness_expiry: Optional[str] = None


class RouteData(BaseModel):
    route_name: str
    route_number: Optional[str] = None
    vehicle_id: Optional[str] = None
    monthly_fee: Optional[float] = 0
    start_time: Optional[str] = None
    end_time: Optional[str] = None


class StopData(BaseModel):
    route_id: str
    stop_name: str
    stop_order: Optional[int] = 1
    pickup_time: Optional[str] = None
    drop_time: Optional[str] = None


class AssignData(BaseModel):
    student_id: str
    route_id: str
    stop_id: Optional[str] = None


# ─── VEHICLES ──────────────────────────────────────────────
@router.post("/vehicles/create")
@require_role(UserRole.SCHOOL_ADMIN)
async def create_vehicle(request: Request, data: VehicleData, db: AsyncSession = Depends(get_db)):
    user = request.state.user
    from models.mega_modules import Vehicle
    v = Vehicle(branch_id=uuid.UUID(user["branch_id"]), vehicle_number=data.vehicle_number,
                vehicle_type=data.vehicle_type, capacity=data.capacity, make_model=data.make_model,
                driver_name=data.driver_name, driver_phone=data.driver_phone, driver_license=data.driver_license,
                conductor_name=data.conductor_name, conductor_phone=data.conductor_phone,
                insurance_number=data.insurance_number)
    db.add(v)
    await log_audit(db, user["branch_id"], user, AuditAction.CREATE, "vehicle", str(v.id),
                    f"Added vehicle {data.vehicle_number}")
    await db.commit()
    return {"id": str(v.id), "message": f"Vehicle {data.vehicle_number} added"}


@router.delete("/vehicles/{vid}")
@require_role(UserRole.SCHOOL_ADMIN)
async def delete_vehicle(request: Request, vid: str, db: AsyncSession = Depends(get_db)):
    from models.mega_modules import Vehicle
    v = (await db.execute(select(Vehicle).where(Vehicle.id == uuid.UUID(vid)))).scalar_one_or_none()
    if not v: raise HTTPException(404, "Vehicle not found")
    v.is_active = False
    await db.commit()
    return {"message": "Vehicle removed"}


@router.put("/vehicles/{vid}")
@require_role(UserRole.SCHOOL_ADMIN)
async def update_vehicle(request: Request, vid: str, db: AsyncSession = Depends(get_db)):
    from models.mega_modules import Vehicle
    data = await request.json()
    v = (await db.execute(select(Vehicle).where(Vehicle.id == uuid.UUID(vid)))).scalar_one_or_none()
    if not v: raise HTTPException(404, "Vehicle not found")
    for field in ["vehicle_number", "vehicle_type", "capacity", "make_model",
                  "driver_name", "driver_phone", "driver_license",
                  "conductor_name", "conductor_phone"]:
        if field in data and data[field] is not None:
            setattr(v, field, data[field])
    await db.commit()
    return {"message": f"Vehicle {v.vehicle_number} updated"}


@router.post("/routes/{route_id}/change-vehicle")
@require_role(UserRole.SCHOOL_ADMIN)
async def change_route_vehicle(request: Request, route_id: str, db: AsyncSession = Depends(get_db)):
    """Change vehicle for a route and notify all assigned students + parents."""
    from models.mega_modules import TransportRoute, Vehicle, StudentTransport
    from models.notification import Notification
    from models.student import Student
    data = await request.json()
    user = request.state.user
    route = (await db.execute(select(TransportRoute).where(TransportRoute.id == uuid.UUID(route_id)))).scalar_one_or_none()
    if not route: raise HTTPException(404)
    old_vehicle = (await db.execute(select(Vehicle).where(Vehicle.id == route.vehicle_id))).scalar_one_or_none() if route.vehicle_id else None
    new_vehicle_id = uuid.UUID(data["vehicle_id"])
    new_vehicle = (await db.execute(select(Vehicle).where(Vehicle.id == new_vehicle_id))).scalar_one_or_none()
    if not new_vehicle: raise HTTPException(404, "New vehicle not found")
    route.vehicle_id = new_vehicle_id
    # Find all students on this route
    assignments = (await db.execute(
        select(StudentTransport).where(StudentTransport.route_id == route.id, StudentTransport.is_active == True)
    )).scalars().all()
    notified = 0
    for a in assignments:
        student = (await db.execute(select(Student).where(Student.id == a.student_id))).scalar_one_or_none()
        if not student: continue
        msg = f"🚌 Bus Change: Route '{route.route_name}' vehicle changed from {old_vehicle.vehicle_number if old_vehicle else 'N/A'} to {new_vehicle.vehicle_number}. New driver: {new_vehicle.driver_name or 'TBA'}, Phone: {new_vehicle.driver_phone or 'TBA'}"
        # Notify student
        if student.user_id:
            db.add(Notification(branch_id=route.branch_id, user_id=student.user_id, title="Bus Changed", message=msg, notification_type="transport"))
            notified += 1
        # Notify parent
        if student.parent_user_id:
            db.add(Notification(branch_id=route.branch_id, user_id=student.parent_user_id, title="Bus Changed for " + student.full_name, message=msg, notification_type="transport"))
            notified += 1
    await db.commit()
    return {"message": f"Vehicle changed. {notified} notifications sent.", "notified": notified}


@router.get("/vehicles/{vid}/students")
@require_role(UserRole.SCHOOL_ADMIN)
async def get_vehicle_students(request: Request, vid: str, db: AsyncSession = Depends(get_db)):
    """Get list of students assigned to a vehicle (via its routes)."""
    from models.mega_modules import TransportRoute, StudentTransport
    from models.student import Student
    routes = (await db.execute(
        select(TransportRoute).where(TransportRoute.vehicle_id == uuid.UUID(vid))
    )).scalars().all()
    students = []
    for r in routes:
        assignments = (await db.execute(
            select(StudentTransport).where(StudentTransport.route_id == r.id, StudentTransport.is_active == True)
        )).scalars().all()
        for a in assignments:
            s = (await db.execute(
                select(Student).where(Student.id == a.student_id)
                .options(selectinload(Student.class_))
            )).scalar_one_or_none()
            if s:
                # Get stop name if stop_id is set
                stop_name = ""
                if a.stop_id:
                    from models.mega_modules import RouteStop
                    stop = (await db.execute(select(RouteStop).where(RouteStop.id == a.stop_id))).scalar_one_or_none()
                    stop_name = stop.stop_name if stop else ""
                students.append({
                    "id": str(s.id),
                    "name": s.full_name,
                    "class_name": s.class_.name if s.class_ else "—",
                    "route": r.route_name,
                    "stop": stop_name,
                    "phone": s.father_phone or s.mother_phone or "",
                })
    return {"students": students, "count": len(students)}


# ─── ROUTES ────────────────────────────────────────────────
@router.post("/routes/create")
@require_role(UserRole.SCHOOL_ADMIN)
async def create_route(request: Request, data: RouteData, db: AsyncSession = Depends(get_db)):
    user = request.state.user
    from models.mega_modules import TransportRoute
    r = TransportRoute(branch_id=uuid.UUID(user["branch_id"]), route_name=data.route_name,
                       route_number=data.route_number, monthly_fee=data.monthly_fee or 0,
                       vehicle_id=uuid.UUID(data.vehicle_id) if data.vehicle_id else None)
    db.add(r)
    await log_audit(db, user["branch_id"], user, AuditAction.CREATE, "route", str(r.id),
                    f"Created route {data.route_name}")
    await db.commit()
    return {"id": str(r.id), "message": f"Route {data.route_name} created"}


@router.post("/stops/create")
@require_role(UserRole.SCHOOL_ADMIN)
async def create_stop(request: Request, data: StopData, db: AsyncSession = Depends(get_db)):
    from models.mega_modules import RouteStop
    s = RouteStop(route_id=uuid.UUID(data.route_id), stop_name=data.stop_name,
                  stop_order=data.stop_order)
    db.add(s)
    await db.commit()
    return {"id": str(s.id), "message": f"Stop {data.stop_name} added"}


# ─── ASSIGNMENTS ───────────────────────────────────────────
@router.post("/assign")
@require_role(UserRole.SCHOOL_ADMIN)
async def assign_student(request: Request, data: AssignData, db: AsyncSession = Depends(get_db)):
    from models.mega_modules import StudentTransport
    # Deactivate existing
    existing = (await db.execute(select(StudentTransport).where(
        StudentTransport.student_id == uuid.UUID(data.student_id), StudentTransport.is_active == True
    ))).scalar_one_or_none()
    if existing:
        existing.is_active = False

    st = StudentTransport(student_id=uuid.UUID(data.student_id),
                          route_id=uuid.UUID(data.route_id),
                          stop_id=uuid.UUID(data.stop_id) if data.stop_id else None)
    db.add(st)
    await db.commit()
    return {"message": "Student assigned to route"}


@router.delete("/unassign/{assignment_id}")
@require_role(UserRole.SCHOOL_ADMIN)
async def unassign_student(request: Request, assignment_id: str, db: AsyncSession = Depends(get_db)):
    """Remove a student's transport assignment."""
    from models.mega_modules import StudentTransport
    a = (await db.execute(
        select(StudentTransport).where(StudentTransport.id == uuid.UUID(assignment_id), StudentTransport.is_active == True)
    )).scalar_one_or_none()
    if not a:
        raise HTTPException(404, "Assignment not found")
    a.is_active = False
    await db.commit()
    return {"message": "Student unassigned from route"}


@router.get("/summary")
@require_role(UserRole.SCHOOL_ADMIN)
async def transport_summary(request: Request, db: AsyncSession = Depends(get_db)):
    user = request.state.user
    branch_id = uuid.UUID(user["branch_id"])
    from models.mega_modules import Vehicle, TransportRoute, StudentTransport
    vehicles = await db.scalar(select(func.count()).select_from(Vehicle).where(Vehicle.branch_id == branch_id, Vehicle.is_active == True)) or 0
    routes = await db.scalar(select(func.count()).select_from(TransportRoute).where(TransportRoute.branch_id == branch_id, TransportRoute.is_active == True)) or 0
    assigned = await db.scalar(select(func.count()).select_from(StudentTransport).where(StudentTransport.is_active == True)) or 0
    return {"vehicles": vehicles, "routes": routes, "students_assigned": assigned}


from sqlalchemy import func