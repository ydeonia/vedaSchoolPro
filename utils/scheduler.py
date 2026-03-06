"""
VedaFlow Automation Engine — Background scheduler for daily/weekly/monthly jobs.
Uses APScheduler AsyncIOScheduler to run within the FastAPI event loop.

Jobs:
  1. daily_fee_automation   — 6:00 AM — auto-generate, overdue, late fees, reminders
  2. daily_attendance_check — 10:00 PM — auto-mark absent for unmarked students
  3. weekly_summary         — Monday 7:00 AM — attendance + fee summary to admin
  4. monthly_report         — 1st of month 8:00 AM — full collection report
"""
import logging
from datetime import datetime, date, timedelta, time
from sqlalchemy import select, func, and_, or_
from database import async_session

logger = logging.getLogger("scheduler")

_scheduler = None


async def start_scheduler(app):
    """Called from main.py lifespan after init_db."""
    global _scheduler
    from config import settings
    if not settings.SCHEDULER_ENABLED:
        logger.info("Scheduler disabled via SCHEDULER_ENABLED=false")
        return

    try:
        from apscheduler.schedulers.asyncio import AsyncIOScheduler
        from apscheduler.triggers.cron import CronTrigger

        _scheduler = AsyncIOScheduler(timezone="Asia/Kolkata")

        # Job 1: Daily fee automation at 6:00 AM
        _scheduler.add_job(
            daily_fee_automation,
            CronTrigger(hour=6, minute=0),
            id="daily_fee_automation",
            replace_existing=True,
            misfire_grace_time=3600,
        )

        # Job 2: Daily attendance check at 10:00 PM
        _scheduler.add_job(
            daily_attendance_check,
            CronTrigger(hour=22, minute=0),
            id="daily_attendance_check",
            replace_existing=True,
            misfire_grace_time=3600,
        )

        # Job 3: Weekly summary — Monday 7:00 AM
        _scheduler.add_job(
            weekly_summary,
            CronTrigger(day_of_week="mon", hour=7, minute=0),
            id="weekly_summary",
            replace_existing=True,
            misfire_grace_time=3600,
        )

        # Job 4: Monthly report — 1st of month 8:00 AM
        _scheduler.add_job(
            monthly_report,
            CronTrigger(day=1, hour=8, minute=0),
            id="monthly_report",
            replace_existing=True,
            misfire_grace_time=3600,
        )

        # Job 5: Online class reminders — every 5 minutes
        _scheduler.add_job(
            online_class_reminder,
            CronTrigger(minute="*/5"),
            id="online_class_reminder",
            replace_existing=True,
            misfire_grace_time=300,
        )

        # Job 6: Platform health check — every 30 minutes
        _scheduler.add_job(
            platform_health_check,
            CronTrigger(minute="*/30"),
            id="platform_health_check",
            replace_existing=True,
            misfire_grace_time=600,
        )

        # Job 7: Nightly branch backup at 2:00 AM
        _scheduler.add_job(
            nightly_branch_backup,
            CronTrigger(hour=2, minute=0),
            id="nightly_branch_backup",
            replace_existing=True,
            misfire_grace_time=7200,
        )

        # Job 8: Subscription late-fee check at 7:00 AM
        _scheduler.add_job(
            subscription_late_fee_check,
            CronTrigger(hour=7, minute=0),
            id="subscription_late_fee_check",
            replace_existing=True,
            misfire_grace_time=3600,
        )

        _scheduler.start()
        logger.info("Automation scheduler started with 8 jobs")
    except ImportError:
        logger.warning("apscheduler not installed — scheduler disabled. Run: pip install apscheduler")
    except Exception as e:
        logger.error(f"Scheduler startup failed: {e}")


def stop_scheduler():
    """Graceful shutdown."""
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped")


# ═══════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════

async def get_active_branch_ids():
    """Get branch IDs with active/trial/grace subscriptions."""
    try:
        from models.subscription import SchoolSubscription
        async with async_session() as db:
            result = await db.execute(
                select(SchoolSubscription.branch_id).where(
                    SchoolSubscription.status.in_(["active", "trial", "grace"])
                )
            )
            return [row[0] for row in result.all()]
    except Exception as e:
        logger.error(f"get_active_branch_ids failed: {e}")
        return []


