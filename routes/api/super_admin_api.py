from fastapi import APIRouter, Request, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, text
from database import get_db
from models.user import User, UserRole
from models.organization import Organization, PlanType
from models.branch import Branch, BranchSettings, PaymentGatewayConfig, CommunicationConfig, BoardType
from utils.auth import hash_password, decode_access_token
from utils.helpers import generate_slug
from utils.permissions import get_current_user, require_role
from pydantic import BaseModel
from typing import Optional
import uuid
from datetime import datetime, timedelta

router = APIRouter(prefix="/api/super-admin")


# --- Pydantic Schemas ---
class OrgCreate(BaseModel):
    name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    pincode: Optional[str] = None
    plan_type: Optional[str] = "basic"


class BranchCreate(BaseModel):
    org_id: str
    name: str
    code: Optional[str] = None
    subdomain: Optional[str] = None  # e.g. "goenkajammu" → goenkajammu.vedaschoolpro.com
    board_type: Optional[str] = "cbse"
    principal_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    pincode: Optional[str] = None


class AdminCreate(BaseModel):
    branch_id: str
    first_name: str
    last_name: Optional[str] = None
    email: str
    phone: Optional[str] = None
    password: str


# --- Auth check helper ---
async def verify_super_admin(request: Request):
    user = await get_current_user(request)
    if not user or user.get("role") != "super_admin":
        raise HTTPException(status_code=403, detail="Access denied")
    return user


