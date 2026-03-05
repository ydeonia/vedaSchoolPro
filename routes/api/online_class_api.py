"""
Online Class API — Schedule, manage, join online classes (Google Meet / Zoom / Teams).
Supports per-teacher OAuth (teachers connect their own Google/Teams accounts)
and branch-level Zoom S2S credentials.
"""
import uuid
import logging
from datetime import date, datetime, time, timedelta
from typing import Optional
from fastapi import APIRouter, Request, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_, desc
from sqlalchemy.orm import selectinload
from database import get_db
from models.user import UserRole
from models.online_class import (
    OnlinePlatformConfig, TeacherPlatformToken, OnlineClass, LectureAttendance,
    OnlinePlatform, OnlineClassStatus, LectureAttendanceType,
)
from models.teacher import Teacher
from models.student import Student
from models.academic import Class, Section, Subject
from utils.permissions import require_role, require_privilege, get_current_user
from utils.crypto import encrypt_value, decrypt_value

logger = logging.getLogger("online_class_api")

router = APIRouter(prefix="/api/online-class", tags=["Online Classes"])


# ═══════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════

def get_branch_id(request: Request) -> uuid.UUID:
    return uuid.UUID(request.state.user.get("branch_id"))


def get_user_id(request: Request) -> uuid.UUID:
    return uuid.UUID(request.state.user.get("user_id"))


async def _get_platform_config(db: AsyncSession, branch_id: uuid.UUID) -> OnlinePlatformConfig:
    result = await db.execute(
        select(OnlinePlatformConfig).where(OnlinePlatformConfig.branch_id == branch_id)
    )
    return result.scalar_one_or_none()


async def _get_teacher_token(db: AsyncSession, teacher_id: uuid.UUID, platform: OnlinePlatform) -> Optional[TeacherPlatformToken]:
    """Get teacher's personal OAuth token for a platform."""
    result = await db.execute(
        select(TeacherPlatformToken).where(
            TeacherPlatformToken.teacher_id == teacher_id,
            TeacherPlatformToken.platform == platform,
            TeacherPlatformToken.is_active == True,
        )
    )
    return result.scalar_one_or_none()


async def _get_teacher_by_user(db: AsyncSession, user_id: uuid.UUID) -> Optional[Teacher]:
    """Get active teacher profile by user_id."""
    return (await db.execute(
        select(Teacher).where(Teacher.user_id == user_id, Teacher.is_active == True)
    )).scalar_one_or_none()


async def _notify_students(db, branch_id, class_id, section_id, title, message, action_url="/student/online-classes"):
    """Send notification to all students in the class/section."""
    try:
        from utils.notifier import send_notification
        query = select(Student).where(
            Student.branch_id == branch_id,
            Student.class_id == class_id,
            Student.is_active == True,
        )
        if section_id:
            query = query.where(Student.section_id == section_id)
        students = (await db.execute(query)).scalars().all()
        for student in students:
            if student.user_id:
                try:
                    await send_notification(
                        db, str(branch_id),
                        user_id=str(student.user_id),
                        notification_type="online_class",
                        title=title,
                        message=message,
                        channels=["in_app"],
                        priority="normal",
                        data={"action_url": action_url},
                    )
                except Exception:
                    pass
    except Exception as e:
        logger.error(f"Notification failed: {e}")


# ═══════════════════════════════════════════════════════════
# TEACHER OAUTH — Per-teacher Google/Teams connection
# Each teacher connects their OWN account independently.
# ═══════════════════════════════════════════════════════════

@router.get("/teacher/oauth/google/start")
@require_role(UserRole.TEACHER, UserRole.SCHOOL_ADMIN)
async def teacher_google_oauth_start(request: Request, db: AsyncSession = Depends(get_db)):
    """Redirect teacher to Google OAuth consent — connects their own Google account."""
    from config import settings
    user_id = get_user_id(request)
    branch_id = get_branch_id(request)

    if not settings.GOOGLE_CLIENT_ID:
        raise HTTPException(400, "Google Client ID not configured. Ask admin to set GOOGLE_CLIENT_ID in server settings.")

    teacher = await _get_teacher_by_user(db, user_id)
    if not teacher:
        raise HTTPException(400, "Teacher profile not found")

    redirect_uri = f"{request.base_url}api/online-class/teacher/oauth/google/callback"
    scopes = "https://www.googleapis.com/auth/calendar.events"
    # Encode teacher_id + branch_id in state
    state = f"{teacher.id}|{branch_id}|{user_id}"

    url = (
        f"https://accounts.google.com/o/oauth2/v2/auth"
        f"?client_id={settings.GOOGLE_CLIENT_ID}"
        f"&redirect_uri={redirect_uri}"
        f"&response_type=code"
        f"&scope={scopes}"
        f"&access_type=offline"
        f"&prompt=consent"
        f"&state={state}"
    )
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url)


@router.get("/teacher/oauth/google/callback")
async def teacher_google_oauth_callback(
    request: Request,
    code: str = None,
    state: str = None,
    error: str = None,
    db: AsyncSession = Depends(get_db),
):
    """Handle Google OAuth callback for teacher — save tokens in TeacherPlatformToken."""
    from fastapi.responses import RedirectResponse
    if error:
        return RedirectResponse(f"/teacher/online-classes?error=google_denied")

    if not code or not state:
        return RedirectResponse(f"/teacher/online-classes?error=missing_code")

    from config import settings
    from utils.http_client import get_http_client

    # Parse state: teacher_id|branch_id|user_id
    parts = state.split("|")
    if len(parts) != 3:
        return RedirectResponse(f"/teacher/online-classes?error=invalid_state")

    teacher_id = uuid.UUID(parts[0])
    branch_id = uuid.UUID(parts[1])
    user_id = uuid.UUID(parts[2])

    redirect_uri = f"{request.base_url}api/online-class/teacher/oauth/google/callback"

    client = await get_http_client()
    resp = await client.post("https://oauth2.googleapis.com/token", data={
        "code": code,
        "client_id": settings.GOOGLE_CLIENT_ID,
        "client_secret": settings.GOOGLE_CLIENT_SECRET,
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code",
    })
    data = resp.json()

    if resp.status_code != 200:
        logger.error(f"Teacher Google OAuth token exchange failed: {data}")
        return RedirectResponse(f"/teacher/online-classes?error=google_token_failed")

    access_token = data["access_token"]
    refresh_token = data.get("refresh_token", "")
    expires_in = data.get("expires_in", 3600)

    # Get teacher's Google email
    user_resp = await client.get(
        "https://www.googleapis.com/oauth2/v2/userinfo",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    email = user_resp.json().get("email", "") if user_resp.status_code == 200 else ""

    # Upsert TeacherPlatformToken
    existing = (await db.execute(
        select(TeacherPlatformToken).where(
            TeacherPlatformToken.teacher_id == teacher_id,
            TeacherPlatformToken.platform == OnlinePlatform.GOOGLE_MEET,
        )
    )).scalar_one_or_none()

    if existing:
        existing.access_token = encrypt_value(access_token)
        existing.refresh_token = encrypt_value(refresh_token)
        existing.token_expiry = datetime.utcnow() + timedelta(seconds=expires_in)
        existing.account_email = email
        existing.error = None
        existing.last_verified = datetime.utcnow()
        existing.is_active = True
    else:
        tok = TeacherPlatformToken(
            teacher_id=teacher_id,
            user_id=user_id,
            branch_id=branch_id,
            platform=OnlinePlatform.GOOGLE_MEET,
            access_token=encrypt_value(access_token),
            refresh_token=encrypt_value(refresh_token),
            token_expiry=datetime.utcnow() + timedelta(seconds=expires_in),
            account_email=email,
        )
        db.add(tok)

    await db.commit()
    return RedirectResponse(f"/teacher/online-classes?success=google_connected")


@router.get("/teacher/oauth/teams/start")
@require_role(UserRole.TEACHER, UserRole.SCHOOL_ADMIN)
async def teacher_teams_oauth_start(request: Request, db: AsyncSession = Depends(get_db)):
    """Redirect teacher to Microsoft OAuth consent — connects their own Teams account."""
    from config import settings
    user_id = get_user_id(request)
    branch_id = get_branch_id(request)

    if not settings.TEAMS_CLIENT_ID:
        raise HTTPException(400, "Teams Client ID not configured. Ask admin to set TEAMS_CLIENT_ID in server settings.")

    teacher = await _get_teacher_by_user(db, user_id)
    if not teacher:
        raise HTTPException(400, "Teacher profile not found")

    redirect_uri = f"{request.base_url}api/online-class/teacher/oauth/teams/callback"
    scopes = "OnlineMeetings.ReadWrite offline_access"
    state = f"{teacher.id}|{branch_id}|{user_id}"

    url = (
        f"https://login.microsoftonline.com/common/oauth2/v2.0/authorize"
        f"?client_id={settings.TEAMS_CLIENT_ID}"
        f"&redirect_uri={redirect_uri}"
        f"&response_type=code"
        f"&scope={scopes}"
        f"&state={state}"
    )
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url)


