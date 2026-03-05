"""
My Account API — Profile viewing, password change, phone/email change with verification.
Available to ALL authenticated users (super_admin, chairman, school_admin, teacher, student).
"""
from fastapi import APIRouter, Request, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_
from database import get_db
from models.user import User
from models.student import Student
from utils.auth import verify_password, hash_password, decode_access_token, create_access_token
from config import settings
import re
import random
import logging
from time import time

logger = logging.getLogger("account")

router = APIRouter(prefix="/api/account", tags=["Account"])

# ─── Temp store for phone/email change OTPs ───
_change_otp_store: dict[str, dict] = {}
CHANGE_OTP_EXPIRY = 300  # 5 minutes
CHANGE_OTP_MAX_ATTEMPTS = 5


def _get_current_user(request: Request) -> dict | None:
    """Get current user from JWT cookie."""
    token = request.cookies.get("access_token")
    if not token:
        return None
    return decode_access_token(token)


def _clean_phone(phone: str) -> str:
    phone = re.sub(r'[+\-\s]', '', phone.strip())
    if phone.startswith("91") and len(phone) == 12:
        phone = phone[2:]
    if phone.startswith("0"):
        phone = phone[1:]
    return phone


# ═══════════════════════════════════════════════════════════
# GET PROFILE
# ═══════════════════════════════════════════════════════════

@router.get("/profile")
async def get_profile(request: Request, db: AsyncSession = Depends(get_db)):
    """Get current user profile data."""
    payload = _get_current_user(request)
    if not payload:
        return JSONResponse({"success": False, "error": "Not authenticated"}, status_code=401)

    user_id = payload.get("user_id")
    if not user_id:
        return JSONResponse({"success": False, "error": "Invalid session"}, status_code=401)

    import uuid
    user = await db.scalar(select(User).where(User.id == uuid.UUID(user_id)))
    if not user:
        return JSONResponse({"success": False, "error": "User not found"}, status_code=404)

    profile = {
        "id": str(user.id),
        "first_name": user.first_name,
        "last_name": user.last_name or "",
        "email": user.email or "",
        "phone": user.phone or "",
        "role": user.role.value,
        "designation": user.designation or "",
        "avatar_url": user.avatar_url or "",
        "is_verified": user.is_verified,
        "created_at": user.created_at.isoformat() if user.created_at else "",
        "last_login": user.last_login.isoformat() if user.last_login else "",
    }

    # If student, add student-specific info
    student_id = payload.get("student_id")
    if student_id:
        student = await db.scalar(select(Student).where(Student.id == uuid.UUID(student_id)))
        if student:
            profile["student_login_id"] = student.student_login_id or student.admission_number or ""
            profile["class_name"] = ""
            profile["section_name"] = ""
            profile["roll_number"] = student.roll_number or ""
            profile["father_name"] = student.father_name or ""
            profile["mother_name"] = student.mother_name or ""

    return JSONResponse({"success": True, "profile": profile})


# ═══════════════════════════════════════════════════════════
# CHANGE PASSWORD
# ═══════════════════════════════════════════════════════════

@router.post("/change-password")
async def change_password(request: Request, db: AsyncSession = Depends(get_db)):
    """Change password — requires current password verification."""
    payload = _get_current_user(request)
    if not payload:
        return JSONResponse({"success": False, "error": "Not authenticated"}, status_code=401)

    body = await request.json()
    current_pwd = body.get("current_password", "")
    new_pwd = body.get("new_password", "")
    confirm_pwd = body.get("confirm_password", "")

    if not current_pwd or not new_pwd:
        return JSONResponse({"success": False, "error": "Current and new passwords are required"}, status_code=400)

    if new_pwd != confirm_pwd:
        return JSONResponse({"success": False, "error": "New passwords do not match"}, status_code=400)

    if len(new_pwd) < 6:
        return JSONResponse({"success": False, "error": "Password must be at least 6 characters"}, status_code=400)

    import uuid
    user = await db.scalar(select(User).where(User.id == uuid.UUID(payload["user_id"])))
    if not user:
        return JSONResponse({"success": False, "error": "User not found"}, status_code=404)

    if not verify_password(current_pwd, user.password_hash):
        return JSONResponse({"success": False, "error": "Current password is incorrect"}, status_code=400)

    user.password_hash = hash_password(new_pwd)
    await db.commit()

    return JSONResponse({"success": True, "message": "Password changed successfully"})


# ═══════════════════════════════════════════════════════════
# CHANGE PHONE — Send OTP to NEW phone, verify, then update
# ═══════════════════════════════════════════════════════════

