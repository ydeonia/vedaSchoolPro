"""
Shared async HTTP client with connection pooling.
Reuse across payment, notification, and external API calls
instead of creating a new httpx.AsyncClient per request.
"""
import httpx
from typing import Optional

_client: Optional[httpx.AsyncClient] = None


async def get_http_client() -> httpx.AsyncClient:
    """Get or create the shared HTTP client."""
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(
            timeout=httpx.Timeout(30.0, connect=10.0),
            limits=httpx.Limits(
                max_connections=100,
                max_keepalive_connections=20,
                keepalive_expiry=30,
            ),
            follow_redirects=True,
        )
    return _client


async def close_http_client():
    """Close the shared HTTP client (call on shutdown)."""
    global _client
    if _client and not _client.is_closed:
        await _client.aclose()
        _client = None
