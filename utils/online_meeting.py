"""
Online Meeting Integration — Google Meet, Zoom, Microsoft Teams.
Supports BOTH admin-level (OnlinePlatformConfig) and per-teacher
(TeacherPlatformToken) OAuth tokens.  Zoom uses branch-level S2S creds
so it always goes through OnlinePlatformConfig.
"""
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any

logger = logging.getLogger("online_meeting")


# ═══════════════════════════════════════════════════════════
# HEALTH CHECK
# ═══════════════════════════════════════════════════════════

async def check_platform_health(config, platform: str) -> Dict[str, Any]:
    """
    Test if a platform's auth tokens are still valid.
    Works with OnlinePlatformConfig (admin) or TeacherPlatformToken (teacher).
    Returns {"healthy": True/False, "error": "..." or None}
    """
    try:
        if platform == "google_meet":
            token = await _get_google_token(config)
            from utils.http_client import get_http_client
            client = await get_http_client()
            resp = await client.get(
                "https://www.googleapis.com/calendar/v3/calendars/primary",
                headers={"Authorization": f"Bearer {token}"},
            )
            if resp.status_code == 200:
                return {"healthy": True, "error": None}
            return {"healthy": False, "error": f"Google API returned {resp.status_code}"}

        elif platform == "zoom":
            token = await _get_zoom_token(config)
            from utils.http_client import get_http_client
            client = await get_http_client()
            resp = await client.get(
                "https://api.zoom.us/v2/users/me",
                headers={"Authorization": f"Bearer {token}"},
            )
            if resp.status_code == 200:
                return {"healthy": True, "error": None}
            return {"healthy": False, "error": f"Zoom API returned {resp.status_code}"}

        elif platform == "teams":
            token = await _get_teams_token(config)
            from utils.http_client import get_http_client
            client = await get_http_client()
            resp = await client.get(
                "https://graph.microsoft.com/v1.0/me",
                headers={"Authorization": f"Bearer {token}"},
            )
            if resp.status_code == 200:
                return {"healthy": True, "error": None}
            return {"healthy": False, "error": f"Teams API returned {resp.status_code}"}

        return {"healthy": False, "error": f"Unknown platform: {platform}"}
    except Exception as e:
        return {"healthy": False, "error": str(e)[:500]}


# ═══════════════════════════════════════════════════════════
# UNIFIED DISPATCHER
# ═══════════════════════════════════════════════════════════

async def generate_meeting_link(
    config,  # OnlinePlatformConfig OR TeacherPlatformToken
    platform: str,
    title: str,
    start_dt: datetime,
    end_dt: datetime = None,
    duration_min: int = 45,
) -> Dict[str, Any]:
    """Unified dispatcher — routes to the correct platform API."""
    if not end_dt:
        end_dt = start_dt + timedelta(minutes=duration_min)

    if platform == "google_meet":
        return await create_google_meet_link(config, title, start_dt, end_dt)
    elif platform == "zoom":
        return await create_zoom_meeting_link(config, title, start_dt, duration_min)
    elif platform == "teams":
        return await create_teams_meeting_link(config, title, start_dt, end_dt)
    else:
        raise ValueError(f"Unsupported platform: {platform}")


# ═══════════════════════════════════════════════════════════
# POLYMORPHIC TOKEN HELPERS
# These detect whether the config object is an admin-level
# OnlinePlatformConfig or a per-teacher TeacherPlatformToken
# and read the correct field names.
# ═══════════════════════════════════════════════════════════

def _is_teacher_token(config) -> bool:
    """Check if config is a TeacherPlatformToken (per-teacher) vs OnlinePlatformConfig."""
    return hasattr(config, 'teacher_id') and hasattr(config, 'access_token')


def _get_refresh_tok(config) -> str:
    """Get the encrypted refresh token field value."""
    if _is_teacher_token(config):
        return config.refresh_token
    return config.google_refresh_token


def _get_access_tok(config) -> str:
    """Get the encrypted access token field value."""
    if _is_teacher_token(config):
        return config.access_token
    return config.google_access_token


def _get_expiry(config):
    """Get token expiry datetime."""
    if _is_teacher_token(config):
        return config.token_expiry
    return config.google_token_expiry


def _set_access_tok(config, encrypted_val):
    """Set the encrypted access token."""
    if _is_teacher_token(config):
        config.access_token = encrypted_val
    else:
        config.google_access_token = encrypted_val


def _set_expiry(config, dt):
    """Set token expiry."""
    if _is_teacher_token(config):
        config.token_expiry = dt
    else:
        config.google_token_expiry = dt


# Teams-specific helpers
def _get_teams_refresh_tok(config) -> str:
    if _is_teacher_token(config):
        return config.refresh_token
    return config.teams_refresh_token


