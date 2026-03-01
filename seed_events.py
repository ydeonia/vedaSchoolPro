"""Seed School Events — Indian school calendar 2025.
Run: python seed_events.py"""
import asyncio, uuid
from datetime import date
from database import engine, async_session, Base
from models.mega_modules import SchoolEvent, EventType
from sqlalchemy import select, func


EVENTS = [
    # ──── NATIONAL HOLIDAYS ────
    ("Republic Day", "2025-01-26", None, "holiday", True, "#EF4444", "National holiday — school closed"),
    ("Maha Shivaratri", "2025-02-26", None, "holiday", True, "#EF4444", ""),
    ("Holi", "2025-03-14", "2025-03-15", "holiday", True, "#EF4444", "Festival of Colors"),
    ("Good Friday", "2025-04-18", None, "holiday", True, "#EF4444", ""),
    ("Eid-ul-Fitr", "2025-03-31", None, "holiday", True, "#EF4444", ""),
    ("Dr. Ambedkar Jayanti", "2025-04-14", None, "holiday", True, "#EF4444", ""),
    ("May Day", "2025-05-01", None, "holiday", True, "#EF4444", "Labour Day"),
    ("Buddha Purnima", "2025-05-12", None, "holiday", True, "#EF4444", ""),
    ("Eid-ul-Adha", "2025-06-07", None, "holiday", True, "#EF4444", ""),
    ("Independence Day", "2025-08-15", None, "holiday", True, "#EF4444", "Flag hoisting ceremony at 8 AM"),
    ("Janmashtami", "2025-08-16", None, "holiday", True, "#EF4444", ""),
    ("Milad-un-Nabi", "2025-09-05", None, "holiday", True, "#EF4444", ""),
    ("Mahatma Gandhi Jayanti", "2025-10-02", None, "holiday", True, "#EF4444", ""),
    ("Dussehra", "2025-10-02", "2025-10-03", "holiday", True, "#EF4444", ""),
    ("Diwali", "2025-10-20", "2025-10-24", "holiday", True, "#EF4444", "Diwali break"),
    ("Guru Nanak Jayanti", "2025-11-05", None, "holiday", True, "#EF4444", ""),
    ("Christmas", "2025-12-25", None, "holiday", True, "#EF4444", ""),

    # ──── SCHOOL VACATIONS ────
    ("Summer Vacation", "2025-05-20", "2025-06-30", "holiday", True, "#F97316", "School closed for summer break"),
    ("Autumn Break", "2025-10-18", "2025-10-26", "holiday", True, "#F97316", "Dussehra + Diwali break"),
    ("Winter Vacation", "2025-12-24", "2026-01-01", "holiday", True, "#F97316", "Winter holidays"),

    # ──── EXAMS ────
    ("Unit Test 1", "2025-02-10", "2025-02-14", "exam", False, "#F59E0B", "First unit test — Classes 6-12"),
    ("Mid-Term Exams", "2025-03-24", "2025-04-04", "exam", False, "#F59E0B", "Mid-term examinations"),
    ("Unit Test 2", "2025-07-14", "2025-07-18", "exam", False, "#F59E0B", "Second unit test"),
    ("Pre-Board Exams (Class 10 & 12)", "2025-11-17", "2025-12-05", "exam", False, "#F59E0B", "Pre-board for board classes"),
    ("Final Exams", "2025-12-08", "2025-12-20", "exam", False, "#F59E0B", "Annual examinations — all classes"),

    # ──── PTM ────
    ("PTM — After Unit Test 1", "2025-02-22", None, "ptm", False, "#3B82F6", "Parent-Teacher Meeting. Time: 9 AM - 1 PM"),
    ("PTM — After Mid-Terms", "2025-04-12", None, "ptm", False, "#3B82F6", "Mid-term PTM. Time: 9 AM - 1 PM"),
    ("PTM — After Final Results", "2025-12-27", None, "ptm", False, "#3B82F6", "Final results PTM"),

    # ──── EVENTS ────
    ("Teachers' Day Celebration", "2025-09-05", None, "cultural", False, "#EC4899", "Students organize program for teachers"),
    ("Children's Day", "2025-11-14", None, "cultural", False, "#EC4899", "Special activities and games for students"),
    ("Annual Day", "2025-02-28", None, "cultural", False, "#EC4899", "Annual Day function — parents invited. Venue: School Auditorium"),
    ("Sports Day", "2025-01-18", None, "sports", False, "#8B5CF6", "Annual sports meet. Track & Field events"),
    ("Science Exhibition", "2025-08-25", "2025-08-26", "event", False, "#10B981", "Students showcase science projects"),
    ("Hindi Diwas", "2025-09-14", None, "cultural", False, "#EC4899", "Hindi poem recitation & essay competition"),
    ("Math Olympiad (Internal)", "2025-08-08", None, "event", False, "#10B981", "Inter-class math competition"),
    ("Art & Craft Exhibition", "2025-11-20", None, "cultural", False, "#EC4899", "Student artwork display"),
    ("Book Fair", "2025-09-22", "2025-09-24", "event", False, "#10B981", "School library book fair"),
    ("Republic Day Parade Practice", "2025-01-20", "2025-01-25", "event", False, "#10B981", "March past practice for R-Day"),

    # ──── DEADLINES ────
    ("Fee Payment Deadline — Q1", "2025-04-15", None, "deadline", False, "#F97316", "Last date for April-June fee payment"),
    ("Fee Payment Deadline — Q2", "2025-07-15", None, "deadline", False, "#F97316", "Last date for July-Sep fee payment"),
    ("Fee Payment Deadline — Q3", "2025-10-15", None, "deadline", False, "#F97316", "Last date for Oct-Dec fee payment"),
    ("Fee Payment Deadline — Q4", "2026-01-15", None, "deadline", False, "#F97316", "Last date for Jan-Mar fee payment"),
]


async def seed_events():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with async_session() as db:
        # Check existing
        count = (await db.execute(select(func.count(SchoolEvent.id)))).scalar()
        if count > 0:
            print(f"⚠️  {count} events already exist. Skipping.")
            return

        # Get first branch
        from models.branch import Branch
        branch = (await db.execute(select(Branch).limit(1))).scalar_one_or_none()
        if not branch:
            print("❌ No branch found. Run seed_army_school.py first.")
            return

        for title, start, end, etype, is_hol, color, desc in EVENTS:
            event = SchoolEvent(
                branch_id=branch.id,
                title=title,
                description=desc,
                event_type=EventType(etype),
                start_date=date.fromisoformat(start),
                end_date=date.fromisoformat(end) if end else None,
                is_holiday=is_hol,
                color=color,
            )
            db.add(event)

        await db.commit()
        print(f"✅ Seeded {len(EVENTS)} school events (holidays, exams, PTMs, cultural events)")
        print(f"   Holidays: {sum(1 for e in EVENTS if e[4])}")
        print(f"   Exams: {sum(1 for e in EVENTS if e[3]=='exam')}")
        print(f"   Events: {sum(1 for e in EVENTS if e[3] in ('event','cultural','sports'))}")
        print(f"   PTMs: {sum(1 for e in EVENTS if e[3]=='ptm')}")


if __name__ == "__main__":
    asyncio.run(seed_events())
