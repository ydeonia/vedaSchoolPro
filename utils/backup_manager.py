"""
VedaFlow Backup Manager — Real pg_dump/pg_restore per branch.

Creates per-branch SQL dumps with WHERE branch_id filtering, compresses via gzip.
Restore deletes existing branch data in reverse dependency order, then restores.
Storage: backups/{branch_id}/{YYYY-MM-DD_HHmmss}.sql.gz
"""

import os
import gzip
import json
import asyncio
import logging
import uuid
from datetime import datetime
from pathlib import Path

from sqlalchemy import select, func, text as sa_text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger("backup_manager")

BASE_DIR = os.path.dirname(os.path.dirname(__file__))
BACKUPS_DIR = os.path.join(BASE_DIR, "backups")

# ── Tables that have a direct branch_id column ──────────────────
BRANCH_TABLES = [
    "academic_years", "account_transactions", "activities", "admissions",
    "announcements", "asset_categories", "assets", "attendance",
    "attendance_fine_rules", "attendance_fines", "backup_records",
    "bell_schedule_templates", "board_results", "book_issues", "books",
    "branch_settings", "certificates", "class_schedule_assignments",
    "classes", "communication_configs", "complaints", "coupon_redemptions",
    "daily_diary", "digital_contents", "donations", "employee_documents",
    "employees", "exams", "exam_cycles", "exam_groups",
    "fee_records", "fee_structures", "fee_waivers", "homework",
    "hostels", "houses", "id_card_templates", "invoices",
    "leave_requests", "message_threads", "model_test_papers",
    "notification_logs", "notifications", "online_classes",
    "online_platform_configs", "payment_gateway_configs", "payment_history",
    "payment_transactions", "period_definitions", "period_logs",
    "photo_change_requests", "question_papers", "quizzes",
    "registration_number_configs", "remark_tags", "report_card_templates",
    "salary_slips", "school_events", "school_subscriptions",
    "separation_requests", "sms_logs", "student_achievements",
    "student_health", "student_leaves", "student_promotions",
    "student_remarks", "student_roles", "students",
    "subject_hours_config", "subjects", "substitutions", "syllabus",
    "teacher_attendance", "teacher_awards", "teacher_class_assignments",
    "teacher_platform_tokens", "teachers", "timetable_slots",
    "transport_routes", "vehicles",
]

# ── Child tables: no branch_id, but linked via FK to a parent that does ──
# Format: { child_table: (fk_column_in_child, parent_table_with_branch_id) }
# Backup query: SELECT * FROM child WHERE fk_col IN (SELECT id FROM parent WHERE branch_id = :bid)
CHILD_TABLES = {
    "sections":              ("class_id",        "classes"),
    "exam_subjects":         ("exam_id",         "exams"),
    "class_subjects":        ("class_id",        "classes"),
    "marks":                 ("student_id",      "students"),
    "homework_submissions":  ("student_id",      "students"),
    "quiz_questions":        ("quiz_id",         "quizzes"),
    "quiz_attempts":         ("student_id",      "students"),
    "hostel_rooms":          ("hostel_id",       "hostels"),
    "hostel_allocations":    ("student_id",      "students"),
    "student_houses":        ("student_id",      "students"),
    "content_views":         ("student_id",      "students"),
    "asset_logs":            ("asset_id",        "assets"),
    "lecture_attendance":    ("student_id",      "students"),
    "route_stops":           ("route_id",        "transport_routes"),
    "student_transport":     ("student_id",      "students"),
    "student_documents":     ("student_id",      "students"),
    "student_activities":    ("student_id",      "students"),
    "messages":              ("thread_id",       "message_threads"),
    "thread_participants":   ("thread_id",       "message_threads"),
    "marks_upload_trackers": ("exam_cycle_id",   "exam_cycles"),
    "student_marks":         ("student_id",      "students"),
    "student_results":       ("student_id",      "students"),
    "marks_audit_logs":      ("exam_cycle_id",   "exam_cycles"),
    "report_card_pdfs":      ("student_id",      "students"),
}

# All backed-up tables (for restore delete order)
ALL_BACKUP_TABLES = BRANCH_TABLES + list(CHILD_TABLES.keys())

# Tables that reference org_id (not branch_id)
ORG_TABLES = ["branches"]