@router.get("/teacher/oauth/teams/callback")
async def teacher_teams_oauth_callback(
    request: Request,
    code: str = None,
    state: str = None,
    error: str = None,
    db: AsyncSession = Depends(get_db),
):
    """Handle Teams OAuth callback for teacher — save tokens in TeacherPlatformToken."""
    from fastapi.responses import RedirectResponse
    if error:
        return RedirectResponse(f"/teacher/online-classes?error=teams_denied")

    if not code or not state:
        return RedirectResponse(f"/teacher/online-classes?error=missing_code")

    from config import settings
    from utils.http_client import get_http_client

    parts = state.split("|")
    if len(parts) != 3:
        return RedirectResponse(f"/teacher/online-classes?error=invalid_state")

    teacher_id = uuid.UUID(parts[0])
    branch_id = uuid.UUID(parts[1])
    user_id = uuid.UUID(parts[2])

    redirect_uri = f"{request.base_url}api/online-class/teacher/oauth/teams/callback"

    client = await get_http_client()
    resp = await client.post(
        "https://login.microsoftonline.com/common/oauth2/v2.0/token",
        data={
            "code": code,
            "client_id": settings.TEAMS_CLIENT_ID,
            "client_secret": settings.TEAMS_CLIENT_SECRET,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
            "scope": "OnlineMeetings.ReadWrite offline_access",
        },
    )
    data = resp.json()

    if resp.status_code != 200:
        logger.error(f"Teacher Teams OAuth token exchange failed: {data}")
        return RedirectResponse(f"/teacher/online-classes?error=teams_token_failed")

    # Get email via Graph /me
    me_resp = await client.get(
        "https://graph.microsoft.com/v1.0/me",
        headers={"Authorization": f"Bearer {data['access_token']}"},
    )
    email = ""
    if me_resp.status_code == 200:
        me_data = me_resp.json()
        email = me_data.get("mail") or me_data.get("userPrincipalName", "")

    # Upsert TeacherPlatformToken
    existing = (await db.execute(
        select(TeacherPlatformToken).where(
            TeacherPlatformToken.teacher_id == teacher_id,
            TeacherPlatformToken.platform == OnlinePlatform.TEAMS,
        )
    )).scalar_one_or_none()

    if existing:
        existing.access_token = encrypt_value(data["access_token"])
        existing.refresh_token = encrypt_value(data.get("refresh_token", ""))
        existing.token_expiry = datetime.utcnow() + timedelta(seconds=data.get("expires_in", 3600))
        existing.tenant_id = data.get("tenant_id", "common")
        existing.account_email = email
        existing.error = None
        existing.last_verified = datetime.utcnow()
        existing.is_active = True
    else:
        tok = TeacherPlatformToken(
            teacher_id=teacher_id,
            user_id=user_id,
            branch_id=branch_id,
            platform=OnlinePlatform.TEAMS,
            access_token=encrypt_value(data["access_token"]),
            refresh_token=encrypt_value(data.get("refresh_token", "")),
            token_expiry=datetime.utcnow() + timedelta(seconds=data.get("expires_in", 3600)),
            tenant_id=data.get("tenant_id", "common"),
            account_email=email,
        )
        db.add(tok)

    await db.commit()
    return RedirectResponse(f"/teacher/online-classes?success=teams_connected")


@router.get("/teacher/platform-tokens")
@require_role(UserRole.TEACHER, UserRole.SCHOOL_ADMIN)
async def get_teacher_tokens(request: Request, db: AsyncSession = Depends(get_db)):
    """Get teacher's connected platform accounts + branch-level Zoom status."""
    user_id = get_user_id(request)
    branch_id = get_branch_id(request)

    teacher = await _get_teacher_by_user(db, user_id)
    if not teacher:
        return {"tokens": [], "zoom_available": False}

    # Teacher's own tokens
    tokens = (await db.execute(
        select(TeacherPlatformToken).where(
            TeacherPlatformToken.teacher_id == teacher.id,
            TeacherPlatformToken.is_active == True,
        )
    )).scalars().all()

    # Branch-level Zoom status
    config = await _get_platform_config(db, branch_id)
    zoom_available = config and config.zoom_enabled and not config.zoom_error

    result = []
    for t in tokens:
        result.append({
            "platform": t.platform.value,
            "account_email": t.account_email or "",
            "healthy": not t.error,
            "error": t.error,
            "last_verified": t.last_verified.isoformat() if t.last_verified else None,
        })

    return {
        "tokens": result,
        "zoom_available": zoom_available,
        "zoom_error": config.zoom_error if config and config.zoom_enabled else None,
    }


@router.post("/teacher/disconnect/{platform}")
@require_role(UserRole.TEACHER, UserRole.SCHOOL_ADMIN)
async def teacher_disconnect_platform(platform: str, request: Request, db: AsyncSession = Depends(get_db)):
    """Teacher disconnects their own Google/Teams account."""
    user_id = get_user_id(request)
    teacher = await _get_teacher_by_user(db, user_id)
    if not teacher:
        raise HTTPException(400, "Teacher profile not found")

    platform_enum = OnlinePlatform.GOOGLE_MEET if platform == "google" else OnlinePlatform.TEAMS
    tok = await _get_teacher_token(db, teacher.id, platform_enum)
    if tok:
        tok.is_active = False
        tok.access_token = None
        tok.refresh_token = None
        tok.token_expiry = None
        tok.account_email = None
        await db.commit()

    return {"status": "ok"}