def _get_teams_access_tok(config) -> str:
    if _is_teacher_token(config):
        return config.access_token
    return config.teams_access_token


def _get_teams_expiry(config):
    if _is_teacher_token(config):
        return config.token_expiry
    return config.teams_token_expiry


def _get_teams_tenant(config) -> str:
    if _is_teacher_token(config):
        return config.tenant_id or "common"
    return config.teams_tenant_id or "common"


def _set_teams_access_tok(config, encrypted_val):
    if _is_teacher_token(config):
        config.access_token = encrypted_val
    else:
        config.teams_access_token = encrypted_val


def _set_teams_refresh_tok(config, encrypted_val):
    if _is_teacher_token(config):
        config.refresh_token = encrypted_val
    else:
        config.teams_refresh_token = encrypted_val


def _set_teams_expiry(config, dt):
    if _is_teacher_token(config):
        config.token_expiry = dt
    else:
        config.teams_token_expiry = dt


# ═══════════════════════════════════════════════════════════
# GOOGLE MEET — via Google Calendar API
# ═══════════════════════════════════════════════════════════

async def _refresh_google_token(config) -> str:
    """Refresh Google OAuth2 access token using refresh_token."""
    from utils.http_client import get_http_client
    from utils.crypto import decrypt_value, encrypt_value
    from config import settings

    refresh_token = decrypt_value(_get_refresh_tok(config))
    client = await get_http_client()

    resp = await client.post("https://oauth2.googleapis.com/token", data={
        "client_id": settings.GOOGLE_CLIENT_ID,
        "client_secret": settings.GOOGLE_CLIENT_SECRET,
        "refresh_token": refresh_token,
        "grant_type": "refresh_token",
    })
    data = resp.json()

    if resp.status_code != 200:
        logger.error(f"Google token refresh failed: {data}")
        raise Exception(f"Google token refresh failed: {data.get('error_description', 'Unknown error')}")

    new_token = data["access_token"]
    _set_access_tok(config, encrypt_value(new_token))
    if "expires_in" in data:
        _set_expiry(config, datetime.utcnow() + timedelta(seconds=data["expires_in"]))

    return new_token


async def _get_google_token(config) -> str:
    """Get valid Google access token, refreshing if expired."""
    from utils.crypto import decrypt_value

    expiry = _get_expiry(config)
    if expiry and expiry > datetime.utcnow():
        return decrypt_value(_get_access_tok(config))
    return await _refresh_google_token(config)


async def create_google_meet_link(
    config, title: str, start_dt: datetime, end_dt: datetime
) -> Dict[str, Any]:
    """Create a Google Calendar event with auto-generated Meet link."""
    from utils.http_client import get_http_client

    token = await _get_google_token(config)
    client = await get_http_client()

    event_body = {
        "summary": title,
        "start": {
            "dateTime": start_dt.isoformat(),
            "timeZone": "Asia/Kolkata",
        },
        "end": {
            "dateTime": end_dt.isoformat(),
            "timeZone": "Asia/Kolkata",
        },
        "conferenceData": {
            "createRequest": {
                "requestId": f"vedaflow-{int(datetime.utcnow().timestamp())}",
                "conferenceSolutionKey": {"type": "hangoutsMeet"},
            }
        },
    }

    resp = await client.post(
        "https://www.googleapis.com/calendar/v3/calendars/primary/events",
        params={"conferenceDataVersion": 1},
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json=event_body,
    )
    data = resp.json()

    if resp.status_code not in (200, 201):
        logger.error(f"Google Calendar API error: {data}")
        raise Exception(f"Failed to create Google Meet: {data.get('error', {}).get('message', 'Unknown error')}")

    meet_link = None
    meeting_id = None
    if "conferenceData" in data and "entryPoints" in data["conferenceData"]:
        for ep in data["conferenceData"]["entryPoints"]:
            if ep.get("entryPointType") == "video":
                meet_link = ep.get("uri")
                break
        conf_id = data["conferenceData"].get("conferenceId")
        if conf_id:
            meeting_id = conf_id

    return {
        "meeting_link": meet_link or "",
        "meeting_id": meeting_id or "",
        "meeting_password": "",
        "calendar_event_id": data.get("id", ""),
    }


async def cancel_google_meet(config, event_id: str):
    """Delete a Google Calendar event (cancels the Meet)."""
    from utils.http_client import get_http_client

    token = await _get_google_token(config)
    client = await get_http_client()
    await client.delete(
        f"https://www.googleapis.com/calendar/v3/calendars/primary/events/{event_id}",
        headers={"Authorization": f"Bearer {token}"},
    )


# ═══════════════════════════════════════════════════════════
# ZOOM — Server-to-Server OAuth (branch-level only)
# ═══════════════════════════════════════════════════════════

