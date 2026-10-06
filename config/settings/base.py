"""
Base settings for SURVERA.
Shared by all environments.
"""
from pathlib import Path

import environ

# -----------------------------------------------------------------------------
# Paths
# -----------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# -----------------------------------------------------------------------------
# Environment
# -----------------------------------------------------------------------------
env = environ.Env(
    DEBUG=(bool, False),
    ALLOWED_HOSTS=(list, []),
)

# Read .env file if it exists (local development)
environ.Env.read_env(BASE_DIR / ".env")

# -----------------------------------------------------------------------------
# Core
# -----------------------------------------------------------------------------
SECRET_KEY = env("SECRET_KEY", default="django-insecure-change-me-in-production")

DEBUG = env("DEBUG")

ALLOWED_HOSTS = env("ALLOWED_HOSTS")

# -----------------------------------------------------------------------------
# Applications
# -----------------------------------------------------------------------------
DJANGO_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
]

THIRD_PARTY_APPS = [
    "django_htmx",
    "modeltranslation",  # must be before apps that use it
    "crispy_forms",
    "crispy_bootstrap5",
]

LOCAL_APPS = [
    "apps.common",
    "apps.accounts",
    "apps.companies",
    "apps.surveys",
    "apps.responses",
    "apps.rewards",
    "apps.notifications",
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

# -----------------------------------------------------------------------------
# Middleware
# -----------------------------------------------------------------------------
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",  # i18n
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "django_htmx.middleware.HtmxMiddleware",
]

ROOT_URLCONF = "config.urls"

# -----------------------------------------------------------------------------
# Templates
# -----------------------------------------------------------------------------
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "django.template.context_processors.i18n",
                "apps.notifications.context_processors.notifications_badge",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

# -----------------------------------------------------------------------------
# Database
# -----------------------------------------------------------------------------
DATABASES = {
    "default": env.db(
        "DATABASE_URL",
        default="postgres://admin:password@localhost:5432/survera_db",
    )
}
DATABASES["default"]["ATOMIC_REQUESTS"] = True

# -----------------------------------------------------------------------------
# Authentication
# -----------------------------------------------------------------------------
AUTH_USER_MODEL = "accounts.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LOGIN_URL = "accounts:login"
LOGIN_REDIRECT_URL = "home"
LOGOUT_REDIRECT_URL = "home"
# Authentication uses email (USERNAME_FIELD on custom User)
AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",
]

# -----------------------------------------------------------------------------
# Internationalization (English + Arabic)
# -----------------------------------------------------------------------------
LANGUAGE_CODE = "en"
LANGUAGES = [
    ("en", "English"),
    ("ar", "العربية"),
]
LOCALE_PATHS = [BASE_DIR / "locale"]
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

# Language cookie (set_language view from django.conf.urls.i18n)
LANGUAGE_COOKIE_NAME = "django_language"
LANGUAGE_COOKIE_AGE = 60 * 60 * 24 * 365  # 1 year
LANGUAGE_COOKIE_HTTPONLY = False
LANGUAGE_COOKIE_SAMESITE = "Lax"

# Modeltranslation (will be configured per model later)
MODELTRANSLATION_DEFAULT_LANGUAGE = "en"
MODELTRANSLATION_LANGUAGES = ("en", "ar")

# -----------------------------------------------------------------------------
# Static & Media
# -----------------------------------------------------------------------------
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

# Django 4.2+ / 6.x preferred storage config (replaces STATICFILES_STORAGE)
STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

# -----------------------------------------------------------------------------
# Default primary key
# -----------------------------------------------------------------------------
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# -----------------------------------------------------------------------------
# Redis / Cache
# -----------------------------------------------------------------------------
REDIS_URL = env("REDIS_URL", default="redis://localhost:6379/0")

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": REDIS_URL,
    }
}

# -----------------------------------------------------------------------------
# Celery
# -----------------------------------------------------------------------------
CELERY_BROKER_URL = env("CELERY_BROKER_URL", default=REDIS_URL)
CELERY_RESULT_BACKEND = env("CELERY_RESULT_BACKEND", default=REDIS_URL)
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = TIME_ZONE
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_TIME_LIMIT = 30 * 60

# Periodic digests (requires celery beat process)
CELERY_BEAT_SCHEDULE = {
    "notifications-daily-digest": {
        "task": "notifications.send_daily_digests",
        "schedule": 60 * 60 * 24,  # every 24 hours
    },
    "notifications-weekly-digest": {
        "task": "notifications.send_weekly_digests",
        "schedule": 60 * 60 * 24 * 7,  # every 7 days
    },
}