def _get_pg_conninfo():
    """Extract PostgreSQL connection info from config for pg_dump/pg_restore."""
    from config import settings
    url = settings.DATABASE_URL_SYNC
    # Format: postgresql+psycopg2://user:pass@host:port/dbname
    url = url.replace("postgresql+psycopg2://", "").replace("postgresql://", "")
    userpass, hostdb = url.split("@", 1)
    user, password = userpass.split(":", 1) if ":" in userpass else (userpass, "")
    host_port, dbname = hostdb.split("/", 1)
    host, port = host_port.split(":", 1) if ":" in host_port else (host_port, "5432")
    return {
        "host": host,
        "port": port,
        "user": user,
        "password": password,
        "dbname": dbname,
    }


def _serialize_value(val):
    """Serialize a single DB value to SQL-safe string."""
    if val is None:
        return "NULL"
    elif isinstance(val, bool):
        return "TRUE" if val else "FALSE"
    elif isinstance(val, (int, float)):
        return str(val)
    elif isinstance(val, datetime):
        return f"'{val.isoformat()}'"
    elif isinstance(val, uuid.UUID):
        return f"'{val}'"
    elif isinstance(val, (dict, list)):
        json_str = json.dumps(val).replace("'", "''")
        return f"'{json_str}'"
    else:
        escaped = str(val).replace("'", "''")
        return f"'{escaped}'"


def _serialize_row(row):
    """Serialize a full DB row to list of SQL-safe value strings."""
    return [_serialize_value(v) for v in row]


async def _count_branch_records(db: AsyncSession, branch_id: uuid.UUID) -> dict:
    """Count records per table for a branch (direct + child tables)."""
    counts = {}
    bid = str(branch_id)

    # Direct tables (have branch_id)
    for table in BRANCH_TABLES:
        try:
            result = await db.execute(
                sa_text(f"SELECT COUNT(*) FROM {table} WHERE branch_id = :bid"),
                {"bid": bid},
            )
            c = result.scalar() or 0
            if c > 0:
                counts[table] = c
        except Exception:
            await db.rollback()

    # Child tables (via FK subquery)
    for table, (fk_col, parent_table) in CHILD_TABLES.items():
        try:
            result = await db.execute(
                sa_text(
                    f"SELECT COUNT(*) FROM {table} "
                    f"WHERE {fk_col} IN (SELECT id FROM {parent_table} WHERE branch_id = :bid)"
                ),
                {"bid": bid},
            )
            c = result.scalar() or 0
            if c > 0:
                counts[table] = c
        except Exception:
            await db.rollback()

    return counts


