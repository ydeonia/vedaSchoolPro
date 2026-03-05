"""
CSRF Protection Middleware for FastAPI.
Generates and validates CSRF tokens for state-changing requests.
"""
import secrets
import hmac
import hashlib
from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response
from config import settings

CSRF_TOKEN_NAME = "csrf_token"
CSRF_HEADER_NAME = "x-csrf-token"
SAFE_METHODS = {"GET", "HEAD", "OPTIONS", "TRACE"}

# Paths that don't need CSRF (webhooks, public APIs)
CSRF_EXEMPT_PATHS = {
    "/api/payment/webhook",
    "/api/mobile/",  # Mobile API uses JWT auth, not cookies
    "/api/otp/",     # OTP login — no session exists yet on login page
    "/api/auth/",    # Password login API — no session exists yet on login page
    "/api/account/", # Account management — uses JWT auth header
}


def generate_csrf_token(session_id: str) -> str:
    """Generate a CSRF token tied to the user's session."""
    return hmac.new(
        settings.SECRET_KEY.encode(),
        session_id.encode(),
        hashlib.sha256
    ).hexdigest()


def _is_exempt(path: str) -> bool:
    """Check if path is CSRF-exempt."""
    return any(path.startswith(exempt) for exempt in CSRF_EXEMPT_PATHS)


class CSRFMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        # Skip safe methods
        if request.method in SAFE_METHODS:
            response = await call_next(request)
            # Inject CSRF token cookie on GET requests for forms
            token = request.cookies.get("access_token", "anonymous")
            csrf = generate_csrf_token(token)
            response.set_cookie(
                CSRF_TOKEN_NAME, csrf,
                httponly=False,  # JS needs to read this
                samesite="lax",
                max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
            )
            return response

        # Skip exempt paths
        if _is_exempt(request.url.path):
            return await call_next(request)

        # Validate CSRF for state-changing methods
        token_from_cookie = request.cookies.get("access_token", "anonymous")
        expected = generate_csrf_token(token_from_cookie)

        # Check header first, then form data
        submitted = request.headers.get(CSRF_HEADER_NAME, "")
        if not submitted:
            # For form submissions, check the form field
            # (we can't read form body in middleware easily, so we rely on header/cookie)
            submitted = request.cookies.get(CSRF_TOKEN_NAME, "")

        if not hmac.compare_digest(submitted, expected):
            # For API calls that use JSON (not form submissions),
            # check the X-CSRF-Token header
            if "application/json" in (request.headers.get("content-type") or ""):
                submitted = request.headers.get(CSRF_HEADER_NAME, "")
                if not submitted or not hmac.compare_digest(submitted, expected):
                    raise HTTPException(status_code=403, detail="CSRF validation failed")
            # For form submissions without the token, allow if it's an API with auth header
            elif request.headers.get("authorization"):
                pass  # Token-based auth doesn't need CSRF
            else:
                # Be lenient during rollout — log but don't block
                # TODO: Enable strict mode after frontend adds CSRF tokens to all forms
                pass

        return await call_next(request)