async def is_holiday(db, branch_id, target_date) -> bool:
    """Check if date is a holiday for this branch."""
    try:
        from models.mega_modules import SchoolEvent
        result = await db.execute(
            select(SchoolEvent).where(
                SchoolEvent.branch_id == branch_id,
                SchoolEvent.is_holiday == True,
                SchoolEvent.start_date <= target_date,
                or_(SchoolEvent.end_date >= target_date, SchoolEvent.end_date == None),
            )
        )
        return result.scalar_one_or_none() is not None
    except Exception:
        return False


def is_quiet_hours(comm_config) -> bool:
    """Check if current time falls within quiet hours."""
    if not comm_config or not comm_config.quiet_hours_enabled:
        return False
    try:
        now = datetime.now().time()
        quiet_start = time(*map(int, (comm_config.quiet_start or "20:00").split(":")))
        quiet_end = time(*map(int, (comm_config.quiet_end or "07:00").split(":")))
        if quiet_start > quiet_end:
            # Overnight window (e.g., 20:00 - 07:00)
            return now >= quiet_start or now <= quiet_end
        else:
            return quiet_start <= now <= quiet_end
    except Exception:
        return False


# ═══════════════════════════════════════════════════════════
# JOB 1: DAILY FEE AUTOMATION (6:00 AM)
# ═══════════════════════════════════════════════════════════

async def daily_fee_automation():
    """Auto-generate fees, mark overdue, apply late fees, send reminders."""
    logger.info("[FEE-AUTO] Starting daily fee automation...")
    from models.branch import BranchSettings, CommunicationConfig
    from models.academic import Class
    from utils.fee_engine import (
        generate_fees_for_class, mark_overdue_fees, apply_late_fees, get_fees_due_in_days
    )

    branch_ids = await get_active_branch_ids()
    today = date.today()

    for branch_id in branch_ids:
        try:
            async with async_session() as db:
                bs = (await db.execute(
                    select(BranchSettings).where(BranchSettings.branch_id == branch_id)
                )).scalar_one_or_none()
                if not bs:
                    continue

                comm = (await db.execute(
                    select(CommunicationConfig).where(CommunicationConfig.branch_id == branch_id)
                )).scalar_one_or_none()

                # Sub-task 1: Auto-generate monthly fees on 1st of month
                custom = bs.custom_data or {}
                if today.day == 1 and custom.get("auto_generate_fees", False):
                    classes = (await db.execute(
                        select(Class).where(Class.branch_id == branch_id, Class.is_active == True)
                    )).scalars().all()
                    total_gen = 0
                    for cls in classes:
                        count = await generate_fees_for_class(
                            db, branch_id, cls.id, today.month, today.year
                        )
                        total_gen += count
                    await db.commit()
                    logger.info(f"[FEE-AUTO] Branch {branch_id}: Generated {total_gen} fee records")

                # Sub-task 2: Mark overdue
                overdue_count = await mark_overdue_fees(db, branch_id)
                await db.commit()
                if overdue_count:
                    logger.info(f"[FEE-AUTO] Branch {branch_id}: Marked {overdue_count} records OVERDUE")

                # Sub-task 3: Apply late fees
                late_pct = bs.late_fee_percentage or 0
                late_days = bs.late_fee_after_days or 15
                if late_pct > 0:
                    late_count = await apply_late_fees(db, branch_id, late_pct, late_days)
                    await db.commit()
                    if late_count:
                        logger.info(f"[FEE-AUTO] Branch {branch_id}: Applied late fee to {late_count} records")

                # Sub-task 4: Send fee reminders (respect quiet hours)
                if bs.notify_fee_reminder and not is_quiet_hours(comm):
                    reminder_days = bs.fee_reminder_days or [7, 3, 1]
                    for days_before in reminder_days:
                        try:
                            fee_student_pairs = await get_fees_due_in_days(db, branch_id, days_before)
                            for fee_rec, student in fee_student_pairs:
                                try:
                                    from utils.notifier import notify_fee_reminder
                                    parent_phone = getattr(student, 'father_phone', '') or getattr(student, 'mother_phone', '') or ''
                                    parent_email = getattr(student, 'father_email', '') or getattr(student, 'mother_email', '') or ''
                                    if parent_phone or parent_email:
                                        balance = float(fee_rec.amount_due) - float(fee_rec.amount_paid or 0)
                                        student_name = f"{student.first_name} {student.last_name or ''}".strip()
                                        await notify_fee_reminder(
                                            db, str(branch_id), str(student.id),
                                            parent_phone, parent_email,
                                            student_name, balance,
                                            fee_rec.due_date.strftime("%d %B %Y"),
                                        )
                                except Exception as e:
                                    logger.error(f"[FEE-AUTO] Reminder send failed: {e}")
                        except Exception as e:
                            logger.error(f"[FEE-AUTO] Reminder query failed for {days_before}d: {e}")

        except Exception as e:
            logger.error(f"[FEE-AUTO] Branch {branch_id} failed: {e}")

    logger.info("[FEE-AUTO] Daily fee automation completed")


