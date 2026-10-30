"""Application configuration.

Secrets come from environment variables; the fallbacks exist only so the project
runs out of the box on a development machine. APP_ENV=production selects
ProductionConfig.
"""
import os
from datetime import timedelta

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
INSTANCE_DIR = os.path.join(BASE_DIR, "instance")
DEV_SECRET_KEY = "dev-only-change-me"


def database_url(raw: str | None) -> str:
    """DATABASE_URL -> SQLAlchemy URL (postgres:// URLs use the psycopg 3 driver)."""
    if not raw:
        return "sqlite:///" + os.path.join(INSTANCE_DIR, "nofai.db")
    for prefix in ("postgres://", "postgresql://"):
        if raw.startswith(prefix):
            return "postgresql+psycopg://" + raw[len(prefix):]
    return raw


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", DEV_SECRET_KEY)

    SQLALCHEMY_DATABASE_URI = database_url(os.environ.get("DATABASE_URL"))
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True}

    # Languages: the first is the fallback when the browser expresses no preference
    LANGUAGES = ("en", "he")
    DEFAULT_LANGUAGE = "en"

    # Admin account created by `flask seed`
    ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "nofar")
    ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "ChangeMe123!")

    # Uploaded images (local storage; see nofai/storage.py)
    UPLOAD_DIR = os.environ.get("UPLOAD_DIR", os.path.join(INSTANCE_DIR, "uploads"))
    MAX_CONTENT_LENGTH = 40 * 1024 * 1024        # whole request (several images at once)
    MAX_IMAGE_BYTES = 15 * 1024 * 1024           # a single file
    IMAGE_MAX_SIDE = 2400                        # longer side after resizing, px

    # New-inquiry e-mail. Unset SMTP_HOST = notifications are only written to the log.
    SMTP_HOST = os.environ.get("SMTP_HOST", "")
    SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
    SMTP_USERNAME = os.environ.get("SMTP_USERNAME", "")
    SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
    MAIL_FROM = os.environ.get("MAIL_FROM", "")
    NOTIFY_EMAIL = os.environ.get("NOTIFY_EMAIL", "")

    # Session cookie hardening
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    PERMANENT_SESSION_LIFETIME = timedelta(hours=12)

    # Admin login brute-force protection
    LOGIN_MAX_ATTEMPTS = 5
    LOGIN_LOCKOUT_SECONDS = 15 * 60

    TRUST_PROXY = os.environ.get("TRUST_PROXY", "0") == "1"
    HSTS = False


class ProductionConfig(Config):
    DEBUG = False
    SESSION_COOKIE_SECURE = True
    REMEMBER_COOKIE_SECURE = True
    PREFERRED_URL_SCHEME = "https"
    HSTS = True
    TRUST_PROXY = os.environ.get("TRUST_PROXY", "1") == "1"


def get_config():
    return ProductionConfig if os.environ.get("APP_ENV") == "production" else Config
