from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from database import get_db
from models.user import User, UserRole
from models.organization import Organization
from models.branch import Branch
from models.student import Student
from models.teacher import Teacher
from utils.permissions import require_role

router = APIRouter(prefix="/super-admin")
templates = Jinja2Templates(directory="templates")


@router.get("/dashboard", response_class=HTMLResponse)
@require_role(UserRole.SUPER_ADMIN)
async def dashboard(request: Request, db: AsyncSession = Depends(get_db)):
    user = request.state.user

    # Get stats
    org_count = await db.scalar(select(func.count(Organization.id)))
    branch_count = await db.scalar(select(func.count(Branch.id)))
    student_count = await db.scalar(select(func.count(Student.id)))
    teacher_count = await db.scalar(select(func.count(Teacher.id)))

    # Get recent organizations
    result = await db.execute(
        select(Organization)
        .options(selectinload(Organization.branches))
        .order_by(Organization.created_at.desc())
        .limit(5)
    )
    organizations = result.scalars().all()

    return templates.TemplateResponse("super_admin/dashboard.html", {
        "request": request,
        "user": user,
        "active_page": "dashboard",
        "stats": {
            "total_orgs": org_count or 0,
            "total_branches": branch_count or 0,
            "total_students": student_count or 0,
            "total_teachers": teacher_count or 0,
        },
        "organizations": organizations,
    })


@router.get("/organizations", response_class=HTMLResponse)
@require_role(UserRole.SUPER_ADMIN)
async def organizations_page(request: Request, db: AsyncSession = Depends(get_db)):
    user = request.state.user
    action = request.query_params.get("action")

    result = await db.execute(
        select(Organization)
        .options(selectinload(Organization.branches))
        .order_by(Organization.created_at.desc())
    )
    organizations = result.scalars().all()

    return templates.TemplateResponse("super_admin/organizations.html", {
        "request": request,
        "user": user,
        "active_page": "organizations",
        "organizations": organizations,
        "action": action,
    })


@router.get("/branches", response_class=HTMLResponse)
@require_role(UserRole.SUPER_ADMIN)
async def branches_page(request: Request, db: AsyncSession = Depends(get_db)):
    user = request.state.user
    action = request.query_params.get("action")

    result = await db.execute(
        select(Branch)
        .options(selectinload(Branch.organization))
        .order_by(Branch.created_at.desc())
    )
    branches = result.scalars().all()

    orgs_result = await db.execute(select(Organization).where(Organization.is_active == True))
    organizations = orgs_result.scalars().all()

    return templates.TemplateResponse("super_admin/branches.html", {
        "request": request,
        "user": user,
        "active_page": "branches",
        "branches": branches,
        "organizations": organizations,
        "action": action,
    })


@router.get("/admins", response_class=HTMLResponse)
@require_role(UserRole.SUPER_ADMIN)
async def admins_page(request: Request, db: AsyncSession = Depends(get_db)):
    user = request.state.user
    action = request.query_params.get("action")

    result = await db.execute(
        select(User)
        .where(User.role == UserRole.SCHOOL_ADMIN, User.is_first_admin == True)
        .options(selectinload(User.branch))
        .order_by(User.created_at.desc())
    )
    admins = result.scalars().all()

    branches_result = await db.execute(
        select(Branch)
        .options(selectinload(Branch.organization))
        .where(Branch.is_active == True)
    )
    branches = branches_result.scalars().all()

    return templates.TemplateResponse("super_admin/admins.html", {
        "request": request,
        "user": user,
        "active_page": "admins",
        "admins": admins,
        "branches": branches,
        "action": action,
    })


@router.get("/audit-logs", response_class=HTMLResponse)
@require_role(UserRole.SUPER_ADMIN)
async def audit_logs_page(request: Request, db: AsyncSession = Depends(get_db)):
    user = request.state.user
    from models.prelaunch import AuditLog
    logs = (await db.execute(
        select(AuditLog).order_by(AuditLog.created_at.desc()).limit(200)
    )).scalars().all()
    return templates.TemplateResponse("super_admin/audit_logs.html", {
        "request": request, "user": user, "active_page": "audit_logs", "logs": logs,
    })