# ═══════════════════════════════════════════════════════════
# JOB 2: DAILY ATTENDANCE CHECK (10:00 PM)
# ═══════════════════════════════════════════════════════════

async def daily_attendance_check():
    """Auto-mark ABSENT for students with no attendance record today."""
    logger.info("[ATTENDANCE-AUTO] Starting daily attendance check...")
    from models.branch import BranchSettings
    from models.student import Student
    from models.attendance import Attendance, AttendanceStatus

    today = date.today()

    # Skip Sundays
    if today.weekday() == 6:
        logger.info("[ATTENDANCE-AUTO] Sunday — skipping")
        return

    branch_ids = await get_active_branch_ids()

    for branch_id in branch_ids:
        try:
            async with async_session() as db:
                bs = (await db.execute(
                    select(BranchSettings).where(BranchSettings.branch_id == branch_id)
                )).scalar_one_or_none()
                if not bs:
                    continue

                # Only for daily attendance type
                if (bs.attendance_type or "daily") != "daily":
                    continue

                # Skip holidays
                if await is_holiday(db, branch_id, today):
                    logger.info(f"[ATTENDANCE-AUTO] Branch {branch_id}: Holiday — skipping")
                    continue

                # Get active students
                students = (await db.execute(
                    select(Student.id, Student.class_id, Student.section_id).where(
                        Student.branch_id == branch_id,
                        Student.is_active == True,
                    )
                )).all()

                # Get students who already have attendance today
                marked = (await db.execute(
                    select(Attendance.student_id).where(
                        Attendance.branch_id == branch_id,
                        Attendance.date == today,
                    )
                )).scalars().all()
                marked_set = set(marked)

                absent_count = 0
                for sid, cid, secid in students:
                    if sid not in marked_set:
                        att = Attendance(
                            student_id=sid,
                            branch_id=branch_id,
                            class_id=cid,
                            section_id=secid,
                            date=today,
                            status=AttendanceStatus.ABSENT,
                            remarks="Auto-marked absent (no record)",
                        )
                        db.add(att)
                        absent_count += 1

                if absent_count:
                    await db.commit()
                    logger.info(f"[ATTENDANCE-AUTO] Branch {branch_id}: Auto-marked {absent_count} students ABSENT")

        except Exception as e:
            logger.error(f"[ATTENDANCE-AUTO] Branch {branch_id} failed: {e}")

    logger.info("[ATTENDANCE-AUTO] Daily attendance check completed")


# ═══════════════════════════════════════════════════════════
# JOB 3: WEEKLY SUMMARY (Monday 7:00 AM)
# ═══════════════════════════════════════════════════════════