# -----------------------------------------------------------------------------
# Email (Django 6.1+ MAILERS; env names kept for .env compatibility)
# -----------------------------------------------------------------------------
# Still read legacy env keys so existing .env / deploy docs keep working.
_EMAIL_HOST = env("EMAIL_HOST", default="")
_EMAIL_PORT = env.int("EMAIL_PORT", default=587)
_EMAIL_HOST_USER = env("EMAIL_HOST_USER", default="")
_EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", default="")
_EMAIL_USE_TLS = env.bool("EMAIL_USE_TLS", default=True)
_EMAIL_USE_SSL = env.bool("EMAIL_USE_SSL", default=False)
_EMAIL_BACKEND = env(
    "EMAIL_BACKEND",
    default="django.core.mail.backends.console.EmailBackend",
)

MAILERS = {
    "default": {
        "BACKEND": _EMAIL_BACKEND,
        "OPTIONS": {
            "host": _EMAIL_HOST,
            "port": _EMAIL_PORT,
            "username": _EMAIL_HOST_USER,
            "password": _EMAIL_HOST_PASSWORD,
            "use_tls": _EMAIL_USE_TLS,
            "use_ssl": _EMAIL_USE_SSL,
        },
    },
}

DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default="noreply@survera.local")

# Dedicated inbox for local/manual email tests (notifications, invites, codes).
# When EMAIL_REDIRECT_TO_TEST is True, all outbound mail is delivered here instead.
EMAIL_FOR_TEST = env("EMAIL_FOR_TEST", default="surveracorp.test@gmail.com")
EMAIL_REDIRECT_TO_TEST = env.bool("EMAIL_REDIRECT_TO_TEST", default=False)

# Public site URL for absolute links in emails (no trailing slash)
SITE_URL = env("SITE_URL", default="http://localhost:8000")

# Keep names used by local.py / production.py conditionals
EMAIL_HOST = _EMAIL_HOST
EMAIL_HOST_USER = _EMAIL_HOST_USER
EMAIL_HOST_PASSWORD = _EMAIL_HOST_PASSWORD
EMAIL_PORT = _EMAIL_PORT
EMAIL_USE_TLS = _EMAIL_USE_TLS
EMAIL_USE_SSL = _EMAIL_USE_SSL
EMAIL_BACKEND = _EMAIL_BACKEND

# -----------------------------------------------------------------------------
# Cloudflare Turnstile (bot protection on register / verification resend)
# -----------------------------------------------------------------------------
# Set TURNSTILE_ENABLED=True and both keys in production.
# Cloudflare always-pass test keys (optional local testing with enforcement on):
#   site: 1x00000000000000000000AA
#   secret: 1x0000000000000000000000000000000AA
TURNSTILE_ENABLED = env.bool("TURNSTILE_ENABLED", default=False)
TURNSTILE_SITE_KEY = env("TURNSTILE_SITE_KEY", default="")
TURNSTILE_SECRET_KEY = env("TURNSTILE_SECRET_KEY", default="")
TURNSTILE_TIMEOUT = env.float("TURNSTILE_TIMEOUT", default=5.0)

# -----------------------------------------------------------------------------
# Crispy Forms
# -----------------------------------------------------------------------------
CRISPY_ALLOWED_TEMPLATE_PACKS = "bootstrap5"
CRISPY_TEMPLATE_PACK = "bootstrap5"

# -----------------------------------------------------------------------------
# SURVERA product limits (legacy; personal surveys removed)
# -----------------------------------------------------------------------------
SURVERA_PERSON_MAX_FREE_SURVEYS = env.int("SURVERA_PERSON_MAX_FREE_SURVEYS", default=5)
SURVERA_PERSON_MAX_POINTS_REWARD = env.int("SURVERA_PERSON_MAX_POINTS_REWARD", default=0)
SURVERA_PERSON_MAX_QUESTIONS = env.int("SURVERA_PERSON_MAX_QUESTIONS", default=20)
SURVERA_PERSON_MAX_RESPONSE_TARGET = env.int("SURVERA_PERSON_MAX_RESPONSE_TARGET", default=100)

# Progression (XP) — separate from redeemable points
SURVERA_XP_SURVEY_COMPLETION = env.int("SURVERA_XP_SURVEY_COMPLETION", default=50)
SURVERA_XP_PROFILE_COMPLETE = env.int("SURVERA_XP_PROFILE_COMPLETE", default=30)
SURVERA_XP_SURVEY_CREATED = env.int("SURVERA_XP_SURVEY_CREATED", default=25)
SURVERA_XP_DAILY_LOGIN = env.int("SURVERA_XP_DAILY_LOGIN", default=10)

# -----------------------------------------------------------------------------
# Security (base – tightened in production)
# -----------------------------------------------------------------------------
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = True
X_FRAME_OPTIONS = "DENY"
SECURE_CONTENT_TYPE_NOSNIFF = True

# -----------------------------------------------------------------------------
# Logging
# -----------------------------------------------------------------------------
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "[{asctime}] {levelname} {name} {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "INFO",
    },
    "loggers": {
        "django": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
        "apps": {
            "handlers": ["console"],
            "level": "DEBUG",
            "propagate": False,
        },
    },
}