# ═══════════════════════════════════════════════════════════
# ADMIN OAUTH — kept as optional fallback for small schools
# that prefer single admin-level auth
# ═══════════════════════════════════════════════════════════

@router.get("/oauth/google/start")
@require_privilege("online_classes")
async def google_oauth_start(request: Request, db: AsyncSession = Depends(get_db)):
    """Redirect admin to Google OAuth consent screen (admin-level fallback)."""
    from config import settings
    branch_id = get_branch_id(request)

    if not settings.GOOGLE_CLIENT_ID:
        raise HTTPException(400, "Google Client ID not configured in server settings")

    redirect_uri = f"{request.base_url}api/online-class/oauth/google/callback"
    scopes = "https://www.googleapis.com/auth/calendar.events"
    state = str(branch_id)

    url = (
        f"https://accounts.google.com/o/oauth2/v2/auth"
        f"?client_id={settings.GOOGLE_CLIENT_ID}"
        f"&redirect_uri={redirect_uri}"
        f"&response_type=code"
        f"&scope={scopes}"
        f"&access_type=offline"
        f"&prompt=consent"
        f"&state={state}"
    )
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url)


@router.get("/oauth/google/callback")
async def google_oauth_callback(
    request: Request,
    code: str = None,
    state: str = None,
    error: str = None,
    db: AsyncSession = Depends(get_db),
):
    """Handle Google OAuth callback — exchange code for tokens (admin-level)."""
    from fastapi.responses import RedirectResponse
    if error:
        return RedirectResponse(f"/school/online-classes?error=google_denied")

    if not code or not state:
        return RedirectResponse(f"/school/online-classes?error=missing_code")

    from config import settings
    from utils.http_client import get_http_client

    branch_id = uuid.UUID(state)
    redirect_uri = f"{request.base_url}api/online-class/oauth/google/callback"

    client = await get_http_client()
    resp = await client.post("https://oauth2.googleapis.com/token", data={
        "code": code,
        "client_id": settings.GOOGLE_CLIENT_ID,
        "client_secret": settings.GOOGLE_CLIENT_SECRET,
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code",
    })
    data = resp.json()

    if resp.status_code != 200:
        logger.error(f"Google OAuth token exchange failed: {data}")
        return RedirectResponse(f"/school/online-classes?error=google_token_failed")

    access_token = data["access_token"]
    refresh_token = data.get("refresh_token", "")
    expires_in = data.get("expires_in", 3600)

    # Get user email
    user_resp = await client.get(
        "https://www.googleapis.com/oauth2/v2/userinfo",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    email = user_resp.json().get("email", "") if user_resp.status_code == 200 else ""

    # Save to config
    config = await _get_platform_config(db, branch_id)
    if not config:
        config = OnlinePlatformConfig(branch_id=branch_id)
        db.add(config)

    config.google_enabled = True
    config.google_access_token = encrypt_value(access_token)
    config.google_refresh_token = encrypt_value(refresh_token)
    config.google_token_expiry = datetime.utcnow() + timedelta(seconds=expires_in)
    config.google_email = email
    config.google_error = None
    config.google_last_verified = datetime.utcnow()
    await db.commit()

    return RedirectResponse(f"/school/online-classes?success=google_connected")


@router.get("/oauth/teams/start")
@require_privilege("online_classes")
async def teams_oauth_start(request: Request, db: AsyncSession = Depends(get_db)):
    """Redirect admin to Microsoft OAuth consent screen (admin-level fallback)."""
    from config import settings
    branch_id = get_branch_id(request)

    if not settings.TEAMS_CLIENT_ID:
        raise HTTPException(400, "Teams Client ID not configured in server settings")

    redirect_uri = f"{request.base_url}api/online-class/oauth/teams/callback"
    scopes = "OnlineMeetings.ReadWrite offline_access"
    state = str(branch_id)

    url = (
        f"https://login.microsoftonline.com/common/oauth2/v2.0/authorize"
        f"?client_id={settings.TEAMS_CLIENT_ID}"
        f"&redirect_uri={redirect_uri}"
        f"&response_type=code"
        f"&scope={scopes}"
        f"&state={state}"
    )
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url)


@router.get("/oauth/teams/callback")
async def teams_oauth_callback(
    request: Request,
    code: str = None,
    state: str = None,
    error: str = None,
    db: AsyncSession = Depends(get_db),
):
    """Handle Microsoft Teams OAuth callback (admin-level fallback)."""
    from fastapi.responses import RedirectResponse
    if error:
        return RedirectResponse(f"/school/online-classes?error=teams_denied")

    if not code or not state:
        return RedirectResponse(f"/school/online-classes?error=missing_code")

    from config import settings
    from utils.http_client import get_http_client

    branch_id = uuid.UUID(state)
    redirect_uri = f"{request.base_url}api/online-class/oauth/teams/callback"

    client = await get_http_client()
    resp = await client.post(
        "https://login.microsoftonline.com/common/oauth2/v2.0/token",
        data={
            "code": code,
            "client_id": settings.TEAMS_CLIENT_ID,
            "client_secret": settings.TEAMS_CLIENT_SECRET,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
            "scope": "OnlineMeetings.ReadWrite offline_access",
        },
    )
    data = resp.json()

    if resp.status_code != 200:
        logger.error(f"Teams OAuth token exchange failed: {data}")
        return RedirectResponse(f"/school/online-classes?error=teams_token_failed")

    config = await _get_platform_config(db, branch_id)
    if not config:
        config = OnlinePlatformConfig(branch_id=branch_id)
        db.add(config)

    config.teams_enabled = True
    config.teams_access_token = encrypt_value(data["access_token"])
    config.teams_refresh_token = encrypt_value(data.get("refresh_token", ""))
    config.teams_token_expiry = datetime.utcnow() + timedelta(seconds=data.get("expires_in", 3600))
    config.teams_tenant_id = data.get("tenant_id", "common")
    config.teams_error = None
    config.teams_last_verified = datetime.utcnow()
    await db.commit()

    return RedirectResponse(f"/school/online-classes?success=teams_connected")


# ═══════════════════════════════════════════════════════════
# ADMIN CONFIG
# ═══════════════════════════════════════════════════════════

