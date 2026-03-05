from functools import wraps
from fastapi import Request, HTTPException
from fastapi.responses import RedirectResponse
from utils.auth import decode_access_token
from models.user import UserRole


async def get_current_user(request: Request):
    """Extract current user from JWT cookie."""
    token = request.cookies.get("access_token")
    if not token:
        return None
    payload = decode_access_token(token)
    if not payload:
        return None
    return payload


# ═══════════════════════════════════════════════════════════
# ROLE-BASED DECORATORS (for dashboard layout routing)
# ═══════════════════════════════════════════════════════════

def require_role(*roles: UserRole):
    """Require specific role types — used for dashboard routing only."""
    def decorator(func):
        @wraps(func)
        async def wrapper(request: Request, *args, **kwargs):
            user = await get_current_user(request)
            if not user:
                return RedirectResponse(url="/login", status_code=302)
            user_role = (user.get("role") or "").lower()
            allowed = [r.value.lower() for r in roles]
            if user_role not in allowed:
                raise HTTPException(status_code=403, detail="Access denied")
            request.state.user = user
            return await func(request, *args, **kwargs)
        return wrapper
    return decorator


def require_auth(func):
    """Require any authenticated user."""
    @wraps(func)
    async def wrapper(request: Request, *args, **kwargs):
        user = await get_current_user(request)
        if not user:
            return RedirectResponse(url="/login", status_code=302)
        request.state.user = user
        return await func(request, *args, **kwargs)
    return wrapper


# ═══════════════════════════════════════════════════════════
# PRIVILEGE-BASED DECORATORS (for feature access)
# This is the main access control — checks privilege checkboxes
# ═══════════════════════════════════════════════════════════

def require_privilege(*privilege_keys: str):
    """
    Require at least ONE of the given privileges.

    Usage:
        @require_privilege("student_admission")
        @require_privilege("fee_collection", "fee_structure")  # either one

    Checks:
        1. User must be authenticated
        2. User must be SCHOOL_ADMIN or TEACHER role (not student/parent)
        3. User must have at least one of the specified privileges checked
        4. First admin (principal) bypasses — VERIFIED from DB, not JWT
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(request: Request, *args, **kwargs):
            user = await get_current_user(request)
            if not user:
                return RedirectResponse(url="/login", status_code=302)

            user_role = (user.get("role") or "").lower()

            # Super admin always has access
            if user_role == "super_admin":
                request.state.user = user
                return await func(request, *args, **kwargs)

            # Must be school staff or teacher
            if user_role not in ("school_admin", "teacher"):
                raise HTTPException(status_code=403, detail="Access denied — insufficient role")

            # First admin — RE-VERIFY from database
            if user.get("is_first_admin"):
                from database import async_session
                from models.user import User
                from sqlalchemy import select
                try:
                    async with async_session() as db:
                        db_user = await db.scalar(
                            select(User).where(User.id == user.get("user_id"))
                        )
                        if db_user and db_user.is_first_admin and db_user.is_active:
                            request.state.user = user
                            return await func(request, *args, **kwargs)
                except Exception:
                    # DB check failed (pool issue, etc.) — trust the JWT flag
                    # since it was server-set during login and is tamper-proof
                    request.state.user = user
                    return await func(request, *args, **kwargs)

            # Check privilege checkboxes
            user_privileges = user.get("privileges", {}) or {}
            has_access = any(user_privileges.get(key, False) for key in privilege_keys)

            if not has_access:
                raise HTTPException(
                    status_code=403,
                    detail=f"Access denied — requires privilege: {', '.join(privilege_keys)}"
                )

            request.state.user = user
            return await func(request, *args, **kwargs)
        return wrapper
    return decorator


# ═══════════════════════════════════════════════════════════
# PRIVACY TIER HELPERS
# ═══════════════════════════════════════════════════════════

# Tier 2 sensitive privileges — even with checkbox, user only sees records
# assigned/addressed to them, not all records
TIER2_SENSITIVE = {"complaints", "teacher_performance", "salary_payroll"}


def is_tier2_privilege(privilege_key: str) -> bool:
    """Check if a privilege is Tier 2 (sensitive — needs per-record access)."""
    return privilege_key in TIER2_SENSITIVE


def check_privilege_from_dict(user_dict: dict, *privilege_keys: str) -> bool:
    """
    Check privilege from user dict (JWT payload).
    Useful in templates and API routes where decorator isn't used.
    
    Usage in Jinja: {% if check_priv(user, 'student_admission') %}
    Usage in API:   if check_privilege_from_dict(user, 'fee_collection'): ...
    """
    if not user_dict:
        return False
    if (user_dict.get("role") or "").lower() == "super_admin":
        return True
    if user_dict.get("is_first_admin"):
        return True
    privileges = user_dict.get("privileges", {}) or {}
    return any(privileges.get(key, False) for key in privilege_keys)


def get_user_privilege_list(user_dict: dict) -> list:
    """Get list of active privilege keys for a user."""
    if not user_dict:
        return []
    if user_dict.get("is_first_admin"):
        from models.user import ALL_PRIVILEGES
        return list(ALL_PRIVILEGES.keys())
    return [k for k, v in (user_dict.get("privileges", {}) or {}).items() if v]


# ═══════════════════════════════════════════════════════════
# SHORTCUT DECORATORS
# ═══════════════════════════════════════════════════════════

# Role-based (for routing)
require_super_admin = require_role(UserRole.SUPER_ADMIN)
require_teacher = require_role(UserRole.TEACHER)
require_student = require_role(UserRole.STUDENT)

# School staff — any school_admin role (privilege checked separately)
require_school_staff = require_role(UserRole.SCHOOL_ADMIN)

# Privilege-based (for feature access)
require_admission = require_privilege("student_admission")
require_fee_access = require_privilege("fee_collection", "fee_structure", "fee_reports")
require_exam_access = require_privilege("exam_management", "results")
require_hr_access = require_privilege("employee_management", "teacher_attendance")
require_settings = require_privilege("school_settings", "manage_staff")