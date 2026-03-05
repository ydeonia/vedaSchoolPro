"""
VedaSchoolPro — Web Authentication v3.0 (FINAL)
PO-Approved: No parent login. Student Login ID for students+parents.

Login IDs:
  Student (+ Parent) → Student Login ID (e.g., GNK24123)
  Staff (Chairman/Admin/Teacher) → Phone or Email
  Super Admin → Email
"""
from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import RedirectResponse, HTMLResponse, JSONResponse
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
import random
import logging
from collections import defaultdict
from time import time

logger = logging.getLogger("auth")

# Simple in-memory rate limiter for login attempts
_login_attempts: dict[str, list[float]] = defaultdict(list)
MAX_LOGIN_ATTEMPTS = 5
LOCKOUT_SECONDS = 300  # 5 minutes


def _check_rate_limit(ip: str) -> bool:
    """Returns True if the IP is rate-limited."""
    now = time()
    # Clean old entries
    _login_attempts[ip] = [t for t in _login_attempts[ip] if now - t < LOCKOUT_SECONDS]
    return len(_login_attempts[ip]) >= MAX_LOGIN_ATTEMPTS


def _record_failed_attempt(ip: str):
    """Record a failed login attempt for rate limiting."""
    _login_attempts[ip].append(time())

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
    except Exception as e:
        import logging
        logging.getLogger("auth").warning(f"Failed to log login attempt: {e}")
        await db.rollback()


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    token = request.cookies.get("access_token")
    if token:
        payload = decode_access_token(token)
        if payload:
            return RedirectResponse(url=get_dashboard_url(payload.get("role")), status_code=302)

    # School branding from subdomain middleware
    school_branch = getattr(request.state, "school_branch", None)
    return templates.TemplateResponse("login.html", {
        "request": request, "user": None,
        "error": request.query_params.get("error"),
        "success": request.query_params.get("success"),
        "school": school_branch,  # dict with name, logo_url, city, etc. or None
    })


@router.post("/login")
async def login_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: AsyncSession = Depends(get_db)
):
    """Form-based login fallback — redirects to JSON API internally."""
    result = await _do_password_login(request, username, password, db)

    # If JSON result (multiple accounts or AJAX), return as-is
    if isinstance(result, JSONResponse):
        return result

    # Normal single-account login — result is dict with token + redirect
    if result.get("success"):
        response = RedirectResponse(url=result["redirect"], status_code=302)
        response.set_cookie(key="access_token", value=result["token"], httponly=True,
            max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60, samesite="lax", secure=not settings.DEBUG)
        return response

    # Error
    return templates.TemplateResponse("login.html", {
        "request": request, "user": None,
        "error": result.get("error", "Login failed"),
        "username": username,
    })


@router.post("/api/auth/login")
async def api_login(request: Request, db: AsyncSession = Depends(get_db)):
    """JSON-based login API — supports multi-role profile selection."""
    try:
        body = await request.json()
        username = body.get("username", "").strip()
        password = body.get("password", "")
    except Exception:
        return JSONResponse({"success": False, "error": "Invalid request"}, status_code=400)

    if not username or not password:
        return JSONResponse({"success": False, "error": "Username and password are required"}, status_code=400)

    result = await _do_password_login(request, username, password, db)
    if isinstance(result, JSONResponse):
        return result
    return JSONResponse(result)


