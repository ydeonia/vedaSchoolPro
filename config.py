import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    APP_NAME: str = "EduFlow — School Management System"
    APP_VERSION: str = "1.0.0"
    APP_TAGLINE: str = "Beautiful School Management, Simplified."

    # Database
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        "postgresql+asyncpg://postgres:postgres@localhost:5432/school_saas"
    )
    DATABASE_URL_SYNC: str = os.getenv(
        "DATABASE_URL_SYNC",
        "postgresql+psycopg2://postgres:postgres@localhost:5432/school_saas"
    )

    # Security
    SECRET_KEY: str = os.getenv("SECRET_KEY", "change-this-to-a-very-long-random-secret-key-in-production")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 24 hours

    # Super Admin defaults
    SUPER_ADMIN_EMAIL: str = os.getenv("SUPER_ADMIN_EMAIL", "admin@eduflow.in")
    SUPER_ADMIN_PASSWORD: str = os.getenv("SUPER_ADMIN_PASSWORD", "Admin@123")
    SUPER_ADMIN_PHONE: str = os.getenv("SUPER_ADMIN_PHONE", "9999999999")

    # File uploads
    UPLOAD_DIR: str = os.getenv("UPLOAD_DIR", "static/uploads")
    MAX_UPLOAD_SIZE: int = 10 * 1024 * 1024  # 10MB

    # Communication defaults (schools configure their own)
    DEFAULT_SMS_PROVIDER: str = "msg91"  # msg91, twilio
    DEFAULT_WHATSAPP_PROVIDER: str = "meta"  # meta business API

    # Supported Payment Gateways
    PAYMENT_GATEWAYS: list = ["razorpay", "phonepe", "upi_direct", "paytm"]


settings = Settings()