@router.post("/change-phone/send-otp")
async def change_phone_send_otp(request: Request, db: AsyncSession = Depends(get_db)):
    """Send OTP to NEW phone number for verification."""
    payload = _get_current_user(request)
    if not payload:
        return JSONResponse({"success": False, "error": "Not authenticated"}, status_code=401)

    body = await request.json()
    new_phone = _clean_phone(body.get("new_phone", ""))

    if not new_phone or len(new_phone) != 10 or not new_phone.isdigit():
        return JSONResponse({"success": False, "error": "Enter a valid 10-digit phone number"}, status_code=400)

    # Check if new phone is already in use by another user
    import uuid
    existing = await db.scalar(
        select(User).where(User.phone == new_phone, User.id != uuid.UUID(payload["user_id"]), User.is_active == True)
    )
    if existing:
        return JSONResponse({"success": False, "error": "This phone number is already registered to another account"}, status_code=400)

    # Rate limit
    key = f"phone_change:{payload['user_id']}:{new_phone}"
    existing_otp = _change_otp_store.get(key)
    if existing_otp and (time() - existing_otp.get("sent_at", 0)) < 60:
        remaining = int(60 - (time() - existing_otp["sent_at"]))
        return JSONResponse({"success": False, "error": f"OTP already sent. Retry in {remaining}s."}, status_code=429)

    # Generate OTP
    otp = str(random.randint(100000, 999999))
    _change_otp_store[key] = {
        "otp": otp,
        "expires": time() + CHANGE_OTP_EXPIRY,
        "attempts": 0,
        "sent_at": time(),
        "new_phone": new_phone,
    }

    # Try to send SMS — PlatformConfig (Super Admin) takes priority, then branch config
    sms_sent = False
    sms_error = ""
    try:
        from utils.notifier import send_sms, normalize_phone, get_sms_config

        branch_id = payload.get("branch_id")
        comm_config = await get_sms_config(db, branch_id)

        if comm_config:
            msg = f"Your phone change OTP is {otp}. Valid for 5 minutes. Do not share."
            result = await send_sms(comm_config, normalize_phone(new_phone), msg, sms_type="otp")
            sms_sent = result.get("status") == "sent"
            if not sms_sent:
                sms_error = result.get("reason", result.get("error", "SMS delivery failed"))
        else:
            sms_error = "No SMS provider configured"
    except Exception as e:
        logger.warning(f"Phone change OTP SMS error: {e}")
        sms_error = str(e)

    if not sms_sent:
        logger.info(f"[PHONE-CHANGE-OTP] User: {payload['user_id']}, Phone: {new_phone}, OTP: {otp}")

    return JSONResponse({
        "success": True,
        "message": f"OTP sent to +91 ******{new_phone[-4:]}" if sms_sent else f"OTP generated for +91 ******{new_phone[-4:]}",
        "sms_sent": sms_sent,
        "sms_error": sms_error if not sms_sent else None,
        "dev_hint": otp if (settings.DEBUG or not sms_sent) else None,
    })


@router.post("/change-phone/verify")
async def change_phone_verify(request: Request, db: AsyncSession = Depends(get_db)):
    """Verify OTP and update phone number."""
    payload = _get_current_user(request)
    if not payload:
        return JSONResponse({"success": False, "error": "Not authenticated"}, status_code=401)

    body = await request.json()
    new_phone = _clean_phone(body.get("new_phone", ""))
    otp_input = str(body.get("otp", "")).strip()

    key = f"phone_change:{payload['user_id']}:{new_phone}"
    stored = _change_otp_store.get(key)

    if not stored:
        return JSONResponse({"success": False, "error": "No OTP found. Request a new one."}, status_code=400)

    if time() > stored["expires"]:
        del _change_otp_store[key]
        return JSONResponse({"success": False, "error": "OTP expired. Request a new one."}, status_code=400)

    if stored["attempts"] >= CHANGE_OTP_MAX_ATTEMPTS:
        del _change_otp_store[key]
        return JSONResponse({"success": False, "error": "Too many wrong attempts."}, status_code=429)

    if otp_input != stored["otp"]:
        stored["attempts"] += 1
        return JSONResponse({"success": False, "error": f"Wrong OTP. {CHANGE_OTP_MAX_ATTEMPTS - stored['attempts']} attempts left."}, status_code=400)

    # OTP valid — update phone
    del _change_otp_store[key]

    import uuid
    user = await db.scalar(select(User).where(User.id == uuid.UUID(payload["user_id"])))
    if not user:
        return JSONResponse({"success": False, "error": "User not found"}, status_code=404)

    old_phone = user.phone
    user.phone = new_phone
    await db.commit()

    # Re-generate token with new phone
    new_token_data = {
        "user_id": str(user.id), "email": user.email, "phone": new_phone,
        "first_name": user.first_name, "last_name": user.last_name or "",
        "role": user.role.value,
        "org_id": str(user.org_id) if user.org_id else None,
        "branch_id": str(user.branch_id) if user.branch_id else None,
        "privileges": user.privileges or {},
    }
    # Preserve student_id if present
    student_id = payload.get("student_id")
    if student_id:
        new_token_data["student_id"] = student_id
        new_token_data["student_login_id"] = payload.get("student_login_id")

    new_token = create_access_token(new_token_data)

    logger.info(f"Phone changed: user={payload['user_id']}, old={old_phone}, new={new_phone}")

    return JSONResponse({
        "success": True,
        "message": "Phone number updated successfully",
        "new_token": new_token,
    })