async def _do_password_login(request: Request, username: str, password: str, db: AsyncSession):
    """Core password login logic — returns dict or JSONResponse."""
    ip = request.headers.get("x-forwarded-for", request.client.host if request.client else "unknown").split(",")[0].strip()
    ua_string = request.headers.get("user-agent", "")
    os_name, browser_name, device_name = _parse_user_agent(ua_string)

    # Rate limit check
    if _check_rate_limit(ip):
        return {"success": False, "error": "Too many login attempts. Please try again in 5 minutes."}

    # Check banned IP
    try:
        from models.login_security import BannedIP
        banned = await db.scalar(select(BannedIP).where(BannedIP.ip_address == ip, BannedIP.is_active == True))
        if banned:
            await _log_attempt(db, username, ip, ua_string, os_name, browser_name, device_name, False, "IP_BANNED")
            return {"success": False, "error": "Access denied. Contact administrator."}
    except Exception as e:
        logger.warning(f"BannedIP check failed: {e}")

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
            return {"success": False, "error": "Invalid Student ID. Check your ID card or contact school."}

        # Find linked User
        user = None
        if student.user_id:
            user = await db.scalar(select(User).where(User.id == student.user_id, User.is_active == True))

        if not user:
            await _log_attempt(db, username, ip, ua_string, os_name, browser_name, device_name, False, "NO_USER_ACCOUNT")
            return {"success": False, "error": "Account not set up yet. Contact school admin."}

        if not verify_password(password, user.password_hash):
            await _log_attempt(db, username, ip, ua_string, os_name, browser_name, device_name, False, "WRONG_PASSWORD", user.id)
            _record_failed_attempt(ip)
            return {"success": False, "error": "Invalid password"}

        # Success → student dashboard
        await _log_attempt(db, username, ip, ua_string, os_name, browser_name, device_name, True, user_id=user.id)

        token_data = {
            "user_id": str(user.id), "email": user.email, "phone": user.phone,
            "first_name": student.first_name, "last_name": student.last_name or "",
            "role": "student",
            "org_id": str(user.org_id) if user.org_id else None,
            "branch_id": str(student.branch_id) if student.branch_id else (str(user.branch_id) if user.branch_id else None),
            "student_id": str(student.id),
            "student_login_id": student.student_login_id or student.admission_number,
            "privileges": user.privileges or {},
        }
        access_token = create_access_token(token_data)
        user.last_login = datetime.utcnow()
        await db.commit()

        return {
            "success": True,
            "token": access_token,
            "redirect": "/student/dashboard",
            "accounts": [{
                "type": "child",
                "name": f"{student.first_name} {student.last_name or ''}".strip(),
                "detail": f"Student · {student.student_login_id or student.admission_number or ''}",
                "token": access_token,
                "redirect": "/student/dashboard",
            }],
        }

    # ═══ PHONE / EMAIL → Staff login (with multi-role support) ═══
    cleaned = username.strip()
    if login_type == "phone":
        phone = re.sub(r'[+\-\s]', '', cleaned)
        if phone.startswith("91") and len(phone) > 10:
            phone = phone[2:]
        result = await db.execute(select(User).where(User.phone == phone, User.is_active == True))
    else:
        result = await db.execute(select(User).where(User.email == cleaned, User.is_active == True))

    users = result.scalars().all()
    # Filter out parent role (parents login via student ID or OTP)
    users = [u for u in users if u.role.value.lower() != "parent"]

    if not users:
        await _log_attempt(db, username, ip, ua_string, os_name, browser_name, device_name, False, "USER_NOT_FOUND")
        return {"success": False, "error": "Invalid credentials. Staff: use phone/email. Students: use Student ID."}

    # Verify password — collect ALL matching users (for multi-role)
    matched_users = []
    for u in users:
        if verify_password(password, u.password_hash):
            matched_users.append(u)

    if not matched_users:
        await _log_attempt(db, username, ip, ua_string, os_name, browser_name, device_name, False, "WRONG_PASSWORD", users[0].id)
        _record_failed_attempt(ip)
        return {"success": False, "error": "Invalid password"}

    # Build accounts list for all matched users
    accounts = []
    for u in matched_users:
        u.last_login = datetime.utcnow()
        token_data = {
            "user_id": str(u.id), "email": u.email, "phone": u.phone,
            "first_name": u.first_name, "last_name": u.last_name or "",
            "role": u.role.value,
            "org_id": str(u.org_id) if u.org_id else None,
            "branch_id": str(u.branch_id) if u.branch_id else None,
            "privileges": u.privileges or {},
            "is_first_admin": getattr(u, 'is_first_admin', False) or False,
            "designation": getattr(u, 'designation', None),
        }
        token = create_access_token(token_data)
        role_label = u.role.value.replace("_", " ").title()
        accounts.append({
            "type": "staff",
            "name": f"{u.first_name} {u.last_name or ''}".strip(),
            "detail": f"{role_label}" + (f" · {u.designation}" if u.designation else ""),
            "token": token,
            "redirect": get_dashboard_url(u.role.value),
        })

    await _log_attempt(db, username, ip, ua_string, os_name, browser_name, device_name, True, uid=matched_users[0].id)
    await db.commit()

    return {
        "success": True,
        "token": accounts[0]["token"],
        "redirect": accounts[0]["redirect"],
        "accounts": accounts,
    }