@router.get("/config")
@require_privilege("online_classes")
async def get_config(request: Request, db: AsyncSession = Depends(get_db)):
    """Get current platform configuration for branch."""
    branch_id = get_branch_id(request)
    config = await _get_platform_config(db, branch_id)

    if not config:
        return {
            "google_enabled": False, "google_email": "",
            "zoom_enabled": False,
            "teams_enabled": False,
            "default_platform": "google_meet",
            "google_healthy": False, "google_error": None,
            "zoom_healthy": False, "zoom_error": None,
            "teams_healthy": False, "teams_error": None,
            "teacher_connections": [],
        }

    # Count how many teachers have connected per platform
    teacher_counts = {}
    for platform in [OnlinePlatform.GOOGLE_MEET, OnlinePlatform.TEAMS]:
        count = (await db.execute(
            select(func.count()).select_from(TeacherPlatformToken).where(
                TeacherPlatformToken.branch_id == branch_id,
                TeacherPlatformToken.platform == platform,
                TeacherPlatformToken.is_active == True,
            )
        )).scalar() or 0
        teacher_counts[platform.value] = count

    return {
        "google_enabled": config.google_enabled,
        "google_email": config.google_email or "",
        "google_healthy": config.google_enabled and not config.google_error,
        "google_error": config.google_error,
        "google_last_verified": config.google_last_verified.isoformat() if config.google_last_verified else None,
        "zoom_enabled": config.zoom_enabled,
        "zoom_account_id": bool(config.zoom_account_id),
        "zoom_healthy": config.zoom_enabled and not config.zoom_error,
        "zoom_error": config.zoom_error,
        "zoom_last_verified": config.zoom_last_verified.isoformat() if config.zoom_last_verified else None,
        "teams_enabled": config.teams_enabled,
        "teams_healthy": config.teams_enabled and not config.teams_error,
        "teams_error": config.teams_error,
        "teams_last_verified": config.teams_last_verified.isoformat() if config.teams_last_verified else None,
        "default_platform": config.default_platform.value if config.default_platform else "google_meet",
        "teacher_google_count": teacher_counts.get("google_meet", 0),
        "teacher_teams_count": teacher_counts.get("teams", 0),
    }


@router.post("/config")
@require_privilege("online_classes")
async def save_config(request: Request, db: AsyncSession = Depends(get_db)):
    """Save platform config (default platform, Zoom creds)."""
    branch_id = get_branch_id(request)
    data = await request.json()

    config = await _get_platform_config(db, branch_id)
    if not config:
        config = OnlinePlatformConfig(branch_id=branch_id)
        db.add(config)

    # Default platform
    if "default_platform" in data:
        config.default_platform = OnlinePlatform(data["default_platform"])

    # Zoom S2S credentials
    if "zoom_account_id" in data and data["zoom_account_id"]:
        config.zoom_enabled = True
        config.zoom_account_id = encrypt_value(data["zoom_account_id"])
        config.zoom_client_id = encrypt_value(data.get("zoom_client_id", ""))
        config.zoom_client_secret = encrypt_value(data.get("zoom_client_secret", ""))

    await db.commit()
    return {"status": "ok"}


@router.post("/config/disconnect/{platform}")
@require_privilege("online_classes")
async def disconnect_platform(platform: str, request: Request, db: AsyncSession = Depends(get_db)):
    """Disconnect a platform — clear admin-level tokens."""
    branch_id = get_branch_id(request)
    config = await _get_platform_config(db, branch_id)
    if not config:
        return {"status": "ok"}

    if platform == "google":
        config.google_enabled = False
        config.google_access_token = None
        config.google_refresh_token = None
        config.google_token_expiry = None
        config.google_email = None
        config.google_error = None
    elif platform == "zoom":
        config.zoom_enabled = False
        config.zoom_account_id = None
        config.zoom_client_id = None
        config.zoom_client_secret = None
        config.zoom_error = None
    elif platform == "teams":
        config.teams_enabled = False
        config.teams_access_token = None
        config.teams_refresh_token = None
        config.teams_token_expiry = None
        config.teams_tenant_id = None
        config.teams_error = None

    await db.commit()
    return {"status": "ok"}


@router.post("/config/health-check")
@require_privilege("online_classes")
async def manual_health_check(request: Request, db: AsyncSession = Depends(get_db)):
    """Admin manually triggers platform health check — returns live status."""
    branch_id = get_branch_id(request)
    config = await _get_platform_config(db, branch_id)
    if not config:
        return {"google": None, "zoom": None, "teams": None}

    from utils.online_meeting import check_platform_health

    results = {}
    now = datetime.utcnow()

    if config.google_enabled:
        r = await check_platform_health(config, "google_meet")
        config.google_last_verified = now
        config.google_error = r["error"]
        results["google"] = r
    else:
        results["google"] = None

    if config.zoom_enabled:
        r = await check_platform_health(config, "zoom")
        config.zoom_last_verified = now
        config.zoom_error = r["error"]
        results["zoom"] = r
    else:
        results["zoom"] = None

    if config.teams_enabled:
        r = await check_platform_health(config, "teams")
        config.teams_last_verified = now
        config.teams_error = r["error"]
        results["teams"] = r
    else:
        results["teams"] = None

    await db.commit()
    return results


@router.get("/platform-status")
@require_role(UserRole.TEACHER, UserRole.SCHOOL_ADMIN)
async def platform_status(request: Request, db: AsyncSession = Depends(get_db)):
    """Teacher-facing: which platforms are available (teacher's own + branch Zoom)?"""
    user_id = get_user_id(request)
    branch_id = get_branch_id(request)

    teacher = await _get_teacher_by_user(db, user_id)
    config = await _get_platform_config(db, branch_id)

    platforms = []

    if teacher:
        # Teacher's own Google Meet token
        g_tok = await _get_teacher_token(db, teacher.id, OnlinePlatform.GOOGLE_MEET)
        if g_tok:
            platforms.append({
                "key": "google_meet", "name": "Google Meet",
                "healthy": not g_tok.error,
                "source": "your_account",
                "email": g_tok.account_email or "",
                "error_msg": f"Your Google session expired. Reconnect in My Connections." if g_tok.error else None,
            })
        elif config and config.google_enabled:
            # Fall back to admin-level
            platforms.append({
                "key": "google_meet", "name": "Google Meet",
                "healthy": not config.google_error,
                "source": "school_admin",
                "email": config.google_email or "",
                "error_msg": "School Google Meet session expired. Ask admin to reconnect." if config.google_error else None,
            })

        # Teacher's own Teams token
        t_tok = await _get_teacher_token(db, teacher.id, OnlinePlatform.TEAMS)
        if t_tok:
            platforms.append({
                "key": "teams", "name": "Microsoft Teams",
                "healthy": not t_tok.error,
                "source": "your_account",
                "email": t_tok.account_email or "",
                "error_msg": f"Your Teams session expired. Reconnect in My Connections." if t_tok.error else None,
            })
        elif config and config.teams_enabled:
            platforms.append({
                "key": "teams", "name": "Microsoft Teams",
                "healthy": not config.teams_error,
                "source": "school_admin",
                "email": "",
                "error_msg": "School Teams session expired. Ask admin to reconnect." if config.teams_error else None,
            })

    # Branch-level Zoom (always school-level)
    if config and config.zoom_enabled:
        platforms.append({
            "key": "zoom", "name": "Zoom",
            "healthy": not config.zoom_error,
            "source": "school_admin",
            "email": "",
            "error_msg": "Zoom credentials invalid. Ask admin to update." if config.zoom_error else None,
        })

    return {
        "configured": len(platforms) > 0,
        "default_platform": config.default_platform.value if config and config.default_platform else "google_meet",
        "platforms": platforms,
    }


