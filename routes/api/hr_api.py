"""HR API — Employee CRUD, Payroll, Salary Slips, ID Cards"""
from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, text
from sqlalchemy.orm import selectinload
from database import get_db
from models.user import UserRole
from utils.permissions import require_role
from utils.audit import log_audit, AuditAction
from pydantic import BaseModel
from typing import Optional
import uuid
from datetime import datetime

router = APIRouter(prefix="/api/school/hr")


class EmployeeData(BaseModel):
    first_name: str
    last_name: Optional[str] = ""
    email: Optional[str] = None
    phone: Optional[str] = None
    employee_type: Optional[str] = "non_teaching"
    designation: Optional[str] = None
    department: Optional[str] = None
    date_of_joining: Optional[str] = None
    date_of_birth: Optional[str] = None
    gender: Optional[str] = None
    blood_group: Optional[str] = None
    address: Optional[str] = None
    emergency_contact_name: Optional[str] = None
    emergency_contact_phone: Optional[str] = None
    basic_salary: Optional[float] = 0
    hra: Optional[float] = 0
    da: Optional[float] = 0
    conveyance: Optional[float] = 0
    medical: Optional[float] = 0
    special_allowance: Optional[float] = 0
    pf_deduction: Optional[float] = 0
    esi_deduction: Optional[float] = 0
    tds_deduction: Optional[float] = 0
    bank_name: Optional[str] = None
    bank_account: Optional[str] = None
    ifsc_code: Optional[str] = None
    pan_number: Optional[str] = None
    aadhaar_number: Optional[str] = None
    bank_ifsc: Optional[str] = None


@router.get("/employees")
@require_role(UserRole.SCHOOL_ADMIN)
async def list_employees(request: Request, db: AsyncSession = Depends(get_db)):
    """List all employees AND teachers for the branch."""
    from models.mega_modules import Employee
    from models.teacher import Teacher
    user = request.state.user
    branch_id = user.get("branch_id")
    if not branch_id:
        return {"employees": []}
    bid = uuid.UUID(branch_id)
    result = []

    # HR Employees (non-teaching staff)
    emps = (await db.execute(
        select(Employee).where(Employee.branch_id == bid).order_by(Employee.first_name)
    )).scalars().all()
    for e in emps:
        result.append({
            "id": str(e.id), "name": f"{e.first_name} {e.last_name or ''}".strip(),
            "emp_id": e.employee_code or "", "type": "employee",
            "designation": e.designation or "", "department": e.department or "",
            "phone": e.phone or "", "email": e.email or "",
            "is_active": e.is_active if hasattr(e, 'is_active') else True,
            "date_of_joining": e.date_of_joining.strftime('%Y-%m-%d') if e.date_of_joining else "",
        })

    # Teachers (teaching staff — principal, VP, HOD, teachers)
    teachers = (await db.execute(
        select(Teacher).where(Teacher.branch_id == bid).order_by(Teacher.first_name)
    )).scalars().all()
    for t in teachers:
        result.append({
            "id": str(t.id), "name": f"{t.first_name} {t.last_name or ''}".strip(),
            "emp_id": t.employee_id or "",
            "type": "teacher",
            "designation": t.designation or "Teacher",
            "department": "Teaching",
            "phone": t.phone or "", "email": t.email or "",
            "is_active": t.is_active if hasattr(t, 'is_active') else True,
            "date_of_joining": t.joining_date.strftime('%Y-%m-%d') if t.joining_date else "",
        })

    result.sort(key=lambda x: x["name"])
    return {"employees": result}


@router.get("/employees/{eid}")
@require_role(UserRole.SCHOOL_ADMIN)
async def get_employee(request: Request, eid: str, db: AsyncSession = Depends(get_db)):
    """Get single employee details for edit form."""
    from models.id_card import Employee
    emp = await db.scalar(select(Employee).where(Employee.id == uuid.UUID(eid)))
    if not emp: return {"employee": None}
    return {"employee": {
        "first_name": emp.first_name, "last_name": emp.last_name or "",
        "phone": emp.phone, "email": emp.email,
        "employee_type": emp.employee_type.value if emp.employee_type else "non_teaching",
        "designation": emp.designation, "department": emp.department,
        "gender": emp.gender, "blood_group": emp.blood_group,
        "date_of_joining": emp.date_of_joining.isoformat() if emp.date_of_joining else "",
        "date_of_birth": emp.date_of_birth.isoformat() if emp.date_of_birth else "",
        "address": emp.address, "basic_salary": float(emp.basic_salary or 0),
        "pan_number": emp.pan_number or "", "aadhaar_number": emp.aadhaar_number or "",
        "bank_account": emp.bank_account or "", "bank_ifsc": emp.ifsc_code or emp.bank_ifsc if hasattr(emp, 'bank_ifsc') else "",
        "emergency_contact_name": emp.emergency_contact_name or "",
        "emergency_contact_phone": emp.emergency_contact_phone or "",
    }}