# ═══════════════════════════════════════════════════════════
# OTP LOGIN — For Parents & Staff (Phone-based)
# ═══════════════════════════════════════════════════════════

_otp_store: dict[str, dict] = {}
OTP_EXPIRY_SECONDS = 300
OTP_MAX_VERIFY_ATTEMPTS = 5
OTP_RESEND_COOLDOWN = 60


def _generate_otp() -> str:
    return str(random.randint(100000, 999999))


def _clean_phone(phone: str) -> str:
    phone = re.sub(r'[+\-\s]', '', phone.strip())
    if phone.startswith("91") and len(phone) == 12:
        phone = phone[2:]
    if phone.startswith("0"):
        phone = phone[1:]
    return phone


@router.post("/api/otp/send")
async def send_otp(request: Request, db: AsyncSession = Depends(get_db)):
    """Send OTP — works for parents (via student phone fields) and staff (via user phone)."""
    body = await request.json()
    phone = _clean_phone(body.get("phone", ""))

    if not phone or len(phone) != 10 or not phone.isdigit():
        return JSONResponse({"success": False, "error": "Enter a valid 10-digit phone number"}, status_code=400)

    ip = request.headers.get("x-forwarded-for", request.client.host if request.client else "unknown").split(",")[0].strip()
    if _check_rate_limit(ip):
        return JSONResponse({"success": False, "error": "Too many attempts. Try again in 5 minutes."}, status_code=429)

    existing = _otp_store.get(phone)
    if existing and (time() - existing.get("sent_at", 0)) < OTP_RESEND_COOLDOWN:
        remaining = int(OTP_RESEND_COOLDOWN - (time() - existing["sent_at"]))
        return JSONResponse({"success": False, "error": f"OTP already sent. Retry in {remaining}s."}, status_code=429)

    # Subdomain branch filtering — if accessed via school subdomain, scope to that school only
    school_branch = getattr(request.state, "school_branch", None)
    import uuid as _uuid_mod
    branch_filter_id = _uuid_mod.UUID(school_branch["id"]) if school_branch else None

    # 1. Find students linked to this phone (parent lookup)
    student_query = select(Student).where(
        Student.is_active == True,
        or_(
            Student.father_phone == phone,
            Student.mother_phone == phone,
            Student.guardian_phone == phone,
        )
    )
    if branch_filter_id:
        student_query = student_query.where(Student.branch_id == branch_filter_id)

    students = (await db.execute(student_query)).scalars().all()

    # 2. Find staff users with this phone (teacher/admin/chairman)
    staff_query = select(User).where(
        User.phone == phone,
        User.is_active == True,
        User.role.notin_([UserRole.STUDENT, UserRole.PARENT]),
    )
    if branch_filter_id:
        staff_query = staff_query.where(User.branch_id == branch_filter_id)

    staff_users = (await db.execute(staff_query)).scalars().all()

    if not students and not staff_users:
        return JSONResponse({"success": False, "error": "No account found for this phone number. Contact school."}, status_code=404)

    # Generate OTP
    otp = _generate_otp()
    _otp_store[phone] = {
        "otp": otp,
        "expires": time() + OTP_EXPIRY_SECONDS,
        "attempts": 0,
        "sent_at": time(),
    }

    # Try to send SMS — PlatformConfig (Super Admin) takes priority, then branch config
    sms_sent = False
    sms_error = ""
    try:
        from utils.notifier import send_sms, normalize_phone, get_sms_config

        # Resolve branch_id for fallback
        branch_id = None
        if students and students[0].branch_id:
            branch_id = str(students[0].branch_id)
        elif staff_users and staff_users[0].branch_id:
            branch_id = str(staff_users[0].branch_id)

        comm_config = await get_sms_config(db, branch_id)

        if comm_config:
            sms_message = f"Your VedaSchoolPro login OTP is {otp}. Valid for 5 minutes. Do not share with anyone."
            result = await send_sms(comm_config, normalize_phone(phone), sms_message, sms_type="otp")
            sms_sent = result.get("status") == "sent"
            if not sms_sent:
                sms_error = result.get("reason", result.get("error", "SMS send failed"))
    except Exception as e:
        logger.warning(f"OTP SMS send error: {e}")
        sms_error = str(e)

    if not sms_sent:
        logger.info(f"[OTP-DEV] Phone: {phone}, OTP: {otp} (SMS not sent: {sms_error})")
        return JSONResponse({
            "success": True,
            "message": "OTP generated. SMS delivery pending — check below.",
            "sms_sent": False,
            "sms_error": sms_error,
            "dev_hint": otp,  # Always show OTP when SMS fails so user is not locked out
        })

    return JSONResponse({
        "success": True,
        "message": f"OTP sent to +91 ******{phone[-4:]}",
        "sms_sent": True,
    })


