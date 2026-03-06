import uvicorn
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from database import init_db, async_session
from config import settings
from models.user import User, UserRole
from utils.auth import hash_password
from sqlalchemy import select

# Import routes
from routes.auth import router as auth_router
from routes.super_admin import router as super_admin_router
from routes.api.super_admin_api import router as super_admin_api_router
from routes.school_admin import router as school_admin_router
from routes.api.school_admin_api import router as school_admin_api_router
from routes.teacher import router as teacher_router
from routes.api.teacher_api import router as teacher_api_router
from routes.student import router as student_router
from routes.api.student_analytics_api import router as student_analytics_api_router
from routes.api.teacher_remarks_api import router as teacher_remarks_api_router
from routes.api.student_remarks_api import router as student_remarks_api_router
from routes.api.sprint21_api import router as sprint21_api_router
from routes.api.parent_api import router as parent_api_router
from routes.parent import router as parent_router
from routes.transport import router as transport_router
from routes.api.transport_api import router as transport_api_router
from routes.hr import router as hr_router
from routes.api.hr_api import router as hr_api_router
from routes.chairman import router as chairman_router
from routes.api.chairman_api import router as chairman_api_router
from routes.extended_modules import router as extended_router
from routes.api.extended_api import router as extended_api_router
from routes.api.analytics_api import router as analytics_api_router
from routes.api.onboarding_api import router as onboarding_api_router
from routes.api.help_api import router as help_api_router
from routes.api.messaging_api import router as messaging_api_router
from routes.api.payment_api import router as payment_api_router
from routes.api.mobile_api_final import router as mobile_api_router
from routes.api.report_card_api import router as report_card_api_router
from routes.api.asset_api import router as asset_api_router
from routes.api.timetable_api import router as timetable_api_router
from routes.api.online_class_api import router as online_class_api_router
from routes.api.account_api import router as account_api_router

# Initialize logging
from utils.logging_config import setup_logging
setup_logging(debug=settings.DEBUG)