@router.post("/employees/create")
@require_role(UserRole.SCHOOL_ADMIN)
async def create_employee(request: Request, data: EmployeeData, db: AsyncSession = Depends(get_db)):
    user = request.state.user
    from models.mega_modules import Employee, EmployeeType
    from datetime import date
    emp = Employee(
        branch_id=uuid.UUID(user["branch_id"]),
        first_name=data.first_name, last_name=data.last_name,
        email=data.email, phone=data.phone,
        employee_type=EmployeeType(data.employee_type) if data.employee_type in ['teaching', 'non_teaching', 'admin', 'support'] else EmployeeType.NON_TEACHING,
        designation=data.designation, department=data.department,
        gender=data.gender, blood_group=data.blood_group, address=data.address,
        emergency_contact_name=data.emergency_contact_name,
        emergency_contact_phone=data.emergency_contact_phone,
        basic_salary=data.basic_salary or 0, hra=data.hra or 0, da=data.da or 0,
        conveyance=data.conveyance or 0, medical=data.medical or 0,
        special_allowance=data.special_allowance or 0,
        pf_deduction=data.pf_deduction or 0, esi_deduction=data.esi_deduction or 0,
        tds_deduction=data.tds_deduction or 0,
        bank_name=data.bank_name, bank_account=data.bank_account,
        ifsc_code=data.ifsc_code, pan_number=data.pan_number,
    )
    if data.date_of_joining:
        try: emp.date_of_joining = date.fromisoformat(data.date_of_joining)
        except: pass
    if data.date_of_birth:
        try: emp.date_of_birth = date.fromisoformat(data.date_of_birth)
        except: pass
    emp.employee_code = f"EMP-{str(uuid.uuid4())[:6].upper()}"
    db.add(emp)
    await log_audit(db, user["branch_id"], user, AuditAction.CREATE, "employee", str(emp.id),
                    f"Added employee {data.first_name} {data.last_name} as {data.designation}")
    await db.commit()
    return {"id": str(emp.id), "message": f"Employee {emp.full_name} added", "code": emp.employee_code}


@router.put("/employees/{eid}")
@require_role(UserRole.SCHOOL_ADMIN)
async def update_employee(request: Request, eid: str, data: EmployeeData, db: AsyncSession = Depends(get_db)):
    from models.mega_modules import Employee
    emp = (await db.execute(select(Employee).where(Employee.id == uuid.UUID(eid)))).scalar_one_or_none()
    if not emp: raise HTTPException(404, "Employee not found")
    for field in ['first_name', 'last_name', 'email', 'phone', 'designation', 'department',
                  'gender', 'blood_group', 'address', 'emergency_contact_name', 'emergency_contact_phone',
                  'bank_name', 'bank_account', 'ifsc_code', 'pan_number']:
        val = getattr(data, field, None)
        if val is not None: setattr(emp, field, val)
    for field in ['basic_salary', 'hra', 'da', 'conveyance', 'medical', 'special_allowance',
                  'pf_deduction', 'esi_deduction', 'tds_deduction']:
        val = getattr(data, field, None)
        if val is not None: setattr(emp, field, val or 0)
    await db.commit()
    return {"message": "Employee updated"}


@router.delete("/employees/{eid}")
@require_role(UserRole.SCHOOL_ADMIN)
async def delete_employee(eid: str, request: Request, db: AsyncSession = Depends(get_db)):
    from models.mega_modules import Employee
    emp = (await db.execute(select(Employee).where(Employee.id == uuid.UUID(eid)))).scalar_one_or_none()
    if not emp: raise HTTPException(404)
    emp.is_active = False
    await db.commit()
    return {"message": "Employee deactivated"}