@router.post("/api/otp/verify")
async def verify_otp(request: Request, db: AsyncSession = Depends(get_db)):
    """Verify OTP and build account list (students + staff) for this phone."""
    body = await request.json()
    phone = _clean_phone(body.get("phone", ""))
    otp_input = str(body.get("otp", "")).strip()

    if not phone or not otp_input:
        return JSONResponse({"success": False, "error": "Phone and OTP are required"}, status_code=400)

    ip = request.headers.get("x-forwarded-for", request.client.host if request.client else "unknown").split(",")[0].strip()
    ua_string = request.headers.get("user-agent", "")
    os_name, browser_name, device_name = _parse_user_agent(ua_string)

    stored = _otp_store.get(phone)
    if not stored:
        return JSONResponse({"success": False, "error": "No OTP found. Please request a new one."}, status_code=400)

    if time() > stored["expires"]:
        del _otp_store[phone]
        return JSONResponse({"success": False, "error": "OTP expired. Please request a new one."}, status_code=400)

    if stored["attempts"] >= OTP_MAX_VERIFY_ATTEMPTS:
        del _otp_store[phone]
        _record_failed_attempt(ip)
        return JSONResponse({"success": False, "error": "Too many wrong attempts. Request a new OTP."}, status_code=429)

    if otp_input != stored["otp"]:
        stored["attempts"] += 1
        remaining = OTP_MAX_VERIFY_ATTEMPTS - stored["attempts"]
        return JSONResponse({"success": False, "error": f"Wrong OTP. {remaining} attempts remaining."}, status_code=400)

    # OTP valid
    del _otp_store[phone]
    await _log_attempt(db, f"OTP:{phone}", ip, ua_string, os_name, browser_name, device_name, True)

    # ── Build all possible accounts for this phone ──
    accounts = []

    # Subdomain branch filtering
    school_branch = getattr(request.state, "school_branch", None)
    import uuid as _uuid_mod
    branch_filter_id = _uuid_mod.UUID(school_branch["id"]) if school_branch else None

    # 1. Staff users (teacher, admin, chairman)
    staff_verify_q = select(User).where(
        User.phone == phone,
        User.is_active == True,
        User.role.notin_([UserRole.STUDENT, UserRole.PARENT]),
    )
    if branch_filter_id:
        staff_verify_q = staff_verify_q.where(User.branch_id == branch_filter_id)

    staff_users = (await db.execute(staff_verify_q)).scalars().all()

    for u in staff_users:
        u.last_login = datetime.utcnow()
        token_data = {
            "user_id": str(u.id), "email": u.email, "phone": u.phone,
            "first_name": u.first_name, "last_name": u.last_name or "",
            "role": u.role.value,
            "org_id": str(u.org_id) if u.org_id else None,
            "branch_id": str(u.branch_id) if u.branch_id else None,
            "privileges": u.privileges or {},
            "is_first_admin": getattr(u, 'is_first_admin', False) or False,
            "designation": getattr(u, 'designation', None),
            "login_method": "otp",
        }
        role_label = u.role.value.replace("_", " ").title()
        accounts.append({
            "type": "staff",
            "name": f"{u.first_name} {u.last_name or ''}".strip(),
            "detail": f"{role_label}" + (f" · {getattr(u, 'designation', '') or ''}" if getattr(u, 'designation', None) else ""),
            "token": create_access_token(token_data),
            "redirect": get_dashboard_url(u.role.value),
        })

    # 2. Students linked to this phone (parent access)
    student_verify_q = select(Student).where(
        Student.is_active == True,
        or_(
            Student.father_phone == phone,
            Student.mother_phone == phone,
            Student.guardian_phone == phone,
        )
    )
    if branch_filter_id:
        student_verify_q = student_verify_q.where(Student.branch_id == branch_filter_id)

    students = (await db.execute(student_verify_q)).scalars().all()

    for s in students:
        # Determine parent name
        parent_name = "Parent"
        if s.father_phone == phone:
            parent_name = s.father_name or "Parent"
        elif s.mother_phone == phone:
            parent_name = s.mother_name or "Parent"
        elif s.guardian_phone == phone:
            parent_name = s.guardian_name or "Guardian"

        # Get linked user if exists
        user = None
        if s.user_id:
            user = await db.scalar(select(User).where(User.id == s.user_id, User.is_active == True))

        if user:
            user.last_login = datetime.utcnow()
            token_data = {
                "user_id": str(user.id), "email": user.email,
                "phone": user.phone or phone,
                "first_name": s.first_name, "last_name": s.last_name or "",
                "role": "student",
                "org_id": str(user.org_id) if user.org_id else None,
                "branch_id": str(s.branch_id) if s.branch_id else None,
                "student_id": str(s.id),
                "student_login_id": s.student_login_id or s.admission_number,
                "login_method": "otp",
                "privileges": user.privileges or {},
            }
        else:
            token_data = {
                "user_id": None, "phone": phone,
                "first_name": s.first_name, "last_name": s.last_name or "",
                "role": "student",
                "org_id": None,
                "branch_id": str(s.branch_id) if s.branch_id else None,
                "student_id": str(s.id),
                "student_login_id": s.student_login_id or s.admission_number,
                "login_method": "otp",
                "privileges": {},
            }

        child_name = f"{s.first_name} {s.last_name or ''}".strip()
        login_id = s.student_login_id or s.admission_number or ""
        accounts.append({
            "type": "child",
            "name": child_name,
            "detail": f"Student · {login_id}" + (f" · as {parent_name}" if parent_name != "Parent" else ""),
            "token": create_access_token(token_data),
            "redirect": "/student/dashboard",
        })

    await db.commit()

    if not accounts:
        return JSONResponse({"success": False, "error": "No accounts found for this phone."}, status_code=404)

    # Single account — direct login
    if len(accounts) == 1:
        return JSONResponse({
            "success": True,
            "message": "Login successful!",
            "token": accounts[0]["token"],
            "redirect": accounts[0]["redirect"],
            "accounts": accounts,
        })

    # Multiple accounts — let user pick
    return JSONResponse({
        "success": True,
        "message": "Select an account to continue",
        "token": accounts[0]["token"],  # Default to first
        "redirect": accounts[0]["redirect"],
        "accounts": accounts,
    })