async def create_super_admin():
    """Create default super admin if not exists"""
    async with async_session() as session:
        result = await session.execute(
            select(User).where(User.role == UserRole.SUPER_ADMIN)
        )
        if not result.scalar_one_or_none():
            admin = User(
                email=settings.SUPER_ADMIN_EMAIL,
                phone=settings.SUPER_ADMIN_PHONE,
                password_hash=hash_password(settings.SUPER_ADMIN_PASSWORD),
                first_name="Super",
                last_name="Admin",
                role=UserRole.SUPER_ADMIN,
                is_active=True,
                is_verified=True,
            )
            session.add(admin)
            await session.commit()
            print(f"✅ Super Admin created: {settings.SUPER_ADMIN_EMAIL}")
        else:
            print("✅ Super Admin already exists")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    print("🚀 Starting VedaSchoolPro School Management System...")
    await init_db()
    print("✅ Database tables created")
    # Auto-migrate: add missing enum values to PostgreSQL enum types
    # ALTER TYPE ADD VALUE cannot run inside a transaction — use raw asyncpg
    try:
        import asyncpg
        from config import Settings
        db_url = Settings().DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")
        pg = await asyncpg.connect(db_url)
        enum_additions = [
            ("admissionstatus", ["WITHDRAWN", "TC_ISSUED", "LEFT"]),
            ("gender", ["OTHER"]),
            ("notificationtype", ["ONLINE_CLASS"]),
            ("onlineplatform", ["GOOGLE_MEET", "ZOOM", "TEAMS"]),
            ("onlineclassstatus", ["SCHEDULED", "LIVE", "COMPLETED", "CANCELLED"]),
            ("lectureattendancetype", ["JOINED", "WATCHED"]),
            ("backupstatus", ["IN_PROGRESS", "COMPLETED", "FAILED"]),
            ("backuptype", ["FULL", "MANUAL", "SCHEDULED", "UPLOADED"]),
            ("discounttype", ["PERCENTAGE", "FLAT"]),
            ("invoicestatus", ["DRAFT", "ISSUED", "PAID", "CANCELLED"]),
        ]
        for enum_name, values in enum_additions:
            for val in values:
                try:
                    await pg.execute(
                        f"ALTER TYPE {enum_name} ADD VALUE IF NOT EXISTS '{val}';"
                    )
                except Exception:
                    pass
        await pg.close()
        print("✅ Enum types verified")
    except Exception as e:
        print(f"⚠️ Enum migration skipped: {e}")
    # Auto-migrate: add check_in/check_out columns to attendance if missing
    try:
        from sqlalchemy import text as sa_text
        from database import engine
        async with engine.begin() as conn:
            await conn.execute(sa_text(
                "ALTER TABLE attendance ADD COLUMN IF NOT EXISTS check_in_time TIME;"
            ))
            await conn.execute(sa_text(
                "ALTER TABLE attendance ADD COLUMN IF NOT EXISTS check_out_time TIME;"
            ))
        print("✅ Attendance time columns verified")
    except Exception as e:
        print(f"⚠️ Attendance migration skipped: {e}")
    # Auto-migrate: add new teacher columns if missing
    try:
        from database import engine
        async with engine.begin() as conn:
            for col in ['city VARCHAR(100)', 'state VARCHAR(100)', 'pincode VARCHAR(10)',
                        'emergency_contact VARCHAR(15)', 'emergency_contact_name VARCHAR(200)',
                        'uses_transport BOOLEAN DEFAULT false', 'transport_route VARCHAR(100)']:
                col_name = col.split()[0]
                await conn.execute(sa_text(
                    f"ALTER TABLE teachers ADD COLUMN IF NOT EXISTS {col_name} {' '.join(col.split()[1:])};"
                ))
        print("✅ Teacher columns verified")
    except Exception as e:
        print(f"⚠️ Teacher migration skipped: {e}")
    # Auto-migrate: create photo_change_requests table if not exists
    try:
        from database import engine
        async with engine.begin() as conn:
            await conn.execute(sa_text("""
                CREATE TABLE IF NOT EXISTS photo_change_requests (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    branch_id UUID NOT NULL REFERENCES branches(id),
                    entity_type VARCHAR(20) NOT NULL,
                    entity_id UUID NOT NULL,
                    requested_by UUID REFERENCES users(id),
                    current_photo_url VARCHAR(500),
                    new_photo_url VARCHAR(500) NOT NULL,
                    status VARCHAR(20) DEFAULT 'pending',
                    reviewed_by UUID REFERENCES users(id),
                    reviewed_at TIMESTAMP,
                    rejection_reason TEXT,
                    created_at TIMESTAMP DEFAULT NOW()
                );
            """))
        print("✅ Photo change requests table verified")
    except Exception as e:
        print(f"⚠️ Photo requests migration skipped: {e}")
    # Auto-migrate: add health-check columns to online_platform_configs if missing
    try:
        from database import engine
        async with engine.begin() as conn:
            opc_cols = [
                'google_last_verified TIMESTAMP',
                'google_error VARCHAR(500)',
                'zoom_last_verified TIMESTAMP',
                'zoom_error VARCHAR(500)',
                'teams_last_verified TIMESTAMP',
                'teams_error VARCHAR(500)',
                'updated_at TIMESTAMP',
            ]
            for col in opc_cols:
                col_name = col.split()[0]
                col_def = ' '.join(col.split()[1:])
                await conn.execute(sa_text(
                    f"ALTER TABLE online_platform_configs ADD COLUMN IF NOT EXISTS {col_name} {col_def};"
                ))
        print("✅ Online platform config columns verified")
    except Exception as e:
        print(f"⚠️ Online platform config migration skipped: {e}")

    # ── Leave requests — add on-behalf columns ──
    try:
        from database import engine as _engine2
        async with _engine2.begin() as conn:
            for col_sql in [
                "applied_on_behalf_by UUID",
                "on_behalf_name VARCHAR(200)",
            ]:
                await conn.execute(sa_text(
                    f"ALTER TABLE leave_requests ADD COLUMN IF NOT EXISTS {col_sql};"
                ))
        print("✅ Leave request on-behalf columns verified")
    except Exception as e:
        print(f"⚠️ Leave request migration skipped: {e}")

    # ── Activities — add target_audience + published_at columns ──
    try:
        from database import engine as _engine3
        async with _engine3.begin() as conn:
            for col_sql in [
                "target_audience JSONB",
                "published_at TIMESTAMP",
            ]:
                await conn.execute(sa_text(
                    f"ALTER TABLE activities ADD COLUMN IF NOT EXISTS {col_sql};"
                ))
        print("✅ Activities target/publish columns verified")
    except Exception as e:
        print(f"⚠️ Activities migration skipped: {e}")

    # ── Exams — add applicable_classes column ──
    try:
        from database import engine as _engine4
        async with _engine4.begin() as conn:
            await conn.execute(sa_text(
                "ALTER TABLE exams ADD COLUMN IF NOT EXISTS applicable_classes JSONB;"
            ))
        print("✅ Exams applicable_classes column verified")
    except Exception as e:
        print(f"⚠️ Exams migration skipped: {e}")

    # ── CommunicationConfig — add sms_route_id column ──
    try:
        from database import engine as _engine5
        async with _engine5.begin() as conn:
            await conn.execute(sa_text(
                "ALTER TABLE communication_configs ADD COLUMN IF NOT EXISTS sms_route_id VARCHAR(10) DEFAULT '8';"
            ))
        print("✅ CommunicationConfig sms_route_id column verified")
    except Exception as e:
        print(f"⚠️ CommunicationConfig migration skipped: {e}")

    # ── Branch — add subdomain column for multi-tenant school URLs ──
    try:
        from database import engine as _engine6
        async with _engine6.begin() as conn:
            await conn.execute(sa_text(
                "ALTER TABLE branches ADD COLUMN IF NOT EXISTS subdomain VARCHAR(63);"
            ))
            # Create unique index if not exists
            await conn.execute(sa_text(
                "CREATE UNIQUE INDEX IF NOT EXISTS ix_branches_subdomain ON branches (subdomain) WHERE subdomain IS NOT NULL;"
            ))
        print("✅ Branch subdomain column verified")
    except Exception as e:
        print(f"⚠️ Branch subdomain migration skipped: {e}")

    # ── Branch maintenance columns ──
    try:
        from database import engine as _engine_maint
        async with _engine_maint.begin() as conn:
            await conn.execute(sa_text("ALTER TABLE branches ADD COLUMN IF NOT EXISTS maintenance_mode BOOLEAN DEFAULT FALSE;"))
            await conn.execute(sa_text("ALTER TABLE branches ADD COLUMN IF NOT EXISTS maintenance_message TEXT;"))
            await conn.execute(sa_text("ALTER TABLE branches ADD COLUMN IF NOT EXISTS maintenance_eta VARCHAR(100);"))
        print("✅ Branch maintenance columns verified")
    except Exception as e:
        print(f"⚠️ Branch maintenance migration skipped: {e}")

    # ── PlatformConfig — create table if not exists ──
    try:
        from database import engine as _engine7
        async with _engine7.begin() as conn:
            await conn.execute(sa_text("""
                CREATE TABLE IF NOT EXISTS platform_configs (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    config JSONB DEFAULT '{}',
                    updated_at TIMESTAMP DEFAULT NOW()
                );
            """))
        print("✅ Platform config table verified")
    except Exception as e:
        print(f"⚠️ Platform config migration skipped: {e}")

    # ── Backup Records table ──
    try:
        from database import engine as _engine_bk
        async with _engine_bk.begin() as conn:
            await conn.execute(sa_text("""
                CREATE TABLE IF NOT EXISTS backup_records (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    branch_id UUID NOT NULL REFERENCES branches(id),
                    org_id UUID NOT NULL REFERENCES organizations(id),
                    file_path VARCHAR(500),
                    file_name VARCHAR(200),
                    file_size_bytes BIGINT DEFAULT 0,
                    backup_type VARCHAR(20) DEFAULT 'manual',
                    status VARCHAR(20) DEFAULT 'in_progress',
                    tables_included JSONB,
                    record_counts JSONB,
                    error_message TEXT,
                    started_at TIMESTAMP DEFAULT NOW(),
                    completed_at TIMESTAMP,
                    triggered_by UUID REFERENCES users(id),
                    is_active BOOLEAN DEFAULT true,
                    created_at TIMESTAMP DEFAULT NOW()
                );
            """))
        print("✅ Backup records table verified")
    except Exception as e:
        print(f"⚠️ Backup records migration skipped: {e}")

    # ── Coupons + Redemptions tables ──
    try:
        from database import engine as _engine_cp
        async with _engine_cp.begin() as conn:
            await conn.execute(sa_text("""
                CREATE TABLE IF NOT EXISTS coupons (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    code VARCHAR(50) UNIQUE NOT NULL,
                    description VARCHAR(300),
                    discount_type VARCHAR(20) DEFAULT 'percentage',
                    discount_value NUMERIC(10,2) NOT NULL,
                    max_discount_amount NUMERIC(10,2),
                    min_plan_amount NUMERIC(10,2) DEFAULT 0,
                    applicable_plans JSONB,
                    applicable_tiers JSONB,
                    max_uses INTEGER DEFAULT 100,
                    max_uses_per_branch INTEGER DEFAULT 1,
                    used_count INTEGER DEFAULT 0,
                    valid_from TIMESTAMP NOT NULL,
                    valid_until TIMESTAMP NOT NULL,
                    is_active BOOLEAN DEFAULT true,
                    created_by UUID REFERENCES users(id),
                    created_at TIMESTAMP DEFAULT NOW(),
                    updated_at TIMESTAMP DEFAULT NOW()
                );
            """))
            await conn.execute(sa_text("""
                CREATE TABLE IF NOT EXISTS coupon_redemptions (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    coupon_id UUID NOT NULL REFERENCES coupons(id),
                    branch_id UUID NOT NULL REFERENCES branches(id),
                    subscription_id UUID REFERENCES school_subscriptions(id),
                    payment_id UUID REFERENCES payment_history(id),
                    original_amount NUMERIC(10,2) NOT NULL,
                    discount_applied NUMERIC(10,2) NOT NULL,
                    final_amount NUMERIC(10,2) NOT NULL,
                    redeemed_at TIMESTAMP DEFAULT NOW(),
                    redeemed_by UUID REFERENCES users(id)
                );
            """))
        print("✅ Coupons & redemptions tables verified")
    except Exception as e:
        print(f"⚠️ Coupons migration skipped: {e}")

    # ── Invoices table ──
    try:
        from database import engine as _engine_inv
        async with _engine_inv.begin() as conn:
            await conn.execute(sa_text("""
                CREATE TABLE IF NOT EXISTS invoices (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    invoice_number VARCHAR(50) UNIQUE NOT NULL,
                    org_id UUID NOT NULL REFERENCES organizations(id),
                    branch_id UUID NOT NULL REFERENCES branches(id),
                    subscription_id UUID REFERENCES school_subscriptions(id),
                    payment_id UUID REFERENCES payment_history(id),
                    supplier_name VARCHAR(300),
                    supplier_gstin VARCHAR(15),
                    supplier_address TEXT,
                    supplier_state_code VARCHAR(2),
                    buyer_name VARCHAR(300),
                    buyer_gstin VARCHAR(15),
                    buyer_address TEXT,
                    buyer_state_code VARCHAR(2),
                    line_items JSONB,
                    subtotal NUMERIC(10,2) DEFAULT 0,
                    discount_amount NUMERIC(10,2) DEFAULT 0,
                    coupon_code VARCHAR(50),
                    taxable_amount NUMERIC(10,2) DEFAULT 0,
                    cgst_rate NUMERIC(5,2) DEFAULT 0,
                    cgst_amount NUMERIC(10,2) DEFAULT 0,
                    sgst_rate NUMERIC(5,2) DEFAULT 0,
                    sgst_amount NUMERIC(10,2) DEFAULT 0,
                    igst_rate NUMERIC(5,2) DEFAULT 0,
                    igst_amount NUMERIC(10,2) DEFAULT 0,
                    total_tax NUMERIC(10,2) DEFAULT 0,
                    total_amount NUMERIC(10,2) DEFAULT 0,
                    invoice_date DATE DEFAULT CURRENT_DATE,
                    due_date DATE,
                    paid_date DATE,
                    status VARCHAR(20) DEFAULT 'draft',
                    pdf_path VARCHAR(500),
                    notes TEXT,
                    is_active BOOLEAN DEFAULT true,
                    created_at TIMESTAMP DEFAULT NOW(),
                    updated_at TIMESTAMP DEFAULT NOW()
                );
            """))
        print("✅ Invoices table verified")
    except Exception as e:
        print(f"⚠️ Invoices migration skipped: {e}")

    # ── Organization billing columns (GST) ──
    try:
        from database import engine as _engine_org_gst
        async with _engine_org_gst.begin() as conn:
            for col_sql in [
                "gstin VARCHAR(15)",
                "billing_name VARCHAR(300)",
                "billing_address TEXT",
                "billing_state_code VARCHAR(2)",
            ]:
                col_name = col_sql.split()[0]
                await conn.execute(sa_text(
                    f"ALTER TABLE organizations ADD COLUMN IF NOT EXISTS {col_sql};"
                ))
        print("✅ Organization GST/billing columns verified")
    except Exception as e:
        print(f"⚠️ Organization GST migration skipped: {e}")

    # ── SchoolSubscription late-fee columns ──
    try:
        from database import engine as _engine_late
        async with _engine_late.begin() as conn:
            for col_sql in [
                "late_fee_amount NUMERIC(10,2) DEFAULT 0",
                "late_fee_applied_at TIMESTAMP",
                "late_fee_waived BOOLEAN DEFAULT false",
                "late_fee_waived_at TIMESTAMP",
                "late_fee_waived_by UUID",
            ]:
                col_name = col_sql.split()[0]
                await conn.execute(sa_text(
                    f"ALTER TABLE school_subscriptions ADD COLUMN IF NOT EXISTS {col_sql};"
                ))
        print("✅ Subscription late-fee columns verified")
    except Exception as e:
        print(f"⚠️ Subscription late-fee migration skipped: {e}")

    # ── Plan late-fee config columns ──
    try:
        from database import engine as _engine_plan_late
        async with _engine_plan_late.begin() as conn:
            for col_sql in [
                "late_fee_type VARCHAR(20) DEFAULT 'percentage'",
                "late_fee_value NUMERIC(10,2) DEFAULT 5",
                "late_fee_grace_days INTEGER DEFAULT 7",
            ]:
                col_name = col_sql.split()[0]
                await conn.execute(sa_text(
                    f"ALTER TABLE plans ADD COLUMN IF NOT EXISTS {col_sql};"
                ))
        print("✅ Plan late-fee config columns verified")
    except Exception as e:
        print(f"⚠️ Plan late-fee config migration skipped: {e}")

    # ── PaymentHistory coupon & late-fee columns ──
    try:
        from database import engine as _engine_ph
        async with _engine_ph.begin() as conn:
            for col_sql in [
                "coupon_code VARCHAR(50)",
                "includes_late_fee BOOLEAN DEFAULT false",
                "late_fee_amount NUMERIC(10,2) DEFAULT 0",
            ]:
                col_name = col_sql.split()[0]
                await conn.execute(sa_text(
                    f"ALTER TABLE payment_history ADD COLUMN IF NOT EXISTS {col_sql};"
                ))
        print("✅ PaymentHistory coupon/late-fee columns verified")
    except Exception as e:
        print(f"⚠️ PaymentHistory migration skipped: {e}")

    # ── Create backups directory ──
    import os as _os_bk
    _os_bk.makedirs("backups", exist_ok=True)
    # ── Create invoices directory ──
    _os_bk.makedirs("static/invoices", exist_ok=True)

    # Initialize i18n
    try:
        from utils.i18n import init_i18n, inject_i18n
        init_i18n()
        # Inject t() into ALL route template engines
        import routes.auth, routes.school_admin, routes.teacher, routes.student
        import routes.parent, routes.chairman, routes.hr, routes.transport, routes.extended_modules, routes.super_admin
        for mod in [routes.auth, routes.school_admin, routes.teacher, routes.student,
                     routes.parent, routes.chairman, routes.hr, routes.transport, routes.extended_modules, routes.super_admin]:
            if hasattr(mod, 'templates'):
                inject_i18n(mod.templates)
        print("🌐 i18n initialized — languages loaded, templates patched")
    except Exception as e:
        print(f"⚠️ i18n init skipped: {e}")
    await create_super_admin()
    # Start automation scheduler
    try:
        from utils.scheduler import start_scheduler, stop_scheduler
        await start_scheduler(app)
        print("Scheduler started -- 4 automation jobs active")
    except Exception as e:
        print(f"Scheduler init skipped: {e}")
    print(f"Server running at http://localhost:8000")
    print(f"Login: {settings.SUPER_ADMIN_EMAIL}")
    yield
    # Shutdown
    try:
        from utils.scheduler import stop_scheduler
        stop_scheduler()
    except Exception:
        pass
    print("Shutting down VedaSchoolPro...")


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    lifespan=lifespan,
)

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Subdomain middleware — extracts school context from URL (runs first)
from utils.subdomain import SubdomainMiddleware
app.add_middleware(SubdomainMiddleware)