# ═══════════════════════════════════════════════════════════
# CHANGE EMAIL — Send OTP to NEW email (or use code), verify, update
# ═══════════════════════════════════════════════════════════

@router.post("/change-email/send-code")
async def change_email_send_code(request: Request, db: AsyncSession = Depends(get_db)):
    """Send verification code to NEW email address."""
    payload = _get_current_user(request)
    if not payload:
        return JSONResponse({"success": False, "error": "Not authenticated"}, status_code=401)

    body = await request.json()
    new_email = (body.get("new_email", "") or "").strip().lower()

    if not new_email or "@" not in new_email:
        return JSONResponse({"success": False, "error": "Enter a valid email address"}, status_code=400)

    # Check uniqueness
    import uuid
    existing = await db.scalar(
        select(User).where(User.email == new_email, User.id != uuid.UUID(payload["user_id"]), User.is_active == True)
    )
    if existing:
        return JSONResponse({"success": False, "error": "This email is already registered to another account"}, status_code=400)

    # Rate limit
    key = f"email_change:{payload['user_id']}:{new_email}"
    existing_code = _change_otp_store.get(key)
    if existing_code and (time() - existing_code.get("sent_at", 0)) < 60:
        remaining = int(60 - (time() - existing_code["sent_at"]))
        return JSONResponse({"success": False, "error": f"Code already sent. Retry in {remaining}s."}, status_code=429)

    # Generate verification code
    code = str(random.randint(100000, 999999))
    _change_otp_store[key] = {
        "otp": code,
        "expires": time() + CHANGE_OTP_EXPIRY,
        "attempts": 0,
        "sent_at": time(),
        "new_email": new_email,
    }

    # Try to send email
    email_sent = False
    try:
        from models.branch import CommunicationConfig
        from utils.notifier import send_email

        branch_id = payload.get("branch_id")
        comm_config = None
        if branch_id:
            comm_config = await db.scalar(
                select(CommunicationConfig).where(
                    CommunicationConfig.branch_id == uuid.UUID(branch_id),
                    CommunicationConfig.email_enabled == True,
                )
            )
        if not comm_config:
            comm_config = await db.scalar(
                select(CommunicationConfig).where(CommunicationConfig.email_enabled == True)
            )

        if comm_config:
            result = await send_email(
                comm_config, new_email,
                "Email Verification Code",
                f"Your email verification code is: {code}\n\nValid for 5 minutes. Do not share with anyone.",
            )
            email_sent = result.get("status") == "sent"
    except Exception as e:
        logger.warning(f"Email change code send error: {e}")

    if not email_sent:
        logger.info(f"[EMAIL-CHANGE] User: {payload['user_id']}, Email: {new_email}, Code: {code}")

    return JSONResponse({
        "success": True,
        "message": f"Verification code sent to {new_email[:3]}***@{new_email.split('@')[1] if '@' in new_email else '...'}",
        "email_sent": email_sent,
        "dev_hint": code if settings.DEBUG else None,
    })


@router.post("/change-email/verify")
async def change_email_verify(request: Request, db: AsyncSession = Depends(get_db)):
    """Verify code and update email."""
    payload = _get_current_user(request)
    if not payload:
        return JSONResponse({"success": False, "error": "Not authenticated"}, status_code=401)

    body = await request.json()
    new_email = (body.get("new_email", "") or "").strip().lower()
    code_input = str(body.get("code", "")).strip()

    key = f"email_change:{payload['user_id']}:{new_email}"
    stored = _change_otp_store.get(key)

    if not stored:
        return JSONResponse({"success": False, "error": "No code found. Request a new one."}, status_code=400)

    if time() > stored["expires"]:
        del _change_otp_store[key]
        return JSONResponse({"success": False, "error": "Code expired. Request a new one."}, status_code=400)

    if stored["attempts"] >= CHANGE_OTP_MAX_ATTEMPTS:
        del _change_otp_store[key]
        return JSONResponse({"success": False, "error": "Too many wrong attempts."}, status_code=429)

    if code_input != stored["otp"]:
        stored["attempts"] += 1
        return JSONResponse({"success": False, "error": f"Wrong code. {CHANGE_OTP_MAX_ATTEMPTS - stored['attempts']} attempts left."}, status_code=400)

    # Code valid — update email
    del _change_otp_store[key]

    import uuid
    user = await db.scalar(select(User).where(User.id == uuid.UUID(payload["user_id"])))
    if not user:
        return JSONResponse({"success": False, "error": "User not found"}, status_code=404)

    old_email = user.email
    user.email = new_email
    user.is_verified = True
    await db.commit()

    # Re-generate token with new email
    new_token_data = {
        "user_id": str(user.id), "email": new_email, "phone": user.phone,
        "first_name": user.first_name, "last_name": user.last_name or "",
        "role": user.role.value,
        "org_id": str(user.org_id) if user.org_id else None,
        "branch_id": str(user.branch_id) if user.branch_id else None,
        "privileges": user.privileges or {},
    }
    student_id = payload.get("student_id")
    if student_id:
        new_token_data["student_id"] = student_id
        new_token_data["student_login_id"] = payload.get("student_login_id")

    new_token = create_access_token(new_token_data)

    logger.info(f"Email changed: user={payload['user_id']}, old={old_email}, new={new_email}")

    return JSONResponse({
        "success": True,
        "message": "Email updated successfully",
        "new_token": new_token,
    })


