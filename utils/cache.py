"""
Simple in-memory cache with TTL expiration.
Use for settings, timezone lookups, and analytics that don't change frequently.
For production, replace with Redis via the redis package.
"""
import time
from typing import Any, Optional
from functools import wraps


class SimpleCache:
    """Thread-safe in-memory cache with TTL."""

    def __init__(self):
        self._store: dict[str, tuple[Any, float]] = {}

    def get(self, key: str) -> Optional[Any]:
        """Get a cached value. Returns None if expired or missing."""
        if key not in self._store:
            return None
        value, expires_at = self._store[key]
        if time.time() > expires_at:
            del self._store[key]
            return None
        return value

    def set(self, key: str, value: Any, ttl: int = 300):
        """Set a cached value with TTL in seconds (default 5 minutes)."""
        self._store[key] = (value, time.time() + ttl)

    def delete(self, key: str):
        """Remove a cached value."""
        self._store.pop(key, None)

    def clear(self):
        """Clear all cached values."""
        self._store.clear()

    def cleanup(self):
        """Remove expired entries."""
        now = time.time()
        expired = [k for k, (_, exp) in self._store.items() if now > exp]
        for k in expired:
            del self._store[k]


# Global cache instance
cache = SimpleCache()


def cached(ttl: int = 300, key_prefix: str = ""):
    """
    Decorator to cache async function results.

    Usage:
        @cached(ttl=600, key_prefix="branch_settings")
        async def get_branch_settings(branch_id: str):
            ...
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Build cache key from function name + args
            parts = [key_prefix or func.__name__]
            parts.extend(str(a) for a in args)
            parts.extend(f"{k}={v}" for k, v in sorted(kwargs.items()))
            cache_key = ":".join(parts)

            # Check cache
            result = cache.get(cache_key)
            if result is not None:
                return result

            # Call function and cache result
            result = await func(*args, **kwargs)
            if result is not None:
                cache.set(cache_key, result, ttl)
            return result

        # Expose cache invalidation
        wrapper.invalidate = lambda *args, **kwargs: cache.delete(
            ":".join([key_prefix or func.__name__] +
                     [str(a) for a in args] +
                     [f"{k}={v}" for k, v in sorted(kwargs.items())])
        )
        return wrapper
    return decorator
