from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_
from database import get_db
from models.user import User, UserRole
from utils.auth import verify_password, create_access_token, hash_password
from config import settings
import uuid

router = APIRouter()
templates = Jinja2Templates(directory="templates")


def _parse_user_agent(ua: str) -> tuple:
    """Parse user-agent string into (os, browser, device)."""
    os_name = "Unknown"
    if "Windows" in ua: os_name = "Windows"
    elif "Mac OS" in ua or "Macintosh" in ua: os_name = "macOS"
    elif "Linux" in ua: os_name = "Linux"
    elif "Android" in ua: os_name = "Android"
    elif "iPhone" in ua or "iPad" in ua: os_name = "iOS"

    browser = "Unknown"
    if "Edg/" in ua: browser = "Edge"
    elif "Chrome/" in ua: browser = "Chrome"
    elif "Firefox/" in ua: browser = "Firefox"
    elif "Safari/" in ua: browser = "Safari"

    device = "Desktop"
    if "Mobile" in ua or "Android" in ua: device = "Mobile"
    elif "iPad" in ua or "Tablet" in ua: device = "Tablet"

    return os_name, browser, device


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    # If already logged in, redirect to dashboard
    token = request.cookies.get("access_token")
    if token:
        from utils.auth import decode_access_token
        payload = decode_access_token(token)
        if payload:
            role = payload.get("role")
            return RedirectResponse(url=get_dashboard_url(role), status_code=302)

    return templates.TemplateResponse("login.html", {
        "request": request,
        "user": None,
        "error": request.query_params.get("error"),
        "success": request.query_params.get("success"),
    })


@router.post("/login")
async def login_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: AsyncSession = Depends(get_db)
):
    # --- Security: Extract client info ---
    ip = request.headers.get("x-forwarded-for", request.client.host if request.client else "unknown").split(",")[0].strip()
    ua_string = request.headers.get("user-agent", "")
    os_name, browser_name, device_name = _parse_user_agent(ua_string)

    # --- Security: Check if IP is banned ---
    try:
        from models.login_security import BannedIP, LoginAttempt
        banned = await db.scalar(
            select(BannedIP).where(BannedIP.ip_address == ip, BannedIP.is_active == True)
        )
        if banned:
            # Log the blocked attempt
            attempt = LoginAttempt(email=username.strip(), ip_address=ip, user_agent=ua_string, os=os_name, browser=browser_name, device=device_name, success=False, failure_reason="IP_BANNED")
            db.add(attempt)
            await db.commit()
            return templates.TemplateResponse("login.html", {"request": request, "user": None, "error": "Access denied. Contact administrator.", "username": username})
    except Exception:
        pass  # Tables might not exist yet

    # Find user by email or phone
    result = await db.execute(
        select(User).where(
            or_(User.email == username.strip(), User.phone == username.strip()),
            User.is_active == True
        )
    )
    user = result.scalar_one_or_none()

    if not user or not verify_password(password, user.password_hash):
        # Log failed attempt
        try:
            from models.login_security import LoginAttempt
            reason = "USER_NOT_FOUND" if not user else "WRONG_PASSWORD"
            attempt = LoginAttempt(email=username.strip(), ip_address=ip, user_agent=ua_string, os=os_name, browser=browser_name, device=device_name, success=False, failure_reason=reason, user_id=user.id if user else None)
            db.add(attempt)
            await db.commit()
        except Exception:
            pass
        return templates.TemplateResponse("login.html", {
            "request": request,
            "user": None,
            "error": "Invalid email/phone or password",
            "username": username,
        })

    # Log successful login
    try:
        from models.login_security import LoginAttempt
        attempt = LoginAttempt(email=username.strip(), ip_address=ip, user_agent=ua_string, os=os_name, browser=browser_name, device=device_name, success=True, user_id=user.id)
        db.add(attempt)
    except Exception:
        pass
    # Create JWT token — include privileges for access control
    token_data = {
        "user_id": str(user.id),
        "email": user.email,
        "phone": user.phone,
        "first_name": user.first_name,
        "last_name": user.last_name or "",
        "role": user.role.value,
        "org_id": str(user.org_id) if user.org_id else None,
        "branch_id": str(user.branch_id) if user.branch_id else None,
        "privileges": user.privileges if user.privileges else {},
        "is_first_admin": getattr(user, 'is_first_admin', False) or False,
        "designation": getattr(user, 'designation', None),
    }
    access_token = create_access_token(token_data)

    # Update last login
    from datetime import datetime
    user.last_login = datetime.utcnow()
    await db.commit()

    # Redirect to role-specific dashboard
    response = RedirectResponse(url=get_dashboard_url(user.role.value), status_code=302)
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        samesite="lax",
    )
    return response


@router.get("/logout")
async def logout(request: Request):
    response = RedirectResponse(url="/login?success=You have been logged out", status_code=302)
    response.delete_cookie("access_token")
    return response


@router.get("/")
async def root(request: Request):
    token = request.cookies.get("access_token")
    if token:
        from utils.auth import decode_access_token
        payload = decode_access_token(token)
        if payload:
            role = payload.get("role")
            return RedirectResponse(url=get_dashboard_url(role), status_code=302)
    return RedirectResponse(url="/login", status_code=302)


def get_dashboard_url(role: str) -> str:
    dashboard_map = {
        "super_admin": "/super-admin/dashboard",
        "chairman": "/chairman/dashboard",
        "school_admin": "/school/dashboard",
        "teacher": "/teacher/dashboard",
        "student": "/student/dashboard",
        "parent": "/parent/dashboard",
    }
    return dashboard_map.get((role or "").lower(), "/login")


# ─── Sprint 26: Public Payment Pages ───

@router.get("/payment/checkout", response_class=HTMLResponse)
async def payment_checkout(request: Request):
    from fastapi.templating import Jinja2Templates
    templates = Jinja2Templates(directory="templates")
    return templates.TemplateResponse("payment/checkout.html", {"request": request})


@router.get("/payment/success", response_class=HTMLResponse)
async def payment_success(request: Request):
    from fastapi.templating import Jinja2Templates
    templates = Jinja2Templates(directory="templates")
    return templates.TemplateResponse("payment/success.html", {"request": request})


@router.get("/pay/{link_id}", response_class=HTMLResponse)
async def payment_link_page(link_id: str, request: Request):
    from fastapi.templating import Jinja2Templates
    templates = Jinja2Templates(directory="templates")
    return templates.TemplateResponse("payment/payment_link.html", {"request": request, "link_id": link_id})


@router.get("/donate", response_class=HTMLResponse)
async def donate_page(request: Request):
    from fastapi.templating import Jinja2Templates
    templates = Jinja2Templates(directory="templates")
    return templates.TemplateResponse("payment/donate.html", {"request": request})