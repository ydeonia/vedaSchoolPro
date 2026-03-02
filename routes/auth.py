"""
VedaSchoolPro — Web Authentication v3.0 (FINAL)
PO-Approved: No parent login. Student Login ID for students+parents.

Login IDs:
  Student (+ Parent) → Student Login ID (e.g., GNK24123)
  Staff (Chairman/Admin/Teacher) → Phone or Email
  Super Admin → Email
"""
from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_, text
from database import get_db
from models.user import User, UserRole
from models.student import Student
from utils.auth import verify_password, create_access_token, decode_access_token
from config import settings
from datetime import datetime
import re

router = APIRouter()
templates = Jinja2Templates(directory="templates")


def _parse_user_agent(ua: str) -> tuple:
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


def _detect_login_type(username: str) -> str:
    """
    Detect login ID type:
      'student_id' → Student Login ID (e.g. GNK24123, CNV251)
      'phone'      → 10+ digit phone number
      'email'      → contains @
    """
    cleaned = username.strip()
    if "@" in cleaned:
        return "email"
    digits_only = re.sub(r'[+\-\s]', '', cleaned)
    if digits_only.isdigit() and len(digits_only) >= 10:
        return "phone"
    return "student_id"


def get_dashboard_url(role: str) -> str:
    dashboard_map = {
        "super_admin": "/super-admin/dashboard",
        "chairman": "/chairman/dashboard",
        "school_admin": "/school/dashboard",
        "teacher": "/teacher/dashboard",
        "student": "/student/dashboard",
        "parent": "/student/dashboard",  # Legacy redirect
    }
    return dashboard_map.get((role or "").lower(), "/login")