async def weekly_summary():
    """Send weekly attendance + fee summary to school admin."""
    logger.info("[WEEKLY] Starting weekly summary...")
    from models.branch import Branch, BranchSettings
    from models.user import User, UserRole
    from models.attendance import Attendance, AttendanceStatus
    from models.fee import FeeRecord, PaymentStatus

    branch_ids = await get_active_branch_ids()
    today = date.today()
    week_start = today - timedelta(days=7)

    for branch_id in branch_ids:
        try:
            async with async_session() as db:
                branch = (await db.execute(
                    select(Branch).where(Branch.id == branch_id)
                )).scalar_one_or_none()
                if not branch:
                    continue

                # Attendance stats for the week
                att_total = (await db.execute(
                    select(func.count()).select_from(Attendance).where(
                        Attendance.branch_id == branch_id,
                        Attendance.date >= week_start,
                        Attendance.date < today,
                    )
                )).scalar() or 0

                att_present = (await db.execute(
                    select(func.count()).select_from(Attendance).where(
                        Attendance.branch_id == branch_id,
                        Attendance.date >= week_start,
                        Attendance.date < today,
                        Attendance.status.in_([AttendanceStatus.PRESENT, AttendanceStatus.LATE]),
                    )
                )).scalar() or 0

                att_pct = round((att_present / att_total * 100), 1) if att_total > 0 else 0

                # Fee collection this week
                fees_collected = (await db.execute(
                    select(func.coalesce(func.sum(FeeRecord.amount_paid), 0)).where(
                        FeeRecord.branch_id == branch_id,
                        FeeRecord.payment_date >= week_start,
                        FeeRecord.payment_date < today,
                    )
                )).scalar() or 0

                # Overdue count
                overdue_count = (await db.execute(
                    select(func.count()).select_from(FeeRecord).where(
                        FeeRecord.branch_id == branch_id,
                        FeeRecord.status == PaymentStatus.OVERDUE,
                    )
                )).scalar() or 0

                summary = (
                    f"Weekly Summary for {branch.name}\n"
                    f"Week: {week_start.strftime('%d %b')} - {today.strftime('%d %b %Y')}\n\n"
                    f"Attendance: {att_pct}% ({att_present}/{att_total} records)\n"
                    f"Fee Collected: Rs {fees_collected:,.0f}\n"
                    f"Overdue Fees: {overdue_count} records\n"
                )

                # Send to admin(s)
                admins = (await db.execute(
                    select(User).where(
                        User.branch_id == branch_id,
                        User.role == UserRole.SCHOOL_ADMIN,
                        User.is_active == True,
                    )
                )).scalars().all()

                from utils.notifier import send_notification
                for admin in admins:
                    try:
                        await send_notification(
                            db, str(branch_id),
                            user_id=str(admin.id),
                            notification_type="report",
                            title="Weekly Summary",
                            message=summary,
                            channels=["in_app", "email"],
                            priority="normal",
                        )
                    except Exception as e:
                        logger.error(f"[WEEKLY] Notification to {admin.email} failed: {e}")

        except Exception as e:
            logger.error(f"[WEEKLY] Branch {branch_id} failed: {e}")

    logger.info("[WEEKLY] Weekly summary completed")


# ═══════════════════════════════════════════════════════════
# JOB 4: MONTHLY REPORT (1st of month, 8:00 AM)
# ═══════════════════════════════════════════════════════════

async def monthly_report():
    """Send monthly collection report to admin + chairman."""
    logger.info("[MONTHLY] Starting monthly report...")
    from models.branch import Branch, BranchSettings
    from models.user import User, UserRole
    from models.fee import FeeRecord, PaymentStatus
    from models.student import Student

    branch_ids = await get_active_branch_ids()
    today = date.today()
    # Previous month
    if today.month == 1:
        prev_month, prev_year = 12, today.year - 1
    else:
        prev_month, prev_year = today.month - 1, today.year

    first_of_prev = date(prev_year, prev_month, 1)
    last_of_prev = today - timedelta(days=today.day)

    for branch_id in branch_ids:
        try:
            async with async_session() as db:
                branch = (await db.execute(
                    select(Branch).where(Branch.id == branch_id)
                )).scalar_one_or_none()
                if not branch:
                    continue

                # Total collected last month
                collected = (await db.execute(
                    select(func.coalesce(func.sum(FeeRecord.amount_paid), 0)).where(
                        FeeRecord.branch_id == branch_id,
                        FeeRecord.payment_date >= first_of_prev,
                        FeeRecord.payment_date <= last_of_prev,
                    )
                )).scalar() or 0

                # Total outstanding
                outstanding = (await db.execute(
                    select(func.coalesce(
                        func.sum(FeeRecord.amount_due - FeeRecord.amount_paid), 0
                    )).where(
                        FeeRecord.branch_id == branch_id,
                        FeeRecord.status.in_([PaymentStatus.PENDING, PaymentStatus.PARTIAL, PaymentStatus.OVERDUE]),
                    )
                )).scalar() or 0

                # Defaulter count
                defaulter_count = (await db.execute(
                    select(func.count(func.distinct(FeeRecord.student_id))).where(
                        FeeRecord.branch_id == branch_id,
                        FeeRecord.status == PaymentStatus.OVERDUE,
                    )
                )).scalar() or 0

                # Active students
                student_count = (await db.execute(
                    select(func.count()).select_from(Student).where(
                        Student.branch_id == branch_id,
                        Student.is_active == True,
                    )
                )).scalar() or 0

                month_name = first_of_prev.strftime("%B %Y")
                report = (
                    f"Monthly Report: {month_name}\n"
                    f"School: {branch.name}\n\n"
                    f"Total Collected: Rs {collected:,.0f}\n"
                    f"Total Outstanding: Rs {outstanding:,.0f}\n"
                    f"Defaulters: {defaulter_count} students\n"
                    f"Active Students: {student_count}\n"
                )

                # Send to admin + chairman
                recipients = (await db.execute(
                    select(User).where(
                        User.is_active == True,
                        or_(
                            and_(User.branch_id == branch_id, User.role == UserRole.SCHOOL_ADMIN),
                            and_(User.org_id == branch.org_id, User.role == UserRole.CHAIRMAN),
                        ),
                    )
                )).scalars().all()

                from utils.notifier import send_notification
                for user in recipients:
                    try:
                        await send_notification(
                            db, str(branch_id),
                            user_id=str(user.id),
                            notification_type="report",
                            title=f"Monthly Report - {month_name}",
                            message=report,
                            channels=["in_app", "email", "whatsapp"],
                            priority="normal",
                        )
                    except Exception as e:
                        logger.error(f"[MONTHLY] Notification to {user.email} failed: {e}")

        except Exception as e:
            logger.error(f"[MONTHLY] Branch {branch_id} failed: {e}")

    logger.info("[MONTHLY] Monthly report completed")