# i18n middleware — must be BEFORE CSRF so it runs first
from utils.i18n import I18nMiddleware
app.add_middleware(I18nMiddleware)

# Security middleware
from utils.csrf import CSRFMiddleware
app.add_middleware(CSRFMiddleware)

# Security headers
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        return response

app.add_middleware(SecurityHeadersMiddleware)


# ── Maintenance Mode Middleware ─────────────────────
class MaintenanceModeMiddleware(BaseHTTPMiddleware):
    """Block non-super-admin access when platform OR branch maintenance mode is ON."""
    async def dispatch(self, request, call_next):
        path = request.url.path
        # Always allow: static files, login page, super-admin routes, API auth
        skip_paths = ("/static", "/login", "/api/auth", "/super-admin", "/api/super-admin", "/maintenance", "/favicon")
        if any(path.startswith(p) for p in skip_paths):
            return await call_next(request)

        try:
            from database import AsyncSessionLocal
            from models.branch import PlatformConfig
            async with AsyncSessionLocal() as db:
                # 1) Platform-level maintenance — blocks everything
                result = await db.execute(select(PlatformConfig))
                pc = result.scalar_one_or_none()
                if pc and pc.config and pc.config.get("maintenance_mode"):
                    from starlette.responses import HTMLResponse
                    msg = pc.config.get("maintenance_message", "")
                    eta = pc.config.get("maintenance_eta", "")
                    html = templates.get_template("maintenance.html").render(
                        message=msg, eta=eta,
                        branch_name="", branch_logo="", branch_motto=""
                    )
                    return HTMLResponse(content=html, status_code=503)

                # 2) Branch-level maintenance — check if the logged-in user's branch is in maintenance
                from utils.auth import decode_access_token
                token = request.cookies.get("access_token")
                if token:
                    payload = decode_access_token(token)
                    if payload and payload.get("branch_id") and payload.get("role") != "super_admin":
                        from models.branch import Branch
                        import uuid as _uuid
                        branch = await db.scalar(
                            select(Branch).where(Branch.id == _uuid.UUID(payload["branch_id"]))
                        )
                        if branch and branch.maintenance_mode:
                            from starlette.responses import HTMLResponse
                            msg = branch.maintenance_message or f"{branch.name} is currently under maintenance."
                            eta = branch.maintenance_eta or ""
                            html = templates.get_template("maintenance.html").render(
                                message=msg, eta=eta,
                                branch_name=branch.name or "",
                                branch_logo=branch.logo_url or "",
                                branch_motto=branch.motto or "",
                            )
                            return HTMLResponse(content=html, status_code=503)
        except Exception:
            pass  # If DB is unreachable, let the request through

        return await call_next(request)