@router.get("/account", response_class=HTMLResponse)
async def my_account_page(request: Request):
    """My Account page — available to all authenticated users."""
    token = request.cookies.get("access_token")
    if not token:
        return RedirectResponse(url="/login", status_code=302)
    payload = decode_access_token(token)
    if not payload:
        return RedirectResponse(url="/login", status_code=302)

    return templates.TemplateResponse("account.html", {
        "request": request,
        "user": payload,
        "active_page": "my_account",
    })


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


# ─── Language API ───

from fastapi.responses import JSONResponse

@router.post("/api/user/set-language")
async def set_language(request: Request):
    """Set user preferred language (stored in cookie by JS, this is optional server-side save)."""
    try:
        body = await request.json()
        lang = body.get("language", "en")
        return JSONResponse({"success": True, "language": lang})
    except Exception:
        return JSONResponse({"success": True, "language": "en"})


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


# ═══════════════════════════════════════════════════════════
# FORGOT PASSWORD — Self-service password reset
# ═══════════════════════════════════════════════════════════

@router.get("/forgot-password", response_class=HTMLResponse)
async def forgot_password_page(request: Request):
    """Public page where users can request a password reset link."""
    return templates.TemplateResponse("forgot_password.html", {"request": request})


@router.post("/api/auth/forgot-password")
async def forgot_password_api(request: Request, db: AsyncSession = Depends(get_db)):
    """Send password reset link to user's email."""
    data = await request.json()
    email = (data.get("email") or "").strip().lower()

    if not email or "@" not in email:
        return JSONResponse({"error": "Please enter a valid email address"})

    # Find user by email
    user = await db.scalar(select(User).where(User.email == email, User.is_active == True))

    # Always return success to prevent email enumeration
    if not user:
        return JSONResponse({"success": True, "message": "If an account exists with that email, a reset link has been sent."})

    import secrets
    from time import time as _now
    from routes.api.super_admin_api import _password_reset_tokens, _RESET_LINK_EXPIRY

    token = secrets.token_urlsafe(48)
    _password_reset_tokens[token] = {
        "user_id": str(user.id),
        "email": user.email,
        "expires": _now() + _RESET_LINK_EXPIRY,
        "created_at": _now(),
    }

    host = request.headers.get("host", "localhost:8000")
    scheme = "https" if "localhost" not in host else "http"
    reset_url = f"{scheme}://{host}/reset-password?token={token}"

    try:
        from utils.notifier import send_platform_email
        body = f"""
        <div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;">
            <div style="background:linear-gradient(135deg,#6366f1,#8b5cf6);padding:24px;border-radius:12px 12px 0 0;">
                <h2 style="color:#fff;margin:0;">Password Reset</h2>
            </div>
            <div style="background:#fff;padding:24px;border:1px solid #e2e8f0;border-radius:0 0 12px 12px;">
                <p style="color:#334155;">Hi <strong>{user.first_name}</strong>,</p>
                <p style="color:#334155;">We received a request to reset your password. Click below to set a new one:</p>
                <div style="text-align:center;margin:24px 0;">
                    <a href="{reset_url}" style="display:inline-block;background:linear-gradient(135deg,#6366f1,#8b5cf6);color:#fff;padding:14px 32px;border-radius:8px;text-decoration:none;font-weight:700;">Reset Password</a>
                </div>
                <p style="color:#64748b;font-size:0.85rem;">Or copy this link: <span style="word-break:break-all;color:#6366f1;">{reset_url}</span></p>
                <p style="color:#ef4444;font-size:0.82rem;font-weight:600;">This link expires in 24 hours.</p>
                <p style="color:#94a3b8;font-size:0.78rem;">If you didn't request this, ignore this email.</p>
            </div>
        </div>"""
        await send_platform_email(db, user.email, "Password Reset — VedaSchoolPro", body)
    except Exception:
        pass  # Don't reveal email errors

    return JSONResponse({"success": True, "message": "If an account exists with that email, a reset link has been sent."})


