"""
Production settings for VPS deployment.

Database: SQLite by default (file under BASE_DIR/data/).
Override with DATABASE_URL only if you intentionally switch engines.
"""
from pathlib import Path

from .base import *  # noqa: F403

DEBUG = False

# These must be set via environment variables in production
SECRET_KEY = env("SECRET_KEY")  # noqa: F405
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS")  # noqa: F405

# Required for HTTPS forms (login, CSRF POSTs) behind a real domain
CSRF_TRUSTED_ORIGINS = env.list("CSRF_TRUSTED_ORIGINS", default=[])  # noqa: F405

# -----------------------------------------------------------------------------
# Database — SQLite (production default)
# -----------------------------------------------------------------------------
_sqlite_name = env("SQLITE_PATH", default="")  # noqa: F405
if _sqlite_name:
    _db_path = Path(_sqlite_name)
else:
    _db_path = BASE_DIR / "data" / "survera_db.sqlite3"  # noqa: F405

_db_path.parent.mkdir(parents=True, exist_ok=True)

# Prefer explicit SQLITE_PATH / default file. DATABASE_URL may still point at
# sqlite:///... if set; otherwise we force SQLite and ignore a postgres default
# inherited from base settings.
if env("DATABASE_URL", default="").startswith("sqlite"):  # noqa: F405
    DATABASES = {
        "default": env.db("DATABASE_URL")  # noqa: F405
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": str(_db_path),
            "OPTIONS": {
                # Reduce "database is locked" under modest concurrent writes
                "timeout": 20,
            },
        }
    }
DATABASES["default"]["ATOMIC_REQUESTS"] = True

# Security hardening
SECURE_SSL_REDIRECT = env.bool("SECURE_SSL_REDIRECT", default=True)  # noqa: F405
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
# USE_X_FORWARDED_HOST = True  # enable only if Nginx rewrites Host

# Email (Django 6.1+ MAILERS; configure real SMTP via env in production)
_prod_backend = env(
    "EMAIL_BACKEND",
    default="django.core.mail.backends.smtp.EmailBackend",
)  # noqa: F405
_prod_host = env("EMAIL_HOST", default="")  # noqa: F405
_prod_port = env.int("EMAIL_PORT", default=587)  # noqa: F405
_prod_user = env("EMAIL_HOST_USER", default="")  # noqa: F405
_prod_password = env("EMAIL_HOST_PASSWORD", default="")  # noqa: F405
_prod_use_tls = env.bool("EMAIL_USE_TLS", default=True)  # noqa: F405
_prod_use_ssl = env.bool("EMAIL_USE_SSL", default=False)  # noqa: F405

MAILERS = {
    "default": {
        "BACKEND": _prod_backend,
        "OPTIONS": {
            "host": _prod_host,
            "port": _prod_port,
            "username": _prod_user,
            "password": _prod_password,
            "use_tls": _prod_use_tls,
            "use_ssl": _prod_use_ssl,
        },
    },
}
# Legacy aliases (still useful for conditionals / third-party code)
EMAIL_BACKEND = _prod_backend
EMAIL_HOST = _prod_host
EMAIL_PORT = _prod_port
EMAIL_HOST_USER = _prod_user
EMAIL_HOST_PASSWORD = _prod_password
EMAIL_USE_TLS = _prod_use_tls
EMAIL_USE_SSL = _prod_use_ssl

# Logging to file on VPS
LOGGING["handlers"]["file"] = {  # noqa: F405
    "class": "logging.handlers.RotatingFileHandler",
    "filename": BASE_DIR / "logs" / "django.log",  # noqa: F405
    "maxBytes": 10 * 1024 * 1024,  # 10 MB
    "backupCount": 5,
    "formatter": "verbose",
}
LOGGING["root"]["handlers"] = ["console", "file"]  # noqa: F405