app.add_middleware(MaintenanceModeMiddleware)

# Include routers
app.include_router(auth_router)
app.include_router(super_admin_router)
app.include_router(super_admin_api_router)
app.include_router(school_admin_router)
app.include_router(school_admin_api_router)
app.include_router(teacher_router)
app.include_router(teacher_api_router)
app.include_router(student_router)
app.include_router(student_analytics_api_router)
app.include_router(teacher_remarks_api_router)
app.include_router(student_remarks_api_router)
app.include_router(sprint21_api_router)
app.include_router(parent_api_router)
app.include_router(parent_router)
app.include_router(transport_router)
app.include_router(transport_api_router)
app.include_router(hr_router)
app.include_router(hr_api_router)
app.include_router(chairman_router)
app.include_router(chairman_api_router)
app.include_router(extended_router)
app.include_router(extended_api_router)
app.include_router(analytics_api_router)
app.include_router(onboarding_api_router)
app.include_router(help_api_router)
app.include_router(messaging_api_router)
app.include_router(payment_api_router)
app.include_router(mobile_api_router)
app.include_router(report_card_api_router)
app.include_router(asset_api_router)
app.include_router(timetable_api_router)  # Timetable V2 — bell schedules, substitutions, subject hours
app.include_router(online_class_api_router)  # Online Classes — Google Meet, Zoom, Teams
app.include_router(account_api_router)  # My Account — password, phone, email changes

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)