async def _log_attempt(db, username, ip, ua, os_n, br, dev, success, reason=None, uid=None):
    try:
        from models.login_security import LoginAttempt
        db.add(LoginAttempt(email=username, ip_address=ip, user_agent=ua,
            os=os_n, browser=br, device=dev, success=success,
            failure_reason=reason, user_id=uid))
        await db.commit()
    except Exception:
        pass


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    token = request.cookies.get("access_token")
    if token:
        payload = decode_access_token(token)
        if payload:
            return RedirectResponse(url=get_dashboard_url(payload.get("role")), status_code=302)
    return templates.TemplateResponse("login.html", {
        "request": request, "user": None,
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
    ip = request.headers.get("x-forwarded-for", request.client.host if request.client else "unknown").split(",")[0].strip()
    ua_string = request.headers.get("user-agent", "")
    os_name, browser_name, device_name = _parse_user_agent(ua_string)

    # Check banned IP
    try:
        from models.login_security import BannedIP
        banned = await db.scalar(select(BannedIP).where(BannedIP.ip_address == ip, BannedIP.is_active == True))
        if banned:
            await _log_attempt(db, username, ip, ua_string, os_name, browser_name, device_name, False, "IP_BANNED")
            return templates.TemplateResponse("login.html", {
                "request": request, "user": None, "error": "Access denied. Contact administrator.", "username": username
            })
    except Exception:
        pass

    login_type = _detect_login_type(username)

    # ═══ STUDENT LOGIN ID → Student/Parent access ═══
    if login_type == "student_id":
        clean_id = username.strip().upper()

        # Try student_login_id first, then admission_number
        student = await db.scalar(select(Student).where(Student.student_login_id == clean_id))
        if not student:
            student = await db.scalar(select(Student).where(Student.admission_number == username.strip()))

        if not student:
            await _log_attempt(db, username, ip, ua_string, os_name, browser_name, device_name, False, "STUDENT_NOT_FOUND")
            return templates.TemplateResponse("login.html", {
                "request": request, "user": None,
                "error": "Invalid Student ID. Check your ID card or contact school.",
                "username": username,
            })

        # Find linked User
        user = None
        if student.user_id:
            user = await db.scalar(select(User).where(User.id == student.user_id, User.is_active == True))

        if not user:
            await _log_attempt(db, username, ip, ua_string, os_name, browser_name, device_name, False, "NO_USER_ACCOUNT")
            return templates.TemplateResponse("login.html", {
                "request": request, "user": None,
                "error": "Account not set up yet. Contact school admin.",
                "username": username,
            })

        if not verify_password(password, user.password_hash):
            await _log_attempt(db, username, ip, ua_string, os_name, browser_name, device_name, False, "WRONG_PASSWORD", user.id)
            return templates.TemplateResponse("login.html", {
                "request": request, "user": None, "error": "Invalid password", "username": username,
            })

        # Success → student dashboard (even if User.role was 'parent')
        await _log_attempt(db, username, ip, ua_string, os_name, browser_name, device_name, True, user_id=user.id)

        token_data = {
            "user_id": str(user.id), "email": user.email, "phone": user.phone,
            "first_name": student.first_name, "last_name": student.last_name or "",
            "role": "student",  # Always student, regardless of User.role
            "org_id": str(user.org_id) if user.org_id else None,
            "branch_id": str(student.branch_id) if student.branch_id else (str(user.branch_id) if user.branch_id else None),
            "student_id": str(student.id),
            "student_login_id": student.student_login_id or student.admission_number,
            "privileges": user.privileges or {},
        }
        access_token = create_access_token(token_data)
        user.last_login = datetime.utcnow()
        await db.commit()

        response = RedirectResponse(url="/student/dashboard", status_code=302)
        response.set_cookie(key="access_token", value=access_token, httponly=True,
            max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60, samesite="lax")
        return response

    # ═══ PHONE / EMAIL → Staff login ═══
    cleaned = username.strip()
    if login_type == "phone":
        phone = re.sub(r'[+\-\s]', '', cleaned)
        if phone.startswith("91") and len(phone) > 10:
            phone = phone[2:]
        result = await db.execute(select(User).where(User.phone == phone, User.is_active == True))
    else:
        result = await db.execute(select(User).where(User.email == cleaned, User.is_active == True))

    users = result.scalars().all()
    # Filter out parent role
    users = [u for u in users if u.role.value.lower() != "parent"]

    if not users:
        await _log_attempt(db, username, ip, ua_string, os_name, browser_name, device_name, False, "USER_NOT_FOUND")
        return templates.TemplateResponse("login.html", {
            "request": request, "user": None,
            "error": "Invalid credentials. Staff: use phone/email. Students: use Student ID.",
            "username": username,
        })

    # Verify password
    user = None
    for u in users:
        if verify_password(password, u.password_hash):
            user = u
            break

    if not user:
        await _log_attempt(db, username, ip, ua_string, os_name, browser_name, device_name, False, "WRONG_PASSWORD", users[0].id)
        return templates.TemplateResponse("login.html", {
            "request": request, "user": None, "error": "Invalid password", "username": username,
        })

    await _log_attempt(db, username, ip, ua_string, os_name, browser_name, device_name, True, user_id=user.id)

    token_data = {
        "user_id": str(user.id), "email": user.email, "phone": user.phone,
        "first_name": user.first_name, "last_name": user.last_name or "",
        "role": user.role.value,
        "org_id": str(user.org_id) if user.org_id else None,
        "branch_id": str(user.branch_id) if user.branch_id else None,
        "privileges": user.privileges or {},
        "is_first_admin": getattr(user, 'is_first_admin', False) or False,
        "designation": getattr(user, 'designation', None),
    }
    access_token = create_access_token(token_data)
    user.last_login = datetime.utcnow()
    await db.commit()

    response = RedirectResponse(url=get_dashboard_url(user.role.value), status_code=302)
    response.set_cookie(key="access_token", value=access_token, httponly=True,
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60, samesite="lax")
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
        payload = decode_access_token(token)
        if payload:
            return RedirectResponse(url=get_dashboard_url(payload.get("role")), status_code=302)
    return RedirectResponse(url="/login", status_code=302)


# ─── Public Payment Pages (unchanged) ───

@router.get("/payment/checkout", response_class=HTMLResponse)
async def payment_checkout(request: Request):
    return templates.TemplateResponse("payment/checkout.html", {"request": request})

@router.get("/payment/success", response_class=HTMLResponse)
async def payment_success(request: Request):
    return templates.TemplateResponse("payment/success.html", {"request": request})

@router.get("/pay/{link_id}", response_class=HTMLResponse)
async def payment_link_page(link_id: str, request: Request):
    return templates.TemplateResponse("payment/payment_link.html", {"request": request, "link_id": link_id})

@router.get("/donate", response_class=HTMLResponse)
async def donate_page(request: Request):
    return templates.TemplateResponse("payment/donate.html", {"request": request})