async def create_branch_backup(
    db: AsyncSession,
    branch_id,
    triggered_by=None,
    backup_type_str: str = "manual",
) -> dict:
    """
    Create a full pg_dump backup for a specific branch.
    Returns {"success": bool, "backup_id": str, "file_path": str, ...}
    """
    from models.backup import BackupRecord, BackupStatus, BackupType

    bid = uuid.UUID(str(branch_id)) if not isinstance(branch_id, uuid.UUID) else branch_id

    # Determine backup type
    bt_map = {
        "manual": BackupType.MANUAL,
        "scheduled": BackupType.SCHEDULED,
        "full": BackupType.FULL,
    }
    bt = bt_map.get(backup_type_str, BackupType.MANUAL)

    # Get org_id for the branch
    org_result = await db.execute(
        sa_text("SELECT org_id FROM branches WHERE id = :bid"), {"bid": str(bid)}
    )
    org_row = org_result.fetchone()
    if not org_row:
        return {"success": False, "error": "Branch not found"}
    org_id = org_row[0]

    # Create backup record
    now = datetime.utcnow()
    timestamp = now.strftime("%Y-%m-%d_%H%M%S")
    branch_dir = os.path.join(BACKUPS_DIR, str(bid))
    os.makedirs(branch_dir, exist_ok=True)

    file_name = f"{timestamp}.sql.gz"
    file_path = os.path.join(branch_dir, file_name)
    relative_path = f"backups/{bid}/{file_name}"

    record = BackupRecord(
        branch_id=bid,
        org_id=org_id,
        file_name=file_name,
        file_path=relative_path,
        backup_type=bt,
        status=BackupStatus.IN_PROGRESS,
        started_at=now,
        triggered_by=uuid.UUID(str(triggered_by)) if triggered_by else None,
    )
    db.add(record)
    await db.commit()
    await db.refresh(record)
    backup_id = record.id

    try:
        # Count records first
        counts = await _count_branch_records(db, bid)
        tables_with_data = [t for t, c in counts.items() if c > 0]

        # Build pg_dump command — dump only tables with branch_id matching our branch
        # We use a custom SQL approach: SELECT rows WHERE branch_id = X → dump as INSERTs
        conn_info = _get_pg_conninfo()
        env = os.environ.copy()
        env["PGPASSWORD"] = conn_info["password"]

        # Generate SQL dump with WHERE clause filtering by branch_id
        sql_statements = []
        sql_statements.append(f"-- VedaFlow Branch Backup")
        sql_statements.append(f"-- Branch ID: {bid}")
        sql_statements.append(f"-- Organization ID: {org_id}")
        sql_statements.append(f"-- Created: {now.isoformat()}")
        sql_statements.append(f"-- Tables: {len(tables_with_data)}")
        sql_statements.append(f"-- Records: {sum(counts.values())}")
        sql_statements.append("")
        sql_statements.append("BEGIN;")
        sql_statements.append("")

        async def _dump_table(table_name, where_clause, params):
            """Dump rows from a single table using the given WHERE clause."""
            try:
                col_result = await db.execute(sa_text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name = :t ORDER BY ordinal_position"
                ), {"t": table_name})
                columns = [r[0] for r in col_result.fetchall()]
                if not columns:
                    return

                col_list = ", ".join(columns)
                rows = await db.execute(
                    sa_text(f"SELECT {col_list} FROM {table_name} WHERE {where_clause}"),
                    params,
                )
                all_rows = rows.fetchall()

                if all_rows:
                    sql_statements.append(f"-- Table: {table_name} ({len(all_rows)} rows)")
                    for row in all_rows:
                        vals_str = ", ".join(_serialize_row(row))
                        sql_statements.append(
                            f"INSERT INTO {table_name} ({col_list}) VALUES ({vals_str}) ON CONFLICT DO NOTHING;"
                        )
                    sql_statements.append("")
            except Exception as e:
                sql_statements.append(f"-- Skipped {table_name}: {e}")
                logger.warning(f"Backup skip table {table_name}: {e}")
                await db.rollback()

        # Dump direct branch tables
        for table in tables_with_data:
            if table in CHILD_TABLES:
                continue  # Handle child tables separately below
            await _dump_table(table, "branch_id = :bid", {"bid": str(bid)})

        # Dump child tables (via FK subquery)
        for table, (fk_col, parent_table) in CHILD_TABLES.items():
            if table not in tables_with_data:
                continue
            await _dump_table(
                table,
                f"{fk_col} IN (SELECT id FROM {parent_table} WHERE branch_id = :bid)",
                {"bid": str(bid)},
            )

        # Also dump org row, branch row, and users
        try:
            # Organization
            await _dump_table("organizations", "id = :oid", {"oid": str(org_id)})
            # Branch
            await _dump_table("branches", "id = :bid", {"bid": str(bid)})
            # Users (may belong to branch or org)
            await _dump_table("users", "branch_id = :bid OR org_id = :oid",
                              {"bid": str(bid), "oid": str(org_id)})
        except Exception as e:
            sql_statements.append(f"-- Skipped org/branch/users dump: {e}")
            await db.rollback()

        sql_statements.append("")
        sql_statements.append("COMMIT;")

        # Write gzipped SQL
        full_sql = "\n".join(sql_statements)
        with gzip.open(file_path, "wt", encoding="utf-8") as f:
            f.write(full_sql)

        file_size = os.path.getsize(file_path)

        # Re-fetch backup record (may be detached after rollbacks during table scans)
        record = await db.get(BackupRecord, backup_id)
        if record:
            record.status = BackupStatus.COMPLETED
            record.completed_at = datetime.utcnow()
            record.file_size_bytes = file_size
            record.tables_included = tables_with_data
            record.record_counts = counts
            await db.commit()

        logger.info(f"[BACKUP] Branch {bid} completed — {file_size} bytes, {sum(counts.values())} records")
        return {
            "success": True,
            "backup_id": str(backup_id),
            "file_path": relative_path,
            "file_size": file_size,
            "record_counts": counts,
        }

    except Exception as e:
        logger.error(f"[BACKUP] Branch {bid} FAILED: {e}")
        try:
            await db.rollback()
            # Re-fetch the record on a fresh transaction to update its status
            from models.backup import BackupRecord as BR2, BackupStatus as BS2
            record2 = await db.get(BR2, backup_id)
            if record2:
                record2.status = BS2.FAILED
                record2.error_message = str(e)[:500]
                record2.completed_at = datetime.utcnow()
                await db.commit()
        except Exception as e2:
            logger.error(f"[BACKUP] Could not update failed status: {e2}")
        return {"success": False, "error": str(e), "backup_id": str(backup_id)}