# ═══════════════════════════════════════════════════════════
# JOB 5: ONLINE CLASS REMINDERS (every 5 minutes)
# ═══════════════════════════════════════════════════════════

async def online_class_reminder():
    """Send 15-min reminder for upcoming online classes."""
    from models.online_class import OnlineClass, OnlineClassStatus
    from models.student import Student

    now = datetime.now()
    target_time = now + timedelta(minutes=15)

    try:
        async with async_session() as db:
            # Find classes starting in next 15 minutes that haven't been reminded
            classes = (await db.execute(
                select(OnlineClass).where(
                    OnlineClass.scheduled_date == now.date(),
                    OnlineClass.start_time >= now.time(),
                    OnlineClass.start_time <= target_time.time(),
                    OnlineClass.status == OnlineClassStatus.SCHEDULED,
                    OnlineClass.reminder_sent == False,
                    OnlineClass.is_active == True,
                )
            )).scalars().all()

            if not classes:
                return

            from utils.notifier import send_notification

            for oc in classes:
                try:
                    students = (await db.execute(
                        select(Student).where(
                            Student.branch_id == oc.branch_id,
                            Student.class_id == oc.class_id,
                            Student.is_active == True,
                        )
                    )).scalars().all()

                    if oc.section_id:
                        students = [s for s in students if s.section_id == oc.section_id]

                    for student in students:
                        if student.user_id:
                            try:
                                await send_notification(
                                    db, str(oc.branch_id),
                                    user_id=str(student.user_id),
                                    notification_type="online_class",
                                    title="Class Starting Soon",
                                    message=f"{oc.title} starts in 15 minutes. Join now!",
                                    channels=["in_app"],
                                    priority="high",
                                )
                            except Exception:
                                pass

                    oc.reminder_sent = True
                except Exception as e:
                    logger.error(f"[REMINDER] Class {oc.id} failed: {e}")

            await db.commit()
            if classes:
                logger.info(f"[REMINDER] Sent reminders for {len(classes)} online classes")

    except Exception as e:
        logger.error(f"[REMINDER] Online class reminder failed: {e}")


# ═══════════════════════════════════════════════════════════
# JOB 6: PLATFORM HEALTH CHECK (every 30 minutes)
# ═══════════════════════════════════════════════════════════