@router.put("/employees/{eid}/separate")
@require_role(UserRole.SCHOOL_ADMIN)
async def separate_employee(request: Request, eid: str, db: AsyncSession = Depends(get_db)):
    """Separate an employee — deactivate and record separation details."""
    from models.mega_modules import Employee
    data = await request.json()
    emp = (await db.execute(select(Employee).where(Employee.id == uuid.UUID(eid)))).scalar_one_or_none()
    if not emp:
        raise HTTPException(404, "Employee not found")
    emp.is_active = False
    if hasattr(emp, 'remarks'):
        emp.remarks = data.get("remarks", "")
    if hasattr(emp, 'separation_date'):
        from datetime import date
        lwd = data.get("lwd")
        if lwd:
            emp.separation_date = date.fromisoformat(lwd)
    await db.commit()
    return {"success": True, "message": f"{emp.first_name} has been separated"}


@router.put("/employees/{eid}/rehire")
@require_role(UserRole.SCHOOL_ADMIN)
async def rehire_employee(request: Request, eid: str, db: AsyncSession = Depends(get_db)):
    """Rehire a separated employee."""
    from models.mega_modules import Employee
    emp = (await db.execute(select(Employee).where(Employee.id == uuid.UUID(eid)))).scalar_one_or_none()
    if not emp:
        raise HTTPException(404, "Employee not found")
    emp.is_active = True
    if hasattr(emp, 'remarks'):
        emp.remarks = (emp.remarks or "") + f" | Rehired on {datetime.utcnow().strftime('%Y-%m-%d')}"
    await db.commit()
    return {"success": True, "message": f"{emp.first_name} has been rehired"}


@router.put("/teachers/{tid}/separate")
@require_role(UserRole.SCHOOL_ADMIN)
async def separate_teacher(request: Request, tid: str, db: AsyncSession = Depends(get_db)):
    """Separate a teacher."""
    from models.teacher import Teacher
    data = await request.json()
    t = (await db.execute(select(Teacher).where(Teacher.id == uuid.UUID(tid)))).scalar_one_or_none()
    if not t:
        raise HTTPException(404, "Teacher not found")
    t.is_active = False
    # Disable linked User account login
    if t.user_id:
        from models.user import User
        linked_user = await db.scalar(select(User).where(User.id == t.user_id))
        if linked_user:
            linked_user.is_active = False
    await db.commit()
    return {"success": True, "message": f"{t.first_name} has been separated"}


@router.put("/teachers/{tid}/rehire")
@require_role(UserRole.SCHOOL_ADMIN)
async def rehire_teacher(request: Request, tid: str, db: AsyncSession = Depends(get_db)):
    """Rehire a separated teacher."""
    from models.teacher import Teacher
    t = (await db.execute(select(Teacher).where(Teacher.id == uuid.UUID(tid)))).scalar_one_or_none()
    if not t:
        raise HTTPException(404, "Teacher not found")
    t.is_active = True
    # Re-enable linked User account login
    if t.user_id:
        from models.user import User
        linked_user = await db.scalar(select(User).where(User.id == t.user_id))
        if linked_user:
            linked_user.is_active = True
    await db.commit()
    return {"success": True, "message": f"{t.first_name} has been rehired"}


# ─── SEPARATION REQUESTS (Teacher self-service) ──────────────
@router.post("/separation-requests")
@require_role(UserRole.SCHOOL_ADMIN, UserRole.TEACHER)
async def create_separation_request(request: Request, db: AsyncSession = Depends(get_db)):
    """Teacher raises a separation request."""
    data = await request.json()
    user = request.state.user
    branch_id = user.get("branch_id")
    # Store as a simple record
    req_id = uuid.uuid4()
    await db.execute(
        text("""INSERT INTO separation_requests (id, branch_id, user_id, employee_name, employee_type, employee_ref_id, reason, requested_date, last_working_day, remarks, status, created_at)
        VALUES (:id, :bid, :uid, :name, :etype, :ref_id, :reason, :req_date, :lwd, :remarks, 'pending', NOW())"""),
        {"id": str(req_id), "bid": branch_id, "uid": user.get("user_id"), "name": data.get("name",""),
         "etype": data.get("type","employee"), "ref_id": data.get("ref_id",""),
         "reason": data.get("reason",""), "req_date": data.get("requested_date",""),
         "lwd": data.get("last_working_day",""), "remarks": data.get("remarks","")}
    )
    await db.commit()
    return {"success": True, "message": "Separation request submitted for approval"}