# ═══════════════════════════════════════════════════════════
# PASSWORD RESET — Token-based public page
# ═══════════════════════════════════════════════════════════

@router.get("/reset-password", response_class=HTMLResponse)
async def reset_password_page(request: Request):
    """Public page where user can set a new password using a reset token."""
    token = request.query_params.get("token", "")
    error = None
    valid = False

    if token:
        from routes.api.super_admin_api import _password_reset_tokens
        from time import time as _now
        info = _password_reset_tokens.get(token)
        if info:
            if info["expires"] > _now():
                valid = True
            else:
                error = "This reset link has expired. Please request a new one."
                del _password_reset_tokens[token]
        else:
            error = "Invalid or expired reset link."

    return templates.TemplateResponse("reset_password.html", {
        "request": request,
        "token": token,
        "valid": valid,
        "error": error,
    })


@router.post("/api/auth/reset-password")
async def do_reset_password(request: Request, db: AsyncSession = Depends(get_db)):
    """Process password reset with a valid token."""
    data = await request.json()
    token = data.get("token", "")
    new_password = data.get("password", "")

    if len(new_password) < 6:
        return JSONResponse({"error": "Password must be at least 6 characters"})

    from routes.api.super_admin_api import _password_reset_tokens
    from time import time as _now

    info = _password_reset_tokens.get(token)
    if not info:
        return JSONResponse({"error": "Invalid or expired reset link"})
    if info["expires"] < _now():
        del _password_reset_tokens[token]
        return JSONResponse({"error": "This reset link has expired"})

    from utils.auth import hash_password
    user = await db.scalar(select(User).where(User.id == __import__('uuid').UUID(info["user_id"])))
    if not user:
        return JSONResponse({"error": "User not found"})

    user.password_hash = hash_password(new_password)
    await db.commit()

    # Invalidate the token after use
    del _password_reset_tokens[token]

    return JSONResponse({"success": True, "message": "Password updated successfully! You can now login with your new password."})