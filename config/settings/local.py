"""
Local development settings.
"""
from .base import *  # noqa: F403

DEBUG = True

ALLOWED_HOSTS = ["localhost", "127.0.0.1", "[::1]"]

# Faster password hashing for development
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.MD5PasswordHasher",
]

# Django Debug Toolbar (optional)
INSTALLED_APPS += ["debug_toolbar"]  # noqa: F405
MIDDLEWARE.insert(0, "debug_toolbar.middleware.DebugToolbarMiddleware")  # noqa: F405
INTERNAL_IPS = ["127.0.0.1"]

# Email: console by default. Use real SMTP when EMAIL_HOST is set in .env
# (e.g. smtp.gmail.com + App Password) so send_test_email can reach a real inbox.
if EMAIL_HOST:  # noqa: F405
    _local_backend = env(  # noqa: F405
        "EMAIL_BACKEND",
        default="django.core.mail.backends.smtp.EmailBackend",
    )
else:
    _local_backend = "django.core.mail.backends.console.EmailBackend"

MAILERS = {  # noqa: F405
    "default": {
        "BACKEND": _local_backend,
        "OPTIONS": {
            "host": EMAIL_HOST,  # noqa: F405
            "port": EMAIL_PORT,  # noqa: F405
            "username": EMAIL_HOST_USER,  # noqa: F405
            "password": EMAIL_HOST_PASSWORD,  # noqa: F405
            "use_tls": EMAIL_USE_TLS,  # noqa: F405
            "use_ssl": EMAIL_USE_SSL,  # noqa: F405
        },
    },
}
# Keep legacy name available for any code still reading settings.EMAIL_BACKEND
EMAIL_BACKEND = _local_backend

# Default: redirect when EMAIL_FOR_TEST is set (override with EMAIL_REDIRECT_TO_TEST=False)
EMAIL_REDIRECT_TO_TEST = env.bool(  # noqa: F405
    "EMAIL_REDIRECT_TO_TEST",
    default=bool(EMAIL_FOR_TEST),  # noqa: F405
)

# Simpler static files in development (override base STORAGES)
STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
    },
}

# Optional: use SQLite for quick local experiments (uncomment if needed)
# DATABASES = {
#     "default": {
#         "ENGINE": "django.db.backends.sqlite3",
#         "NAME": BASE_DIR / "data" / "survera_db.sqlite3",
#     }
# }