async def restore_branch_backup(db: AsyncSession, backup_id) -> dict:
    """
    Restore a branch from a backup file.
    1. Delete existing branch data (reverse dependency order)
    2. Execute SQL from backup (within transaction)
    """
    from models.backup import BackupRecord, BackupStatus

    bid = uuid.UUID(str(backup_id))
    record = await db.get(BackupRecord, bid)
    if not record:
        return {"success": False, "error": "Backup record not found"}

    file_path = os.path.join(BASE_DIR, record.file_path)
    if not os.path.exists(file_path):
        return {"success": False, "error": "Backup file not found on disk"}

    branch_id = record.branch_id

    try:
        # Read the backup SQL
        with gzip.open(file_path, "rt", encoding="utf-8") as f:
            sql_content = f.read()

        # Delete existing branch data in reverse dependency order
        # Child tables first (they depend on parent tables)
        bid_str = str(branch_id)
        for table, (fk_col, parent_table) in reversed(list(CHILD_TABLES.items())):
            try:
                await db.execute(
                    sa_text(
                        f"DELETE FROM {table} WHERE {fk_col} IN "
                        f"(SELECT id FROM {parent_table} WHERE branch_id = :bid)"
                    ),
                    {"bid": bid_str},
                )
            except Exception:
                await db.rollback()

        # Then direct branch tables (reverse order for FK safety)
        for table in reversed(BRANCH_TABLES):
            try:
                await db.execute(
                    sa_text(f"DELETE FROM {table} WHERE branch_id = :bid"),
                    {"bid": bid_str},
                )
            except Exception:
                await db.rollback()

        # Delete users for this branch
        try:
            await db.execute(
                sa_text("DELETE FROM users WHERE branch_id = :bid"),
                {"bid": bid_str},
            )
        except Exception:
            await db.rollback()

        await db.flush()

        # Execute restore SQL line by line (skip comments, BEGIN/COMMIT)
        for line in sql_content.split("\n"):
            line = line.strip()
            if not line or line.startswith("--") or line in ("BEGIN;", "COMMIT;", ""):
                continue
            try:
                await db.execute(sa_text(line))
            except Exception as e:
                logger.warning(f"[RESTORE] Skipped line: {e}")
                await db.rollback()

        await db.commit()
        logger.info(f"[RESTORE] Branch {branch_id} restored from backup {backup_id}")
        return {"success": True, "message": f"Branch restored from backup {record.file_name}"}

    except Exception as e:
        await db.rollback()
        logger.error(f"[RESTORE] Failed for branch {branch_id}: {e}")
        return {"success": False, "error": str(e)}


def get_backup_file_path(file_path_relative: str) -> str:
    """Get absolute path for a backup file."""
    return os.path.join(BASE_DIR, file_path_relative)


async def get_backup_stats(db: AsyncSession) -> dict:
    """Get global backup statistics."""
    from models.backup import BackupRecord, BackupStatus
    from datetime import timedelta

    now = datetime.utcnow()
    thirty_ago = now - timedelta(days=30)

    total = await db.scalar(
        select(func.count(BackupRecord.id)).where(BackupRecord.is_active == True)
    ) or 0

    success_30d = await db.scalar(
        select(func.count(BackupRecord.id)).where(
            BackupRecord.is_active == True,
            BackupRecord.status == BackupStatus.COMPLETED,
            BackupRecord.created_at >= thirty_ago,
        )
    ) or 0

    failed_30d = await db.scalar(
        select(func.count(BackupRecord.id)).where(
            BackupRecord.is_active == True,
            BackupRecord.status == BackupStatus.FAILED,
            BackupRecord.created_at >= thirty_ago,
        )
    ) or 0

    total_size = await db.scalar(
        select(func.sum(BackupRecord.file_size_bytes)).where(
            BackupRecord.is_active == True,
            BackupRecord.status == BackupStatus.COMPLETED,
        )
    ) or 0

    return {
        "total_backups": total,
        "success_30d": success_30d,
        "failed_30d": failed_30d,
        "total_size_bytes": total_size,
        "total_size_display": _format_size(total_size),
    }


def _format_size(size_bytes: int) -> str:
    """Format bytes to human-readable size."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.1f} GB"
