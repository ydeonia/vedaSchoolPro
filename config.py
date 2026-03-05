"""
VedaFlow Configuration — loaded from environment variables with safe defaults.
See .env.example for all available settings.
"""
import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    # ── App Identity ──────────────────────────────────────
    APP_NAME: str = "EduFlow — School Management System"
    APP_VERSION: str = "1.1.0"
    APP_TAGLINE: str = "Beautiful School Management, Simplified."

    # ── Database ──────────────────────────────────────────
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        "postgresql+asyncpg://postgres:postgres@localhost:5432/school_saas"
    )
    DATABASE_URL_SYNC: str = os.getenv(
        "DATABASE_URL_SYNC",
        "postgresql+psycopg2://postgres:postgres@localhost:5432/school_saas"
    )

    # ── Security ──────────────────────────────────────────
    SECRET_KEY: str = os.getenv("SECRET_KEY", "change-this-to-a-very-long-random-secret-key-in-production")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 24 hours
    DEBUG: bool = os.getenv("DEBUG", "false").lower() == "true"

    # ── Super Admin (initial bootstrap) ───────────────────
    SUPER_ADMIN_EMAIL: str = os.getenv("SUPER_ADMIN_EMAIL", "admin@eduflow.in")
    SUPER_ADMIN_PASSWORD: str = os.getenv("SUPER_ADMIN_PASSWORD", "Admin@123")
    SUPER_ADMIN_PHONE: str = os.getenv("SUPER_ADMIN_PHONE", "9999999999")

    # ── File Uploads ──────────────────────────────────────
    UPLOAD_DIR: str = os.getenv("UPLOAD_DIR", "static/uploads")
    MAX_UPLOAD_SIZE: int = 10 * 1024 * 1024  # 10 MB

    # ── Communication ─────────────────────────────────────
    DEFAULT_SMS_PROVIDER: str = "msg91"
    DEFAULT_WHATSAPP_PROVIDER: str = "meta"

    # ── Payment Gateways ──────────────────────────────────
    PAYMENT_GATEWAYS: list = ["razorpay", "phonepe", "upi_direct", "paytm"]

    # ── Online Classes (OAuth) ──────────────────────────
    GOOGLE_CLIENT_ID: str = os.getenv("GOOGLE_CLIENT_ID", "")
    GOOGLE_CLIENT_SECRET: str = os.getenv("GOOGLE_CLIENT_SECRET", "")
    TEAMS_CLIENT_ID: str = os.getenv("TEAMS_CLIENT_ID", "")
    TEAMS_CLIENT_SECRET: str = os.getenv("TEAMS_CLIENT_SECRET", "")

    # ── Scheduler / Automation ──────────────────────────
    SCHEDULER_ENABLED: bool = os.getenv("SCHEDULER_ENABLED", "true").lower() == "true"
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")


settings = Settings()