async def _get_zoom_token(config) -> str:
    """Get Zoom access token via Server-to-Server OAuth (account-level)."""
    from utils.http_client import get_http_client
    from utils.crypto import decrypt_value
    import base64

    account_id = decrypt_value(config.zoom_account_id)
    client_id = decrypt_value(config.zoom_client_id)
    client_secret = decrypt_value(config.zoom_client_secret)

    credentials = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
    client = await get_http_client()

    resp = await client.post(
        "https://zoom.us/oauth/token",
        params={"grant_type": "account_credentials", "account_id": account_id},
        headers={"Authorization": f"Basic {credentials}"},
    )
    data = resp.json()

    if resp.status_code != 200:
        logger.error(f"Zoom token failed: {data}")
        raise Exception(f"Zoom auth failed: {data.get('reason', 'Unknown error')}")

    return data["access_token"]


async def create_zoom_meeting_link(
    config, title: str, start_dt: datetime, duration_min: int = 45
) -> Dict[str, Any]:
    """Create a Zoom meeting via REST API."""
    from utils.http_client import get_http_client

    token = await _get_zoom_token(config)
    client = await get_http_client()

    meeting_body = {
        "topic": title,
        "type": 2,  # Scheduled meeting
        "start_time": start_dt.strftime("%Y-%m-%dT%H:%M:%S"),
        "duration": duration_min,
        "timezone": "Asia/Kolkata",
        "settings": {
            "join_before_host": False,
            "waiting_room": True,
            "auto_recording": "none",
        },
    }

    resp = await client.post(
        "https://api.zoom.us/v2/users/me/meetings",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json=meeting_body,
    )
    data = resp.json()

    if resp.status_code not in (200, 201):
        logger.error(f"Zoom API error: {data}")
        raise Exception(f"Failed to create Zoom meeting: {data.get('message', 'Unknown error')}")

    return {
        "meeting_link": data.get("join_url", ""),
        "meeting_id": str(data.get("id", "")),
        "meeting_password": data.get("password", ""),
        "calendar_event_id": "",
    }


# ═══════════════════════════════════════════════════════════
# MICROSOFT TEAMS — via Graph API
# ═══════════════════════════════════════════════════════════

async def _refresh_teams_token(config) -> str:
    """Refresh Microsoft Teams OAuth2 token."""
    from utils.http_client import get_http_client
    from utils.crypto import decrypt_value, encrypt_value
    from config import settings

    refresh_token = decrypt_value(_get_teams_refresh_tok(config))
    tenant_id = _get_teams_tenant(config)
    client = await get_http_client()

    resp = await client.post(
        f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token",
        data={
            "client_id": settings.TEAMS_CLIENT_ID,
            "client_secret": settings.TEAMS_CLIENT_SECRET,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
            "scope": "OnlineMeetings.ReadWrite offline_access",
        },
    )
    data = resp.json()

    if resp.status_code != 200:
        logger.error(f"Teams token refresh failed: {data}")
        raise Exception(f"Teams token refresh failed: {data.get('error_description', 'Unknown error')}")

    new_token = data["access_token"]
    _set_teams_access_tok(config, encrypt_value(new_token))
    if "refresh_token" in data:
        _set_teams_refresh_tok(config, encrypt_value(data["refresh_token"]))
    if "expires_in" in data:
        _set_teams_expiry(config, datetime.utcnow() + timedelta(seconds=data["expires_in"]))

    return new_token


async def _get_teams_token(config) -> str:
    """Get valid Teams access token, refreshing if expired."""
    from utils.crypto import decrypt_value

    expiry = _get_teams_expiry(config)
    if expiry and expiry > datetime.utcnow():
        return decrypt_value(_get_teams_access_tok(config))
    return await _refresh_teams_token(config)


async def create_teams_meeting_link(
    config, title: str, start_dt: datetime, end_dt: datetime
) -> Dict[str, Any]:
    """Create a Microsoft Teams online meeting via Graph API."""
    from utils.http_client import get_http_client

    token = await _get_teams_token(config)
    client = await get_http_client()

    meeting_body = {
        "subject": title,
        "startDateTime": start_dt.isoformat() + "+05:30",
        "endDateTime": end_dt.isoformat() + "+05:30",
    }

    resp = await client.post(
        "https://graph.microsoft.com/v1.0/me/onlineMeetings",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json=meeting_body,
    )
    data = resp.json()

    if resp.status_code not in (200, 201):
        logger.error(f"Teams API error: {data}")
        raise Exception(f"Failed to create Teams meeting: {data.get('error', {}).get('message', 'Unknown error')}")

    return {
        "meeting_link": data.get("joinWebUrl", ""),
        "meeting_id": data.get("id", ""),
        "meeting_password": "",
        "calendar_event_id": "",
    }
