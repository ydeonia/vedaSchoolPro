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
from routes.api.parent_api import router as parent_api_router
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
            print(f"✅ Super Admin created: {settings.SUPER_ADMIN_EMAIL} / {settings.SUPER_ADMIN_PASSWORD}")
        else:
            print("✅ Super Admin already exists")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    print("🚀 Starting EduFlow School Management System...")
    await init_db()
    print("✅ Database tables created")
    # Initialize i18n
    try:
        from utils.i18n import init_i18n
        init_i18n()
        print("🌐 i18n initialized — languages loaded")
    except Exception as e:
        print(f"⚠️ i18n init skipped: {e}")
    await create_super_admin()
    print(f"🌐 Server running at http://localhost:8000")
    print(f"📧 Login: {settings.SUPER_ADMIN_EMAIL} / {settings.SUPER_ADMIN_PASSWORD}")
    yield
    # Shutdown
    print("👋 Shutting down EduFlow...")


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    lifespan=lifespan,
)

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

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
app.include_router(parent_api_router)
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


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)