# ═══════════════════════════════════════════════════════════
# TEACHER — CREATE / MANAGE CLASSES
# ═══════════════════════════════════════════════════════════

@router.post("/create")
@require_role(UserRole.TEACHER, UserRole.SCHOOL_ADMIN)
async def create_online_class(request: Request, db: AsyncSession = Depends(get_db)):
    """
    Create an online class + auto-generate meeting link.
    Priority: teacher's own token → admin-level config → manual link fallback.
    """
    branch_id = get_branch_id(request)
    user_id = get_user_id(request)
    data = await request.json()

    teacher = await _get_teacher_by_user(db, user_id)
    if not teacher:
        raise HTTPException(400, "Teacher profile not found")

    # Parse date/time
    scheduled_date = date.fromisoformat(data["date"])
    start_time = time.fromisoformat(data["start_time"])
    end_time = time.fromisoformat(data["end_time"]) if data.get("end_time") else None
    duration = data.get("duration_minutes", 45)

    platform_str = data.get("platform", "google_meet")
    platform = OnlinePlatform(platform_str)

    # Create class record
    online_class = OnlineClass(
        branch_id=branch_id,
        teacher_id=teacher.id,
        class_id=uuid.UUID(data["class_id"]),
        section_id=uuid.UUID(data["section_id"]) if data.get("section_id") else None,
        subject_id=uuid.UUID(data["subject_id"]) if data.get("subject_id") else None,
        title=data["title"],
        description=data.get("description", ""),
        scheduled_date=scheduled_date,
        start_time=start_time,
        end_time=end_time,
        duration_minutes=duration,
        platform=platform,
        status=OnlineClassStatus.SCHEDULED,
    )

    # Try to auto-generate meeting link
    # Priority: 1) Teacher's own token, 2) Admin-level config, 3) Manual link
    link_error = None
    link_generated = False
    config = await _get_platform_config(db, branch_id)

    start_dt = datetime.combine(scheduled_date, start_time)
    end_dt = datetime.combine(scheduled_date, end_time) if end_time else None

    if platform_str in ("google_meet", "teams"):
        # Try teacher's own token first
        teacher_tok = await _get_teacher_token(db, teacher.id, platform)
        if teacher_tok and not teacher_tok.error:
            try:
                from utils.online_meeting import generate_meeting_link
                result = await generate_meeting_link(
                    teacher_tok, platform_str, data["title"], start_dt, end_dt, duration
                )
                online_class.meeting_link = result.get("meeting_link", "")
                online_class.meeting_id = result.get("meeting_id", "")
                online_class.meeting_password = result.get("meeting_password", "")
                online_class.calendar_event_id = result.get("calendar_event_id", "")
                # Clear any stale error
                teacher_tok.error = None
                teacher_tok.last_verified = datetime.utcnow()
                link_generated = True
            except Exception as e:
                error_msg = str(e)
                logger.error(f"Teacher token link generation failed: {error_msg}")
                teacher_tok.error = error_msg[:500]
                link_error = f"Your {platform_str.replace('_', ' ').title()} session failed: {error_msg[:150]}. Try reconnecting in My Connections."

        # Fall back to admin-level config
        if not link_generated and config:
            prefix = platform_str.replace("_meet", "")  # google_meet → google
            platform_enabled = getattr(config, f"{prefix}_enabled", False)
            known_error = getattr(config, f"{prefix}_error", None)

            if platform_enabled and not known_error:
                try:
                    from utils.online_meeting import generate_meeting_link
                    result = await generate_meeting_link(
                        config, platform_str, data["title"], start_dt, end_dt, duration
                    )
                    online_class.meeting_link = result.get("meeting_link", "")
                    online_class.meeting_id = result.get("meeting_id", "")
                    online_class.meeting_password = result.get("meeting_password", "")
                    online_class.calendar_event_id = result.get("calendar_event_id", "")
                    setattr(config, f"{prefix}_error", None)
                    setattr(config, f"{prefix}_last_verified", datetime.utcnow())
                    link_generated = True
                    link_error = None  # Clear teacher-level error if admin fallback worked
                except Exception as e:
                    error_msg = str(e)
                    logger.error(f"Admin-level link generation failed: {error_msg}")
                    setattr(config, f"{prefix}_error", error_msg[:500])
                    if not link_error:
                        link_error = f"Failed to generate link: {error_msg[:200]}. You can paste a manual link instead."

        if not link_generated and not link_error:
            if not teacher_tok and (not config or not getattr(config, f"{platform_str.replace('_meet', '')}_enabled", False)):
                link_error = f"Connect your {platform_str.replace('_', ' ').title()} account in My Connections above, or ask admin to enable it."

    elif platform_str == "zoom":
        # Zoom is always branch-level S2S
        if config and config.zoom_enabled and not config.zoom_error:
            try:
                from utils.online_meeting import generate_meeting_link
                result = await generate_meeting_link(
                    config, platform_str, data["title"], start_dt, end_dt, duration
                )
                online_class.meeting_link = result.get("meeting_link", "")
                online_class.meeting_id = result.get("meeting_id", "")
                online_class.meeting_password = result.get("meeting_password", "")
                config.zoom_error = None
                config.zoom_last_verified = datetime.utcnow()
                link_generated = True
            except Exception as e:
                error_msg = str(e)
                logger.error(f"Zoom link generation failed: {error_msg}")
                config.zoom_error = error_msg[:500]
                link_error = f"Zoom link failed: {error_msg[:200]}. Ask admin to check Zoom credentials."
        elif config and config.zoom_enabled and config.zoom_error:
            link_error = "Zoom credentials are invalid. Ask admin to update in Platform Settings."
        else:
            link_error = "Zoom is not configured. Ask admin to add Zoom credentials in Platform Settings."
    else:
        link_error = f"No platform configured yet. Connect your account in My Connections."

    if not online_class.meeting_link:
        online_class.meeting_link = data.get("meeting_link", "")

    db.add(online_class)
    await db.commit()
    await db.refresh(online_class)

    # Notify students (only if we have a meeting link)
    if online_class.meeting_link:
        await _notify_students(
            db, branch_id, online_class.class_id, online_class.section_id,
            "Online Class Scheduled",
            f"{data['title']} on {scheduled_date.strftime('%d %b %Y')} at {start_time.strftime('%I:%M %p')}. Tap to view.",
        )

    return {
        "status": "ok",
        "id": str(online_class.id),
        "meeting_link": online_class.meeting_link,
        "meeting_password": online_class.meeting_password or "",
        "link_error": link_error,
    }