@router.get("/plans", response_class=HTMLResponse)
@require_role(UserRole.SUPER_ADMIN)
async def plans_page(request: Request, db: AsyncSession = Depends(get_db)):
    user = request.state.user
    from models.subscription import Plan, SchoolSubscription
    from sqlalchemy.orm import selectinload

    plans = (await db.execute(select(Plan).where(Plan.is_active == True).order_by(Plan.display_order))).scalars().all()
    subs = (await db.execute(select(SchoolSubscription).options(selectinload(SchoolSubscription.plan)))).scalars().all()

    sub_data = []
    for s in subs:
        branch = await db.scalar(select(Branch).where(Branch.id == s.branch_id))
        sub_data.append({
            "branch_name": branch.name if branch else "?",
            "plan_name": s.plan.name if s.plan else "?",
            "status": s.status.value if hasattr(s.status, 'value') else str(s.status),
            "billing_cycle": s.billing_cycle.value if hasattr(s.billing_cycle, 'value') else "monthly",
            "expires": s.current_period_end.strftime('%d %b %Y') if s.current_period_end else "—",
        })

    return templates.TemplateResponse("super_admin/plans.html", {
        "request": request, "user": user, "active_page": "plans",
        "plans": plans, "subscriptions": sub_data,
    })


@router.get("/organizations/{org_id}", response_class=HTMLResponse)
@require_role(UserRole.SUPER_ADMIN)
async def organization_detail(request: Request, org_id: str, db: AsyncSession = Depends(get_db)):
    """Organization detail page — view org info, branches, admins, subscription"""
    user = request.state.user
    import uuid as _uuid

    org = (await db.execute(
        select(Organization)
        .options(selectinload(Organization.branches))
        .where(Organization.id == _uuid.UUID(org_id))
    )).scalar_one_or_none()

    if not org:
        from fastapi.responses import RedirectResponse
        return RedirectResponse("/super-admin/organizations", status_code=302)

    # Get ONLY first_admin users (actual branch admins, not principals/clerks)
    branch_ids = [b.id for b in org.branches]
    admins = []
    if branch_ids:
        admins = (await db.execute(
            select(User)
            .options(selectinload(User.branch))
            .where(
                User.role == UserRole.SCHOOL_ADMIN,
                User.branch_id.in_(branch_ids),
                User.is_first_admin == True,
            )
        )).scalars().all()

    # Get subscriptions PER BRANCH (plans are branch-level, not org-level)
    from models.subscription import SchoolSubscription, Plan
    branch_subs = {}  # branch_id -> {plan_name, status, period_end, ...}
    if branch_ids:
        subs = (await db.execute(
            select(SchoolSubscription).where(SchoolSubscription.branch_id.in_(branch_ids))
        )).scalars().all()
        for sub in subs:
            plan = await db.scalar(select(Plan).where(Plan.id == sub.plan_id))
            branch_subs[str(sub.branch_id)] = {
                "plan_name": plan.name if plan else "Unknown",
                "plan_tier": plan.tier.value if plan else "",
                "billing_cycle": sub.billing_cycle.value if sub.billing_cycle else "monthly",
                "status": sub.status.value if hasattr(sub.status, 'value') else str(sub.status),
                "period_end": sub.current_period_end.strftime('%d %b %Y') if sub.current_period_end else None,
                "last_amount": float(sub.last_payment_amount) if sub.last_payment_amount else 0,
            }

    # Get all plans for assignment modal
    plans = (await db.execute(select(Plan).where(Plan.is_active == True).order_by(Plan.display_order))).scalars().all()

    return templates.TemplateResponse("super_admin/org_detail.html", {
        "request": request, "user": user, "active_page": "organizations",
        "org": org, "admins": admins, "branch_subs": branch_subs, "plans": plans,
    })


@router.get("/settings", response_class=HTMLResponse)
@require_role(UserRole.SUPER_ADMIN)
async def settings_page(request: Request, db: AsyncSession = Depends(get_db)):
    """Super Admin platform settings"""
    user = request.state.user
    from config import settings as app_settings

    org_count = await db.scalar(select(func.count(Organization.id))) or 0
    branch_count = await db.scalar(select(func.count(Branch.id))) or 0

    return templates.TemplateResponse("super_admin/settings.html", {
        "request": request, "user": user, "active_page": "settings",
        "app_name": app_settings.APP_NAME,
        "app_version": app_settings.APP_VERSION,
        "org_count": org_count,
        "branch_count": branch_count,
    })


@router.get("/system-analytics", response_class=HTMLResponse)
@require_role(UserRole.SUPER_ADMIN)
async def system_analytics_page(request: Request, db: AsyncSession = Depends(get_db)):
    user = request.state.user
    return templates.TemplateResponse("super_admin/system_analytics.html", {
        "request": request, "user": user, "active_page": "system_analytics"
    })


