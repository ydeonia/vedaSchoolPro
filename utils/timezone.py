"""Timezone utility — get school's configured time from BranchSettings."""
from datetime import datetime, timezone, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from models.branch import BranchSettings
import uuid

# Common timezone offsets (no pytz needed)
TIMEZONE_OFFSETS = {
    "Asia/Kolkata": timedelta(hours=5, minutes=30),
    "Asia/Dubai": timedelta(hours=4),
    "Asia/Karachi": timedelta(hours=5),
    "Asia/Dhaka": timedelta(hours=6),
    "Asia/Kathmandu": timedelta(hours=5, minutes=45),
    "Asia/Colombo": timedelta(hours=5, minutes=30),
    "Asia/Singapore": timedelta(hours=8),
    "Asia/Tokyo": timedelta(hours=9),
    "Asia/Shanghai": timedelta(hours=8),
    "Asia/Riyadh": timedelta(hours=3),
    "Europe/London": timedelta(hours=0),
    "Europe/Paris": timedelta(hours=1),
    "Europe/Berlin": timedelta(hours=1),
    "America/New_York": timedelta(hours=-5),
    "America/Chicago": timedelta(hours=-6),
    "America/Los_Angeles": timedelta(hours=-8),
    "Africa/Nairobi": timedelta(hours=3),
    "Africa/Lagos": timedelta(hours=1),
    "Australia/Sydney": timedelta(hours=11),
    "Pacific/Auckland": timedelta(hours=13),
    "UTC": timedelta(hours=0),
}

# Display names
TIMEZONE_LABELS = {
    "Asia/Kolkata": "IST (India +5:30)",
    "Asia/Dubai": "GST (UAE +4:00)",
    "Asia/Karachi": "PKT (Pakistan +5:00)",
    "Asia/Dhaka": "BST (Bangladesh +6:00)",
    "Asia/Kathmandu": "NPT (Nepal +5:45)",
    "Asia/Colombo": "SLST (Sri Lanka +5:30)",
    "Asia/Singapore": "SGT (Singapore +8:00)",
    "Asia/Tokyo": "JST (Japan +9:00)",
    "Asia/Shanghai": "CST (China +8:00)",
    "Asia/Riyadh": "AST (Saudi +3:00)",
    "Europe/London": "GMT (London +0:00)",
    "Europe/Paris": "CET (Paris +1:00)",
    "Europe/Berlin": "CET (Berlin +1:00)",
    "America/New_York": "EST (New York -5:00)",
    "America/Chicago": "CST (Chicago -6:00)",
    "America/Los_Angeles": "PST (Los Angeles -8:00)",
    "Africa/Nairobi": "EAT (Nairobi +3:00)",
    "Africa/Lagos": "WAT (Lagos +1:00)",
    "Australia/Sydney": "AEDT (Sydney +11:00)",
    "Pacific/Auckland": "NZDT (Auckland +13:00)",
    "UTC": "UTC (+0:00)",
}


def get_tz_offset(tz_name: str) -> timedelta:
    """Get timezone offset from IANA name. Defaults to IST."""
    return TIMEZONE_OFFSETS.get(tz_name, timedelta(hours=5, minutes=30))


def now_in_tz(tz_name: str = "Asia/Kolkata") -> datetime:
    """Get current datetime in specified timezone."""
    offset = get_tz_offset(tz_name)
    tz = timezone(offset)
    return datetime.now(tz)


def time_in_tz(tz_name: str = "Asia/Kolkata"):
    """Get current time (not datetime) in specified timezone."""
    return now_in_tz(tz_name).time()


async def get_branch_timezone(db: AsyncSession, branch_id) -> str:
    """Get timezone setting for a branch. Defaults to Asia/Kolkata."""
    if isinstance(branch_id, str):
        branch_id = uuid.UUID(branch_id)
    result = await db.execute(
        select(BranchSettings.timezone).where(BranchSettings.branch_id == branch_id)
    )
    tz = result.scalar_one_or_none()
    return tz or "Asia/Kolkata"


async def get_school_now(db: AsyncSession, branch_id) -> datetime:
    """Get current datetime in the school's timezone."""
    tz_name = await get_branch_timezone(db, branch_id)
    return now_in_tz(tz_name)


async def get_school_time(db: AsyncSession, branch_id):
    """Get current time in the school's timezone."""
    tz_name = await get_branch_timezone(db, branch_id)
    return time_in_tz(tz_name), tz_name