@router.get("/my-classes")
@require_role(UserRole.TEACHER, UserRole.SCHOOL_ADMIN)
async def get_my_classes(
    request: Request,
    filter: str = "upcoming",
    db: AsyncSession = Depends(get_db),
):
    """Teacher's classes — upcoming or past."""
    user_id = get_user_id(request)
    teacher = await _get_teacher_by_user(db, user_id)
    if not teacher:
        return []

    today = date.today()
    query = select(OnlineClass).where(
        OnlineClass.teacher_id == teacher.id,
        OnlineClass.is_active == True,
    ).options(
        selectinload(OnlineClass.class_),
        selectinload(OnlineClass.section),
        selectinload(OnlineClass.subject),
    )

    if filter == "upcoming":
        query = query.where(
            OnlineClass.scheduled_date >= today,
            OnlineClass.status.in_([OnlineClassStatus.SCHEDULED, OnlineClassStatus.LIVE]),
        ).order_by(OnlineClass.scheduled_date, OnlineClass.start_time)
    else:
        query = query.where(
            or_(
                OnlineClass.scheduled_date < today,
                OnlineClass.status == OnlineClassStatus.COMPLETED,
            )
        ).order_by(desc(OnlineClass.scheduled_date), desc(OnlineClass.start_time))

    classes = (await db.execute(query.limit(100))).scalars().all()

    result = []
    for c in classes:
        att_count = (await db.execute(
            select(func.count()).select_from(LectureAttendance).where(
                LectureAttendance.online_class_id == c.id,
                LectureAttendance.attendance_type == LectureAttendanceType.JOINED,
            )
        )).scalar() or 0

        result.append({
            "id": str(c.id),
            "title": c.title,
            "description": c.description or "",
            "date": c.scheduled_date.isoformat(),
            "start_time": c.start_time.strftime("%H:%M"),
            "end_time": c.end_time.strftime("%H:%M") if c.end_time else "",
            "duration_minutes": c.duration_minutes,
            "class_name": c.class_.name if c.class_ else "",
            "section_name": c.section.name if c.section else "",
            "subject_name": c.subject.name if c.subject else "",
            "platform": c.platform.value,
            "meeting_link": c.meeting_link or "",
            "meeting_password": c.meeting_password or "",
            "status": c.status.value,
            "recording_url": c.recording_url or "",
            "attended_count": att_count,
        })

    return result