# --- Organization APIs ---
@router.post("/organizations")
async def create_organization(
    data: OrgCreate,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    await verify_super_admin(request)

    org = Organization(
        name=data.name,
        slug=generate_slug(data.name),
        email=data.email,
        phone=data.phone,
        address=data.address,
        city=data.city,
        state=data.state,
        pincode=data.pincode,
        plan_type=PlanType(data.plan_type) if data.plan_type else PlanType.BASIC,
    )
    db.add(org)
    await db.flush()

    return {"success": True, "message": "Organization created", "id": str(org.id)}


@router.delete("/organizations/{org_id}")
async def delete_organization(
    org_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    await verify_super_admin(request)

    result = await db.execute(select(Organization).where(Organization.id == uuid.UUID(org_id)))
    org = result.scalar_one_or_none()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")

    org.is_active = False
    return {"success": True, "message": "Organization deactivated"}


# --- Branch APIs ---
@router.post("/branches")
async def create_branch(
    data: BranchCreate,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    await verify_super_admin(request)

    # Validate subdomain — lowercase, alphanumeric + hyphens, no spaces
    subdomain_val = None
    if data.subdomain:
        import re as _re
        subdomain_val = _re.sub(r'[^a-z0-9\-]', '', data.subdomain.lower().strip())
        if subdomain_val:
            # Check uniqueness
            existing_sub = await db.scalar(select(Branch).where(Branch.subdomain == subdomain_val))
            if existing_sub:
                raise HTTPException(status_code=400, detail=f"Subdomain '{subdomain_val}' already taken")

    branch = Branch(
        org_id=uuid.UUID(data.org_id),
        name=data.name,
        code=data.code,
        subdomain=subdomain_val,
        board_type=BoardType(data.board_type) if data.board_type else BoardType.CBSE,
        principal_name=data.principal_name,
        email=data.email,
        phone=data.phone,
        address=data.address,
        city=data.city,
        state=data.state,
        pincode=data.pincode,
    )
    db.add(branch)
    await db.flush()

    # Create default settings for the branch
    settings = BranchSettings(branch_id=branch.id)
    db.add(settings)

    # Create empty payment config
    payment_config = PaymentGatewayConfig(branch_id=branch.id)
    db.add(payment_config)

    # Create empty communication config
    comm_config = CommunicationConfig(branch_id=branch.id)
    db.add(comm_config)

    return {"success": True, "message": "Branch created", "id": str(branch.id), "subdomain": subdomain_val}


@router.put("/branches/{branch_id}/subdomain")
async def update_branch_subdomain(
    branch_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """Set or update a branch's subdomain (e.g. goenkajammu → goenkajammu.vedaschoolpro.com)"""
    await verify_super_admin(request)
    body = await request.json()
    new_subdomain = body.get("subdomain", "").lower().strip()

    branch = await db.scalar(select(Branch).where(Branch.id == uuid.UUID(branch_id)))
    if not branch:
        raise HTTPException(status_code=404, detail="Branch not found")

    if new_subdomain:
        import re as _re
        new_subdomain = _re.sub(r'[^a-z0-9\-]', '', new_subdomain)
        if not new_subdomain:
            raise HTTPException(status_code=400, detail="Invalid subdomain. Use only letters, numbers, hyphens.")
        if len(new_subdomain) < 3:
            raise HTTPException(status_code=400, detail="Subdomain must be at least 3 characters")
        if len(new_subdomain) > 63:
            raise HTTPException(status_code=400, detail="Subdomain must be 63 characters or fewer")

        # Check reserved
        from utils.subdomain import RESERVED_SUBDOMAINS
        if new_subdomain in RESERVED_SUBDOMAINS:
            raise HTTPException(status_code=400, detail=f"'{new_subdomain}' is a reserved name")

        # Check uniqueness
        existing = await db.scalar(
            select(Branch).where(Branch.subdomain == new_subdomain, Branch.id != branch.id)
        )
        if existing:
            raise HTTPException(status_code=400, detail=f"Subdomain '{new_subdomain}' is already taken")

        branch.subdomain = new_subdomain
    else:
        branch.subdomain = None  # Remove subdomain

    await db.commit()
    return {
        "success": True,
        "message": f"Subdomain {'set to ' + new_subdomain if new_subdomain else 'removed'}",
        "subdomain": new_subdomain or None,
        "url": f"https://{new_subdomain}.vedaschoolpro.com" if new_subdomain else None,
    }


# --- School Admin APIs ---
@router.post("/admins")
async def create_admin(
    data: AdminCreate,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    await verify_super_admin(request)

    # Check if email already exists
    existing = await db.execute(select(User).where(User.email == data.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Email already registered")

    # Get branch to find org_id
    branch_result = await db.execute(select(Branch).where(Branch.id == uuid.UUID(data.branch_id)))
    branch = branch_result.scalar_one_or_none()
    if not branch:
        raise HTTPException(status_code=404, detail="Branch not found")

    admin = User(
        first_name=data.first_name,
        last_name=data.last_name,
        email=data.email,
        phone=data.phone,
        password_hash=hash_password(data.password),
        role=UserRole.SCHOOL_ADMIN,
        org_id=branch.org_id,
        branch_id=branch.id,
        is_active=True,
        is_verified=True,
    )
    db.add(admin)

    return {"success": True, "message": "School admin created"}


@router.post("/chairman")
async def create_chairman(
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """Create a Chairman/Trustee user for an organization."""
    await verify_super_admin(request)
    data = await request.json()
    org_id = data.get("org_id")
    email = data.get("email")
    if not org_id or not email:
        raise HTTPException(400, "org_id and email required")

    # Check if email already exists
    existing = await db.execute(select(User).where(User.email == email))
    if existing.scalar_one_or_none():
        raise HTTPException(400, "Email already registered")

    password = data.get("password", "Chairman@123")
    chairman = User(
        first_name=data.get("first_name", "Chairman"),
        last_name=data.get("last_name", ""),
        email=email,
        phone=data.get("phone", ""),
        password_hash=hash_password(password),
        role=UserRole.CHAIRMAN,
        org_id=uuid.UUID(org_id),
        is_active=True,
        is_verified=True,
    )
    db.add(chairman)
    return {"success": True, "message": f"Chairman created. Login: {email} / {password}"}


@router.put("/chairman/{chairman_id}/toggle")
async def toggle_chairman(request: Request, chairman_id: str, db: AsyncSession = Depends(get_db)):
    """Enable/disable a chairman."""
    await verify_super_admin(request)
    user = await db.scalar(select(User).where(User.id == uuid.UUID(chairman_id)))
    if not user:
        raise HTTPException(404, "Chairman not found")
    user.is_active = not user.is_active
    await db.commit()
    status = "enabled" if user.is_active else "disabled"
    return {"success": True, "message": f"Chairman {user.first_name} {status}"}


@router.put("/chairman/{chairman_id}")
async def update_chairman(request: Request, chairman_id: str, db: AsyncSession = Depends(get_db)):
    """Edit chairman details."""
    await verify_super_admin(request)
    data = await request.json()
    user = await db.scalar(select(User).where(User.id == uuid.UUID(chairman_id)))
    if not user:
        raise HTTPException(404, "Chairman not found")
    if data.get("first_name"): user.first_name = data["first_name"]
    if data.get("last_name") is not None: user.last_name = data["last_name"]
    if data.get("email"): user.email = data["email"]
    if data.get("phone") is not None: user.phone = data["phone"]
    if data.get("org_id"): user.org_id = uuid.UUID(data["org_id"])
    await db.commit()
    return {"success": True, "message": f"Chairman {user.first_name} updated"}


@router.delete("/admins/{admin_id}")
async def delete_admin(
    admin_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    await verify_super_admin(request)

    result = await db.execute(select(User).where(User.id == uuid.UUID(admin_id)))
    admin = result.scalar_one_or_none()
    if not admin:
        raise HTTPException(status_code=404, detail="Admin not found")

    admin.is_active = False
    return {"success": True, "message": "Admin deactivated"}


@router.get("/system-analytics")
@require_role(UserRole.SUPER_ADMIN)
async def system_analytics(request: Request, db: AsyncSession = Depends(get_db)):
    """System-level analytics — server health, school usage, etc."""
    import sys, platform
    from models.organization import Organization
    from models.branch import Branch
    from models.student import Student

    # Counts
    orgs = await db.scalar(select(func.count(Organization.id))) or 0
    branches_list = (await db.execute(select(Branch))).scalars().all()
    total_students = await db.scalar(select(func.count(Student.id))) or 0
    total_users = await db.scalar(select(func.count(User.id))) or 0

    # Server health
    server = {}
    try:
        import psutil
        server["cpu_percent"] = psutil.cpu_percent(interval=0.5)
        mem = psutil.virtual_memory()
        server["ram_total"] = round(mem.total / (1024**3), 1)
        server["ram_used"] = round(mem.used / (1024**3), 1)
        disk = psutil.disk_usage('/')
        server["disk_total"] = round(disk.total / (1024**3), 1)
        server["disk_used"] = round(disk.used / (1024**3), 1)
        import time, datetime as dt
        boot = psutil.boot_time()
        uptime_secs = time.time() - boot
        days = int(uptime_secs // 86400)
        hours = int((uptime_secs % 86400) // 3600)
        server["uptime"] = f"{days}d {hours}h"
    except ImportError:
        server = {"cpu_percent": 0, "ram_total": 0, "ram_used": 0, "disk_total": 0, "disk_used": 0, "uptime": "psutil not installed"}

    # DB size
    try:
        result = await db.execute(text("SELECT pg_database_size(current_database())"))
        db_bytes = result.scalar() or 0
        server["db_size"] = f"{db_bytes / (1024*1024):.1f} MB"
    except:
        server["db_size"] = "N/A"

    server["python_version"] = f"Python {sys.version.split()[0]} / FastAPI"

    # Per-school stats
    schools = []
    from models.teacher import Teacher
    for b in branches_list:
        stu_count = await db.scalar(select(func.count(Student.id)).where(Student.branch_id == b.id)) or 0
        teacher_count = await db.scalar(select(func.count(Teacher.id)).where(Teacher.branch_id == b.id)) or 0
        org_name = ""
        try:
            org = await db.scalar(select(Organization).where(Organization.id == b.org_id))
            org_name = org.name if org else ""
        except:
            pass
        schools.append({
            "name": b.name, "org": org_name, "students": stu_count, "teachers": teacher_count,
            "storage": "N/A", "db_rows": stu_count, "active": b.is_active if hasattr(b, 'is_active') else True,
            "branch_id": str(b.id),
            "subdomain": getattr(b, 'subdomain', None),
            "url": f"https://{b.subdomain}.vedaschoolpro.com" if getattr(b, 'subdomain', None) else None,
        })

    # GA ID
    ga_id = None
    try:
        from models.branch import BranchSettings
        # For super admin, store GA in a global setting or first branch
        # For now, check env
        import os
        ga_id = os.environ.get("GOOGLE_ANALYTICS_ID", "")
    except:
        pass

    return {
        "orgs": orgs, "branches": len(branches_list), "students": total_students, "users": total_users,
        "server": server, "schools": schools, "ga_id": ga_id, "recent_activity": []
    }


@router.post("/save-ga")
@require_role(UserRole.SUPER_ADMIN)
async def save_ga(request: Request, db: AsyncSession = Depends(get_db)):
    """Save Google Analytics ID."""
    data = await request.json()
    import os
    os.environ["GOOGLE_ANALYTICS_ID"] = data.get("ga_id", "")
    return {"status": "saved"}


# ═══════════════════════════════════════════════════════════
# SCHOOL & BRANCH MANAGEMENT — Activate / Deactivate
# ═══════════════════════════════════════════════════════════

@router.put("/organizations/{org_id}/toggle")
async def toggle_organization(request: Request, org_id: str, db: AsyncSession = Depends(get_db)):
    """Activate or deactivate an organization (school)."""
    user = await verify_super_admin(request)
    org = await db.scalar(select(Organization).where(Organization.id == uuid.UUID(org_id)))
    if not org:
        return {"error": "Organization not found"}
    org.is_active = not org.is_active
    # Also deactivate all branches and users
    if not org.is_active:
        branches = (await db.execute(select(Branch).where(Branch.org_id == org.id))).scalars().all()
        for b in branches:
            b.is_active = False
        users = (await db.execute(select(User).where(User.org_id == org.id, User.role != UserRole.SUPER_ADMIN))).scalars().all()
        for u in users:
            u.is_active = False
    await db.commit()
    status = "activated" if org.is_active else "deactivated"
    return {"success": True, "message": f"Organization '{org.name}' {status}", "is_active": org.is_active}


@router.put("/branches/{branch_id}/toggle")
async def toggle_branch(request: Request, branch_id: str, db: AsyncSession = Depends(get_db)):
    """Activate or deactivate a branch."""
    user = await verify_super_admin(request)
    branch = await db.scalar(select(Branch).where(Branch.id == uuid.UUID(branch_id)))
    if not branch:
        return {"error": "Branch not found"}
    branch.is_active = not branch.is_active
    # Also deactivate users of this branch
    if not branch.is_active:
        users = (await db.execute(select(User).where(User.branch_id == branch.id, User.role != UserRole.SUPER_ADMIN))).scalars().all()
        for u in users:
            u.is_active = False
    else:
        # Reactivate users when branch is reactivated
        users = (await db.execute(select(User).where(User.branch_id == branch.id))).scalars().all()
        for u in users:
            u.is_active = True
    await db.commit()
    status = "activated" if branch.is_active else "deactivated"
    return {"success": True, "message": f"Branch '{branch.name}' {status}", "is_active": branch.is_active}


# ═══════════════════════════════════════════════════════════
# PLAN MANAGEMENT
# ═══════════════════════════════════════════════════════════

@router.get("/plans")
async def list_plans(request: Request, db: AsyncSession = Depends(get_db)):
    """List all subscription plans."""
    user = await verify_super_admin(request)
    from models.subscription import Plan
    plans = (await db.execute(select(Plan).where(Plan.is_active == True).order_by(Plan.display_order))).scalars().all()
    return {"plans": [{
        "id": str(p.id), "name": p.name, "tier": p.tier.value, "tagline": p.tagline,
        "price_monthly": float(p.price_monthly or 0), "price_yearly": float(p.price_yearly or 0),
        "max_students": p.max_students, "max_teachers": p.max_teachers, "max_branches": p.max_branches,
        "max_storage_gb": p.max_storage_gb, "sms_credits_monthly": p.sms_credits_monthly,
        "whatsapp_enabled": p.whatsapp_enabled, "custom_branding": p.custom_branding,
        "priority_support": p.priority_support, "transport_module": p.transport_module,
        "hostel_module": p.hostel_module, "library_module": p.library_module,
        "hr_payroll": p.hr_payroll, "online_fee_payment": p.online_fee_payment,
        "id_card_generator": p.id_card_generator, "complaints_system": p.complaints_system,
        "advanced_analytics": p.advanced_analytics, "api_access": p.api_access,
        "enabled_modules": p.enabled_modules or [],
    } for p in plans]}


@router.post("/plans/seed")
@router.post("/plans")
async def create_plan(request: Request, db: AsyncSession = Depends(get_db)):
    """Create a new plan."""
    user = await verify_super_admin(request)
    data = await request.json()
    from models.subscription import Plan, PlanTier
    try:
        plan = Plan(
            name=data["name"],
            tier=PlanTier(data.get("tier", "starter")),
            tagline=data.get("tagline", ""),
            price_monthly=data.get("price_monthly", 0),
            price_yearly=data.get("price_yearly", 0),
            max_students=data.get("max_students", 300),
            max_teachers=data.get("max_teachers", 15),
            max_branches=data.get("max_branches", 1),
            max_storage_gb=data.get("max_storage_gb", 5),
            sms_credits_monthly=data.get("sms_credits_monthly", 0),
            backup_frequency=data.get("backup_frequency", "weekly"),
            display_order=data.get("display_order", 1),
        )
        # Boolean features
        for f in ["whatsapp_enabled","online_fee_payment","transport_module","hostel_module",
                   "library_module","hr_payroll","advanced_analytics","priority_support",
                   "api_access","custom_branding","id_card_generator","complaints_system",
                   "data_export","parent_app","teacher_app","messaging_system","email_notifications"]:
            if f in data:
                setattr(plan, f, bool(data[f]))
        db.add(plan)
        await db.commit()
        return {"success": True, "message": f"Plan '{plan.name}' created"}
    except Exception as e:
        await db.rollback()
        return {"error": str(e)}


@router.put("/plans/{plan_id}")
async def update_plan(request: Request, plan_id: str, db: AsyncSession = Depends(get_db)):
    """Update an existing plan."""
    user = await verify_super_admin(request)
    data = await request.json()
    from models.subscription import Plan, PlanTier
    plan = await db.scalar(select(Plan).where(Plan.id == uuid.UUID(plan_id)))
    if not plan:
        return {"error": "Plan not found"}
    try:
        for f in ["name","tagline","backup_frequency"]:
            if f in data: setattr(plan, f, data[f])
        for f in ["price_monthly","price_yearly"]:
            if f in data: setattr(plan, f, float(data[f]))
        for f in ["max_students","max_teachers","max_branches","max_storage_gb","sms_credits_monthly","display_order"]:
            if f in data: setattr(plan, f, int(data[f]))
        if "tier" in data:
            plan.tier = PlanTier(data["tier"])
        for f in ["whatsapp_enabled","online_fee_payment","transport_module","hostel_module",
                   "library_module","hr_payroll","advanced_analytics","priority_support",
                   "api_access","custom_branding","id_card_generator","complaints_system",
                   "data_export","parent_app","teacher_app","messaging_system","email_notifications"]:
            if f in data: setattr(plan, f, bool(data[f]))
        await db.commit()
        return {"success": True, "message": f"Plan '{plan.name}' updated"}
    except Exception as e:
        await db.rollback()
        return {"error": str(e)}


@router.post("/plans/seed")
async def seed_plans(request: Request, db: AsyncSession = Depends(get_db)):
    """Create default plans if they don't exist."""
    user = await verify_super_admin(request)
    from models.subscription import Plan, PlanTier, DEFAULT_PLANS

    existing = (await db.execute(select(Plan))).scalars().all()
    if existing:
        return {"message": f"Plans already exist ({len(existing)} plans). Delete them first to re-seed."}

    for pdata in DEFAULT_PLANS:
        plan = Plan(
            name=pdata["name"],
            tier=PlanTier(pdata["tier"]),
            tagline=pdata.get("tagline"),
            price_monthly=pdata["price_monthly"],
            price_yearly=pdata["price_yearly"],
            max_students=pdata["max_students"],
            max_teachers=pdata["max_teachers"],
            max_branches=pdata.get("max_branches", 1),
            max_storage_gb=pdata.get("max_storage_gb", 5),
            sms_credits_monthly=pdata.get("sms_credits_monthly", 0),
            whatsapp_enabled=pdata.get("whatsapp_enabled", False),
            custom_branding=pdata.get("custom_branding", False),
            priority_support=pdata.get("priority_support", False),
            api_access=pdata.get("api_access", False),
            advanced_analytics=pdata.get("advanced_analytics", False),
            online_fee_payment=pdata.get("online_fee_payment", False),
            id_card_generator=pdata.get("id_card_generator", False),
            transport_module=pdata.get("transport_module", False),
            hostel_module=pdata.get("hostel_module", False),
            library_module=pdata.get("library_module", False),
            hr_payroll=pdata.get("hr_payroll", False),
            complaints_system=pdata.get("complaints_system", False),
            backup_frequency=pdata.get("backup_frequency", "weekly"),
            display_order=pdata.get("display_order", 0),
            enabled_modules=pdata.get("enabled_modules", []),
        )
        db.add(plan)
    await db.commit()
    return {"success": True, "message": f"Created {len(DEFAULT_PLANS)} plans: Starter, Growth, Pro, Enterprise"}


# ═══════════════════════════════════════════════════════════
# SUBSCRIPTION MANAGEMENT
# ═══════════════════════════════════════════════════════════

@router.get("/subscriptions")
async def list_subscriptions(request: Request, db: AsyncSession = Depends(get_db)):
    """List all school subscriptions with plan details."""
    user = await verify_super_admin(request)
    from models.subscription import SchoolSubscription
    from sqlalchemy.orm import selectinload

    subs = (await db.execute(
        select(SchoolSubscription).options(selectinload(SchoolSubscription.plan)).order_by(SchoolSubscription.created_at.desc())
    )).scalars().all()

    result = []
    for s in subs:
        branch = await db.scalar(select(Branch).where(Branch.id == s.branch_id))
        org = await db.scalar(select(Organization).where(Organization.id == s.org_id)) if s.org_id else None
        result.append({
            "id": str(s.id),
            "branch_id": str(s.branch_id),
            "branch_name": branch.name if branch else "Unknown",
            "org_name": org.name if org else "Unknown",
            "plan_name": s.plan.name if s.plan else "No Plan",
            "plan_tier": s.plan.tier.value if s.plan else "",
            "status": s.status.value if s.status else "unknown",
            "billing_cycle": s.billing_cycle.value if s.billing_cycle else "monthly",
            "current_period_end": s.current_period_end.strftime("%d %b %Y") if s.current_period_end else "—",
            "student_count": s.current_student_count or 0,
            "teacher_count": s.current_teacher_count or 0,
            "auto_deactivated": s.auto_deactivated,
        })
    return {"subscriptions": result}


@router.post("/subscriptions/assign")
async def assign_subscription(request: Request, db: AsyncSession = Depends(get_db)):
    """Assign a plan to a school branch."""
    user = await verify_super_admin(request)
    from models.subscription import SchoolSubscription, Plan, SubscriptionStatus, BillingCycle
    from datetime import timedelta

    data = await request.json()
    branch_id = data.get("branch_id")
    plan_id = data.get("plan_id")
    billing_cycle = data.get("billing_cycle", "monthly")
    payment_ref = data.get("payment_ref", "")

    if not branch_id or not plan_id:
        return {"error": "branch_id and plan_id required"}

    branch = await db.scalar(select(Branch).where(Branch.id == uuid.UUID(branch_id)))
    if not branch:
        return {"error": "Branch not found"}
    plan = await db.scalar(select(Plan).where(Plan.id == uuid.UUID(plan_id)))
    if not plan:
        return {"error": "Plan not found"}

    # Check existing subscription
    existing = await db.scalar(select(SchoolSubscription).where(SchoolSubscription.branch_id == branch.id))

    now = datetime.utcnow()
    cycle = BillingCycle(billing_cycle) if billing_cycle in ("monthly", "yearly") else BillingCycle.MONTHLY
    period_days = 30 if cycle == BillingCycle.MONTHLY else 365
    period_end = now + timedelta(days=period_days)
    grace_end = period_end + timedelta(days=7)
    amount = float(plan.price_monthly) if cycle == BillingCycle.MONTHLY else float(plan.price_yearly)

    if existing:
        existing.plan_id = plan.id
        existing.status = SubscriptionStatus.ACTIVE
        existing.billing_cycle = cycle
        existing.current_period_start = now
        existing.current_period_end = period_end
        existing.grace_period_end = grace_end
        existing.next_payment_due = period_end
        existing.last_payment_amount = amount
        existing.last_payment_date = now
        existing.last_payment_ref = payment_ref
        existing.auto_deactivated = False
        existing.deactivated_at = None
        sub = existing
    else:
        sub = SchoolSubscription(
            org_id=branch.org_id,
            branch_id=branch.id,
            plan_id=plan.id,
            status=SubscriptionStatus.ACTIVE,
            billing_cycle=cycle,
            current_period_start=now,
            current_period_end=period_end,
            grace_period_end=grace_end,
            next_payment_due=period_end,
            last_payment_amount=amount,
            last_payment_date=now,
            last_payment_ref=payment_ref,
        )
        db.add(sub)

    # Ensure branch is active
    branch.is_active = True
    # Reactivate users
    users = (await db.execute(select(User).where(User.branch_id == branch.id))).scalars().all()
    for u in users:
        u.is_active = True

    await db.flush()

    # Log payment
    from models.subscription import PaymentHistory
    payment = PaymentHistory(
        subscription_id=sub.id,
        branch_id=branch.id,
        amount=amount,
        plan_name=plan.name,
        billing_cycle=cycle.value,
        period_start=now,
        period_end=period_end,
        payment_ref=payment_ref,
        payment_method="manual",
    )
    db.add(payment)
    await db.commit()

    return {
        "success": True,
        "message": f"Assigned {plan.name} ({cycle.value}) to {branch.name} until {period_end.strftime('%d %b %Y')}",
    }


# ═══════════════════════════════════════════════════════════
# IMPERSONATION — Login as School Admin
# ═══════════════════════════════════════════════════════════

@router.post("/impersonate/{branch_id}")
async def impersonate_branch(request: Request, branch_id: str, db: AsyncSession = Depends(get_db)):
    """Super admin impersonates a school admin for a given branch."""
    user = await verify_super_admin(request)
    from utils.auth import create_access_token
    from fastapi.responses import JSONResponse

    branch = await db.scalar(select(Branch).where(Branch.id == uuid.UUID(branch_id)))
    if not branch:
        return {"error": "Branch not found"}

    admin = await db.scalar(
        select(User).where(User.branch_id == branch.id, User.is_first_admin == True, User.role == UserRole.SCHOOL_ADMIN)
    )
    if not admin:
        admin = await db.scalar(select(User).where(User.branch_id == branch.id, User.role == UserRole.SCHOOL_ADMIN))
    if not admin:
        return {"error": "No admin found for this branch. Create one first."}

    token = create_access_token({
        "user_id": str(admin.id), "email": admin.email, "role": admin.role.value,
        "branch_id": str(admin.branch_id), "org_id": str(admin.org_id) if admin.org_id else None,
        "first_name": admin.first_name, "last_name": admin.last_name or "",
        "is_first_admin": getattr(admin, 'is_first_admin', False) or False,
        "privileges": admin.privileges if admin.privileges else {},
        "impersonated_by": str(user.get("user_id")),
    })

    # Save super admin's original token so they can return
    original_token = request.cookies.get("access_token")

    response = JSONResponse({
        "success": True,
        "admin_name": f"{admin.first_name} {admin.last_name or ''}".strip(),
        "branch_name": branch.name,
        "redirect": "/school/dashboard",
    })
    response.set_cookie(key="access_token", value=token, httponly=True, max_age=3600, samesite="lax")
    # Store original super admin token in separate cookie
    if original_token:
        response.set_cookie(key="sa_token", value=original_token, httponly=True, max_age=3600, samesite="lax")
    return response


@router.post("/return-from-impersonate")
async def return_from_impersonate(request: Request):
    """Return to super admin after impersonation."""
    from fastapi.responses import JSONResponse
    sa_token = request.cookies.get("sa_token")
    if not sa_token:
        return {"error": "No super admin session found. Please login again."}

    # Verify the saved token is valid super admin
    payload = decode_access_token(sa_token)
    if not payload or payload.get("role") != "super_admin":
        return {"error": "Invalid super admin session. Please login again."}

    response = JSONResponse({"success": True, "redirect": "/super-admin/dashboard"})
    response.set_cookie(key="access_token", value=sa_token, httponly=True, max_age=3600, samesite="lax")
    response.delete_cookie(key="sa_token")
    return response


# ═══════════════════════════════════════════════════════════
# BRANCH EDIT
# ═══════════════════════════════════════════════════════════

@router.put("/branches/{branch_id}")
async def update_branch(request: Request, branch_id: str, db: AsyncSession = Depends(get_db)):
    """Update branch details."""
    user = await verify_super_admin(request)
    data = await request.json()

    branch = await db.scalar(select(Branch).where(Branch.id == uuid.UUID(branch_id)))
    if not branch:
        return {"error": "Branch not found"}

    # Update fields
    for field in ["name", "code", "email", "phone", "address", "city", "state", "pincode", "website_url", "affiliation_number", "motto", "timezone", "currency", "language"]:
        if field in data and data[field] is not None:
            setattr(branch, field, data[field])

    # Board type
    if "board_type" in data and data["board_type"]:
        from models.branch import BoardType
        try:
            branch.board_type = BoardType(data["board_type"])
        except ValueError:
            pass

    await db.commit()
    return {"success": True, "message": f"Branch '{branch.name}' updated"}


# ═══════════════════════════════════════════════════════════
# ADMIN PASSWORD RESET
# ═══════════════════════════════════════════════════════════

@router.post("/admins/{admin_id}/reset-password")
async def reset_admin_password(request: Request, admin_id: str, db: AsyncSession = Depends(get_db)):
    """Reset a school admin's password. Optionally email the new password."""
    user = await verify_super_admin(request)
    data = await request.json()
    new_password = data.get("password", "")
    send_email_flag = data.get("send_email", False)

    if len(new_password) < 6:
        return {"error": "Password must be at least 6 characters"}

    admin = await db.scalar(select(User).where(User.id == uuid.UUID(admin_id)))
    if not admin:
        return {"error": "Admin not found"}

    admin.password_hash = hash_password(new_password)
    await db.commit()

    email_sent = False
    if send_email_flag and admin.email:
        try:
            from utils.notifier import send_platform_email
            body = f"""
            <div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;">
                <div style="background:linear-gradient(135deg,#6366f1,#8b5cf6);padding:24px;border-radius:12px 12px 0 0;">
                    <h2 style="color:#fff;margin:0;">Password Reset</h2>
                </div>
                <div style="background:#fff;padding:24px;border:1px solid #e2e8f0;border-radius:0 0 12px 12px;">
                    <p style="color:#334155;">Hi <strong>{admin.first_name}</strong>,</p>
                    <p style="color:#334155;">Your password has been reset by the platform administrator.</p>
                    <div style="background:#f1f5f9;padding:16px;border-radius:8px;text-align:center;margin:16px 0;">
                        <div style="font-size:0.75rem;color:#64748b;margin-bottom:4px;">Your New Password</div>
                        <code style="font-size:1.2rem;font-weight:800;color:#6366f1;letter-spacing:1px;">{new_password}</code>
                    </div>
                    <p style="color:#64748b;font-size:0.85rem;">Please login and change your password immediately for security.</p>
                </div>
                <p style="color:#94a3b8;font-size:0.75rem;text-align:center;margin-top:12px;">VedaSchoolPro</p>
            </div>"""
            result = await send_platform_email(db, admin.email, "Your Password Has Been Reset", body)
            email_sent = result.get("status") == "sent"
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"Password email failed: {e}")

    return {
        "success": True,
        "message": f"Password reset for {admin.first_name}",
        "email_sent": email_sent,
    }


# ═══════════════════════════════════════════════════════════
# PASSWORD RESET LINK — Token-based, 24hr expiry
# ═══════════════════════════════════════════════════════════

import secrets
from time import time as _time

# In-memory reset tokens store: { token: { user_id, email, expires } }
_password_reset_tokens: dict = {}
_RESET_LINK_EXPIRY = 60 * 60 * 24  # 24 hours


@router.post("/admins/{admin_id}/send-reset-link")
async def send_reset_link(request: Request, admin_id: str, db: AsyncSession = Depends(get_db)):
    """Send a password reset link to admin's email. Link expires in 24 hours."""
    user = await verify_super_admin(request)

    admin = await db.scalar(select(User).where(User.id == uuid.UUID(admin_id)))
    if not admin:
        return {"error": "Admin not found"}
    if not admin.email:
        return {"error": f"{admin.first_name} has no email on file"}

    # Generate secure token
    token = secrets.token_urlsafe(48)
    _password_reset_tokens[token] = {
        "user_id": str(admin.id),
        "email": admin.email,
        "expires": _time() + _RESET_LINK_EXPIRY,
        "created_at": _time(),
    }

    # Clean expired tokens
    now = _time()
    expired = [t for t, v in _password_reset_tokens.items() if v["expires"] < now]
    for t in expired:
        del _password_reset_tokens[t]

    # Build reset URL
    host = request.headers.get("host", "localhost:8000")
    scheme = "https" if "localhost" not in host else "http"
    reset_url = f"{scheme}://{host}/reset-password?token={token}"

    try:
        from utils.notifier import send_platform_email
        body = f"""
        <div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;">
            <div style="background:linear-gradient(135deg,#6366f1,#8b5cf6);padding:24px;border-radius:12px 12px 0 0;">
                <h2 style="color:#fff;margin:0;">Password Reset Request</h2>
            </div>
            <div style="background:#fff;padding:24px;border:1px solid #e2e8f0;border-radius:0 0 12px 12px;">
                <p style="color:#334155;">Hi <strong>{admin.first_name}</strong>,</p>
                <p style="color:#334155;">A password reset was requested for your account. Click the button below to set a new password:</p>
                <div style="text-align:center;margin:24px 0;">
                    <a href="{reset_url}" style="display:inline-block;background:linear-gradient(135deg,#6366f1,#8b5cf6);color:#fff;padding:14px 32px;border-radius:8px;text-decoration:none;font-weight:700;font-size:0.95rem;">Reset My Password</a>
                </div>
                <p style="color:#64748b;font-size:0.85rem;">Or copy and paste this link in your browser:</p>
                <p style="word-break:break-all;background:#f1f5f9;padding:10px;border-radius:6px;font-size:0.78rem;color:#6366f1;">{reset_url}</p>
                <p style="color:#ef4444;font-size:0.82rem;font-weight:600;"><i>This link expires in 24 hours.</i></p>
                <p style="color:#94a3b8;font-size:0.78rem;">If you did not request this, please ignore this email.</p>
            </div>
            <p style="color:#94a3b8;font-size:0.75rem;text-align:center;margin-top:12px;">VedaSchoolPro</p>
        </div>"""
        result = await send_platform_email(db, admin.email, "Password Reset Link — VedaSchoolPro", body)
        if result.get("status") == "sent":
            return {"success": True, "message": f"Reset link sent to {admin.email}"}
        else:
            return {"error": result.get("reason", "Failed to send email. Check SMTP settings.")}
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"Reset link email failed: {e}")
        return {"error": f"Email sending failed: {str(e)}"}


# ═══════════════════════════════════════════════════════════
# LOGIN SECURITY — View attempts, ban IPs
# ═══════════════════════════════════════════════════════════

@router.get("/login-attempts")
async def get_login_attempts(request: Request, db: AsyncSession = Depends(get_db)):
    """Get recent login attempts with pagination."""
    user = await verify_super_admin(request)
    try:
        from models.login_security import LoginAttempt
        limit = int(request.query_params.get("limit", 50))
        offset = int(request.query_params.get("offset", 0))
        attempts = (await db.execute(
            select(LoginAttempt).order_by(LoginAttempt.created_at.desc()).limit(limit).offset(offset)
        )).scalars().all()
        total = await db.scalar(select(func.count(LoginAttempt.id))) or 0
        return {"attempts": [{
            "id": str(a.id), "email": a.email, "ip": a.ip_address, "os": a.os,
            "browser": a.browser, "device": a.device, "success": a.success,
            "reason": a.failure_reason, "time": a.created_at.strftime("%d %b %Y %H:%M") if a.created_at else "",
        } for a in attempts], "total": total}
    except Exception as e:
        return {"attempts": [], "total": 0, "error": str(e)}


@router.post("/ban-ip")
async def ban_ip(request: Request, db: AsyncSession = Depends(get_db)):
    """Ban an IP address."""
    user = await verify_super_admin(request)
    data = await request.json()
    ip = data.get("ip", "").strip()
    reason = data.get("reason", "Suspicious activity")
    if not ip:
        return {"error": "IP address required"}
    try:
        from models.login_security import BannedIP
        existing = await db.scalar(select(BannedIP).where(BannedIP.ip_address == ip))
        if existing:
            existing.is_active = True
            existing.reason = reason
        else:
            ban = BannedIP(ip_address=ip, reason=reason, banned_by=uuid.UUID(user.get("user_id")))
            db.add(ban)
        await db.commit()
        return {"success": True, "message": f"IP {ip} banned"}
    except Exception as e:
        return {"error": str(e)}


@router.post("/unban-ip")
async def unban_ip(request: Request, db: AsyncSession = Depends(get_db)):
    """Unban an IP address."""
    user = await verify_super_admin(request)
    data = await request.json()
    ip = data.get("ip", "").strip()
    try:
        from models.login_security import BannedIP
        ban = await db.scalar(select(BannedIP).where(BannedIP.ip_address == ip))
        if ban:
            ban.is_active = False
            await db.commit()
            return {"success": True, "message": f"IP {ip} unbanned"}
        return {"error": "IP not found in ban list"}
    except Exception as e:
        return {"error": str(e)}


@router.get("/banned-ips")
async def get_banned_ips(request: Request, db: AsyncSession = Depends(get_db)):
    """Get all banned IPs."""
    user = await verify_super_admin(request)
    try:
        from models.login_security import BannedIP
        bans = (await db.execute(
            select(BannedIP).where(BannedIP.is_active == True).order_by(BannedIP.banned_at.desc())
        )).scalars().all()
        return {"banned": [{"ip": b.ip_address, "reason": b.reason, "since": b.banned_at.strftime("%d %b %Y %H:%M") if b.banned_at else ""} for b in bans]}
    except Exception as e:
        return {"banned": [], "error": str(e)}


@router.put("/admins/{admin_id}/suspend")
async def suspend_admin(request: Request, admin_id: str, db: AsyncSession = Depends(get_db)):
    """Suspend a school admin."""
    user = await verify_super_admin(request)
    admin = await db.scalar(select(User).where(User.id == uuid.UUID(admin_id)))
    if not admin:
        return {"error": "Admin not found"}
    admin.is_active = False
    await db.commit()
    return {"success": True, "message": f"{admin.first_name} has been suspended"}


@router.put("/admins/{admin_id}/activate")
async def activate_admin(request: Request, admin_id: str, db: AsyncSession = Depends(get_db)):
    """Reactivate a suspended school admin."""
    user = await verify_super_admin(request)
    admin = await db.scalar(select(User).where(User.id == uuid.UUID(admin_id)))
    if not admin:
        return {"error": "Admin not found"}
    admin.is_active = True
    await db.commit()
    return {"success": True, "message": f"{admin.first_name} has been reactivated"}


@router.post("/send-email")
async def send_email_to_admin(request: Request, db: AsyncSession = Depends(get_db)):
    """Send custom email to admin (placeholder — needs SMTP config)."""
    user = await verify_super_admin(request)
    data = await request.json()
    to = data.get("to", "")
    subject = data.get("subject", "")
    body = data.get("body", "")
    if not to or not subject or not body:
        return {"error": "To, subject, and body required"}
    # TODO: Implement actual email sending via SMTP/Brevo
    # For now, return success placeholder
    return {"error": "Email service not configured yet. Configure SMTP in Settings → Email."}


# ═══════════════════════════════════════════════════════════
# PLATFORM SETTINGS — Save / Load (single-row JSON config)
# ═══════════════════════════════════════════════════════════

@router.post("/platform-settings")
async def save_platform_settings(request: Request, db: AsyncSession = Depends(get_db)):
    """Save platform-wide settings (SMTP, SMS, general, storage, defaults, security)."""
    user = await verify_super_admin(request)
    data = await request.json()
    section = data.get("_section", "general")  # which tab is saving

    from models.branch import PlatformConfig
    result = await db.execute(select(PlatformConfig))
    config = result.scalar_one_or_none()
    if not config:
        config = PlatformConfig(config={})
        db.add(config)

    existing = dict(config.config or {})

    # Merge new data — skip masked passwords
    for key, value in data.items():
        if key == "_section":
            continue
        if isinstance(value, str) and "••••" in value:
            continue  # keep existing password
        existing[key] = value

    config.config = existing
    await db.commit()
    return {"success": True, "message": f"{section.capitalize()} settings saved!"}


@router.get("/platform-settings")
async def load_platform_settings(request: Request, db: AsyncSession = Depends(get_db)):
    """Load platform-wide settings."""
    user = await verify_super_admin(request)
    from models.branch import PlatformConfig
    result = await db.execute(select(PlatformConfig))
    config = result.scalar_one_or_none()
    if not config:
        return {"config": {}}

    # Mask sensitive fields
    safe = dict(config.config or {})
    for key in list(safe.keys()):
        if "password" in key or "secret" in key or "api_key" in key:
            if safe[key]:
                safe[key] = "••••••••"
    return {"config": safe}


# ═══════════════════════════════════════════════════════════
# SCHOOL ADMIN — Edit / Update / Photo / Logs
# ═══════════════════════════════════════════════════════════

@router.put("/admins/{admin_id}")
async def update_admin(request: Request, admin_id: str, db: AsyncSession = Depends(get_db)):
    """Update school admin details (name, email, phone, designation)."""
    user = await verify_super_admin(request)
    data = await request.json()

    admin = await db.scalar(select(User).where(User.id == uuid.UUID(admin_id)))
    if not admin:
        return {"error": "Admin not found"}

    # Update basic fields
    if data.get("first_name"):
        admin.first_name = data["first_name"]
    if "last_name" in data:
        admin.last_name = data["last_name"] or ""
    if data.get("email"):
        # Check uniqueness
        existing = await db.scalar(
            select(User).where(User.email == data["email"], User.id != admin.id)
        )
        if existing:
            return {"error": f"Email '{data['email']}' is already registered to another user"}
        admin.email = data["email"]
    if "phone" in data:
        if data["phone"]:
            existing = await db.scalar(
                select(User).where(User.phone == data["phone"], User.id != admin.id)
            )
            if existing:
                return {"error": f"Phone '{data['phone']}' is already registered to another user"}
        admin.phone = data["phone"]
    if "designation" in data:
        admin.designation = data["designation"]

    await db.commit()
    return {"success": True, "message": f"Admin {admin.first_name} updated"}


@router.post("/admins/{admin_id}/photo")
async def upload_admin_photo(request: Request, admin_id: str, db: AsyncSession = Depends(get_db)):
    """Upload/update a school admin's photo."""
    user = await verify_super_admin(request)
    from fastapi import UploadFile
    import os

    admin = await db.scalar(select(User).where(User.id == uuid.UUID(admin_id)))
    if not admin:
        return {"error": "Admin not found"}

    form = await request.form()
    photo = form.get("photo")
    if not photo:
        return {"error": "No photo file provided"}

    # Validate file type
    filename = getattr(photo, 'filename', '') or ''
    ext = os.path.splitext(filename)[1].lower()
    if ext not in ('.jpg', '.jpeg', '.png', '.webp'):
        return {"error": "Only JPG, PNG, WEBP images allowed"}

    # Read file content
    content = await photo.read()
    if len(content) > 5 * 1024 * 1024:  # 5MB limit
        return {"error": "Photo must be under 5MB"}

    # Save to static/uploads/avatars/
    upload_dir = os.path.join("static", "uploads", "avatars")
    os.makedirs(upload_dir, exist_ok=True)
    safe_name = f"admin_{admin_id}{ext}"
    file_path = os.path.join(upload_dir, safe_name)
    with open(file_path, "wb") as f:
        f.write(content)

    admin.avatar_url = f"/static/uploads/avatars/{safe_name}"
    await db.commit()
    return {"success": True, "message": "Photo updated", "url": admin.avatar_url}


@router.get("/admins/{admin_id}")
async def get_admin_detail(request: Request, admin_id: str, db: AsyncSession = Depends(get_db)):
    """Get detailed admin info including login logs."""
    user = await verify_super_admin(request)
    from sqlalchemy.orm import selectinload

    admin = await db.scalar(
        select(User).where(User.id == uuid.UUID(admin_id)).options(selectinload(User.branch))
    )
    if not admin:
        return {"error": "Admin not found"}

    # Get recent login attempts for this admin
    login_logs = []
    try:
        from models.login_security import LoginAttempt
        attempts = (await db.execute(
            select(LoginAttempt)
            .where(LoginAttempt.email == admin.email)
            .order_by(LoginAttempt.created_at.desc())
            .limit(20)
        )).scalars().all()
        login_logs = [{
            "time": a.created_at.strftime("%d %b %Y %H:%M") if a.created_at else "",
            "ip": a.ip_address or "",
            "browser": a.browser or "",
            "os": a.os or "",
            "device": a.device or "",
            "success": a.success,
            "reason": a.failure_reason or "",
        } for a in attempts]
    except Exception:
        pass

    return {
        "admin": {
            "id": str(admin.id),
            "first_name": admin.first_name,
            "last_name": admin.last_name or "",
            "email": admin.email or "",
            "phone": admin.phone or "",
            "designation": admin.designation or "",
            "avatar_url": admin.avatar_url or "",
            "is_active": admin.is_active,
            "is_first_admin": admin.is_first_admin,
            "branch_name": admin.branch.name if admin.branch else "",
            "branch_id": str(admin.branch_id) if admin.branch_id else "",
            "last_login": admin.last_login.strftime("%d %b %Y %H:%M") if admin.last_login else "Never",
            "created_at": admin.created_at.strftime("%d %b %Y") if admin.created_at else "",
        },
        "login_logs": login_logs,
    }