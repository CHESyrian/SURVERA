"""
Test settings – fast and isolated.
"""
from .base import *  # noqa: F403

DEBUG = False
ALLOWED_HOSTS = ["testserver", "localhost", "127.0.0.1"]

# Use in-memory SQLite for speed (or keep PostgreSQL if you prefer)
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}

# Faster password hasher
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.MD5PasswordHasher",
]

# Disable migrations for speed (optional – comment out if you need real migrations in tests)
# class DisableMigrations:
#     def __contains__(self, item):
#         return True
#     def __getitem__(self, item):
#         return None
# MIGRATION_MODULES = DisableMigrations()

EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
# Tests assert against this fixed receiver address.
EMAIL_FOR_TEST = "surveracorp.test@gmail.com"
EMAIL_REDIRECT_TO_TEST = False  # use real user.email in unit tests unless overridden

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
    }
}

CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True

# CAPTCHA off in tests (forms stay simple; dedicated tests mock verify)
TURNSTILE_ENABLED = False
TURNSTILE_SITE_KEY = ""
TURNSTILE_SECRET_KEY = ""

# Quiet logging during tests
LOGGING["root"]["level"] = "WARNING"  # noqa: F405