@router.put("/{class_id}")
@require_role(UserRole.TEACHER, UserRole.SCHOOL_ADMIN)
async def update_online_class(class_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    """Edit an online class (title, time, description)."""
    oc = (await db.execute(
        select(OnlineClass).where(OnlineClass.id == uuid.UUID(class_id))
    )).scalar_one_or_none()
    if not oc:
        raise HTTPException(404, "Class not found")

    data = await request.json()
    if "title" in data:
        oc.title = data["title"]
    if "description" in data:
        oc.description = data["description"]
    if "date" in data:
        oc.scheduled_date = date.fromisoformat(data["date"])
    if "start_time" in data:
        oc.start_time = time.fromisoformat(data["start_time"])
    if "end_time" in data:
        oc.end_time = time.fromisoformat(data["end_time"])
    if "meeting_link" in data:
        oc.meeting_link = data["meeting_link"]

    await db.commit()
    return {"status": "ok"}


@router.delete("/{class_id}")
@require_role(UserRole.TEACHER, UserRole.SCHOOL_ADMIN)
async def cancel_online_class(class_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    """Cancel an online class."""
    oc = (await db.execute(
        select(OnlineClass).where(OnlineClass.id == uuid.UUID(class_id))
    )).scalar_one_or_none()
    if not oc:
        raise HTTPException(404, "Class not found")

    oc.status = OnlineClassStatus.CANCELLED
    await db.commit()

    # Notify students
    await _notify_students(
        db, oc.branch_id, oc.class_id, oc.section_id,
        "Class Cancelled",
        f"{oc.title} on {oc.scheduled_date.strftime('%d %b')} has been cancelled.",
    )

    return {"status": "ok"}


@router.post("/{class_id}/recording")
@require_role(UserRole.TEACHER, UserRole.SCHOOL_ADMIN)
async def add_recording(class_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    """Add recording URL to a completed class."""
    oc = (await db.execute(
        select(OnlineClass).where(OnlineClass.id == uuid.UUID(class_id))
    )).scalar_one_or_none()
    if not oc:
        raise HTTPException(404, "Class not found")

    data = await request.json()
    oc.recording_url = data.get("recording_url", "")
    oc.recording_added_at = datetime.utcnow()
    if oc.status == OnlineClassStatus.SCHEDULED:
        oc.status = OnlineClassStatus.COMPLETED
    await db.commit()

    # Notify students about recording
    await _notify_students(
        db, oc.branch_id, oc.class_id, oc.section_id,
        "Recording Available",
        f"Recording for \"{oc.title}\" is now available. Watch it anytime.",
    )

    return {"status": "ok"}


@router.post("/{class_id}/reshare")
@require_role(UserRole.TEACHER, UserRole.SCHOOL_ADMIN)
async def reshare_class(class_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    """Re-send notification to students."""
    oc = (await db.execute(
        select(OnlineClass).where(OnlineClass.id == uuid.UUID(class_id))
    )).scalar_one_or_none()
    if not oc:
        raise HTTPException(404, "Class not found")

    await _notify_students(
        db, oc.branch_id, oc.class_id, oc.section_id,
        "Online Class Reminder",
        f"{oc.title} — {oc.scheduled_date.strftime('%d %b')} at {oc.start_time.strftime('%I:%M %p')}. Join now!",
    )

    return {"status": "ok"}


@router.post("/{class_id}/complete")
@require_role(UserRole.TEACHER, UserRole.SCHOOL_ADMIN)
async def complete_class(class_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    """Mark class as completed."""
    oc = (await db.execute(
        select(OnlineClass).where(OnlineClass.id == uuid.UUID(class_id))
    )).scalar_one_or_none()
    if not oc:
        raise HTTPException(404, "Class not found")

    oc.status = OnlineClassStatus.COMPLETED
    await db.commit()
    return {"status": "ok"}


# ═══════════════════════════════════════════════════════════
# STUDENT ENDPOINTS
# ═══════════════════════════════════════════════════════════

@router.get("/upcoming")
@require_role(UserRole.STUDENT)
async def student_upcoming(request: Request, db: AsyncSession = Depends(get_db)):
    """Upcoming classes for student's class/section."""
    user_id = get_user_id(request)
    student = (await db.execute(
        select(Student).where(Student.user_id == user_id, Student.is_active == True)
    )).scalar_one_or_none()
    if not student:
        return []

    today = date.today()
    query = select(OnlineClass).where(
        OnlineClass.branch_id == student.branch_id,
        OnlineClass.class_id == student.class_id,
        OnlineClass.scheduled_date >= today,
        OnlineClass.status.in_([OnlineClassStatus.SCHEDULED, OnlineClassStatus.LIVE]),
        OnlineClass.is_active == True,
    ).options(
        selectinload(OnlineClass.teacher),
        selectinload(OnlineClass.subject),
        selectinload(OnlineClass.section),
    )
    if student.section_id:
        query = query.where(
            or_(OnlineClass.section_id == student.section_id, OnlineClass.section_id == None)
        )
    query = query.order_by(OnlineClass.scheduled_date, OnlineClass.start_time).limit(50)

    classes = (await db.execute(query)).scalars().all()

    result = []
    for c in classes:
        # Check if student already joined
        att = (await db.execute(
            select(LectureAttendance).where(
                LectureAttendance.online_class_id == c.id,
                LectureAttendance.student_id == student.id,
                LectureAttendance.attendance_type == LectureAttendanceType.JOINED,
            )
        )).scalar_one_or_none()

        result.append({
            "id": str(c.id),
            "title": c.title,
            "date": c.scheduled_date.isoformat(),
            "start_time": c.start_time.strftime("%H:%M"),
            "end_time": c.end_time.strftime("%H:%M") if c.end_time else "",
            "subject_name": c.subject.name if c.subject else "",
            "platform": c.platform.value,
            "meeting_link": c.meeting_link or "",
            "meeting_password": c.meeting_password or "",
            "status": c.status.value,
            "attended": att is not None,
            "recording_url": c.recording_url or "",
        })

    return result


@router.get("/past")
@require_role(UserRole.STUDENT)
async def student_past(
    request: Request,
    q: str = "",
    subject_id: str = "",
    db: AsyncSession = Depends(get_db),
):
    """Past lectures with search & filter."""
    user_id = get_user_id(request)
    student = (await db.execute(
        select(Student).where(Student.user_id == user_id, Student.is_active == True)
    )).scalar_one_or_none()
    if not student:
        return []

    today = date.today()
    query = select(OnlineClass).where(
        OnlineClass.branch_id == student.branch_id,
        OnlineClass.class_id == student.class_id,
        or_(
            OnlineClass.scheduled_date < today,
            OnlineClass.status == OnlineClassStatus.COMPLETED,
        ),
        OnlineClass.is_active == True,
    ).options(
        selectinload(OnlineClass.subject),
        selectinload(OnlineClass.teacher),
    )

    if student.section_id:
        query = query.where(
            or_(OnlineClass.section_id == student.section_id, OnlineClass.section_id == None)
        )
    if q:
        query = query.where(OnlineClass.title.ilike(f"%{q}%"))
    if subject_id:
        query = query.where(OnlineClass.subject_id == uuid.UUID(subject_id))

    query = query.order_by(desc(OnlineClass.scheduled_date), desc(OnlineClass.start_time)).limit(100)
    classes = (await db.execute(query)).scalars().all()

    result = []
    for c in classes:
        # Check attendance
        att_joined = (await db.execute(
            select(LectureAttendance).where(
                LectureAttendance.online_class_id == c.id,
                LectureAttendance.student_id == student.id,
                LectureAttendance.attendance_type == LectureAttendanceType.JOINED,
            )
        )).scalar_one_or_none()
        att_watched = (await db.execute(
            select(LectureAttendance).where(
                LectureAttendance.online_class_id == c.id,
                LectureAttendance.student_id == student.id,
                LectureAttendance.attendance_type == LectureAttendanceType.WATCHED,
            )
        )).scalar_one_or_none()

        result.append({
            "id": str(c.id),
            "title": c.title,
            "date": c.scheduled_date.isoformat(),
            "start_time": c.start_time.strftime("%H:%M"),
            "subject_name": c.subject.name if c.subject else "",
            "recording_url": c.recording_url or "",
            "joined": att_joined is not None,
            "watched": att_watched is not None,
        })

    return result


@router.post("/{class_id}/join")
@require_role(UserRole.STUDENT)
async def join_class(class_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    """Auto-mark attendance when student clicks Join. Returns meeting link."""
    user_id = get_user_id(request)
    student = (await db.execute(
        select(Student).where(Student.user_id == user_id, Student.is_active == True)
    )).scalar_one_or_none()
    if not student:
        raise HTTPException(400, "Student profile not found")

    oc = (await db.execute(
        select(OnlineClass).where(
            OnlineClass.id == uuid.UUID(class_id),
            OnlineClass.is_active == True,
        )
    )).scalar_one_or_none()
    if not oc:
        raise HTTPException(404, "Class not found")

    # Mark attendance (JOINED)
    existing = (await db.execute(
        select(LectureAttendance).where(
            LectureAttendance.online_class_id == oc.id,
            LectureAttendance.student_id == student.id,
            LectureAttendance.attendance_type == LectureAttendanceType.JOINED,
        )
    )).scalar_one_or_none()

    if not existing:
        att = LectureAttendance(
            online_class_id=oc.id,
            student_id=student.id,
            user_id=user_id,
            attendance_type=LectureAttendanceType.JOINED,
            ip_address=request.client.host if request.client else None,
        )
        db.add(att)
        await db.commit()

    return {
        "status": "ok",
        "meeting_link": oc.meeting_link or "",
        "meeting_password": oc.meeting_password or "",
    }


@router.post("/{class_id}/watched")
@require_role(UserRole.STUDENT)
async def mark_watched(class_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    """Mark that student watched the recording."""
    user_id = get_user_id(request)
    student = (await db.execute(
        select(Student).where(Student.user_id == user_id, Student.is_active == True)
    )).scalar_one_or_none()
    if not student:
        raise HTTPException(400, "Student profile not found")

    existing = (await db.execute(
        select(LectureAttendance).where(
            LectureAttendance.online_class_id == uuid.UUID(class_id),
            LectureAttendance.student_id == student.id,
            LectureAttendance.attendance_type == LectureAttendanceType.WATCHED,
        )
    )).scalar_one_or_none()

    if not existing:
        att = LectureAttendance(
            online_class_id=uuid.UUID(class_id),
            student_id=student.id,
            user_id=user_id,
            attendance_type=LectureAttendanceType.WATCHED,
        )
        db.add(att)
        await db.commit()

    return {"status": "ok"}


# ═══════════════════════════════════════════════════════════
# ADMIN ENDPOINTS
# ═══════════════════════════════════════════════════════════

@router.get("/all")
@require_privilege("online_classes")
async def get_all_classes(
    request: Request,
    class_id: str = "",
    status: str = "",
    date_from: str = "",
    date_to: str = "",
    db: AsyncSession = Depends(get_db),
):
    """All online classes for branch — admin view with filters."""
    branch_id = get_branch_id(request)

    query = select(OnlineClass).where(
        OnlineClass.branch_id == branch_id,
        OnlineClass.is_active == True,
    ).options(
        selectinload(OnlineClass.teacher),
        selectinload(OnlineClass.class_),
        selectinload(OnlineClass.section),
        selectinload(OnlineClass.subject),
    )

    if class_id:
        query = query.where(OnlineClass.class_id == uuid.UUID(class_id))
    if status:
        query = query.where(OnlineClass.status == OnlineClassStatus(status))
    if date_from:
        query = query.where(OnlineClass.scheduled_date >= date.fromisoformat(date_from))
    if date_to:
        query = query.where(OnlineClass.scheduled_date <= date.fromisoformat(date_to))

    query = query.order_by(desc(OnlineClass.scheduled_date), desc(OnlineClass.start_time)).limit(200)
    classes = (await db.execute(query)).scalars().all()

    result = []
    for c in classes:
        att_count = (await db.execute(
            select(func.count()).select_from(LectureAttendance).where(
                LectureAttendance.online_class_id == c.id,
                LectureAttendance.attendance_type == LectureAttendanceType.JOINED,
            )
        )).scalar() or 0

        teacher_name = ""
        if c.teacher and c.teacher.user_id:
            from models.user import User
            tu = (await db.execute(select(User).where(User.id == c.teacher.user_id))).scalar_one_or_none()
            if tu:
                teacher_name = tu.full_name

        result.append({
            "id": str(c.id),
            "title": c.title,
            "date": c.scheduled_date.isoformat(),
            "start_time": c.start_time.strftime("%H:%M"),
            "end_time": c.end_time.strftime("%H:%M") if c.end_time else "",
            "class_name": c.class_.name if c.class_ else "",
            "section_name": c.section.name if c.section else "",
            "subject_name": c.subject.name if c.subject else "",
            "teacher_name": teacher_name,
            "platform": c.platform.value,
            "meeting_link": c.meeting_link or "",
            "status": c.status.value,
            "recording_url": c.recording_url or "",
            "attended_count": att_count,
        })

    return result


@router.get("/{class_id}/attendance")
@require_privilege("online_classes")
async def get_class_attendance(class_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    """Attendance list for a specific online class."""
    records = (await db.execute(
        select(LectureAttendance).where(
            LectureAttendance.online_class_id == uuid.UUID(class_id),
        ).options(selectinload(LectureAttendance.online_class))
    )).scalars().all()

    result = []
    for r in records:
        student = (await db.execute(
            select(Student).where(Student.id == r.student_id)
        )).scalar_one_or_none()
        student_name = f"{student.first_name} {student.last_name or ''}".strip() if student else "Unknown"

        result.append({
            "student_id": str(r.student_id),
            "student_name": student_name,
            "type": r.attendance_type.value,
            "joined_at": r.joined_at.isoformat() if r.joined_at else "",
        })

    return result


# ═══════════════════════════════════════════════════════════
# CALENDAR API (Outlook-style)
# ═══════════════════════════════════════════════════════════

@router.get("/calendar")
@require_role(UserRole.TEACHER, UserRole.SCHOOL_ADMIN)
async def teacher_calendar(
    request: Request,
    week_start: str = "",
    db: AsyncSession = Depends(get_db),
):
    """Teacher's calendar — classes grouped by day for week view."""
    user_id = get_user_id(request)
    teacher = await _get_teacher_by_user(db, user_id)
    if not teacher:
        return {"week_start": week_start, "days": []}

    if week_start:
        ws = date.fromisoformat(week_start)
    else:
        today = date.today()
        ws = today - timedelta(days=today.weekday())  # Monday

    we = ws + timedelta(days=6)  # Sunday

    classes = (await db.execute(
        select(OnlineClass).where(
            OnlineClass.teacher_id == teacher.id,
            OnlineClass.scheduled_date >= ws,
            OnlineClass.scheduled_date <= we,
            OnlineClass.is_active == True,
            OnlineClass.status != OnlineClassStatus.CANCELLED,
        ).options(
            selectinload(OnlineClass.class_),
            selectinload(OnlineClass.section),
            selectinload(OnlineClass.subject),
        ).order_by(OnlineClass.start_time)
    )).scalars().all()

    day_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    days = []
    for i in range(7):
        d = ws + timedelta(days=i)
        day_classes = [c for c in classes if c.scheduled_date == d]
        days.append({
            "date": d.isoformat(),
            "weekday": day_names[i],
            "classes": [{
                "id": str(c.id),
                "title": c.title,
                "class_name": f"{c.class_.name}{'-' + c.section.name if c.section else ''}" if c.class_ else "",
                "subject": c.subject.name if c.subject else "",
                "start_time": c.start_time.strftime("%H:%M"),
                "end_time": c.end_time.strftime("%H:%M") if c.end_time else "",
                "status": c.status.value,
                "meeting_link": c.meeting_link or "",
                "meeting_password": c.meeting_password or "",
                "platform": c.platform.value,
                "recording_url": c.recording_url or "",
            } for c in day_classes],
        })

    return {"week_start": ws.isoformat(), "days": days}


@router.get("/student-calendar")
@require_role(UserRole.STUDENT)
async def student_calendar(
    request: Request,
    week_start: str = "",
    db: AsyncSession = Depends(get_db),
):
    """Student's calendar — read-only view of scheduled classes."""
    user_id = get_user_id(request)
    student = (await db.execute(
        select(Student).where(Student.user_id == user_id, Student.is_active == True)
    )).scalar_one_or_none()
    if not student:
        return {"week_start": week_start, "days": []}

    if week_start:
        ws = date.fromisoformat(week_start)
    else:
        today = date.today()
        ws = today - timedelta(days=today.weekday())

    we = ws + timedelta(days=6)

    query = select(OnlineClass).where(
        OnlineClass.branch_id == student.branch_id,
        OnlineClass.class_id == student.class_id,
        OnlineClass.scheduled_date >= ws,
        OnlineClass.scheduled_date <= we,
        OnlineClass.is_active == True,
        OnlineClass.status != OnlineClassStatus.CANCELLED,
    ).options(
        selectinload(OnlineClass.subject),
        selectinload(OnlineClass.teacher),
        selectinload(OnlineClass.section),
        selectinload(OnlineClass.class_),
    )
    if student.section_id:
        query = query.where(
            or_(OnlineClass.section_id == student.section_id, OnlineClass.section_id == None)
        )
    query = query.order_by(OnlineClass.start_time)

    classes = (await db.execute(query)).scalars().all()

    # Get attendance records for this student in this week
    att_records = (await db.execute(
        select(LectureAttendance).where(
            LectureAttendance.student_id == student.id,
            LectureAttendance.attendance_type == LectureAttendanceType.JOINED,
        )
    )).scalars().all()
    attended_ids = {str(a.online_class_id) for a in att_records}

    day_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    days = []
    for i in range(7):
        d = ws + timedelta(days=i)
        day_classes = [c for c in classes if c.scheduled_date == d]

        teacher_names = {}
        for c in day_classes:
            if c.teacher and c.teacher.user_id and str(c.teacher_id) not in teacher_names:
                from models.user import User
                tu = (await db.execute(select(User).where(User.id == c.teacher.user_id))).scalar_one_or_none()
                if tu:
                    teacher_names[str(c.teacher_id)] = tu.full_name

        days.append({
            "date": d.isoformat(),
            "weekday": day_names[i],
            "classes": [{
                "id": str(c.id),
                "title": c.title,
                "class_name": f"{c.class_.name}{'-' + c.section.name if c.section else ''}" if c.class_ else "",
                "subject": c.subject.name if c.subject else "",
                "start_time": c.start_time.strftime("%H:%M"),
                "end_time": c.end_time.strftime("%H:%M") if c.end_time else "",
                "status": c.status.value,
                "meeting_link": c.meeting_link or "",
                "meeting_password": c.meeting_password or "",
                "platform": c.platform.value,
                "recording_url": c.recording_url or "",
                "teacher_name": teacher_names.get(str(c.teacher_id), ""),
                "attended": str(c.id) in attended_ids,
            } for c in day_classes],
        })

    return {"week_start": ws.isoformat(), "days": days}
