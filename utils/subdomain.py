"""
Subdomain Middleware — Maps school subdomains to branches.

How it works:
  goenkajammu.vedaschoolpro.com → Branch(subdomain="goenkajammu")
  conventgwalior.vedaschoolpro.com → Branch(subdomain="conventgwalior")
  app.vedaschoolpro.com → No branch (super admin or generic login)
  localhost:8000 → No branch (dev mode)

Sets request.state.school_branch (Branch object or None)
Sets request.state.subdomain (string or None)
"""
import logging
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response, HTMLResponse
from sqlalchemy import select

logger = logging.getLogger("subdomain")

# Subdomains that are NOT school codes (reserved)
RESERVED_SUBDOMAINS = {"www", "app", "api", "admin", "mail", "ftp", "static", "cdn", "docs", "help", "support", "status"}

# Base domains — subdomains are extracted from these
BASE_DOMAINS = {"vedaschoolpro.com", "vedaflow.in"}


def extract_subdomain(host: str) -> str | None:
    """
    Extract school subdomain from Host header.
    Returns None if no subdomain or if it's reserved.

    Examples:
      "goenkajammu.vedaschoolpro.com" → "goenkajammu"
      "app.vedaschoolpro.com" → None (reserved)
      "localhost:8000" → None (dev)
      "vedaschoolpro.com" → None (bare domain)
      "192.168.1.5:8000" → None (IP)
    """
    if not host:
        return None

    # Strip port
    hostname = host.split(":")[0].lower().strip()

    # Skip IPs and localhost
    if hostname in ("localhost", "127.0.0.1", "0.0.0.0") or hostname.replace(".", "").isdigit():
        return None

    # Check against known base domains
    for base in BASE_DOMAINS:
        if hostname.endswith("." + base):
            # Extract the subdomain part
            sub = hostname[: -(len(base) + 1)]  # everything before ".vedaschoolpro.com"
            # Handle nested subdomains — take the leftmost part
            sub = sub.split(".")[0] if "." in sub else sub
            if sub and sub not in RESERVED_SUBDOMAINS:
                return sub
            return None

    return None


class SubdomainMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        # Default: no school context
        request.state.school_branch = None
        request.state.subdomain = None

        host = request.headers.get("host", "")
        subdomain = extract_subdomain(host)

        if subdomain:
            request.state.subdomain = subdomain
            # Look up branch from DB — only on page loads, not static files
            path = request.url.path
            if not path.startswith("/static/") and not path.startswith("/favicon"):
                try:
                    from database import async_session
                    from models.branch import Branch

                    async with async_session() as session:
                        branch = await session.scalar(
                            select(Branch).where(
                                Branch.subdomain == subdomain,
                                Branch.is_active == True,
                            )
                        )
                        if branch:
                            # Store serializable branch info (not the ORM object)
                            request.state.school_branch = {
                                "id": str(branch.id),
                                "org_id": str(branch.org_id),
                                "name": branch.name,
                                "code": branch.code,
                                "subdomain": branch.subdomain,
                                "logo_url": branch.logo_url,
                                "city": branch.city,
                                "phone": branch.phone,
                                "email": branch.email,
                                "motto": branch.motto,
                                "tagline": branch.tagline,
                            }
                        else:
                            logger.warning(f"Subdomain '{subdomain}' not found in branches")
                except Exception as e:
                    logger.error(f"Subdomain lookup error: {e}")

        response = await call_next(request)
        return response