async def platform_health_check():
    """
    Verify OAuth tokens for all connected platforms are still valid.
    If broken → mark error on config + alert admin immediately.
    If was broken but now fixed → clear error.
    """
    from models.online_class import OnlinePlatformConfig
    from utils.online_meeting import check_platform_health

    try:
        async with async_session() as db:
            configs = (await db.execute(
                select(OnlinePlatformConfig).where(OnlinePlatformConfig.is_active == True)
            )).scalars().all()

            if not configs:
                return

            from utils.notifier import send_notification
            from models.user import User, UserRole
            now = datetime.now()

            for config in configs:
                platforms_to_check = []
                if config.google_enabled:
                    platforms_to_check.append(("google_meet", "Google Meet"))
                if config.zoom_enabled:
                    platforms_to_check.append(("zoom", "Zoom"))
                if config.teams_enabled:
                    platforms_to_check.append(("teams", "Microsoft Teams"))

                for platform_key, platform_name in platforms_to_check:
                    result = await check_platform_health(config, platform_key)

                    # Map platform_key to config field prefix
                    prefix = platform_key.replace("_meet", "")  # google_meet → google

                    if result["healthy"]:
                        # Clear any previous error
                        setattr(config, f"{prefix}_error", None)
                        setattr(config, f"{prefix}_last_verified", now)
                    else:
                        was_healthy = getattr(config, f"{prefix}_error") is None
                        setattr(config, f"{prefix}_error", result["error"])
                        setattr(config, f"{prefix}_last_verified", now)

                        # Only notify admin on FIRST failure (not every 30 min)
                        if was_healthy:
                            logger.warning(
                                f"[HEALTH] {platform_name} disconnected for branch {config.branch_id}: {result['error']}"
                            )
                            # Find branch admin(s) and alert them
                            try:
                                admins = (await db.execute(
                                    select(User).where(
                                        User.branch_id == config.branch_id,
                                        User.role == UserRole.SCHOOL_ADMIN,
                                        User.is_active == True,
                                    )
                                )).scalars().all()

                                for admin in admins:
                                    try:
                                        await send_notification(
                                            db, str(config.branch_id),
                                            user_id=str(admin.id),
                                            notification_type="online_class",
                                            title=f"{platform_name} Disconnected",
                                            message=(
                                                f"{platform_name} session has expired or been revoked. "
                                                f"Teachers cannot generate meeting links until you reconnect. "
                                                f"Go to Online Classes → Platform Settings to reconnect."
                                            ),
                                            channels=["in_app"],
                                            priority="urgent",
                                        )
                                    except Exception:
                                        pass
                            except Exception as e:
                                logger.error(f"[HEALTH] Admin notify failed: {e}")

            await db.commit()

    except Exception as e:
        logger.error(f"[HEALTH] Platform health check failed: {e}")


# ═══════════════════════════════════════════════════════════
# JOB 7: NIGHTLY BRANCH BACKUP — 2:00 AM
# ═══════════════════════════════════════════════════════════

async def nightly_branch_backup():
    """
    Run nightly backups for all active branches.
    Respects plan backup_frequency (daily/weekly).
    """
    from models.subscription import SchoolSubscription
    from sqlalchemy.orm import selectinload

    try:
        async with async_session() as db:
            branch_ids = await get_active_branch_ids()
            logger.info(f"[BACKUP] Nightly backup starting for {len(branch_ids)} branches")

            today = datetime.now()
            is_sunday = today.weekday() == 6  # Weekly backups on Sunday

            backed_up = 0
            skipped = 0
            failed = 0

            for bid in branch_ids:
                try:
                    # Check plan backup_frequency
                    sub = await db.scalar(
                        select(SchoolSubscription)
                        .where(SchoolSubscription.branch_id == bid)
                        .options(selectinload(SchoolSubscription.plan))
                    )

                    frequency = "weekly"  # Default
                    if sub and sub.plan:
                        frequency = sub.plan.backup_frequency or "weekly"

                    # Skip if weekly and not Sunday
                    if frequency == "weekly" and not is_sunday:
                        skipped += 1
                        continue

                    # Create backup
                    from utils.backup_manager import create_branch_backup
                    result = await create_branch_backup(
                        db, bid,
                        backup_type_str="scheduled",
                    )

                    if result.get("success"):
                        backed_up += 1
                    else:
                        failed += 1
                        logger.warning(f"[BACKUP] Branch {bid} failed: {result.get('error')}")

                except Exception as e:
                    failed += 1
                    logger.error(f"[BACKUP] Branch {bid} error: {e}")

            logger.info(
                f"[BACKUP] Nightly complete — backed up: {backed_up}, "
                f"skipped: {skipped}, failed: {failed}"
            )

    except Exception as e:
        logger.error(f"[BACKUP] Nightly backup job failed: {e}")