@router.get("/separation-requests")
@require_role(UserRole.SCHOOL_ADMIN)
async def list_separation_requests(request: Request, db: AsyncSession = Depends(get_db)):
    """List all separation requests for the branch."""
    user = request.state.user
    branch_id = user.get("branch_id")
    rows = (await db.execute(
        text("SELECT * FROM separation_requests WHERE branch_id = :bid ORDER BY created_at DESC"),
        {"bid": branch_id}
    )).mappings().all()
    return {"requests": [dict(r) for r in rows]}


@router.put("/separation-requests/{req_id}")
@require_role(UserRole.SCHOOL_ADMIN)
async def update_separation_request(req_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    """Approve or reject a separation request."""
    data = await request.json()
    status = data.get("status")  # 'approved' or 'rejected'
    if status not in ("approved", "rejected"):
        return {"error": "Status must be approved or rejected"}
    await db.execute(
        text("UPDATE separation_requests SET status = :status, reviewed_by = :by, reviewed_at = NOW() WHERE id = :id"),
        {"status": status, "by": request.state.user.get("user_id"), "id": req_id}
    )

    # ── AUTO-DEACTIVATE on approval ──
    if status == "approved":
        try:
            ref_row = (await db.execute(
                text("SELECT employee_ref_id, employee_type FROM separation_requests WHERE id = :id"),
                {"id": req_id}
            )).mappings().first()
            if ref_row and ref_row.get("employee_type") == "teacher":
                from models.teacher import Teacher
                from models.user import User
                teacher = (await db.execute(
                    select(Teacher).where(Teacher.id == uuid.UUID(ref_row["employee_ref_id"]))
                )).scalar_one_or_none()
                if teacher:
                    teacher.is_active = False
                    teacher.work_status = "resigned"
                    if teacher.user_id:
                        user_obj = (await db.execute(
                            select(User).where(User.id == teacher.user_id)
                        )).scalar_one_or_none()
                        if user_obj:
                            user_obj.is_active = False
        except Exception as e:
            print(f"[WARN] Separation auto-deactivation failed: {e}")

    await db.commit()
    return {"success": True, "message": f"Request {status}"}


# ─── EMPLOYEE DOCUMENTS (stored on profile) ──────────────
@router.post("/employees/{eid}/documents")
@require_role(UserRole.SCHOOL_ADMIN)
async def save_employee_document(request: Request, eid: str, db: AsyncSession = Depends(get_db)):
    """Save a generated document reference to employee profile."""
    data = await request.json()
    user = request.state.user
    branch_id = user.get("branch_id")
    try:
        await db.execute(
            text("""INSERT INTO employee_documents (id, branch_id, employee_id, employee_type, doc_type, ref_number, generated_by, generated_at)
            VALUES (:id, :bid, :eid, :etype, :dtype, :ref, :by, NOW())"""),
            {"id": str(uuid.uuid4()), "bid": branch_id, "eid": eid,
             "etype": data.get("employee_type", "employee"),
             "dtype": data.get("doc_type", ""), "ref": data.get("ref_number", ""),
             "by": data.get("generated_by", "")}
        )
        await db.commit()
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.get("/employees/{eid}/documents")
@require_role(UserRole.SCHOOL_ADMIN)
async def list_employee_documents(request: Request, eid: str, db: AsyncSession = Depends(get_db)):
    """List all documents generated for an employee."""
    try:
        rows = (await db.execute(
            text("SELECT * FROM employee_documents WHERE employee_id = :eid ORDER BY generated_at DESC"),
            {"eid": eid}
        )).mappings().all()
        return {"documents": [dict(r) for r in rows]}
    except:
        return {"documents": []}


# ─── PAYROLL ───────────────────────────────────────────────
class PayrollGenData(BaseModel):
    month: int
    year: int


@router.post("/payroll/generate")
@require_role(UserRole.SCHOOL_ADMIN)
async def generate_payroll(request: Request, data: PayrollGenData, db: AsyncSession = Depends(get_db)):
    user = request.state.user
    branch_id = uuid.UUID(user["branch_id"])
    from models.mega_modules import Employee, SalarySlip
    employees = (await db.execute(
        select(Employee).where(Employee.branch_id == branch_id, Employee.is_active == True)
    )).scalars().all()

    count = 0
    for emp in employees:
        # Check if already generated
        existing = (await db.execute(select(SalarySlip).where(
            SalarySlip.employee_id == emp.id, SalarySlip.month == data.month, SalarySlip.year == data.year
        ))).scalar_one_or_none()
        if existing: continue

        slip = SalarySlip(
            branch_id=branch_id, employee_id=emp.id,
            month=data.month, year=data.year,
            basic_salary=emp.basic_salary, hra=emp.hra, da=emp.da,
            conveyance=emp.conveyance, medical=emp.medical,
            special_allowance=emp.special_allowance,
            pf_deduction=emp.pf_deduction, esi_deduction=emp.esi_deduction,
            tds_deduction=emp.tds_deduction, other_deduction=emp.other_deduction or 0,
            working_days=26, days_present=26,
            gross_salary=emp.gross_salary, total_deductions=emp.total_deductions,
            net_salary=emp.net_salary, status="generated",
        )
        db.add(slip)
        count += 1

    await log_audit(db, user["branch_id"], user, AuditAction.CREATE, "payroll", "",
                    f"Generated payroll for {data.month}/{data.year} — {count} slips")
    await db.commit()
    return {"message": f"Payroll generated for {count} employees", "count": count}


@router.get("/salary-slip-pdf/{slip_id}")
@require_role(UserRole.SCHOOL_ADMIN)
async def salary_slip_pdf(request: Request, slip_id: str, db: AsyncSession = Depends(get_db)):
    from models.mega_modules import SalarySlip, Employee
    from models.branch import Branch
    from utils.id_card_generator import generate_salary_slip_pdf

    slip = (await db.execute(select(SalarySlip).where(SalarySlip.id == uuid.UUID(slip_id)))).scalar_one_or_none()
    if not slip: raise HTTPException(404)
    emp = (await db.execute(select(Employee).where(Employee.id == slip.employee_id))).scalar_one_or_none()
    branch = (await db.execute(select(Branch).where(Branch.id == slip.branch_id))).scalar_one_or_none()

    school_data = {"name": branch.name if branch else "", "address": branch.address if branch else "",
                   "logo_url": branch.logo_url if branch else ""}
    salary_data = {
        "employee_name": emp.full_name if emp else "", "employee_code": emp.employee_code if emp else "",
        "designation": emp.designation if emp else "", "department": emp.department if emp else "",
        "month": slip.month, "year": slip.year,
        "basic": float(slip.basic_salary), "hra": float(slip.hra), "da": float(slip.da),
        "conveyance": float(slip.conveyance), "medical": float(slip.medical),
        "special": float(slip.special_allowance),
        "pf": float(slip.pf_deduction), "esi": float(slip.esi_deduction),
        "tds": float(slip.tds_deduction), "other_ded": float(slip.other_deduction),
        "gross": float(slip.gross_salary), "deductions": float(slip.total_deductions),
        "net": float(slip.net_salary),
        "days_present": slip.days_present, "days_absent": slip.days_absent,
        "working_days": slip.working_days,
    }
    pdf_bytes = generate_salary_slip_pdf(school_data, salary_data)
    return Response(content=pdf_bytes, media_type="application/pdf",
                    headers={"Content-Disposition": f"inline; filename=salary_{emp.employee_code}_{slip.month}_{slip.year}.pdf"})


# ─── ID CARDS ──────────────────────────────────────────────
@router.get("/student-id-card/{student_id}")
@require_role(UserRole.SCHOOL_ADMIN)
async def student_id_card(request: Request, student_id: str, db: AsyncSession = Depends(get_db)):
    from models.student import Student
    from models.branch import Branch
    from utils.id_card_generator import generate_student_id_card_pdf

    student = (await db.execute(
        select(Student).where(Student.id == uuid.UUID(student_id))
        .options(selectinload(Student.class_), selectinload(Student.section))
    )).scalar_one_or_none()
    if not student: raise HTTPException(404)
    branch = (await db.execute(select(Branch).where(Branch.id == student.branch_id))).scalar_one_or_none()

    school_data = {
        "name": branch.name if branch else "", "logo_url": branch.logo_url if branch else "",
        "motto": branch.motto if branch else "", "accreditation": branch.accreditation if branch else "",
        "address": branch.address if branch else "", "phone": branch.phone if branch else "",
        "landline": branch.landline if branch else "", "website": branch.website_url if branch else "",
    }
    student_data = {
        "name": student.full_name, "student_id": str(student.id),
        "roll_number": student.roll_number or "", "admission_number": student.admission_number or "",
        "dob": student.date_of_birth.strftime('%d %b %Y') if student.date_of_birth else "",
        "blood_group": student.blood_group or "", "photo_url": student.photo_url or "",
        "father_name": student.father_name or "", "mother_name": student.mother_name or "",
        "emergency_contact": student.emergency_contact or student.father_phone or "",
        "address": student.address or "", "valid_from": "Apr 2025", "valid_to": "Mar 2026",
    }
    # Get class/section names safely
    from models.academic import Class as Cls, Section
    cls_name = await db.scalar(select(Cls.name).where(Cls.id == student.class_id)) if student.class_id else ""
    sec_name = await db.scalar(select(Section.name).where(Section.id == student.section_id)) if student.section_id else ""
    student_data["class_name"] = f"{cls_name or ''} {sec_name or ''}".strip()
    pdf_bytes = generate_student_id_card_pdf(school_data, student_data)
    return Response(content=pdf_bytes, media_type="application/pdf",
                    headers={"Content-Disposition": f"inline; filename=id_card_{student.admission_number or student.id}.pdf"})


@router.get("/employee-id-card/{emp_id}")
@require_role(UserRole.SCHOOL_ADMIN)
async def employee_id_card(request: Request, emp_id: str, db: AsyncSession = Depends(get_db)):
    from models.mega_modules import Employee
    from models.branch import Branch
    from utils.id_card_generator import generate_employee_id_card_pdf

    emp = (await db.execute(select(Employee).where(Employee.id == uuid.UUID(emp_id)))).scalar_one_or_none()
    if not emp: raise HTTPException(404)
    branch = (await db.execute(select(Branch).where(Branch.id == emp.branch_id))).scalar_one_or_none()

    school_data = {
        "name": branch.name if branch else "", "logo_url": branch.logo_url if branch else "",
        "motto": branch.motto if branch else "", "accreditation": branch.accreditation if branch else "",
        "address": branch.address if branch else "", "phone": branch.phone if branch else "",
        "landline": branch.landline if branch else "",
    }
    employee_data = {
        "name": emp.full_name, "employee_id": str(emp.id), "employee_code": emp.employee_code or "",
        "designation": emp.designation or "", "department": emp.department or "",
        "dob": emp.date_of_birth.strftime('%d %b %Y') if emp.date_of_birth else "",
        "blood_group": emp.blood_group or "", "photo_url": emp.photo_url or "",
        "emergency_contact_name": emp.emergency_contact_name or "",
        "emergency_contact_phone": emp.emergency_contact_phone or "",
        "address": emp.address or "", "valid_from": "Apr 2025", "valid_to": "Mar 2026",
    }
    pdf_bytes = generate_employee_id_card_pdf(school_data, employee_data)
    return Response(content=pdf_bytes, media_type="application/pdf",
                    headers={"Content-Disposition": f"inline; filename=id_{emp.employee_code}.pdf"})


@router.get("/teacher-id-card/{teacher_id}")
@require_role(UserRole.SCHOOL_ADMIN)
async def teacher_id_card(request: Request, teacher_id: str, db: AsyncSession = Depends(get_db)):
    from models.teacher import Teacher
    from models.branch import Branch
    from utils.id_card_generator import generate_teacher_id_card_pdf

    teacher = (await db.execute(select(Teacher).where(Teacher.id == uuid.UUID(teacher_id)))).scalar_one_or_none()
    if not teacher: raise HTTPException(404)
    branch = (await db.execute(select(Branch).where(Branch.id == teacher.branch_id))).scalar_one_or_none()

    school_data = {
        "name": branch.name if branch else "", "logo_url": branch.logo_url if branch else "",
        "motto": branch.motto if branch else "", "address": branch.address if branch else "",
        "phone": branch.phone if branch else "",
    }
    teacher_data = {
        "name": teacher.full_name, "employee_code": teacher.employee_code or "",
        "designation": teacher.designation or "Teacher",
        "department": teacher.department or teacher.specialization or "",
        "dob": teacher.date_of_birth.strftime('%d %b %Y') if teacher.date_of_birth else "",
        "blood_group": teacher.blood_group or "", "photo_url": teacher.photo_url or "",
        "emergency_contact_phone": teacher.emergency_contact or "",
        "valid_from": "Apr 2025", "valid_to": "Mar 2026",
    }
    pdf_bytes = generate_teacher_id_card_pdf(school_data, teacher_data)
    return Response(content=pdf_bytes, media_type="application/pdf",
                    headers={"Content-Disposition": f"inline; filename=teacher_id_{teacher.employee_code or teacher.id}.pdf"})


@router.post("/visitor-card")
@require_role(UserRole.SCHOOL_ADMIN)
async def visitor_card(request: Request, db: AsyncSession = Depends(get_db)):
    from models.branch import Branch
    from utils.id_card_generator import generate_visitor_card_pdf
    from datetime import datetime

    user = request.state.user
    branch_id = uuid.UUID(user["branch_id"])
    data = await request.json()

    branch = (await db.execute(select(Branch).where(Branch.id == branch_id))).scalar_one_or_none()
    school_data = {"name": branch.name if branch else "", "address": branch.address if branch else ""}
    visitor_data = {
        "name": data.get("name", "Guest"),
        "purpose": data.get("purpose", ""),
        "visiting_whom": data.get("visiting_whom", ""),
        "phone": data.get("phone", ""),
        "date": datetime.now().strftime("%d %b %Y"),
        "valid_until": data.get("valid_until", "Today Only"),
    }
    pdf_bytes = generate_visitor_card_pdf(school_data, visitor_data)
    return Response(content=pdf_bytes, media_type="application/pdf",
                    headers={"Content-Disposition": f"inline; filename=visitor_pass.pdf"})


@router.get("/verify-card/{qr_data}")
async def verify_id_card(request: Request, qr_data: str, db: AsyncSession = Depends(get_db)):
    """
    Verify a scanned QR code from ID card.
    QR format: EDUFLOW|TYPE|UUID|HMAC16
    Returns student/employee info if valid, error if tampered.
    """
    import hmac as hmac_mod, hashlib
    from utils.id_card_generator import QR_SECRET

    parts = qr_data.split("|")
    if len(parts) != 4 or parts[0] != "EDUFLOW":
        return {"valid": False, "error": "Invalid QR format"}

    _, entity_type, entity_id, provided_sig = parts
    expected_payload = f"{entity_type}|{entity_id}"
    expected_sig = hmac_mod.new(QR_SECRET.encode(), expected_payload.encode(), hashlib.sha256).hexdigest()[:16]

    if provided_sig != expected_sig:
        return {"valid": False, "error": "⚠️ TAMPERED CARD — signature mismatch"}

    # Valid! Fetch details
    if entity_type == "STUDENT":
        student = await db.scalar(select(Student).where(Student.id == uuid.UUID(entity_id)))
        if not student:
            return {"valid": False, "error": "Student not found"}
        from models.academic import Class as Cls, Section
        cls_name = await db.scalar(select(Cls.name).where(Cls.id == student.class_id)) if student.class_id else ""
        return {"valid": True, "type": "STUDENT", "name": student.full_name,
                "class": cls_name or "", "admission_no": student.admission_number or "",
                "photo_url": student.photo_url or ""}
    elif entity_type == "EMPLOYEE":
        from models.id_card import Employee
        emp = await db.scalar(select(Employee).where(Employee.id == uuid.UUID(entity_id)))
        if not emp:
            return {"valid": False, "error": "Employee not found"}
        return {"valid": True, "type": "EMPLOYEE", "name": emp.full_name,
                "designation": emp.designation or "", "department": emp.department or "",
                "employee_code": emp.employee_code or "", "photo_url": emp.photo_url or ""}
    return {"valid": False, "error": "Unknown entity type"}