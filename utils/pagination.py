"""
Reusable pagination utilities for API endpoints.
Supports cursor-based and offset-based pagination.
"""
from typing import Any, Optional
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import Select


async def paginate(
    db: AsyncSession,
    query: Select,
    page: int = 1,
    per_page: int = 25,
    max_per_page: int = 100,
) -> dict[str, Any]:
    """
    Apply offset-based pagination to a SQLAlchemy select query.

    Returns:
        {
            "items": [...],
            "total": 150,
            "page": 1,
            "per_page": 25,
            "pages": 6,
            "has_next": True,
            "has_prev": False,
        }
    """
    # Clamp values
    page = max(1, page)
    per_page = min(max(1, per_page), max_per_page)

    # Count total
    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar() or 0

    # Calculate pages
    pages = max(1, (total + per_page - 1) // per_page)
    page = min(page, pages)

    # Apply offset/limit
    offset = (page - 1) * per_page
    items_query = query.offset(offset).limit(per_page)
    result = await db.execute(items_query)
    items = result.scalars().all()

    return {
        "items": items,
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": pages,
        "has_next": page < pages,
        "has_prev": page > 1,
    }


def parse_pagination_params(
    page: Optional[int] = None,
    per_page: Optional[int] = None,
    default_per_page: int = 25,
) -> tuple[int, int]:
    """Parse and validate pagination query parameters."""
    return (
        max(1, page or 1),
        min(max(1, per_page or default_per_page), 100),
    )