# ═══════════════════════════════════════════════════════════
# JOB 8: SUBSCRIPTION LATE FEE CHECK — 7:00 AM
# ═══════════════════════════════════════════════════════════

async def subscription_late_fee_check():
    """
    Check for overdue subscriptions and apply late fees.
    Runs daily — finds subscriptions past grace period with no late fee yet.
    """
    from models.subscription import SchoolSubscription, PaymentHistory, SubscriptionStatus
    from sqlalchemy.orm import selectinload
    from decimal import Decimal

    try:
        async with async_session() as db:
            # Find subscriptions in GRACE status with next_payment_due past the grace period
            now = datetime.now()

            result = await db.execute(
                select(SchoolSubscription)
                .where(
                    SchoolSubscription.status == SubscriptionStatus.GRACE,
                    SchoolSubscription.late_fee_amount == 0,
                    SchoolSubscription.late_fee_waived == False,
                    SchoolSubscription.next_payment_due.isnot(None),
                )
                .options(selectinload(SchoolSubscription.plan))
            )
            subs = result.scalars().all()

            applied = 0
            for sub in subs:
                try:
                    plan = sub.plan
                    if not plan:
                        continue

                    grace_days = plan.late_fee_grace_days or 7
                    late_fee_type = plan.late_fee_type or "percentage"
                    late_fee_value = float(plan.late_fee_value or 5)

                    # Check if past grace period
                    if sub.next_payment_due:
                        days_overdue = (now - sub.next_payment_due).days
                        if days_overdue < grace_days:
                            continue  # Still within grace
                    else:
                        continue

                    # Calculate late fee
                    if sub.billing_cycle and sub.billing_cycle.value == "yearly":
                        plan_price = float(plan.price_yearly or 0)
                    else:
                        plan_price = float(plan.price_monthly or 0)

                    if late_fee_type == "percentage":
                        late_fee = round(plan_price * late_fee_value / 100, 2)
                    else:
                        late_fee = late_fee_value

                    if late_fee <= 0:
                        continue

                    # Apply late fee
                    sub.late_fee_amount = Decimal(str(late_fee))
                    sub.late_fee_applied_at = now

                    # Create payment history entry
                    payment = PaymentHistory(
                        subscription_id=sub.id,
                        branch_id=sub.branch_id,
                        amount=Decimal(str(late_fee)),
                        currency="INR",
                        plan_name=plan.name,
                        billing_cycle=sub.billing_cycle.value if sub.billing_cycle else "monthly",
                        status="late_fee_pending",
                        includes_late_fee=True,
                        late_fee_amount=Decimal(str(late_fee)),
                        notes=f"Late fee ({late_fee_type}: {late_fee_value}{'%' if late_fee_type == 'percentage' else ''}) — {days_overdue} days overdue",
                    )
                    db.add(payment)

                    # Notify branch admin
                    try:
                        admins = (await db.execute(
                            select(User).where(
                                User.branch_id == sub.branch_id,
                                User.role == UserRole.SCHOOL_ADMIN,
                                User.is_active == True,
                            )
                        )).scalars().all()

                        for admin in admins:
                            from utils.notifier import send_notification
                            try:
                                await send_notification(
                                    db, str(sub.branch_id),
                                    user_id=str(admin.id),
                                    notification_type="alert",
                                    title="Late Fee Applied",
                                    message=f"A late fee of Rs.{late_fee:.2f} has been applied to your {plan.name} subscription. Please renew to avoid service interruption.",
                                    channels=["in_app", "email"],
                                    recipient_email=admin.email,
                                    priority="urgent",
                                )
                            except Exception:
                                pass
                    except Exception:
                        pass

                    applied += 1
                    logger.info(f"[LATE-FEE] Applied Rs.{late_fee} to branch {sub.branch_id}")

                except Exception as e:
                    logger.error(f"[LATE-FEE] Error for sub {sub.id}: {e}")

            await db.commit()
            if applied > 0:
                logger.info(f"[LATE-FEE] Applied late fees to {applied} subscriptions")

    except Exception as e:
        logger.error(f"[LATE-FEE] Job failed: {e}")