# ═══════════════════════════════════════════════════════════
# PROFILE SWITCHER — Get all profiles for current phone/email
# ═══════════════════════════════════════════════════════════

@router.get("/profiles")
async def get_all_profiles(request: Request, db: AsyncSession = Depends(get_db)):
    """Get all user profiles linked to current user's phone/email (for profile switcher)."""
    payload = _get_current_user(request)
    if not payload:
        return JSONResponse({"success": False, "error": "Not authenticated"}, status_code=401)

    phone = payload.get("phone")
    email = payload.get("email")
    current_user_id = payload.get("user_id")

    if not phone and not email:
        return JSONResponse({"success": True, "profiles": [], "has_multiple": False})

    import uuid

    # Find all active users with same phone or email
    conditions = []
    if phone:
        conditions.append(User.phone == phone)
    if email:
        conditions.append(User.email == email)

    users = (await db.execute(
        select(User).where(or_(*conditions), User.is_active == True)
    )).scalars().all()

    # Also check student parent phones
    parent_students = []
    if phone:
        parent_students = (await db.execute(
            select(Student).where(
                Student.is_active == True,
                or_(
                    Student.father_phone == phone,
                    Student.mother_phone == phone,
                    Student.guardian_phone == phone,
                )
            )
        )).scalars().all()

    profiles = []
    seen_ids = set()

    for u in users:
        if str(u.id) in seen_ids:
            continue
        seen_ids.add(str(u.id))
        role_label = u.role.value.replace("_", " ").title()
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
        from routes.auth import get_dashboard_url
        profiles.append({
            "user_id": str(u.id),
            "name": f"{u.first_name} {u.last_name or ''}".strip(),
            "role": role_label,
            "detail": u.designation or role_label,
            "is_current": str(u.id) == current_user_id,
            "token": create_access_token(token_data),
            "redirect": get_dashboard_url(u.role.value),
        })

    for s in parent_students:
        # Skip if student's user is already in the list
        if s.user_id and str(s.user_id) in seen_ids:
            continue

        child_name = f"{s.first_name} {s.last_name or ''}".strip()
        login_id = s.student_login_id or s.admission_number or ""

        if s.user_id:
            user = await db.scalar(select(User).where(User.id == s.user_id, User.is_active == True))
            if not user:
                continue
            seen_ids.add(str(user.id))
            token_data = {
                "user_id": str(user.id), "email": user.email,
                "phone": user.phone or phone,
                "first_name": s.first_name, "last_name": s.last_name or "",
                "role": "student",
                "org_id": str(user.org_id) if user.org_id else None,
                "branch_id": str(s.branch_id) if s.branch_id else None,
                "student_id": str(s.id),
                "student_login_id": login_id,
                "privileges": user.privileges or {},
            }
        else:
            token_data = {
                "user_id": None, "phone": phone,
                "first_name": s.first_name, "last_name": s.last_name or "",
                "role": "student",
                "branch_id": str(s.branch_id) if s.branch_id else None,
                "student_id": str(s.id),
                "student_login_id": login_id,
                "privileges": {},
            }

        profiles.append({
            "user_id": str(s.user_id) if s.user_id else f"student:{s.id}",
            "name": child_name,
            "role": "Student",
            "detail": f"Student · {login_id}",
            "is_current": (str(s.user_id) == current_user_id) if s.user_id else False,
            "token": create_access_token(token_data),
            "redirect": "/student/dashboard",
        })

    return JSONResponse({
        "success": True,
        "profiles": profiles,
        "has_multiple": len(profiles) > 1,
    })