@router.get("/branches/{branch_id}", response_class=HTMLResponse)
@require_role(UserRole.SUPER_ADMIN)
async def branch_detail(request: Request, branch_id: str, db: AsyncSession = Depends(get_db)):
    """Branch detail page — view/edit branch info, admins, stats, impersonate"""
    user = request.state.user
    import uuid as _uuid
    from models.student import Student
    from models.teacher import Teacher

    branch = (await db.execute(
        select(Branch)
        .options(selectinload(Branch.organization))
        .where(Branch.id == _uuid.UUID(branch_id))
    )).scalar_one_or_none()

    if not branch:
        from fastapi.responses import RedirectResponse
        return RedirectResponse("/super-admin/branches", status_code=302)

    # Get admins for this branch (first_admin only)
    admins = (await db.execute(
        select(User)
        .where(User.branch_id == branch.id, User.is_first_admin == True)
    )).scalars().all()

    # Get ALL staff for this branch
    all_staff = (await db.execute(
        select(User)
        .where(User.branch_id == branch.id, User.role == UserRole.SCHOOL_ADMIN)
    )).scalars().all()

    # Counts
    student_count = await db.scalar(select(func.count(Student.id)).where(Student.branch_id == branch.id)) or 0
    teacher_count = await db.scalar(select(func.count(Teacher.id)).where(Teacher.branch_id == branch.id)) or 0

    # Subscription
    from models.subscription import SchoolSubscription, Plan
    subscription = None
    sub = (await db.execute(
        select(SchoolSubscription).where(SchoolSubscription.branch_id == branch.id)
    )).scalars().first()
    if sub:
        plan = await db.scalar(select(Plan).where(Plan.id == sub.plan_id))
        subscription = {
            "plan_name": plan.name if plan else "Unknown",
            "billing_cycle": sub.billing_cycle.value if sub.billing_cycle else "monthly",
            "status": sub.status.value if hasattr(sub.status, 'value') else str(sub.status),
            "period_end": sub.current_period_end.strftime('%d %b %Y') if sub.current_period_end else None,
            "last_amount": float(sub.last_payment_amount) if sub.last_payment_amount else 0,
        }

    return templates.TemplateResponse("super_admin/branch_detail.html", {
        "request": request, "user": user, "active_page": "branches",
        "branch": branch, "admins": admins, "all_staff": all_staff,
        "student_count": student_count, "teacher_count": teacher_count,
        "subscription": subscription,
    })


@router.get("/backups")
@require_role(UserRole.SUPER_ADMIN)
async def backups_page(request: Request, db: AsyncSession = Depends(get_db)):
    user = request.state.user
    # Get all orgs with their branches
    from models.organization import Organization
    from models.branch import Branch
    orgs = (await db.execute(
        select(Organization).where(Organization.is_active == True).order_by(Organization.name)
    )).scalars().all()
    org_data = []
    for org in orgs:
        branches = (await db.execute(
            select(Branch).where(Branch.org_id == org.id, Branch.is_active == True).order_by(Branch.name)
        )).scalars().all()
        org_data.append({"org": org, "branches": branches})
    return templates.TemplateResponse("super_admin/backups.html", {
        "request": request, "user": user, "active_page": "backups",
        "org_data": org_data,
    })


@router.get("/chairmen")
@require_role(UserRole.SUPER_ADMIN)
async def chairmen_page(request: Request, db: AsyncSession = Depends(get_db)):
    user = request.state.user
    from models.organization import Organization
    chairmen_raw = (await db.execute(
        select(User).where(User.role == UserRole.CHAIRMAN).order_by(User.first_name)
    )).scalars().all()
    # Build org name lookup
    org_ids = [c.org_id for c in chairmen_raw if c.org_id]
    org_map = {}
    if org_ids:
        orgs_result = (await db.execute(
            select(Organization).where(Organization.id.in_(org_ids))
        )).scalars().all()
        org_map = {o.id: o.name for o in orgs_result}
    # Attach org_name to each chairman
    chairmen = []
    for c in chairmen_raw:
        c._org_name = org_map.get(c.org_id, "—")
        chairmen.append(c)
    orgs = (await db.execute(
        select(Organization).where(Organization.is_active == True).order_by(Organization.name)
    )).scalars().all()
    return templates.TemplateResponse("super_admin/chairmen.html", {
        "request": request, "user": user, "active_page": "chairmen",
        "chairmen": chairmen, "orgs": orgs,
    })